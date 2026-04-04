"""
MSI Automotive - Element Tools for LangGraph Agent.

These tools allow the conversational agent to identify, list, and calculate
tariffs based on the new Element catalog system (Element + TierElementInclusion).

This replaces the old keyword-based ElementDocumentation system with a more
structured approach that:
- Uses Element catalog with standardized codes
- Supports TierElementInclusion for precise tier-element relationships
- Provides confidence scores for element matching
- Returns element-specific images and warnings
"""

import asyncio
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

import structlog
from langchain_core.tools import tool

from agent.services.element_service import get_element_service
from agent.services.tarifa_service import get_tarifa_service
from agent.services.variant_interpretation_service import (
    VariantInterpretationResult,
    interpret_variant_allocations,
    validate_and_apply_allocations,
)
from agent.state.conversation_state import PendingVariantGroup
from agent.state.helpers import get_current_state, normalize_pending_variants
from agent.utils.validation import validate_category_slug
from database.connection import get_async_session
from database.models import VehicleCategory
from shared.config import get_settings

logger = structlog.get_logger(__name__)


async def get_or_fetch_category_id(category_slug: str) -> str | None:
    """
    Get category ID with Redis caching (5 min TTL).

    Reduces DB queries by caching category_id lookups with automatic expiration.
    Falls back to DB query if Redis is unavailable.

    Args:
        category_slug: The category slug (e.g., "motos-part")

    Returns:
        Category UUID as string, or None if not found
    """
    from shared.redis_client import get_redis_client

    cache_key = f"category:slug:{category_slug}"
    CACHE_TTL = 300  # 5 minutes

    # Try Redis cache first
    try:
        redis = get_redis_client()
        cached = await redis.get(cache_key)
        if cached:
            logger.debug(
                "Category ID cache hit", extra={"category_slug": category_slug}
            )
            # Handle both str (decode_responses=True) and bytes (decode_responses=False)
            if isinstance(cached, bytes):
                return cached.decode("utf-8")
            else:
                return cached  # Already a str
    except Exception as e:
        logger.warning(
            "Redis cache read failed, falling back to DB",
            extra={"error": str(e), "cache_key": cache_key},
            exc_info=True,
        )

    # Fetch from database
    category_id = await _get_category_id_by_slug(category_slug)

    # Cache result in Redis with TTL
    if category_id:
        try:
            redis = get_redis_client()
            await redis.setex(cache_key, CACHE_TTL, category_id)
            logger.debug(
                f"Category ID cached with TTL={CACHE_TTL}s",
                extra={"category_slug": category_slug},
            )
        except Exception as e:
            logger.warning(
                "Redis cache write failed",
                extra={"error": str(e), "cache_key": cache_key},
                exc_info=True,
            )

    return category_id


async def _get_category_id_by_slug(category_slug: str) -> str | None:
    """
    Get category ID from slug with comprehensive error handling.

    Args:
        category_slug: Category slug (must be validated before calling)

    Returns:
        Category UUID as string, or None if not found or error occurs
    """
    from sqlalchemy import select
    from sqlalchemy.exc import SQLAlchemyError

    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(VehicleCategory)
                .where(VehicleCategory.slug == category_slug)
                .where(VehicleCategory.is_active == True)
            )
            category = result.scalar_one_or_none()
            return str(category.id) if category else None

    except SQLAlchemyError as e:
        logger.error(
            "Database error fetching category by slug",
            exc_info=True,
            extra={
                "category_slug": category_slug,
                "error_type": type(e).__name__,
                "error": str(e),
            },
        )
        return None
    except Exception as e:
        logger.error(
            "Unexpected error fetching category by slug",
            exc_info=True,
            extra={"category_slug": category_slug, "error_type": type(e).__name__},
        )
        return None


def normalize_element_code(code: str, valid_codes: set[str]) -> tuple[str | None, bool]:
    """
    Normalize an element code to find a valid match.

    Handles common LLM errors like:
    - Case variations (asideros → ASIDEROS)
    - Singular/plural (ASIDERO → ASIDEROS)
    - Extra/missing 'S' at the end

    Args:
        code: The element code to normalize
        valid_codes: Set of valid element codes for the category

    Returns:
        Tuple of (matched_code, was_corrected):
        - matched_code: The valid code found, or None if no match
        - was_corrected: True if the code was modified to find a match
    """
    if not code or not valid_codes:
        return None, False

    normalized = code.upper().strip()

    # 1. Exact match (case-insensitive)
    if normalized in valid_codes:
        return normalized, normalized != code

    # 2. Try adding 'S' (singular → plural): ASIDERO → ASIDEROS
    with_s = normalized + "S"
    if with_s in valid_codes:
        logger.info(
            f"[normalize_element_code] Auto-corrected '{code}' → '{with_s}' (added S)",
            extra={"original": code, "corrected": with_s},
        )
        return with_s, True

    # 3. Try removing 'S' (plural → singular): ESCAPESS → ESCAPES edge case
    if normalized.endswith("S") and len(normalized) > 1:
        without_s = normalized[:-1]
        if without_s in valid_codes:
            logger.info(
                f"[normalize_element_code] Auto-corrected '{code}' → '{without_s}' (removed S)",
                extra={"original": code, "corrected": without_s},
            )
            return without_s, True

    # 4. Try adding 'ES' for words ending in consonant: MOTOR → MOTORES
    if not normalized.endswith(("A", "E", "I", "O", "U", "S")):
        with_es = normalized + "ES"
        if with_es in valid_codes:
            logger.info(
                f"[normalize_element_code] Auto-corrected '{code}' → '{with_es}' (added ES)",
                extra={"original": code, "corrected": with_es},
            )
            return with_es, True

    # 5. Fuzzy match (last resort — combined SequenceMatcher + token-Jaccard)
    fuzzy_match = _fuzzy_best_match(normalized, valid_codes)
    if fuzzy_match:
        logger.warning(
            f"[normalize_element_code] Fuzzy-corrected '{code}' → '{fuzzy_match}'",
            extra={"original": code, "corrected": fuzzy_match},
        )
        return fuzzy_match, True

    return None, False


def _fuzzy_best_match(
    code: str,
    valid_codes: set[str],
    threshold: float = 0.50,
) -> str | None:
    """
    Combined SequenceMatcher + token-Jaccard fuzzy match.

    Scoring: 0.6 * sequence_ratio + 0.4 * token_jaccard.
    Returns the best match above *threshold*, or None if no match
    or if the top two candidates are tied (ambiguous).

    Args:
        code: Uppercased element code to match.
        valid_codes: Set of valid element codes.
        threshold: Minimum combined score to accept a match.

    Returns:
        Best matching code or None.
    """
    if not code or not valid_codes:
        return None

    code_tokens = set(code.split("_"))
    best_score: float = 0.0
    second_score: float = 0.0
    best_match: str | None = None

    for vc in valid_codes:
        seq = SequenceMatcher(None, code, vc).ratio()
        vc_tokens = set(vc.split("_"))
        union = code_tokens | vc_tokens
        jaccard = len(code_tokens & vc_tokens) / len(union) if union else 0.0
        combined = 0.6 * seq + 0.4 * jaccard

        if combined > best_score:
            second_score = best_score
            best_score = combined
            best_match = vc
        elif combined > second_score:
            second_score = combined

    # Reject if below threshold
    if best_score < threshold:
        return None

    # Reject ties (ambiguous — top two scores within 1e-9)
    if abs(best_score - second_score) < 1e-9:
        return None

    return best_match


def normalize_element_codes(
    codes: list[str], valid_codes: set[str]
) -> tuple[list[str], list[str], list[str]]:
    """
    Normalize a list of element codes.

    Args:
        codes: List of element codes to normalize
        valid_codes: Set of valid element codes for the category

    Returns:
        Tuple of (normalized_codes, corrected_codes, invalid_codes):
        - normalized_codes: List of valid codes (corrected where possible)
        - corrected_codes: List of codes that were auto-corrected (original → corrected)
        - invalid_codes: List of codes that couldn't be matched
    """
    normalized = []
    corrected = []
    invalid = []

    for code in codes:
        matched, was_corrected = normalize_element_code(code, valid_codes)
        if matched:
            normalized.append(matched)
            if was_corrected:
                corrected.append(f"{code} → {matched}")
        else:
            invalid.append(code)

    return normalized, corrected, invalid


async def _validate_element_codes(
    categoria_vehiculo: str,
    codigos_elementos: list[str],
    confianzas: dict[str, float] | None = None,
) -> dict:
    """
    Internal validation of element codes.

    This is the core validation logic used by both validar_elementos and
    calcular_tarifa_con_elementos. It is NOT decorated with @tool so it
    can be called directly from other functions.

    Args:
        categoria_vehiculo: Category slug (e.g., "motos-part")
        codigos_elementos: List of element codes to validate
        confianzas: Optional dict with confidence scores

    Returns:
        dict with:
        - "valid": bool - True if all codes are valid
        - "status": "OK" | "CONFIRMAR" | "ERROR"
        - "message": str - Formatted message for LLM
        - "valid_elements": list[dict] - Valid elements found
        - "invalid_codes": list[str] - Codes not found
        - "low_confidence": list[dict] - Elements with low confidence
    """
    from agent.services.tarifa_service import get_tarifa_service

    tarifa_service = get_tarifa_service()
    element_service = get_element_service()

    # Normalize category slug (LLM may send "MOTOS-PART" instead of "motos-part")
    categoria_vehiculo = categoria_vehiculo.lower().strip()

    # Get category from active categories
    categories = await tarifa_service.get_active_categories()
    category = next((c for c in categories if c["slug"] == categoria_vehiculo), None)

    if not category:
        return {
            "valid": False,
            "status": "ERROR",
            "message": f"ERROR: Categoría '{categoria_vehiculo}' no encontrada.",
            "valid_elements": [],
            "invalid_codes": [],
            "low_confidence": [],
        }

    # Get valid elements for category
    elements = await element_service.get_elements_by_category(
        category["id"], is_active=True
    )
    element_by_code = {e["code"].upper(): e for e in elements}
    element_by_id = {e["id"]: e for e in elements}

    # Build map of parent elements → their children
    # This allows us to reject parent elements that have variants
    parent_to_children: dict[str, list[dict]] = {}
    for elem in elements:
        parent_id = elem.get("parent_element_id")
        if parent_id and parent_id in element_by_id:
            parent_elem = element_by_id[parent_id]
            parent_code = parent_elem["code"].upper()
            if parent_code not in parent_to_children:
                parent_to_children[parent_code] = []
            parent_to_children[parent_code].append(elem)

    # Validate codes
    valid_elements = []
    invalid_codes = []
    low_confidence = []
    parent_elements_rejected = []  # Elements that have children (require variant selection)

    # Confidence threshold (60%)
    CONFIDENCE_THRESHOLD = 0.6

    for code in codigos_elementos:
        code_upper = code.upper()
        if code_upper in element_by_code:
            elem = element_by_code[code_upper]

            # REJECT parent elements that have children - user must select a variant
            if code_upper in parent_to_children:
                children = parent_to_children[code_upper]
                parent_elements_rejected.append(
                    {
                        "code": code_upper,
                        "name": elem["name"],
                        "children": [
                            {"code": c["code"], "name": c["name"]} for c in children
                        ],
                        "question_hint": elem.get("question_hint")
                        or f"¿Qué tipo de {elem['name'].lower()}?",
                    }
                )
                continue  # DO NOT add to valid_elements

            valid_elements.append(elem)

            # Check confidence if provided
            if confianzas:
                conf = confianzas.get(code_upper) or confianzas.get(code)
                if conf is not None and conf < CONFIDENCE_THRESHOLD:
                    low_confidence.append(
                        {"code": code_upper, "name": elem["name"], "confidence": conf}
                    )
        else:
            invalid_codes.append(code)

    # Generate response
    lines = []

    if invalid_codes:
        # Log invalid codes for debugging
        logger.warning(
            f"[_validate_element_codes] Invalid codes detected",
            extra={
                "invalid_codes": invalid_codes,
                "category": categoria_vehiculo,
                "valid_codes_available": list(element_by_code.keys())[:20],
            },
            exc_info=False,
        )

        lines.append(f"ERROR: Códigos no válidos: {', '.join(invalid_codes)}")
        lines.append("")
        lines.append("Códigos disponibles:")
        for code, elem in sorted(element_by_code.items())[:10]:
            lines.append(f"  - {code}: {elem['name']}")
        if len(element_by_code) > 10:
            lines.append(f"  ... y {len(element_by_code) - 10} más")

        return {
            "valid": False,
            "status": "ERROR",
            "message": "\n".join(lines),
            "valid_elements": valid_elements,
            "invalid_codes": invalid_codes,
            "low_confidence": low_confidence,
        }

    # Check for parent elements that have children (require variant selection)
    if parent_elements_rejected:
        lines = ["=== ERROR: ELEMENTOS SIN VARIANTE ESPECIFICADA ===", ""]
        lines.append("Los siguientes elementos requieren que especifiques la variante:")
        lines.append("")

        for parent in parent_elements_rejected:
            lines.append(f"❌ '{parent['name']}' tiene variantes disponibles:")
            for child in parent["children"]:
                lines.append(f"   • {child['name']} ({child['code']})")
            lines.append("")
            lines.append(f"   Pregunta sugerida: {parent['question_hint']}")
            lines.append("")

        lines.append("⚠️ ACCIÓN OBLIGATORIA:")
        lines.append("1. Pregunta al usuario qué variante específica necesita")
        lines.append("2. Usa el código de la VARIANTE (no del elemento base)")
        lines.append("3. Vuelve a llamar validar_elementos con los códigos correctos")
        lines.append("")
        lines.append(
            "IMPORTANTE: Los elementos padre NO son homologables directamente."
        )
        lines.append("Solo se pueden homologar las variantes específicas.")

        return {
            "valid": False,
            "status": "ERROR_VARIANTE_REQUERIDA",
            "message": "\n".join(lines),
            "valid_elements": valid_elements,
            "invalid_codes": invalid_codes,
            "parent_elements_rejected": parent_elements_rejected,
            "low_confidence": low_confidence,
        }

    # Internal format - NOT to show to user
    lines.append("=== VALIDACIÓN INTERNA ===")
    lines.append("")

    # List elements by name only (codes are internal)
    element_names = [elem["name"] for elem in valid_elements]
    lines.append(f"Elementos válidos: {', '.join(element_names)}")

    if low_confidence:
        lines.append("")
        lines.append("=== ACCIÓN REQUERIDA ===")
        lines.append("Confirma con el usuario de forma NATURAL sobre:")
        for lc in low_confidence:
            lines.append(f"  - {lc['name']}")
        lines.append("")
        lines.append("Ejemplo de pregunta cercana:")
        lines.append(
            f'  "Sobre {low_confidence[0]["name"].lower()}, ¿podrías confirmarme exactamente qué modificación has hecho?"'
        )
        lines.append("")
        lines.append("RECUERDA:")
        lines.append("- NO menciones 'confianza' ni porcentajes")
        lines.append("- NO uses códigos internos")
        lines.append("- Pregunta de forma natural y cercana")
        lines.append("")
        lines.append("Estado: CONFIRMAR")

        return {
            "valid": True,
            "status": "CONFIRMAR",
            "message": "\n".join(lines),
            "valid_elements": valid_elements,
            "invalid_codes": invalid_codes,
            "low_confidence": low_confidence,
        }

    lines.append("")
    lines.append("Estado: OK - Puedes calcular tarifa")

    return {
        "valid": True,
        "status": "OK",
        "message": "\n".join(lines),
        "valid_elements": valid_elements,
        "invalid_codes": invalid_codes,
        "low_confidence": low_confidence,
    }


@tool
async def listar_elementos(categoria_vehiculo: str) -> dict[str, Any]:
    """
    Lista todos los elementos homologables disponibles para una categoría de vehículo.

    Usa esta herramienta cuando el usuario pregunte qué elementos puede homologar
    o necesite ver el catálogo de elementos disponibles.

    IMPORTANTE: Usa el slug de categoría correcto:
    - "motos-part" para motocicletas de particulares
    - "aseicars-prof" para autocaravanas de profesionales

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")

    Returns:
        Lista formateada de elementos con códigos, nombres y keywords.
    """
    # Normalize category slug (LLM may send uppercase)
    categoria_vehiculo = categoria_vehiculo.lower().strip()

    # Validate category slug for security
    try:
        validate_category_slug(categoria_vehiculo)
    except ValueError as e:
        logger.error(f"Invalid category slug rejected in listar_elementos: {e}")
        return {"error": str(e)}

    element_service = get_element_service()

    # Get category ID from slug (cached)
    category_id = await get_or_fetch_category_id(categoria_vehiculo)
    if not category_id:
        tarifa_service = get_tarifa_service()
        categories = await tarifa_service.get_active_categories()
        available = ", ".join(c["slug"] for c in categories)
        return {
            "error": f"Categoría '{categoria_vehiculo}' no encontrada. Categorías disponibles: {available}"
        }

    # Get elements for category
    elements = await element_service.get_elements_by_category(
        category_id, is_active=True
    )

    if not elements:
        return {
            "error": f"No hay elementos configurados para la categoría '{categoria_vehiculo}'."
        }

    lines = [
        f"ELEMENTOS HOMOLOGABLES PARA {categoria_vehiculo.upper()}:",
        "",
    ]

    for elem in elements:
        lines.append(f"- {elem['name']}")

    lines.append("")
    lines.append(f"Total: {len(elements)} elementos disponibles.")

    return {"elementos": "\n".join(lines)}


# ---------------------------------------------------------------------------
# Positional normalization helper for seleccionar_variante_por_respuesta
# ---------------------------------------------------------------------------

_POSITIONAL_LETTER_RE = re.compile(
    r"^\s*(?:(?:la\s+|el\s+)?opci[oó]n\s+|la\s+|el\s+)?([a-eA-E])[.):\s]*$",
    re.IGNORECASE,
)

# Matches a single positional letter "a"-"e" (bare, no other content)
_BARE_LETTER_RE = re.compile(r"^[a-eA-E]$")

# Domain vocabulary for bare-letter confidence gate (REQ-3).
# If the user's fragment contains at least one of these tokens, bare-letter
# positional mapping is trusted even when avg_confidence < 0.3.
# Each tuple is (normalized_term, original) — normalized via simple lower().
_GALIBO_VOCABULARY: tuple[str, ...] = (
    "galibo",
    "gálibo",
    "ancho",
    "anchura",
    "sobresale",
    "sobresaliente",
    "alero",
)
_REGULADOR_VOCABULARY: tuple[str, ...] = (
    "oculto",
    "visible",
    "armario",
    "maletero",
    "cocina",
    "regulador",
    "interior",
)

# Union of all domain vocabulary tokens used by the confidence gate.
_ALL_DOMAIN_VOCABULARY: frozenset[str] = frozenset(
    _GALIBO_VOCABULARY + _REGULADOR_VOCABULARY
)

# ─────────────────────────────────────────────────────────────────────────────
# Phase 4: Early ambiguity exit — Trust the LLM (ADR-006)
# ─────────────────────────────────────────────────────────────────────────────
# When keyword_score < AMBIGUITY_THRESHOLD AND the user input contains no
# vocabulary specific to any variant, skip Tier-1 LLM interpretation and
# return needs_clarification=True immediately so the main LLM can ask the
# user a clear clarifying question.
AMBIGUITY_THRESHOLD = 0.3


def _has_domain_vocabulary_from_variants(
    user_input: str, variant_options: list[dict]
) -> bool:
    """
    Return True if *user_input* contains vocabulary specific to any of the
    given variant options (keywords or name words longer than 3 chars).

    Unlike _has_domain_vocabulary(), this function derives the domain words
    dynamically from the variant data rather than a static vocabulary list.
    Used by the early-ambiguity-exit gate (Phase 4) to decide whether to skip
    Tier-1 LLM interpretation or return needs_clarification immediately.

    Args:
        user_input:       Raw user message text.
        variant_options:  List of variant dicts (each with "keywords", "name").

    Returns:
        True when at least one domain word (>3 chars) from any variant appears
        in the normalised input.
    """
    if not variant_options:
        return False

    def _strip_accents(text: str) -> str:
        nfkd = unicodedata.normalize("NFD", text.lower())
        return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")

    domain_words: set[str] = set()
    for v in variant_options:
        for kw in v.get("keywords", []):
            for word in _strip_accents(kw).split():
                if len(word) > 3:
                    domain_words.add(word)
        for word in _strip_accents(v.get("name", "")).split():
            if len(word) > 3:
                domain_words.add(word)

    normalized_input = _strip_accents(user_input)
    return any(w in normalized_input for w in domain_words)


def _has_domain_vocabulary(fragment: str) -> bool:
    """
    Return True if *fragment* contains at least one domain vocabulary token.

    The check is accent-insensitive and case-insensitive.  Used by the
    bare-letter confidence gate: when a user's message contains a domain
    keyword (e.g. "gálibo", "oculto") the positional bare-letter mapping is
    trusted even if avg_confidence < 0.3.

    Args:
        fragment: The raw user message fragment.

    Returns:
        True when at least one domain token appears in the normalised fragment.
    """
    import unicodedata as _unicodedata

    def _strip_accents(text: str) -> str:
        nfkd = _unicodedata.normalize("NFKD", text)
        return "".join(c for c in nfkd if not _unicodedata.combining(c)).lower()

    normalized = _strip_accents(fragment)
    return any(_strip_accents(token) in normalized for token in _ALL_DOMAIN_VOCABULARY)


def _normalize_to_canonical_letter(response: str) -> str | None:
    """
    Extract canonical positional letter from decorated user responses.

    Matches: "b", "B", "opción b", "opción B", "la b", "el b",
             "b.", "b)", "la opción b", "B." etc.
    Does NOT match: "el visible", "el más barato", "2", "modelo b", etc.

    Returns: lowercase letter "a"-"e", or None if not a positional response.
    """
    m = _POSITIONAL_LETTER_RE.match(response.strip())
    return m.group(1).lower() if m else None


# ---------------------------------------------------------------------------
# Fragment extraction helper for combined user responses
# ---------------------------------------------------------------------------

# Clause-splitting pattern: splits on "y el", "y la", "y los", "y las",
# "y", comma, semicolon, slash — keeping short determiners together with
# the noun so context is preserved.
_CLAUSE_SPLIT_RE = re.compile(
    r"\s*(?:y\s+(?:el|la|los|las)\s+|y\s+|,\s*|;\s*|/\s*)",
    re.IGNORECASE,
)

# Stop-words to drop when computing an element anchor from a code/name
_ANCHOR_STOP_WORDS = frozenset(
    {"de", "del", "el", "la", "los", "las", "un", "una", "y", "con", "para"}
)

# Minimum anchor score for a clause to be considered "matching"
_FRAGMENT_MIN_SCORE = 0.25


def _build_element_anchors(
    codigo_elemento_base: str,
    base_element: dict[str, Any] | None,
    current_pending: "PendingVariantGroup | None",
    variants: list[dict[str, Any]],
) -> list[str]:
    """
    Build a list of anchor words derived from the current element context.

    Anchors are used to score clauses from a combined user response against
    the active element being resolved.

    Returns a list of normalized anchor strings (multi-word possible).
    """
    from agent.utils.text_utils import normalize_text

    anchors: list[str] = []

    # 1. From element code: "PLACA_SOLAR" → "placa solar"
    code_words = [
        w
        for w in normalize_text(codigo_elemento_base.replace("_", " ")).split()
        if w not in _ANCHOR_STOP_WORDS and len(w) > 2
    ]
    if code_words:
        anchors.append(" ".join(code_words))
        # Also add individual meaningful words from code
        for w in code_words:
            if len(w) > 3:
                anchors.append(w)

    # 2. From element display name (if available)
    if base_element:
        name_words = [
            w
            for w in normalize_text(base_element.get("name", "")).split()
            if w not in _ANCHOR_STOP_WORDS and len(w) > 3
        ]
        if name_words:
            anchors.append(" ".join(name_words))
            for w in name_words:
                anchors.append(w)

    # 3. From the pending question text (most specific signal)
    if current_pending:
        pregunta = current_pending.get("pregunta", "")
        if pregunta:
            q_words = [
                w
                for w in normalize_text(pregunta).split()
                if w not in _ANCHOR_STOP_WORDS and len(w) > 3
            ]
            for w in q_words[:5]:  # First 5 meaningful words
                anchors.append(w)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_anchors: list[str] = []
    for a in anchors:
        if a not in seen:
            seen.add(a)
            unique_anchors.append(a)

    return unique_anchors


def _score_clause_for_element(
    clause: str,
    anchors: list[str],
) -> float:
    """
    Score how relevant a normalized clause is to the given element anchors.

    Returns a float 0.0-1.0.  The scoring is purely deterministic (no LLM).
    """
    from agent.utils.text_utils import normalize_text

    clause_norm = normalize_text(clause)
    if not clause_norm:
        return 0.0

    score = 0.0
    for anchor in anchors:
        if anchor in clause_norm:
            # Longer anchors are more specific → reward proportionally
            score += 0.3 + 0.1 * min(len(anchor.split()), 3)
        else:
            # Partial word overlap
            anchor_words = set(anchor.split())
            clause_words = set(clause_norm.split())
            overlap = anchor_words & clause_words
            if overlap:
                score += 0.15 * (len(overlap) / len(anchor_words))

    return min(score, 1.0)


_MULTI_LETTER_RE = re.compile(
    r"^([a-z])(?:\s*(?:y|and|,|;)\s*([a-z]))+$",
    re.IGNORECASE,
)
_MULTI_LETTER_TOKEN_RE = re.compile(r"[a-z]", re.IGNORECASE)


def _extract_positional_letters(respuesta: str) -> list[str] | None:
    """
    If *respuesta* (stripped) is exclusively positional letters separated by
    "y", "and", commas, semicolons or spaces — return them as lowercase list.

    Examples:
        "B y A"  → ["b", "a"]
        "a, b"   → ["a", "b"]
        "b y a"  → ["b", "a"]
        "A"      → None  (single letter — handled by existing positional path)
        "regulador oculto y toldo normal" → None  (semantic words present)

    Returns None when the response is NOT a pure multi-letter pattern (i.e.
    it contains semantic words or is a single-letter response).
    """
    stripped = respuesta.strip()
    # Must contain at least one separator to be a multi-letter pattern
    if not re.search(r"[,;]|\s+(?:y|and)\s+|\s", stripped):
        return None

    # Remove separators and check that all remaining tokens are single letters
    # Replace separators with spaces, then split
    candidate = re.sub(r"\s*(?:y|and)\s*|[,;]\s*|\s+", " ", stripped.lower()).strip()
    tokens = candidate.split()

    # Every token must be a single letter a-e (the valid positional range)
    if not tokens:
        return None
    if not all(len(t) == 1 and t.isalpha() for t in tokens):
        return None
    # Require at least 2 letters (single letter uses existing path)
    if len(tokens) < 2:
        return None

    return tokens


def _extract_element_fragment(
    respuesta: str,
    codigo_elemento_base: str,
    base_element: dict[str, Any] | None,
    current_pending: "PendingVariantGroup | None",
    variants: list[dict[str, Any]],
    current_pending_idx: int = -1,
    total_pending_count: int = 0,
) -> str:
    """
    Extract the clause from a combined user response that refers to the current element.

    For example, given response "placa solar opcion b y el toldo A" while resolving
    PLACA_SOLAR, returns "placa solar opcion b".

    The function is PURE (no side effects, no LLM calls).

    Algorithm:
    0. [NEW] Detect pure positional multi-letter responses (e.g. "B y A").
       When the entire response is N letters separated by conjunctions/commas,
       and N matches the number of pending variant groups, assign the i-th letter
       to the i-th element (current_pending_idx). This runs BEFORE semantic
       extraction so the existing positional_match path handles the single letter.
    1. Split response into clauses on conjunctions/punctuation.
    2. If only one clause (no split occurred), return original — nothing to do.
    3. Score each clause against anchors built from the element code, name, and
       pending question text.
    4. Return the highest-scoring clause if it exceeds _FRAGMENT_MIN_SCORE.
    5. If no clause scores above threshold, return the full original response
       (safe fallback — preserves existing behavior).

    Args:
        respuesta: Raw user response text.
        codigo_elemento_base: Base element code (e.g., "PLACA_SOLAR").
        base_element: Dict from element service for the base element (may be None).
        current_pending: Active PendingVariantGroup for this element (may be None).
        variants: List of variant dicts for this element.
        current_pending_idx: Index of this element within the pending list (-1 if unknown).
        total_pending_count: Total number of pending variant groups (0 if unknown).

    Returns:
        The most relevant fragment (stripped), or the original response as fallback.
    """
    respuesta_stripped = respuesta.strip()

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 0 (NEW): Pure positional multi-letter shortcut.
    # Detects responses like "B y A", "a, b", "b y a" where the user answers
    # multiple variant questions at once using positional letters.
    # When detected and we know our index, return just the i-th letter so the
    # existing positional_match path resolves it correctly.
    # ─────────────────────────────────────────────────────────────────────────
    if current_pending_idx >= 0 and total_pending_count >= 2:
        letters = _extract_positional_letters(respuesta_stripped)
        if letters is not None and len(letters) == total_pending_count:
            # Each pending element gets the letter at its ordinal position
            if current_pending_idx < len(letters):
                extracted_letter = letters[current_pending_idx]
                logger.debug(
                    "extract_element_fragment_positional_multi_letter",
                    respuesta=respuesta_stripped,
                    codigo_base=codigo_elemento_base,
                    pending_idx=current_pending_idx,
                    extracted=extracted_letter,
                )
                return extracted_letter

    # Split into clauses
    clauses = _CLAUSE_SPLIT_RE.split(respuesta_stripped)
    clauses = [c.strip() for c in clauses if c.strip()]

    # If nothing to split, return as-is (no combined response)
    if len(clauses) <= 1:
        return respuesta_stripped

    # Build anchors for this element
    anchors = _build_element_anchors(
        codigo_elemento_base, base_element, current_pending, variants
    )

    if not anchors:
        # No anchor context — cannot discriminate, return original
        return respuesta_stripped

    # Score each clause
    best_clause = respuesta_stripped
    best_score = 0.0

    for clause in clauses:
        score = _score_clause_for_element(clause, anchors)
        if score > best_score:
            best_score = score
            best_clause = clause

    if best_score < _FRAGMENT_MIN_SCORE:
        # No clause confidently matched — return full response as safe fallback
        return respuesta_stripped

    return best_clause


@tool
async def seleccionar_variante_por_respuesta(
    categoria_vehiculo: str,
    codigo_elemento_base: str,
    respuesta_usuario: str,
) -> dict[str, Any]:
    """
    Mapea la respuesta del usuario a un código de variante específico.

    USA ESTA TOOL después de preguntar al usuario sobre la variante que necesita.
    La herramienta analiza la respuesta y determina qué variante corresponde.

    Soporta:
    - Selección única: "delantera" → SUSPENSION_DEL
    - Multi-selección: "ambos", "todos" → TODAS las variantes
    - Distribución multi-unidad: "2 delanteras y 1 trasera" → asignación por cantidad

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        codigo_elemento_base: Código del elemento base (ej: "BOLA_REMOLQUE")
        respuesta_usuario: Texto de respuesta del usuario (ej: "sí, aumenta MMR", "ambos", "delantera", "2 delanteras y 1 trasera")

    Returns:
        JSON con UNO de estos formatos:

        Selección única:
        {"selected_variant": "BOLA_CON_MMR", "confidence": 0.95, "name": "..."}

        Multi-selección (usuario quiere todas):
        {"selected_variants": ["INTERMITENTES_DEL", "INTERMITENTES_TRAS"], "mode": "multi_select", "names": [...]}

        Distribución multi-unidad:
        {"selected_variant": "SUSPENSION_DEL", "confidence": 0.9, "applied_allocations": [...], "resolution_status": "resolved", "pending_count": 0}

    Si confidence < 0.7, pregunta al usuario de forma más específica.
    """
    # Normalize category slug (LLM may send uppercase)
    categoria_vehiculo = categoria_vehiculo.lower().strip()

    # Validate category slug for security
    try:
        validate_category_slug(categoria_vehiculo)
    except ValueError as e:
        logger.error(
            "invalid_category_slug_rejected",
            tool="seleccionar_variante_por_respuesta",
            error=str(e),
        )
        return {"error": str(e)}

    element_service = get_element_service()

    # Get category ID from slug (cached)
    category_id = await get_or_fetch_category_id(categoria_vehiculo)
    if not category_id:
        return {"error": f"Categoría '{categoria_vehiculo}' no encontrada"}

    # Normalize element code
    codigo_normalizado = codigo_elemento_base.upper().strip()

    # Get variants for this element
    variants = await element_service.get_element_variants(
        element_code=codigo_normalizado,
        category_id=category_id,
    )

    # If no variants found, try fuzzy matching by name
    # LLM sometimes sends "Bola de remolque" instead of "BOLA_REMOLQUE"
    if not variants:
        # Get all base elements and try to match by name
        all_elements = await element_service.get_elements_by_category(
            category_id, is_active=True
        )

        from agent.utils.text_utils import normalize_text

        search_term = normalize_text(codigo_elemento_base)

        # Find best match by name similarity
        best_match_elem = None
        for elem in all_elements:
            if elem.get("parent_element_id"):  # Skip variants, only check base elements
                continue
            elem_name_normalized = normalize_text(elem["name"])
            elem_code_normalized = normalize_text(elem["code"])

            # Check if search term is contained in name or code
            if (
                search_term in elem_name_normalized
                or elem_name_normalized in search_term
            ):
                best_match_elem = elem
                break
            if search_term in elem_code_normalized:
                best_match_elem = elem
                break

        if best_match_elem:
            logger.info(
                "seleccionar_variante_fuzzy_match",
                original=codigo_elemento_base,
                matched=best_match_elem["code"],
            )
            codigo_normalizado = best_match_elem["code"]
            # Try getting variants again with corrected code
            variants = await element_service.get_element_variants(
                element_code=codigo_normalizado,
                category_id=category_id,
            )

    if not variants:
        # Still no variants - return helpful error
        all_elements = await element_service.get_elements_by_category(
            category_id, is_active=True
        )
        base_elements = [e for e in all_elements if not e.get("parent_element_id")]
        available_codes = ", ".join(e["code"] for e in base_elements[:10])
        return {
            "error": f"No se encontraron variantes para '{codigo_elemento_base}'",
            "hint": f"Elementos base disponibles: {available_codes}",
            "instrucciones": "Verifica que el código sea correcto. Usa identificar_y_resolver_elementos para obtener los códigos.",
        }

    # Normalize user response (remove accents for matching)
    from agent.utils.text_utils import normalize_text

    respuesta_lower = respuesta_usuario.lower().strip()
    respuesta_normalized = normalize_text(respuesta_usuario)

    # === DATA-DRIVEN MULTI-SELECT CHECK ===
    # Check if the base element defines multi_select_keywords (e.g., "ambos", "todos")
    # If the user's response matches, return ALL variants at once.
    base_element = await element_service.get_element_by_code(
        element_code=codigo_elemento_base.upper(),
        category_id=category_id,
    )
    multi_select_kw = (
        base_element.get("multi_select_keywords", []) if base_element else []
    )

    if multi_select_kw:
        for kw in multi_select_kw:
            kw_normalized = normalize_text(kw)
            if (
                kw_normalized in respuesta_normalized
                or respuesta_normalized in kw_normalized
            ):
                # User wants ALL variants - return them all
                return {
                    "selected_variants": [v["code"] for v in variants],
                    "mode": "multi_select",
                    "matched_keyword": kw,
                    "names": [v["name"] for v in variants],
                    "instrucciones": (
                        f"El usuario quiere TODAS las variantes. "
                        f"Usa todos los códigos: {[v['code'] for v in variants]} "
                        f"en calcular_tarifa_con_elementos."
                    ),
                }

    # ═══════════════════════════════════════════════════════════════════
    # Resolve pending variant state for multi-unit awareness
    # ═══════════════════════════════════════════════════════════════════
    state = get_current_state()
    mode_context = state.get("mode_context", {}) if state else {}
    raw_pending = mode_context.get("pending_variants", [])
    normalized_pending = normalize_pending_variants(raw_pending)

    # Find the pending entry for this element base code
    current_pending: PendingVariantGroup | None = None
    current_pending_idx: int = -1
    for idx, pv in enumerate(normalized_pending):
        if pv.get("codigo_base", "").upper() == codigo_normalizado:
            current_pending = pv
            current_pending_idx = idx
            break

    cantidad_pendiente = (
        current_pending.get("cantidad_pendiente", 1) if current_pending else 1
    )
    is_multi_unit = cantidad_pendiente > 1
    llm_variant_interpretation_enabled = (
        get_settings().ENABLE_LLM_VARIANT_INTERPRETATION
    )

    # ═══════════════════════════════════════════════════════════════════
    # Bug 1 Fix: Extract the relevant fragment from a combined response.
    # e.g., "placa solar opcion b y el toldo A" → "placa solar opcion b"
    # This runs BEFORE positional and keyword matching so all subsequent
    # paths work against the relevant fragment, not the full mixed reply.
    #
    # Bug 2 Fix (positional multi-letter): Pure letter responses like
    # "B y A" have no semantic anchors — the fragment extractor now
    # detects this pattern and assigns the i-th letter to the i-th
    # pending element (current_pending_idx), so positional_match works.
    # ═══════════════════════════════════════════════════════════════════
    respuesta_para_matching = _extract_element_fragment(
        respuesta=respuesta_usuario,
        codigo_elemento_base=codigo_normalizado,
        base_element=base_element,
        current_pending=current_pending,
        variants=variants,
        current_pending_idx=current_pending_idx,
        total_pending_count=len(normalized_pending),
    )
    if respuesta_para_matching != respuesta_usuario.strip():
        logger.debug(
            "seleccionar_variante_fragment_extracted",
            original=respuesta_usuario,
            fragment=respuesta_para_matching,
            codigo_base=codigo_normalizado,
        )

    # === PHASE 0: Positional matching via variant_position field ===
    # When the user answers "A", "B", "C" — map directly to variant_position from DB.
    # variant_position is the canonical presentation order (1=A, 2=B, 3=C...).
    # This field is set on creation and only changed via the reorder endpoint,
    # making it a formal contract between admin panel and agent.
    # NOTE: Numbers (1/2/3) intentionally excluded — some variants use digits as
    # keywords (e.g., FAROS_LA_2F has "2" to mean "2 headlights"), so a number
    # response like "2" could conflict with positional mapping. Letters are safe.
    # Only apply positional match for single-unit; multi-unit needs allocation logic.
    LETTER_TO_POSITION: dict[str, int] = {
        "a": 1,
        "b": 2,
        "c": 3,
        "d": 4,
        "e": 5,
    }
    # Use the extracted fragment (lower-cased) for positional and keyword matching
    respuesta_stripped = respuesta_para_matching.lower().strip()
    canonical = _normalize_to_canonical_letter(respuesta_stripped)
    lookup_key = canonical if canonical is not None else respuesta_stripped
    if not is_multi_unit and lookup_key in LETTER_TO_POSITION:
        target_position = LETTER_TO_POSITION[lookup_key]
        # Find variant with matching variant_position
        positional_match = next(
            (v for v in variants if v.get("variant_position") == target_position),
            None,
        )
        if positional_match:
            logger.info(
                "seleccionar_variante_positional_match",
                user_response=respuesta_usuario,
                position=target_position,
                matched_code=positional_match["code"],
            )
            result = _build_single_variant_result(
                positional_match,
                codigo_elemento_base,
                0.95,
                "variant_position",
            )
            # Apply single-unit resolution to pending state
            result = _apply_single_resolution_to_pending(
                result,
                positional_match,
                current_pending,
                current_pending_idx,
                normalized_pending,
            )
            return result

    # === SINGLE VARIANT MATCHING (keyword-based, deterministic) ===
    # Match user response to variant using DATA-DRIVEN keywords.
    # Use the extracted fragment (not the full combined response) so that a
    # fragment from another element (e.g., "toldo A") does not pollute scoring
    # for the current element.
    fragment_normalized = normalize_text(respuesta_para_matching)

    best_match = None
    best_score = 0.0

    for variant in variants:
        score = 0.0
        variant_code_lower = (variant.get("variant_code") or "").lower()
        variant_name_lower = variant["name"].lower()
        keywords = variant.get("keywords", [])

        # === PHASE 1: Keyword matching from variant data (primary mechanism) ===
        for kw in keywords:
            kw_normalized = normalize_text(kw)
            # Full keyword match in response fragment
            if kw_normalized in fragment_normalized:
                score += 0.8
            # Partial word overlap for multi-word keywords
            elif " " in kw:
                kw_words = set(kw_normalized.split())
                resp_words = set(fragment_normalized.split())
                overlap = len(kw_words & resp_words)
                if overlap > 0:
                    score += 0.4 * (overlap / len(kw_words))

        # === PHASE 2: Variant code matching (fallback) ===
        if variant_code_lower:
            variant_code_normalized = normalize_text(
                variant_code_lower.replace("_", " ")
            )
            if variant_code_normalized in fragment_normalized:
                score += 0.7

        # === PHASE 3: Name word overlap (secondary fallback) ===
        name_words = [
            w for w in normalize_text(variant_name_lower).split() if len(w) > 3
        ]
        matching_words = sum(1 for word in name_words if word in fragment_normalized)
        if matching_words > 0 and name_words:
            score += 0.3 * (matching_words / len(name_words))

        if score > best_score:
            best_score = score
            best_match = variant

    # ═══════════════════════════════════════════════════════════════════
    # Task 3.2: Single-variant fast-path (backward compatible)
    # When cantidad_pendiente == 1 AND keyword match >= 0.5, use
    # the deterministic path with the same output shape as before.
    # ═══════════════════════════════════════════════════════════════════
    if (
        best_match
        and best_score >= 0.5
        and (not is_multi_unit or not llm_variant_interpretation_enabled)
    ):
        if is_multi_unit and not llm_variant_interpretation_enabled:
            logger.info(
                "seleccionar_variante_keyword_only_fallback",
                codigo_base=codigo_normalizado,
                cantidad_pendiente=cantidad_pendiente,
            )
        logger.info(
            "seleccionar_variante_single_fast_path",
            matched_code=best_match["code"],
            confidence=round(best_score, 2),
            codigo_base=codigo_normalizado,
        )
        result = _build_single_variant_result(
            best_match,
            codigo_elemento_base,
            best_score,
            "keyword",
        )
        # Apply single-unit resolution to pending state
        result = _apply_single_resolution_to_pending(
            result,
            best_match,
            current_pending,
            current_pending_idx,
            normalized_pending,
        )
        return result

    # ═══════════════════════════════════════════════════════════════════
    # Task 3.1: Multi-unit OR low-confidence → LLM interpretation service
    # ═══════════════════════════════════════════════════════════════════
    if (
        llm_variant_interpretation_enabled
        and current_pending
        and (is_multi_unit or best_score < 0.5)
    ):
        # ── Phase 4: Early ambiguity exit (ADR-006) ──────────────────────
        # For single-unit requests, when the keyword score is very low AND
        # the user's message contains no domain vocabulary from the variant
        # options, skip Tier-1 LLM interpretation and return
        # needs_clarification=True immediately.  This avoids sending an
        # ambiguous message (e.g. "sí") to qwen2.5:3b which then hallucinates
        # a bare-letter allocation with 0.95 confidence.
        if (
            not is_multi_unit
            and best_score < AMBIGUITY_THRESHOLD
            and not _has_domain_vocabulary_from_variants(respuesta_usuario, variants)
        ):
            logger.info(
                "seleccionar_variante_early_ambiguity_exit",
                keyword_score=round(best_score, 2),
                element=current_pending.get("codigo_base", "unknown"),
            )
            return {
                "needs_clarification": True,
                "clarification_reason": (
                    "La respuesta no contiene vocabulario específico de la variante."
                ),
                "pregunta": current_pending.get("pregunta", ""),
                "opciones_disponibles": [v.get("name", "") for v in variants],
            }
        # ── End Phase 4 early exit ────────────────────────────────────────

        logger.info(
            "seleccionar_variante_llm_interpretation",
            codigo_base=codigo_normalizado,
            cantidad_pendiente=cantidad_pendiente,
            is_multi_unit=is_multi_unit,
            keyword_score=round(best_score, 2),
        )
        interpretation: VariantInterpretationResult = (
            await interpret_variant_allocations(
                user_message=respuesta_usuario,
                pending_variant=current_pending,
                conversation_context=None,
            )
        )

        if interpretation.needs_clarification:
            return {
                "error": "No se pudo determinar la variante con certeza.",
                "needs_clarification": True,
                "clarification_reason": interpretation.clarification_reason,
                "sugerencia": interpretation.clarification_reason
                or "Pregunta al usuario de forma más específica.",
                "opciones_disponibles": [f"- {v['name']}" for v in variants],
            }

        # Build option text → element code map for correct storage
        opciones = current_pending.get("opciones", [])
        option_to_code_map: dict[str, str] = {}
        for i, opcion in enumerate(opciones):
            if i < len(variants):
                option_to_code_map[opcion] = variants[i]["code"]

        # Apply allocations to pending state
        updated_pending, apply_errors = validate_and_apply_allocations(
            current_pending,
            interpretation.allocations,
            dry_run=False,
            option_to_code_map=option_to_code_map,
        )

        if apply_errors:
            logger.warning(
                "seleccionar_variante_apply_errors",
                codigo_base=codigo_normalizado,
                errors=apply_errors,
            )
            return {
                "error": "No se pudieron aplicar las asignaciones.",
                "apply_errors": apply_errors,
                "sugerencia": "Pregunta al usuario de forma más específica.",
                "opciones_disponibles": [f"- {v['name']}" for v in variants],
            }

        # Build updated pending_variants list
        new_pending_list = list(normalized_pending)
        new_pending_list[current_pending_idx] = updated_pending

        # Determine overall resolution status
        all_resolved = all(pv.get("status") == "resolved" for pv in new_pending_list)
        unresolved_count = sum(
            1 for pv in new_pending_list if pv.get("status") != "resolved"
        )

        # Extract the first allocation's variant code for backward-compatible
        # selected_variant field
        first_alloc = (
            interpretation.allocations[0] if interpretation.allocations else None
        )
        first_variant_code = first_alloc.variant_code if first_alloc else None

        # Try to resolve the allocation's variant_code to an actual DB variant code
        resolved_db_code = None
        resolved_db_name = None
        if first_variant_code:
            # Match the allocation's variant_code against DB variants by name similarity
            alloc_norm = normalize_text(first_variant_code)
            for v in variants:
                v_name_norm = normalize_text(v["name"])
                v_code_norm = normalize_text(v.get("variant_code", ""))
                if (
                    (len(alloc_norm) > 2 and alloc_norm in v_name_norm)
                    or v_name_norm in alloc_norm
                    or alloc_norm == v_code_norm
                ):
                    resolved_db_code = v["code"]
                    resolved_db_name = v["name"]
                    break

        # ── Bug 1 Fix Task 2.3: Bare-letter guard ───────────────────────────
        # If the LLM resolved to a bare positional letter ("a"-"e") instead of
        # a real DB code, try to map it via LETTER_TO_POSITION before accepting.
        # If it still cannot be mapped, reject and request clarification.
        selected_variant_code = resolved_db_code or first_variant_code
        if selected_variant_code and _BARE_LETTER_RE.match(
            selected_variant_code.strip()
        ):
            letter = selected_variant_code.strip().lower()
            target_position = LETTER_TO_POSITION.get(letter)
            positional_fallback = (
                next(
                    (
                        v
                        for v in variants
                        if v.get("variant_position") == target_position
                    ),
                    None,
                )
                if target_position
                else None
            )
            if positional_fallback:
                # ── Confidence gate (REQ-3) ──────────────────────────────────
                # When the LLM resolved to a bare letter with very low confidence
                # AND the user's fragment contains no domain vocabulary that
                # confirms the variant type, reject the mapping and ask for
                # clarification.  This prevents the system from silently
                # auto-committing variants from hallucinated bare letters.
                avg_confidence = sum(
                    a.confidence for a in interpretation.allocations
                ) / max(len(interpretation.allocations), 1)
                if avg_confidence < 0.3 and not _has_domain_vocabulary(
                    respuesta_usuario
                ):
                    logger.warning(
                        "seleccionar_variante_bare_letter_low_confidence",
                        bare_letter=letter,
                        avg_confidence=round(avg_confidence, 2),
                        codigo_base=codigo_normalizado,
                        reason="low_confidence_no_domain_vocabulary",
                    )
                    return {
                        "error": "No se pudo determinar la variante con certeza.",
                        "needs_clarification": True,
                        "clarification_reason": (
                            "La respuesta no fue suficientemente clara para "
                            "seleccionar la variante con seguridad."
                        ),
                        "sugerencia": "Pregunta al usuario de forma más específica.",
                        "opciones_disponibles": [f"- {v['name']}" for v in variants],
                    }
                # ── End confidence gate ──────────────────────────────────────
                logger.info(
                    "seleccionar_variante_bare_letter_mapped",
                    bare_letter=letter,
                    resolved_code=positional_fallback["code"],
                    codigo_base=codigo_normalizado,
                )
                resolved_db_code = positional_fallback["code"]
                resolved_db_name = positional_fallback["name"]
                selected_variant_code = resolved_db_code
            else:
                # Cannot map bare letter → reject to avoid fabricated codes
                logger.warning(
                    "seleccionar_variante_bare_letter_rejected",
                    bare_letter=letter,
                    codigo_base=codigo_normalizado,
                    available_positions=[v.get("variant_position") for v in variants],
                )
                return {
                    "error": "No se pudo determinar la variante con certeza.",
                    "needs_clarification": True,
                    "clarification_reason": (
                        f"La interpretación resultó en '{selected_variant_code}' que no "
                        "corresponde a ninguna variante conocida."
                    ),
                    "sugerencia": "Pregunta al usuario de forma más específica.",
                    "opciones_disponibles": [f"- {v['name']}" for v in variants],
                }
        # ── End bare-letter guard ────────────────────────────────────────────

        response_data: dict[str, Any] = {
            "selected_variant": selected_variant_code,
            "confidence": round(
                sum(a.confidence for a in interpretation.allocations)
                / max(len(interpretation.allocations), 1),
                2,
            ),
            "name": resolved_db_name or (first_variant_code or ""),
            "applied_allocations": [
                {
                    "variant_code": a.variant_code,
                    "quantity": a.quantity,
                    "confidence": round(a.confidence, 2),
                }
                for a in interpretation.allocations
            ],
            "resolution_status": updated_pending.get("status", "pending"),
            "pending_count": unresolved_count,
            "instrucciones": (
                f"Todas las variantes de '{codigo_elemento_base}' están resueltas. "
                "Puedes proceder a calcular tarifa."
                if updated_pending.get("status") == "resolved"
                else f"Faltan {updated_pending.get('cantidad_pendiente', 0)} unidades por resolver "
                f"de '{codigo_elemento_base}'. Pregunta al usuario."
            ),
            "_internal_flags": {
                "pending_variants": [dict(pv) for pv in new_pending_list],
            },
        }

        logger.info(
            "seleccionar_variante_multi_unit_resolved",
            codigo_base=codigo_normalizado,
            resolution_status=updated_pending.get("status"),
            all_resolved=all_resolved,
            pending_count=unresolved_count,
        )

        return response_data

    # === FALLBACK: No match, no multi-unit, no pending context ===
    if not best_match or best_score < 0.5:
        available_options = [f"- {v['name']}" for v in variants]
        return {
            "error": "No se pudo determinar la variante con certeza.",
            "sugerencia": "Pregunta al usuario de forma más específica.",
            "opciones_disponibles": available_options,
        }

    # Low confidence single match without pending state
    result = _build_single_variant_result(
        best_match,
        codigo_elemento_base,
        best_score,
        "keyword",
    )
    return result


# ---------------------------------------------------------------------------
# Private helpers for seleccionar_variante_por_respuesta
# ---------------------------------------------------------------------------


def _build_single_variant_result(
    variant: dict[str, Any],
    codigo_elemento_base: str,
    confidence: float,
    match_method: str,
) -> dict[str, Any]:
    """
    Build the standard single-variant selection result dict.

    Preserves backward-compatible output shape.

    Args:
        variant: The matched variant dict from the element service.
        codigo_elemento_base: The original base element code.
        confidence: Match confidence score.
        match_method: How the match was determined (e.g., "keyword", "variant_position").

    Returns:
        Result dict ready for JSON serialization.
    """
    result: dict[str, Any] = {
        "selected_variant": variant["code"],
        "confidence": round(confidence, 2),
        "name": variant["name"],
        "variant_code": variant.get("variant_code", ""),
    }

    if match_method == "variant_position":
        result["match_method"] = "variant_position"
        result["variant_position"] = variant.get("variant_position")

    if confidence >= 0.7:
        result["instrucciones"] = (
            f"Usa el código '{variant['code']}' en lugar de '{codigo_elemento_base}' "
            "para calcular_tarifa_con_elementos y validar_elementos."
        )
    else:
        result["instrucciones"] = (
            "Confidence bajo. Pregunta al usuario para confirmar la selección."
        )

    return result


def _apply_single_resolution_to_pending(
    result: dict[str, Any],
    matched_variant: dict[str, Any],
    current_pending: PendingVariantGroup | None,
    current_pending_idx: int,
    normalized_pending: list[PendingVariantGroup],
) -> dict[str, Any]:
    """
    Apply a single-unit resolution to the pending_variants state.

    Updates the matching pending entry's status and returns updated
    _internal_flags for the mode to apply.

    Args:
        result: The result dict being built.
        matched_variant: The resolved variant.
        current_pending: The matching pending entry (or None).
        current_pending_idx: Index in normalized_pending.
        normalized_pending: Full normalized pending list.

    Returns:
        Updated result dict with _internal_flags if applicable.
    """
    if current_pending is None or current_pending_idx < 0:
        return result

    # Build updated pending entry with this unit resolved
    from agent.state.conversation_state import VariantResolution

    existing_resoluciones = list(current_pending.get("resoluciones", []))
    existing_resoluciones.append(
        VariantResolution(
            variant_code=matched_variant["code"],
            quantity=1,
            confidence=result.get("confidence", 0.9),
            source="user_explicit",
        )
    )

    nueva_resuelta = current_pending.get("cantidad_resuelta", 0) + 1
    nueva_total = current_pending.get("cantidad_total", 1)
    nueva_pendiente = nueva_total - nueva_resuelta

    if nueva_resuelta >= nueva_total:
        new_status = "resolved"
    elif nueva_resuelta > 0:
        new_status = "partial"
    else:
        new_status = "pending"

    updated_entry = PendingVariantGroup(
        pending_id=current_pending.get("pending_id", "UNKNOWN"),
        codigo_base=current_pending.get("codigo_base", "UNKNOWN"),
        pregunta=current_pending.get("pregunta", ""),
        opciones=current_pending.get("opciones", []),
        cantidad_total=nueva_total,
        cantidad_resuelta=nueva_resuelta,
        cantidad_pendiente=nueva_pendiente,
        resoluciones=existing_resoluciones,
        status=new_status,
    )

    # Build new pending list
    new_pending_list = list(normalized_pending)
    new_pending_list[current_pending_idx] = updated_entry

    all_resolved = all(pv.get("status") == "resolved" for pv in new_pending_list)
    unresolved_count = sum(
        1 for pv in new_pending_list if pv.get("status") != "resolved"
    )

    result["resolution_status"] = new_status
    result["pending_count"] = unresolved_count
    result["_internal_flags"] = {
        "pending_variants": [dict(pv) for pv in new_pending_list],
    }

    return result


@tool
async def calcular_tarifa_con_elementos(
    categoria_vehiculo: str,
    codigos_elementos: list[str],
    skip_validation: bool = False,
) -> dict[str, Any]:
    """
    Calcula el precio de homologación basándose en elementos específicos del catálogo.

    ⚠️ IMPORTANTE:
    - USA EXACTAMENTE los códigos retornados por `identificar_elementos`
    - NO inventes códigos nuevos
    - DEBES llamar `validar_elementos` ANTES de esta herramienta (o usar skip_validation=True si ya validaste)

    Esta herramienta valida que los elementos existan y busca la tarifa que los cubra.
    La tarifa seleccionada es la más económica que incluye TODOS los elementos especificados.

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        codigos_elementos: Lista de códigos EXACTOS retornados por identificar_elementos
                          Ejemplo: ["ESCAPE", "MANILLAR"] (NO uses variaciones)
        skip_validation: Si True, omite la validación previa de códigos (usar cuando ya se validó
                        previamente con validar_elementos o identificar_y_resolver_elementos).
                        Default: False

    REFACTOR-001 Note: This tool sets precio_comunicado=True via _internal_flags,
    signaling that a price has been calculated and will be communicated to the user
    in the LLM's response. The flag is automatically applied by the mode handler.

    Returns:
        Tarifa seleccionada, precio, elementos incluidos y advertencias.
        Los precios son SIN IVA.
    """
    # ═══════════════════════════════════════════════════════════════════
    # DIAGNOSTIC: Log if variants appear pending (may be stale ContextVar).
    #
    # FIX 3 (fix/variant-state-persistence): Converted from HARD BLOCK to
    # SOFT WARNING. The old guard returned {"success": False} when it saw
    # unresolved pending_variants in the ContextVar. This caused a regression
    # because the ContextVar snapshot is set at the START of each iteration
    # (before any tools run), so it always reflects the CHECKPOINT state —
    # not the updated state after seleccionar_variante_por_respuesta ran.
    #
    # The real defense is the tariff_blocked_parent_codes guard below
    # (DB-level check that blocks parent element codes). That guard is the
    # structural safety net. Trust the LLM: the inject_message already
    # informed the LLM that all variants are resolved.
    # ═══════════════════════════════════════════════════════════════════
    state = get_current_state()
    if state is None:
        logger.warning(
            "calcular_tarifa_state_unavailable",
            codigos_solicitados=codigos_elementos,
        )
    else:
        mode_context = state.get("mode_context", {})
        raw_pending = mode_context.get("pending_variants", [])
        if raw_pending:
            # Normalize to enriched shape and filter only unresolved
            norm_pending = normalize_pending_variants(raw_pending)
            unresolved_pending = [
                pv for pv in norm_pending if pv.get("status") != "resolved"
            ]
            if unresolved_pending:
                logger.warning(
                    "tariff_calc_with_pending_variants_soft_warning",
                    pending_count=len(unresolved_pending),
                    codigos_solicitados=codigos_elementos,
                    pending_codes=[pv.get("codigo_base") for pv in unresolved_pending],
                    note=(
                        "ContextVar may be stale snapshot from checkpoint. "
                        "Continuing execution — parent_codes guard is the real defense."
                    ),
                )
                # Trust the LLM: inject_message already guided the LLM to call this
                # tool only after all variants are resolved. If this is a genuine
                # premature call, the parent_codes guard below will block parent codes.
    # ═══════════════════════════════════════════════════════════════════

    # Normalize category slug (LLM may send uppercase)
    categoria_vehiculo = categoria_vehiculo.lower().strip()

    # Validate category slug for security
    try:
        validate_category_slug(categoria_vehiculo)
    except ValueError as e:
        logger.error(
            f"Invalid category slug rejected in calcular_tarifa_con_elementos: {e}"
        )
        return {"success": False, "error": str(e)}

    tarifa_service = get_tarifa_service()
    element_service = get_element_service()

    # === VALIDACIÓN PREVIA (skip if already validated) ===
    if not skip_validation:
        # Validate codes using internal function (NOT the @tool decorated function)
        validation = await _validate_element_codes(
            categoria_vehiculo=categoria_vehiculo,
            codigos_elementos=codigos_elementos,
            confianzas=None,
        )

        if not validation["valid"]:
            return {
                "success": False,
                "error": (
                    f"❌ ERROR: No puedo calcular tarifa con códigos inválidos.\n\n"
                    f"{validation['message']}\n\n"
                    f"Debes usar `identificar_elementos` primero para obtener códigos válidos."
                ),
            }
    # === FIN VALIDACIÓN ===

    # Log codes being used for tariff calculation
    logger.info(
        f"[calcular_tarifa] Calculating with validated codes | category={categoria_vehiculo}",
        extra={"codes": codigos_elementos},
    )

    # Get category ID from slug (cached)
    category_id = await get_or_fetch_category_id(categoria_vehiculo)
    if not category_id:
        categories = await tarifa_service.get_active_categories()
        available = ", ".join(c["slug"] for c in categories)
        return {
            "success": False,
            "error": f"Categoría '{categoria_vehiculo}' no encontrada. Categorías disponibles: {available}",
        }

    if not codigos_elementos:
        return {
            "success": False,
            "error": "Debes especificar al menos un código de elemento.",
        }

    # Get element details for each code
    elements = await element_service.get_elements_by_category(
        category_id, is_active=True
    )
    element_by_code = {e["code"]: e for e in elements}

    # Validate element codes and collect element info
    # Use fuzzy matching to auto-correct common LLM errors (ASIDERO → ASIDEROS)
    valid_codes_set = set(element_by_code.keys())
    normalized_codes, corrections, truly_invalid = normalize_element_codes(
        codigos_elementos, valid_codes_set
    )

    # Log any auto-corrections made
    if corrections:
        logger.info(
            f"[calcular_tarifa] Auto-corrected element codes: {corrections}",
            extra={"corrections": corrections, "category": categoria_vehiculo},
        )

    # Now validate with normalized codes
    valid_elements = []
    invalid_codes = []

    for code in normalized_codes:
        if code in element_by_code:
            valid_elements.append(element_by_code[code])
        else:
            invalid_codes.append(code)

    # Add truly invalid codes (those that couldn't be normalized)
    invalid_codes.extend(truly_invalid)

    if invalid_codes:
        available_codes = ", ".join(sorted(element_by_code.keys()))
        return {
            "success": False,
            "error": (
                f"Error: Códigos no encontrados: {', '.join(invalid_codes)}\n\n"
                f"Códigos válidos para {categoria_vehiculo}: {available_codes}\n\n"
                "Usa `identificar_elementos` para obtener los códigos correctos."
            ),
        }

    if not valid_elements:
        return {"success": False, "error": "No se encontraron elementos válidos."}

    # ═══════════════════════════════════════════════════════════════════
    # UNCONDITIONAL GUARD: Reject parent elements that have children
    # This runs REGARDLESS of skip_validation to prevent parent codes
    # from reaching tariff calculation (e.g., TOLDO_LAT when user must
    # pick TOLDO_SIMPLE or TOLDO_ARTICULADO).
    # Reuses already-fetched `elements` — NO new DB queries.
    # ═══════════════════════════════════════════════════════════════════
    element_by_id: dict[str, dict[str, Any]] = {e["id"]: e for e in elements}
    parent_to_children: dict[str, list[dict[str, str]]] = {}
    for el in elements:
        parent_id = el.get("parent_element_id")
        if parent_id and parent_id in element_by_id:
            parent_elem = element_by_id[parent_id]
            parent_code = parent_elem["code"]
            parent_to_children.setdefault(parent_code, []).append(
                {
                    "code": el["code"],
                    "name": el["name"],
                }
            )

    parent_codes_found: list[dict[str, Any]] = []
    remaining_valid: list[dict[str, Any]] = []
    for elem in valid_elements:
        if elem["code"] in parent_to_children:
            children = parent_to_children[elem["code"]]
            parent_codes_found.append(
                {
                    "code": elem["code"],
                    "name": elem["name"],
                    "children": children,
                    "variant_codes": [c["code"] for c in children],
                    "question_hint": elem.get("question_hint")
                    or f"¿Qué tipo de {elem['name'].lower()}?",
                }
            )
        else:
            remaining_valid.append(elem)

    if parent_codes_found:
        logger.warning(
            "tariff_blocked_parent_codes",
            extra={
                "parent_codes": [p["code"] for p in parent_codes_found],
                "category": categoria_vehiculo,
                "skip_validation": skip_validation,
            },
        )

        lines_err = ["=== ERROR: ELEMENTOS SIN VARIANTE ESPECIFICADA ===", ""]
        lines_err.append(
            "Los siguientes elementos requieren que especifiques la variante:"
        )
        lines_err.append("")

        for parent in parent_codes_found:
            lines_err.append(f"❌ '{parent['name']}' tiene variantes disponibles:")
            for child in parent["children"]:
                lines_err.append(f"   • {child['name']} ({child['code']})")
            lines_err.append("")
            lines_err.append(f"   Pregunta sugerida: {parent['question_hint']}")
            lines_err.append("")

        lines_err.append("⚠️ ACCIÓN OBLIGATORIA:")
        lines_err.append("1. Pregunta al usuario qué variante específica necesita")
        lines_err.append("2. Usa el código de la VARIANTE (no del elemento base)")
        lines_err.append(
            "3. Vuelve a llamar calcular_tarifa_con_elementos con los códigos correctos"
        )
        lines_err.append("")
        lines_err.append(
            "IMPORTANTE: Los elementos padre NO son homologables directamente."
        )
        lines_err.append("Solo se pueden homologar las variantes específicas.")

        return {
            "success": False,
            "status": "ERROR_VARIANTE_REQUERIDA",
            "message": "\n".join(lines_err),
            "parent_elements_rejected": parent_codes_found,
            "_internal_flags": {
                "precio_comunicado": False,
            },
        }
    # ═══════════════════════════════════════════════════════════════════

    # Get current client type from state
    state = get_current_state()
    client_type = state.get("client_type", "particular") if state else "particular"

    # Calculate tariff using the element count and description
    # Build description from element names for rule matching
    description = ", ".join(e["name"] for e in valid_elements)

    # Pass element_codes for tier validation
    result = await tarifa_service.select_tariff_by_rules(
        category_slug=categoria_vehiculo,
        elements_description=description,
        element_count=len(valid_elements),
        element_codes=[code.upper() for code in codigos_elementos],
    )

    if "error" in result:
        return {"success": False, "error": result["error"]}

    # Get warnings per element for grouped display
    # We collect per-element to maintain the element→warning association
    element_count = len(valid_elements)
    existing_warning_codes = {w.get("code") for w in result.get("warnings", [])}
    element_warnings_grouped: dict[str, list[dict]] = {}  # element_code -> [warnings]
    total_element_warnings = 0

    for elem in valid_elements:
        elem_warnings = await element_service.get_element_warnings(elem["id"])
        active_warnings_for_elem = []

        for ew in elem_warnings:
            if ew["code"] in existing_warning_codes:
                continue

            # Evaluate show_condition
            show_condition = ew.get("show_condition", "always")
            threshold = ew.get("threshold_quantity")

            should_show = False
            if show_condition == "always":
                should_show = True
            elif show_condition == "on_exceed_max" and threshold is not None:
                should_show = element_count > threshold
            elif show_condition == "on_below_min" and threshold is not None:
                should_show = element_count < threshold
            else:
                should_show = True

            if should_show:
                warning_data = {
                    "code": ew["code"],
                    "message": ew["message"],
                    "severity": ew["severity"],
                    "element_code": elem["code"],
                    "element_name": elem["name"],
                }
                active_warnings_for_elem.append(warning_data)
                result.setdefault("warnings", []).append(warning_data)
                existing_warning_codes.add(ew["code"])

        if active_warnings_for_elem:
            element_warnings_grouped[elem["code"]] = active_warnings_for_elem
            total_element_warnings += len(active_warnings_for_elem)

    logger.info(
        f"[calcular_tarifa] Retrieved {total_element_warnings} warnings for {len(valid_elements)} elements",
        extra={
            "element_count": len(valid_elements),
            "warning_count": total_element_warnings,
            "elements_with_warnings": list(element_warnings_grouped.keys()),
        },
    )

    # === DOCUMENTACIÓN E IMÁGENES ===
    # Get base documentation for the category
    category_data = await tarifa_service.get_category_data(categoria_vehiculo)
    base_documentation = []
    base_images = []

    if category_data and category_data.get("base_documentation"):
        for base_doc in category_data["base_documentation"]:
            base_documentation.append(
                {
                    "descripcion": base_doc["description"],
                    "imagen_url": base_doc.get("image_url"),
                }
            )
            if base_doc.get("image_url"):
                base_images.append(
                    {
                        "url": base_doc["image_url"],
                        "tipo": "base",
                        "descripcion": base_doc["description"],
                        "status": "active",  # BaseDocumentation images are admin-set
                    }
                )

    # Get images for each element
    element_documentation = []
    element_images = []

    for elem in valid_elements:
        elem_details = await element_service.get_element_with_images(elem["id"])
        elem_doc = {
            "codigo": elem["code"],
            "nombre": elem["name"],
            "imagenes": [],
        }

        if elem_details and elem_details.get("images"):
            for img in elem_details["images"]:
                img_status = img.get("status", "placeholder")
                img_info = {
                    "url": img["image_url"],
                    "tipo": img["image_type"],
                    "titulo": img.get("title", ""),
                    "descripcion": img.get("description", ""),
                    "requerida": img.get("is_required", False),
                    "instruccion_usuario": img.get("user_instruction", ""),
                    "status": img_status,
                }
                elem_doc["imagenes"].append(img_info)
                element_images.append(
                    {
                        "url": img["image_url"],
                        "tipo": img["image_type"],
                        "elemento": elem["name"],
                        "descripcion": img.get("description") or img.get("title", ""),
                        "status": img_status,
                    }
                )

        element_documentation.append(elem_doc)

    # Format response
    lines = [
        f"TARIFA RECOMENDADA: {result['tier_name']}",
        f"Precio: {result['price']} EUR (IVA no incluido)",
        "",
    ]

    if result.get("conditions"):
        lines.append(f"Condiciones: {result['conditions']}")
        lines.append("")

    lines.append(f"Elementos incluidos ({len(valid_elements)}):")
    for elem in valid_elements:
        lines.append(f"- {elem['name']}")
    lines.append("")

    # Add warnings grouped by element
    if result.get("warnings"):
        logger.info(
            f"[calcular_tarifa] Including {len(result['warnings'])} warnings in response text",
            extra={"warnings": [w.get("code") for w in result["warnings"]]},
        )
        lines.append("ADVERTENCIAS:")

        # First: element-specific warnings, grouped by element
        if element_warnings_grouped:
            for elem_code, elem_warns in element_warnings_grouped.items():
                elem_name = next(
                    (e["name"] for e in valid_elements if e["code"] == elem_code),
                    elem_code,
                )
                lines.append(f"\n  {elem_name}:")
                for w in elem_warns:
                    severity_icon = (
                        "🔴"
                        if w.get("severity") == "error"
                        else "⚠️"
                        if w.get("severity") == "warning"
                        else "ℹ️"
                    )
                    lines.append(f"    {severity_icon} {w['message']}")

        # Then: general warnings (rule-based, without element association)
        general_warnings = [w for w in result["warnings"] if not w.get("element_code")]
        if general_warnings:
            if element_warnings_grouped:
                lines.append("\n  General:")
            for w in general_warnings:
                severity_icon = (
                    "🔴"
                    if w.get("severity") == "error"
                    else "⚠️"
                    if w.get("severity") == "warning"
                    else "ℹ️"
                )
                prefix = "    " if element_warnings_grouped else "  "
                lines.append(f"{prefix}{severity_icon} {w['message']}")

        lines.append("")

    # Add element validation warnings (elements not in tier)
    validation = result.get("element_validation", {})
    if not validation.get("valid", True) and validation.get("missing_elements"):
        lines.append("")
        lines.append("⚠️ ADVERTENCIA - ELEMENTOS NO INCLUIDOS EN TARIFA:")
        for code in validation["missing_elements"]:
            lines.append(f"  • {code}")
        lines.append("")
        lines.append("Estos elementos pueden requerir tarifa adicional o")
        lines.append("una combinación diferente de elementos.")
        lines.append("")

    # Add additional services if available
    if result.get("additional_services"):
        lines.append("Servicios adicionales disponibles:")
        for s in result["additional_services"][:3]:  # Show first 3
            lines.append(f"- {s['name']}: {s['price']} EUR")
        if len(result.get("additional_services", [])) > 3:
            lines.append(f"  ... y {len(result['additional_services']) - 3} mas")
        lines.append("")

    # Add documentation section
    lines.append("DOCUMENTACION REQUERIDA:")
    lines.append("")

    # Base documentation (always required)
    if base_documentation:
        lines.append("Documentacion base obligatoria:")
        for doc in base_documentation:
            lines.append(f"  - {doc['descripcion']}")
        lines.append("")

    # Element-specific documentation
    if element_documentation:
        lines.append("Documentacion por elemento:")
        for elem_doc in element_documentation:
            if elem_doc["imagenes"]:
                lines.append(f"  {elem_doc['nombre']}:")
                for img in elem_doc["imagenes"]:
                    desc = (
                        img.get("descripcion")
                        or img.get("titulo")
                        or "Foto del elemento"
                    )
                    lines.append(f"    - {desc}")
            else:
                lines.append(
                    f"  {elem_doc['nombre']}: Foto del elemento con matricula visible"
                )
        lines.append("")

    # User instructions for required documents (from DB, NOT to be invented)
    user_instructions = []
    for elem_doc in element_documentation:
        for img in elem_doc.get("imagenes", []):
            if img.get("requerida") and img.get("instruccion_usuario"):
                user_instructions.append(
                    {
                        "elemento": elem_doc["nombre"],
                        "instruccion": img["instruccion_usuario"],
                    }
                )

    if user_instructions:
        lines.append(
            "INSTRUCCIONES PARA EL USUARIO (datos oficiales de la DB, NO inventes):"
        )
        for instr in user_instructions:
            lines.append(f"  [{instr['elemento']}]: {instr['instruccion']}")
        lines.append("")
        lines.append(
            "Cuando el usuario pregunte que fotos necesita, usa EXACTAMENTE estas instrucciones."
        )
        lines.append("")

    # Image count summary (only count active images)
    active_images = [
        img for img in (base_images + element_images) if img.get("status") == "active"
    ]
    active_base_images = [img for img in base_images if img.get("status") == "active"]
    active_element_images = [
        img for img in element_images if img.get("status") == "active"
    ]

    # Check which elements have NO active images
    elements_without_images = []
    for elem_doc in element_documentation:
        elem_active_images = [
            img for img in elem_doc.get("imagenes", []) if img.get("status") == "active"
        ]
        if not elem_active_images:
            elements_without_images.append(elem_doc["nombre"])

    if active_images:
        lines.append(
            f"IMAGENES DE EJEMPLO DISPONIBLES (enviar en turno siguiente, NO en este mismo turno): {len(active_images)}"
        )
        lines.append(f"  - Base (ficha técnica, permiso): {len(active_base_images)}")
        lines.append(f"  - Elementos específicos: {len(active_element_images)}")
        lines.append(
            "INSTRUCCIÓN: Comunica el precio al usuario AHORA. Ofrece opciones A/B. Llama enviar_imagenes_ejemplo SOLO si el usuario elige opción A en el SIGUIENTE turno."
        )

        if elements_without_images:
            lines.append("")
            lines.append(
                f"⚠️ ELEMENTOS SIN IMAGENES DE EJEMPLO: {', '.join(elements_without_images)}"
            )
            lines.append(
                "  Para estos elementos, describe la documentación requerida sin prometer fotos de ejemplo."
            )
        lines.append("")
    elif base_images or element_images:
        lines.append(
            "IMAGENES DE EJEMPLO: No disponibles en este momento (pendientes de configuracion)."
        )
        lines.append(
            "NO prometas imagenes al usuario. Describele la documentacion usando SOLO los datos de arriba."
        )
        lines.append("")

    # Build structured response for case creation
    text_response = "\n".join(lines)

    # Build JSON response with structured data for iniciar_expediente
    response = {
        "texto": text_response,
        "datos": {
            "tier_id": result["tier_id"],
            "tier_name": result["tier_name"],
            "price": float(result["price"]),
            "elements": [e["name"] for e in valid_elements],
            "element_codes": codigos_elementos,
            "warnings": [
                {
                    "message": w["message"],
                    "severity": w.get("severity", "info"),
                    "element_code": w.get("element_code"),
                    "element_name": w.get("element_name"),
                }
                for w in result.get("warnings", [])
            ],
        },
        "documentacion": {
            "base": base_documentation,
            "elementos": element_documentation,
        },
        "imagenes_ejemplo": base_images + element_images,
        "_internal_flags": {  # REFACTOR-001 Phase 4: Set state explicitly
            "precio_comunicado": True,
            "imagenes_enviadas": False,  # Reset when new price calculated
        },
    }

    # ── DraftQuote fire-and-forget write ─────────────────────────────────────
    # Write the quote to DB asynchronously. Errors never surface to the LLM.
    state_for_draft = get_current_state()
    conv_id_for_draft = (
        state_for_draft.get("conversation_id") if state_for_draft else None
    )
    if conv_id_for_draft:
        await _fire_and_forget_draft_quote(
            conversation_id=str(conv_id_for_draft),
            category_slug=categoria_vehiculo,
            elements=list(codigos_elementos),
            tier_id=str(result.get("tier_id")) if result.get("tier_id") else None,
            precio_final=result["price"],
        )
    # ─────────────────────────────────────────────────────────────────────────

    return response


async def _fire_and_forget_draft_quote(
    conversation_id: str,
    category_slug: str,
    elements: list[str],
    tier_id: str | None,
    precio_final: Any,
) -> None:
    """
    Write a DraftQuote to DB. Catches ALL exceptions so errors never propagate.

    This is the fire-and-forget wrapper used by calcular_tarifa_con_elementos.

    Args:
        conversation_id: Conversation UUID as string.
        category_slug: Vehicle category slug.
        elements: List of element codes.
        tier_id: Resolved tier UUID as string (or None).
        precio_final: Final price (Decimal or float).
    """
    from decimal import Decimal as _Decimal
    from database.connection import get_async_session
    from agent.tools.draft_quote_service import _upsert_draft_quote

    try:
        price = _Decimal(str(precio_final))
        async with get_async_session() as session:
            await _upsert_draft_quote(
                session=session,
                conversation_id=conversation_id,
                category_slug=category_slug,
                elements=elements,
                tier_id=tier_id,
                precio_final=price,
            )
            await session.commit()
    except Exception as exc:
        logger.warning(
            "draft_quote_write_failed",
            conversation_id=conversation_id,
            error=str(exc),
        )


@tool
async def obtener_documentacion_elemento(
    categoria_vehiculo: str,
    codigo_elemento: str,
) -> dict[str, Any]:
    """
    Obtiene la documentación e imágenes necesarias para homologar un elemento específico.

    Usa esta herramienta cuando el usuario pregunte qué fotos o documentos necesita
    para homologar un elemento concreto.

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        codigo_elemento: Código del elemento (ej: "ESCAPE", "ESC_MEC")

    Returns:
        Dictionary with:
        - "texto": Text description of required documentation
        - "imagenes": List of example image URLs to send to user
    """
    # Normalize category slug (LLM may send uppercase)
    categoria_vehiculo = categoria_vehiculo.lower().strip()

    # Validate category slug for security
    try:
        validate_category_slug(categoria_vehiculo)
    except ValueError as e:
        logger.error(
            f"Invalid category slug rejected in obtener_documentacion_elemento: {e}"
        )
        return {
            "texto": f"Error: {str(e)}",
            "imagenes": [],
        }

    element_service = get_element_service()

    # Get category ID from slug (cached)
    category_id = await get_or_fetch_category_id(categoria_vehiculo)
    if not category_id:
        return {
            "texto": f"Categoría '{categoria_vehiculo}' no encontrada.",
            "imagenes": [],
        }

    # Get elements to find the one we need
    elements = await element_service.get_elements_by_category(
        category_id, is_active=True
    )
    element_by_code = {e["code"]: e for e in elements}

    code_upper = codigo_elemento.upper()
    if code_upper not in element_by_code:
        available_codes = ", ".join(sorted(element_by_code.keys()))
        return {
            "texto": (
                f"Elemento '{codigo_elemento}' no encontrado.\n"
                f"Códigos válidos: {available_codes}"
            ),
            "imagenes": [],
        }

    # Get element with images
    element = element_by_code[code_upper]
    element_details = await element_service.get_element_with_images(element["id"])

    if not element_details:
        return {
            "texto": f"No se encontró información para el elemento {code_upper}.",
            "imagenes": [],
        }

    lines = [
        f"DOCUMENTACION PARA {element_details['name'].upper()} ({code_upper}):",
        "",
    ]

    images = []

    if element_details.get("images"):
        required_docs = []
        example_docs = []

        for img in element_details["images"]:
            img_info = {
                "url": img["image_url"],
                "tipo": img["image_type"],
                "descripcion": img.get("description", img.get("title", "")),
            }

            if img.get("is_required"):
                required_docs.append(img)
            else:
                example_docs.append(img)

            images.append(img_info)

        if required_docs:
            lines.append("Documentos requeridos:")
            for doc in required_docs:
                lines.append(f"- {doc['title']}")
                if doc.get("description"):
                    lines.append(f"  {doc['description']}")
            lines.append("")

        if example_docs:
            lines.append("Fotos de ejemplo:")
            for doc in example_docs:
                lines.append(f"- {doc['title']}")
                if doc.get("description"):
                    lines.append(f"  {doc['description']}")
            lines.append("")
    else:
        lines.append("No hay documentacion especifica configurada para este elemento.")
        lines.append("Documentacion general requerida:")
        lines.append("- Foto del elemento con matricula visible")
        lines.append("- Certificado o placa del fabricante (si aplica)")

    # Get warnings for this element
    warnings = await element_service.get_element_warnings(element["id"])
    if warnings:
        lines.append("")
        lines.append("ADVERTENCIAS:")
        for w in warnings:
            lines.append(f"- {w['message']}")

    # Get base documentation for the category (always required)
    from agent.services.tarifa_service import get_tarifa_service

    tarifa_service = get_tarifa_service()
    category_data = await tarifa_service.get_category_data(categoria_vehiculo)

    if category_data and category_data.get("base_documentation"):
        lines.append("")
        lines.append("Documentacion base obligatoria:")
        for base_doc in category_data["base_documentation"]:
            lines.append(f"- {base_doc['description']}")
            if base_doc.get("image_url"):
                images.append(
                    {
                        "url": base_doc["image_url"],
                        "tipo": "base",  # Estandarizado para coincidir con condición en main.py
                        "descripcion": base_doc["description"],
                    }
                )

    return {
        "texto": "\n".join(lines),
        "imagenes": images,
    }


@tool
async def identificar_y_resolver_elementos(
    categoria_vehiculo: str,
    descripcion: str,
) -> dict[str, Any]:
    """
    Identifica elementos Y detecta variantes en UNA sola llamada.

    Esta herramienta CONSOLIDA las funciones de:
    - identificar_elementos()
    - verificar_si_tiene_variantes() para cada elemento

    Usa esta herramienta como PRIMER PASO cuando el usuario describe qué quiere homologar.
    Es más eficiente que llamar a identificar_elementos + verificar_si_tiene_variantes por separado.

    IMPORTANTE: Usa el slug de categoría correcto según el tipo de cliente:
    - "motos-part" para motocicletas de PARTICULARES
    - "motos-prof" para motocicletas de PROFESIONALES (si existe)
    - "aseicars-part" para autocaravanas de PARTICULARES
    - "aseicars-prof" para autocaravanas de PROFESIONALES

    El sufijo DEBE coincidir con el client_type del estado:
    - client_type="particular" → usa "-part"
    - client_type="professional" → usa "-prof"

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        descripcion: Descripción del usuario con elementos a homologar.
                    Ejemplo: "quiero homologar el escape y el manillar"

    Returns:
        JSON con:
        - elementos_listos: elementos SIN variantes (listos para calcular tarifa)
        - elementos_con_variantes: elementos QUE REQUIEREN clarificación del usuario
        - preguntas_variantes: preguntas a hacer al usuario para resolver variantes
        - terminos_no_reconocidos: términos que no coincidieron con ningún elemento

    Flujo simplificado:
    1. Llama a identificar_y_resolver_elementos()
       → Si hay elementos_con_variantes: pregunta al usuario y espera respuesta
       → Si todos están listos: llama a calcular_tarifa_con_elementos()
    2. Cuando el usuario responde sobre una variante:
       → Usa seleccionar_variante_por_respuesta() (NO vuelvas a llamar identificar_y_resolver_elementos)
    3. Una vez resueltas todas las variantes:
       → Llama a calcular_tarifa_con_elementos() con skip_validation=True
    """
    import json

    # Normalize category slug (LLM may send uppercase)
    categoria_vehiculo = categoria_vehiculo.lower().strip()

    # ═══════════════════════════════════════════════════════════════════
    # VALIDATION: Cross-check category suffix against client_type
    # Returns educational error if mismatch detected.
    # ═══════════════════════════════════════════════════════════════════
    state = get_current_state()
    client_type = state.get("client_type", "particular") if state else "particular"
    expected_suffix = "-part" if client_type == "particular" else "-prof"
    opposite_suffix = "-prof" if client_type == "particular" else "-part"

    if categoria_vehiculo.endswith(opposite_suffix):
        corrected_slug = categoria_vehiculo.replace(opposite_suffix, expected_suffix)

        # Verify corrected slug exists in DB before suggesting
        corrected_id = await get_or_fetch_category_id(corrected_slug)

        logger.warning(
            "category_client_type_mismatch",
            extra={
                "categoria_recibida": categoria_vehiculo,
                "client_type": client_type,
                "corrected_slug": corrected_slug if corrected_id else None,
            },
        )

        if corrected_id:
            return {
                "error": (
                    f"CATEGORÍA INCORRECTA: El cliente es '{client_type}', "
                    f"debes usar '{corrected_slug}' en lugar de '{categoria_vehiculo}'."
                ),
                "categoria_correcta": corrected_slug,
                "accion_requerida": (
                    f"Vuelve a llamar esta herramienta con "
                    f"categoria_vehiculo='{corrected_slug}'"
                ),
                "elementos_listos": [],
                "elementos_con_variantes": [],
                "_internal_flags": {
                    "precio_comunicado": False,
                    "imagenes_enviadas": False,
                    "waiting_for_image_choice": False,
                },
            }
    # ═══════════════════════════════════════════════════════════════════

    # Validate category slug for security
    try:
        validate_category_slug(categoria_vehiculo)
    except ValueError as e:
        logger.error(
            f"Invalid category slug rejected in identificar_y_resolver_elementos: {e}"
        )
        return {
            "error": str(e),
            "elementos_listos": [],
            "elementos_con_variantes": [],
        }

    element_service = get_element_service()
    tarifa_service = get_tarifa_service()

    # Get category ID from slug (cached)
    category_id = await get_or_fetch_category_id(categoria_vehiculo)
    if not category_id:
        # Build available_categories list filtered by client_type when possible.
        # client_type is already resolved from get_current_state() above.
        # Graceful degradation: if DB/cache fails, return empty list (no exception propagates)
        try:
            raw_categories = await tarifa_service.get_active_categories(
                client_type=client_type,
            )
            available_categories = [
                {"slug": c["slug"], "name": c["name"]} for c in raw_categories
            ]
        except Exception as _cat_err:
            logger.warning(
                "get_active_categories_failed_on_category_not_found",
                extra={"error": str(_cat_err), "categoria": categoria_vehiculo},
            )
            available_categories = []

        return {
            "error": "category_not_found",
            "categoria_usada": categoria_vehiculo,
            "available_categories": available_categories,
            "sugerencia": (
                "Usa listar_categorias() para ver todas las opciones disponibles "
                "o elige una de available_categories."
            ),
            "elementos_listos": [],
            "elementos_con_variantes": [],
        }

    # Get all elements for this category
    elements = await element_service.get_elements_by_category(
        category_id, is_active=True
    )
    if not elements:
        return {
            "error": f"No hay elementos configurados para la categoría '{categoria_vehiculo}'",
            "elementos_listos": [],
            "elementos_con_variantes": [],
        }

    # 1. NLP-based element identification
    identified_result = await element_service.match_elements_with_unmatched(
        description=descripcion,
        category_id=category_id,
        only_base_elements=True,
    )

    # Extract results from the returned dict
    # match_elements_with_unmatched returns:
    # {"matches": [(elem_dict, confidence), ...], "unmatched_terms": [...], ...}
    matches = identified_result.get("matches", [])
    matched_elements = [elem_dict for elem_dict, _confidence in matches]
    unmatched_terms = identified_result.get("unmatched_terms", [])
    # Note: ambiguous_candidates and quantities may not be in the response
    ambiguous_candidates = identified_result.get("ambiguous_candidates", [])
    quantities = identified_result.get("quantities", {})

    # Log identification results (Fase 2)
    logger.info(
        f"[identificar_y_resolver_elementos] Phase 2 - Element identification | category={categoria_vehiculo}",
        extra={
            "description_input": descripcion[:100],
            "matched_count": len(matched_elements),
            "matched_codes": [e.get("code") for e in matched_elements],
            "unmatched_terms": unmatched_terms,
        },
    )

    # 2. Check each matched element for variants
    elementos_listos = []
    elementos_con_variantes = []
    preguntas_variantes = []

    # Filter elements with valid codes
    valid_elements = [e for e in matched_elements if e.get("code")]

    # Gather 1: fetch all variant queries in parallel
    variant_coros = [
        element_service.get_element_variants(
            element_code=e["code"],
            category_id=category_id,
        )
        for e in valid_elements
    ]
    variant_results = (
        await asyncio.gather(*variant_coros, return_exceptions=True)
        if variant_coros
        else []
    )

    # Identify which elements have variants and need base element lookup
    elements_with_variants = []
    for elem, variants in zip(valid_elements, variant_results):
        if isinstance(variants, Exception):
            logger.warning(
                f"Variant fetch failed for {elem['code']}, treating as no-variants: {variants}"
            )
            elementos_listos.append(
                {
                    "codigo": elem["code"],
                    "nombre": elem.get("name"),
                    "cantidad": quantities.get(elem["code"], 1),
                }
            )
        elif variants:
            elements_with_variants.append((elem, variants))
        else:
            elementos_listos.append(
                {
                    "codigo": elem["code"],
                    "nombre": elem.get("name"),
                    "cantidad": quantities.get(elem["code"], 1),
                }
            )

    # Gather 2: fetch base elements for those with variants (need question_hint)
    if elements_with_variants:
        base_coros = [
            element_service.get_element_by_code(
                element_code=elem["code"],
                category_id=category_id,
            )
            for elem, _ in elements_with_variants
        ]
        base_results = await asyncio.gather(*base_coros, return_exceptions=True)

        for (elem, variants), base_element in zip(elements_with_variants, base_results):
            if isinstance(base_element, Exception):
                logger.warning(
                    f"Base element fetch failed for {elem['code']}: {base_element}"
                )
                base_element = None

            question_hint = (
                base_element.get("question_hint")
                if base_element and base_element.get("question_hint")
                else f"¿Qué tipo de {elem.get('name', elem['code']).lower()}?"
            )

            elementos_con_variantes.append(
                {
                    "codigo_base": elem["code"],
                    "nombre": elem.get("name"),
                    "variantes": [
                        {"codigo": v["code"], "nombre": v["name"]} for v in variants
                    ],
                }
            )
            preguntas_variantes.append(
                {
                    "codigo_base": elem["code"],
                    "pregunta": question_hint,
                    "opciones": [
                        f"{chr(64 + v['variant_position'])} - {v['name']}"
                        if v.get("variant_position") is not None
                        else v["name"]
                        for v in variants
                    ],
                }
            )

    # 3. Build response
    response = {
        "elementos_listos": elementos_listos,
        "elementos_con_variantes": elementos_con_variantes,
        "preguntas_variantes": preguntas_variantes,
        "terminos_no_reconocidos": unmatched_terms,
        "categoria_slug": categoria_vehiculo,
    }

    # Add instructions for LLM
    if elementos_con_variantes:
        response["instrucciones"] = (
            "DEBES preguntar al usuario SOLO sobre las variantes. "
            "Tu respuesta debe contener ÚNICAMENTE la(s) pregunta(s) de variantes. "
            "NO menciones documentación, imágenes, fotos de ejemplo ni información sobre elementos listos. "
            "Cuando el usuario responda, usa "
            "seleccionar_variante_por_respuesta() para obtener el código correcto."
        )
    elif elementos_listos and not unmatched_terms:
        response["instrucciones"] = (
            f"Todos los elementos están listos. Puedes calcular tarifa con: "
            f"calcular_tarifa_con_elementos('{categoria_vehiculo}', "
            f"{[e['codigo'] for e in elementos_listos]}, skip_validation=True)"
        )

    if ambiguous_candidates and len(ambiguous_candidates) > 1:
        response["ambiguedad"] = {
            "mensaje": "Múltiples elementos tienen puntuación similar. Pregunta al usuario cuál necesita.",
            "candidatos": [c["name"] for c in ambiguous_candidates],
        }

    # REFACTOR-001: Explicit flag reset on new identification
    # When user re-identifies elements, pricing state must reset
    # RC-3: Also reset imagenes_envio_intent_creado so image delivery
    # is unblocked after re-identification + variant resolution
    response["_internal_flags"] = {
        "precio_comunicado": False,
        "imagenes_enviadas": False,
        "waiting_for_image_choice": False,
        "imagenes_envio_intent_creado": False,
    }

    # Log detailed result for debugging (Fase 3)
    response_json = json.dumps(
        response, ensure_ascii=False, indent=2
    )  # keep for logging
    logger.info(
        f"[identificar_y_resolver_elementos] Result | category={categoria_vehiculo}",
        extra={
            "description_input": descripcion[:100],
            "elementos_listos_count": len(elementos_listos),
            "elementos_listos": [e["codigo"] for e in elementos_listos],
            "elementos_con_variantes_count": len(elementos_con_variantes),
            "elementos_con_variantes": [
                e["codigo_base"] for e in elementos_con_variantes
            ],
            "terminos_no_reconocidos": unmatched_terms,
            "tiene_instrucciones": "instrucciones" in response,
            "response_preview": response_json[:500]
            if len(response_json) > 500
            else response_json,
        },
    )

    return response  # return the dict, not the JSON string


# Export ONLY the tools we want the LLM to use
ELEMENT_TOOLS = [
    listar_elementos,
    identificar_y_resolver_elementos,  # Consolidated tool (replaces identificar + verificar)
    seleccionar_variante_por_respuesta,
    calcular_tarifa_con_elementos,
    obtener_documentacion_elemento,
]


def get_element_tools() -> list:
    """Get all element-related tools for the agent."""
    return ELEMENT_TOOLS


__all__ = [
    "listar_elementos",
    "identificar_y_resolver_elementos",
    "seleccionar_variante_por_respuesta",
    "calcular_tarifa_con_elementos",
    "obtener_documentacion_elemento",
    "get_element_tools",
    "ELEMENT_TOOLS",
    "get_or_fetch_category_id",
    "normalize_element_code",
    "normalize_element_codes",
]
