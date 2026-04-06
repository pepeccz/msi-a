"""
Variant Interpretation Service.

Interprets user responses to variant questions for multi-element quantity allocation.
Uses LLM extraction (local-first with cloud escalation) to parse natural language
responses like "2 delanteras y 1 trasera" into structured allocations.

This service is self-contained — it does not import from tools or modes.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

import structlog
from pydantic import BaseModel, Field, field_validator

from agent.state.conversation_state import PendingVariantGroup, VariantResolution
from shared.config import get_settings
from shared.llm_router import LLMResponse, ModelTier, TaskType, get_llm_router

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Response Schemas (Task 2.2)
# ---------------------------------------------------------------------------


class VariantAllocation(BaseModel):
    """A single allocation of quantity to a specific variant option."""

    variant_code: str = Field(
        ...,
        description="Must match one of the option codes/labels from the variant question.",
    )
    quantity: int = Field(
        ...,
        ge=1,
        description="How many units are assigned to this variant.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this allocation (0.0 = guess, 1.0 = certain).",
    )
    position: int | None = Field(
        None,
        ge=1,
        le=5,
        description=(
            "Ordinal position (1=A, 2=B…5=E) if user gave a positional reference. "
            "When set, DB lookup prefers variant_position over code string match."
        ),
    )


class VariantInterpretationResult(BaseModel):
    """Result of interpreting a user's variant allocation response."""

    allocations: list[VariantAllocation] = Field(default_factory=list)
    needs_clarification: bool = Field(
        False,
        description="True if the user's response could not be reliably interpreted.",
    )
    clarification_reason: str | None = Field(
        None,
        description="Human-readable reason why clarification is needed (in Spanish).",
    )
    raw_response: str | None = Field(
        None,
        description="Raw LLM response for debugging purposes.",
    )
    has_explicit_evidence: bool = Field(
        False,
        description=(
            "True only when the user's message contains specific words or phrases "
            "that clearly distinguish the chosen variant from the others."
        ),
    )

    @field_validator("allocations")
    @classmethod
    def allocations_must_have_items_unless_clarification(
        cls,
        v: list[VariantAllocation],
        info: Any,
    ) -> list[VariantAllocation]:
        """Allow empty allocations only when clarification is needed."""
        # info.data may not have 'needs_clarification' yet during construction,
        # so we validate at the model level instead.
        return v


# ---------------------------------------------------------------------------
# Extraction Prompt (Generic — no hardcoded element names)
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """Eres un extractor de datos. El usuario está respondiendo a una pregunta sobre variantes de un elemento de homologación vehicular.

PREGUNTA QUE SE LE HIZO:
{pregunta}

OPCIONES DISPONIBLES:
{opciones_formatted}

CANTIDAD TOTAL A ASIGNAR: {cantidad_pendiente}
{context_section}
RESPUESTA DEL USUARIO:
"{user_message}"

INSTRUCCIONES:
1. Interpreta la respuesta del usuario y determina cuántas unidades asigna a cada opción.
2. La suma de las cantidades DEBE ser exactamente {cantidad_pendiente}.
3. Si el usuario solo menciona UNA opción sin cantidad, asigna TODAS las {cantidad_pendiente} unidades a esa opción.
4. Si el usuario da cantidades parciales que no suman {cantidad_pendiente}, marca confidence baja.
5. Si la respuesta es ambigua o no se puede interpretar, indica que se necesita aclaración.
6. IMPORTANTE - Evalúa has_explicit_evidence:
   - true SOLO si el mensaje del usuario contiene palabras o frases específicas que distinguen claramente UNA opción de las demás.
   - Ejemplos de evidencia explícita: "oculto en armario" (distingue regulador oculto vs visible), "sin afectar al ancho" (distingue galibo vs no galibo).
   - NO es evidencia explícita: mencionar solo el nombre genérico del elemento (ej: "toldo", "placa solar"), ni asumir la opción más común, ni razonamiento estadístico o por defecto.
   - Si no hay evidencia explícita, has_explicit_evidence DEBE ser false aunque tengas alta confianza en cuál es la opción más probable.

Responde SOLO con JSON (sin markdown, sin ```):
{{"allocations": [{{"variant_code": "nombre_opcion", "quantity": N, "confidence": 0.0-1.0}}], "needs_clarification": false, "clarification_reason": null, "has_explicit_evidence": true}}

Si necesitas aclaración:
{{"allocations": [], "needs_clarification": true, "clarification_reason": "razón en español", "has_explicit_evidence": false}}"""


# ---------------------------------------------------------------------------
# Core Service Functions (Tasks 2.1, 2.3, 2.4)
# ---------------------------------------------------------------------------


async def interpret_variant_allocations(
    user_message: str,
    pending_variant: PendingVariantGroup,
    conversation_context: str | None = None,
) -> VariantInterpretationResult:
    """
    Interpret a user's natural language response to a variant question.

    Strategy:
    1. Try local extraction (TaskType.EXTRACTION → Tier 1 fast).
    2. If confidence < 0.6 OR parse/validation fails → escalate to cloud.
    3. If cloud also fails → return needs_clarification=True.

    Never loops more than once: local → cloud → clarification.

    Args:
        user_message: The user's raw message text.
        pending_variant: The pending variant group being resolved.
        conversation_context: Optional recent conversation context for disambiguation.

    Returns:
        VariantInterpretationResult with allocations or clarification request.
    """
    settings = get_settings()
    codigo_base = pending_variant.get("codigo_base", "UNKNOWN")
    cantidad_pendiente = pending_variant.get("cantidad_pendiente", 1)

    if not settings.ENABLE_LLM_VARIANT_INTERPRETATION:
        reason = "Interpretación automática de variantes desactivada por configuración"
        logger.info(
            "variant_interpretation_clarification_needed",
            element=codigo_base,
            reason=reason,
        )
        return VariantInterpretationResult(
            allocations=[],
            needs_clarification=True,
            clarification_reason=reason,
            raw_response=None,
        )

    router = get_llm_router()
    prompt = _build_extraction_prompt(user_message, pending_variant, conversation_context)

    messages = [{"role": "user", "content": prompt}]

    # --- Step 1: Local extraction (Tier 1 fast) ---
    logger.info(
        "variant_interpretation_started",
        element=codigo_base,
        quantity=cantidad_pendiente,
        local_cloud="local",
    )

    local_response = await router.invoke(
        task_type=TaskType.EXTRACTION,
        messages=messages,
        temperature=0.1,
        max_tokens=500,
    )

    if local_response.success:
        result = _parse_llm_response(local_response, pending_variant)
        if result is not None and not result.needs_clarification:
            # Validate allocations against pending state
            _, errors = validate_and_apply_allocations(
                pending_variant,
                result.allocations,
                dry_run=True,
            )
            avg_confidence = _average_confidence(result.allocations)

            if not errors and avg_confidence >= 0.6:
                # Evidence gate: if the LLM resolved with high confidence but
                # without explicit user evidence, force clarification instead
                # of silently auto-resolving based on statistical priors.
                if not result.has_explicit_evidence:
                    logger.warning(
                        "variant_interpretation_no_explicit_evidence",
                        codigo_base=codigo_base,
                        avg_confidence=round(avg_confidence, 2),
                        tier=local_response.tier.value,
                        raw_response=result.raw_response[:200] if result.raw_response else None,
                    )
                    return VariantInterpretationResult(
                        allocations=[],
                        needs_clarification=True,
                        clarification_reason=(
                            "El mensaje del usuario no contiene información "
                            "específica para distinguir entre las opciones disponibles."
                        ),
                        raw_response=result.raw_response,
                        has_explicit_evidence=False,
                    )

                logger.info(
                    "variant_interpretation_local_success",
                    codigo_base=codigo_base,
                    allocations_count=len(result.allocations),
                    avg_confidence=round(avg_confidence, 2),
                    tier=local_response.tier.value,
                )
                logger.info(
                    "variant_interpretation_completed",
                    element=codigo_base,
                    allocations_count=len(result.allocations),
                    confidence_avg=round(avg_confidence, 2),
                    turns_to_complete=1,
                )
                return result

            # Low confidence or validation errors → escalate
            escalation_reason = (
                f"validation_errors={errors}" if errors
                else f"low_confidence={avg_confidence:.2f}"
            )
            logger.info(
                "variant_interpretation_escalated",
                element=codigo_base,
                reason=escalation_reason,
                from_tier=local_response.tier.value,
                to_tier=ModelTier.CLOUD_STANDARD.value,
            )
        elif result is not None and result.needs_clarification:
            # Local LLM explicitly says it needs clarification — still try cloud
            logger.info(
                "variant_interpretation_local_needs_clarification",
                codigo_base=codigo_base,
                reason=result.clarification_reason,
            )
        else:
            logger.warning(
                "variant_interpretation_local_parse_failed",
                codigo_base=codigo_base,
                raw_content=local_response.content[:200],
            )
    else:
        logger.warning(
            "variant_interpretation_local_call_failed",
            codigo_base=codigo_base,
            error=local_response.error,
        )

    # --- Step 2: Cloud escalation (Tier 3) ---
    logger.info(
        "variant_interpretation_started",
        element=codigo_base,
        quantity=cantidad_pendiente,
        local_cloud="cloud",
    )

    cloud_response = await router.invoke(
        task_type=TaskType.EXTRACTION,
        messages=messages,
        temperature=0.1,
        max_tokens=500,
        force_tier=ModelTier.CLOUD_STANDARD,
    )

    if cloud_response.success:
        result = _parse_llm_response(cloud_response, pending_variant)
        if result is not None and not result.needs_clarification:
            _, errors = validate_and_apply_allocations(
                pending_variant,
                result.allocations,
                dry_run=True,
            )
            if not errors:
                avg_confidence = _average_confidence(result.allocations)
                if avg_confidence < 0.6:
                    logger.warning(
                        "variant_interpretation_cloud_low_confidence",
                        codigo_base=codigo_base,
                        avg_confidence=round(avg_confidence, 2),
                        tier=cloud_response.tier.value,
                    )
                    return VariantInterpretationResult(
                        allocations=[],
                        needs_clarification=True,
                        clarification_reason=(
                            "La interpretación automática no tiene suficiente "
                            "certeza. Pregunta al usuario de forma más específica."
                        ),
                        raw_response=cloud_response.content,
                        has_explicit_evidence=False,
                    )
                # Evidence gate (same as local path)
                if not result.has_explicit_evidence:
                    logger.warning(
                        "variant_interpretation_no_explicit_evidence",
                        codigo_base=codigo_base,
                        avg_confidence=round(avg_confidence, 2),
                        tier=cloud_response.tier.value,
                        raw_response=result.raw_response[:200] if result.raw_response else None,
                    )
                    return VariantInterpretationResult(
                        allocations=[],
                        needs_clarification=True,
                        clarification_reason=(
                            "El mensaje del usuario no contiene información "
                            "específica para distinguir entre las opciones disponibles."
                        ),
                        raw_response=result.raw_response,
                        has_explicit_evidence=False,
                    )

                logger.info(
                    "variant_interpretation_cloud_success",
                    codigo_base=codigo_base,
                    allocations_count=len(result.allocations),
                    avg_confidence=round(avg_confidence, 2),
                    tier=cloud_response.tier.value,
                )
                logger.info(
                    "variant_interpretation_completed",
                    element=codigo_base,
                    allocations_count=len(result.allocations),
                    confidence_avg=round(avg_confidence, 2),
                    turns_to_complete=2,
                )
                return result

            logger.warning(
                "variant_interpretation_cloud_validation_failed",
                codigo_base=codigo_base,
                errors=errors,
            )
        elif result is not None and result.needs_clarification:
            reason = result.clarification_reason or "LLM requested clarification"
            logger.info(
                "variant_interpretation_clarification_needed",
                element=codigo_base,
                reason=reason,
            )
            return result

    # --- Step 3: Give up → clarification ---
    final_reason = (
        "No he podido interpretar tu respuesta. "
        "Por favor, indica cuántas unidades quieres de cada opción "
        f"({', '.join(pending_variant.get('opciones', []))})."
    )
    logger.info(
        "variant_interpretation_clarification_needed",
        element=codigo_base,
        reason=final_reason,
    )
    logger.warning(
        "variant_interpretation_failed_needs_clarification",
        codigo_base=codigo_base,
        user_message=user_message[:100],
    )

    return VariantInterpretationResult(
        allocations=[],
        needs_clarification=True,
        clarification_reason=final_reason,
        raw_response=cloud_response.content if cloud_response.success else None,
    )


def validate_and_apply_allocations(
    pending: PendingVariantGroup,
    allocations: list[VariantAllocation],
    *,
    dry_run: bool = False,
    option_to_code_map: dict[str, str] | None = None,
) -> tuple[PendingVariantGroup, list[str]]:
    """
    Validate allocations against pending state and optionally apply them.

    Validation rules:
    - Sum of allocation quantities must equal cantidad_pendiente.
    - Each variant_code must match an option in pending.opciones (fuzzy).
    - No duplicate variant_codes.

    If valid and dry_run=False:
    - Append to resoluciones.
    - Recalculate cantidad_resuelta, cantidad_pendiente, status.

    If invalid: return errors and do NOT modify pending state.

    Args:
        pending: The pending variant group to validate against.
        allocations: List of allocations to validate/apply.
        dry_run: If True, only validate without modifying pending.
        option_to_code_map: Maps option text to element code for storage.

    Returns:
        Tuple of (updated_or_original pending group, list of error strings).
    """
    errors: list[str] = []
    cantidad_pendiente = pending.get("cantidad_pendiente", 1)
    opciones = pending.get("opciones", [])

    if not allocations:
        errors.append("No allocations provided.")
        return pending, errors

    # Check for duplicate variant_codes
    codes_seen: set[str] = set()
    for alloc in allocations:
        code_lower = alloc.variant_code.lower().strip()
        if code_lower in codes_seen:
            errors.append(f"Duplicate variant_code: '{alloc.variant_code}'.")
        codes_seen.add(code_lower)

    # Validate each allocation against opciones
    resolved_codes: list[tuple[VariantAllocation, str]] = []
    for alloc in allocations:
        matched_option = _fuzzy_match_option(alloc.variant_code, opciones)
        if matched_option is None:
            errors.append(
                f"variant_code '{alloc.variant_code}' does not match any option: {opciones}."
            )
        else:
            resolved_codes.append((alloc, matched_option))

    # Validate quantity sum
    total_allocated = sum(a.quantity for a in allocations)
    allow_sequential_single_unit = (
        total_allocated < cantidad_pendiente
        and len(allocations) == 1
        and allocations[0].quantity == 1
    )

    if total_allocated != cantidad_pendiente and not allow_sequential_single_unit:
        errors.append(
            f"Sum of quantities ({total_allocated}) != cantidad_pendiente ({cantidad_pendiente})."
        )

    if errors:
        return pending, errors

    # --- Apply allocations ---
    if dry_run:
        return pending, []

    # Build updated pending group (immutable pattern — return new dict)
    existing_resoluciones: list[VariantResolution] = list(
        pending.get("resoluciones", [])
    )
    for alloc, matched_option in resolved_codes:
        stored_code = matched_option
        if option_to_code_map:
            stored_code = option_to_code_map.get(matched_option, matched_option)
        existing_resoluciones.append(
            VariantResolution(
                variant_code=stored_code,
                quantity=alloc.quantity,
                confidence=alloc.confidence,
                source="user_explicit",
            )
        )

    nueva_resuelta = pending.get("cantidad_resuelta", 0) + total_allocated
    nueva_total = pending.get("cantidad_total", 1)
    nueva_pendiente = nueva_total - nueva_resuelta

    if nueva_resuelta >= nueva_total:
        new_status = "resolved"
    elif nueva_resuelta > 0:
        new_status = "partial"
    else:
        new_status = "pending"

    updated = PendingVariantGroup(
        pending_id=pending.get("pending_id", "UNKNOWN"),
        codigo_base=pending.get("codigo_base", "UNKNOWN"),
        pregunta=pending.get("pregunta", ""),
        opciones=opciones,
        cantidad_total=nueva_total,
        cantidad_resuelta=nueva_resuelta,
        cantidad_pendiente=nueva_pendiente,
        resoluciones=existing_resoluciones,
        status=new_status,
    )

    logger.info(
        "variant_allocations_applied",
        pending_id=updated.get("pending_id"),
        codigo_base=updated.get("codigo_base"),
        cantidad_resuelta=nueva_resuelta,
        cantidad_pendiente=nueva_pendiente,
        status=new_status,
    )

    return updated, []


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------


def _build_extraction_prompt(
    user_message: str,
    pending_variant: PendingVariantGroup,
    conversation_context: str | None,
) -> str:
    """Build the extraction prompt from the pending variant state."""
    opciones = pending_variant.get("opciones", [])
    opciones_formatted = "\n".join(f"  - {opt}" for opt in opciones)

    context_section = ""
    if conversation_context:
        context_section = f"CONTEXTO DE LA CONVERSACIÓN:\n{conversation_context[:500]}\n\n"

    return _EXTRACTION_PROMPT.format(
        pregunta=pending_variant.get("pregunta", ""),
        opciones_formatted=opciones_formatted,
        cantidad_pendiente=pending_variant.get("cantidad_pendiente", 1),
        context_section=context_section,
        user_message=user_message,
    )


def _parse_llm_response(
    response: LLMResponse,
    pending_variant: PendingVariantGroup,
) -> VariantInterpretationResult | None:
    """
    Parse the LLM response into a VariantInterpretationResult.

    Handles common LLM output quirks: markdown fences, trailing commas, etc.

    Args:
        response: The raw LLM response.
        pending_variant: The pending variant (for context in error messages).

    Returns:
        Parsed result or None if parsing fails completely.
    """
    content = response.content.strip()

    # Strip markdown code fences if present
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first line (```json or ```) and last line (```)
        end_idx = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end_idx = i
                break
        content = "\n".join(lines[1:end_idx]).strip()
        # Remove optional "json" prefix on first line
        if content.startswith("json"):
            content = content[4:].strip()

    # Remove trailing commas before closing braces/brackets (common LLM mistake)
    content = re.sub(r",\s*([\]}])", r"\1", content)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning(
            "variant_interpretation_json_parse_failed",
            codigo_base=pending_variant.get("codigo_base"),
            error=str(e),
            raw_content=content[:300],
        )
        return None

    # Extract evidence flag (default False if missing or non-boolean)
    raw_evidence = data.get("has_explicit_evidence")
    has_explicit_evidence = bool(raw_evidence) if isinstance(raw_evidence, bool) else False

    # Handle the case where LLM returns needs_clarification
    if data.get("needs_clarification"):
        return VariantInterpretationResult(
            allocations=[],
            needs_clarification=True,
            clarification_reason=data.get("clarification_reason"),
            raw_response=content,
            has_explicit_evidence=has_explicit_evidence,
        )

    # Parse allocations
    raw_allocations = data.get("allocations", [])
    if not isinstance(raw_allocations, list):
        logger.warning(
            "variant_interpretation_invalid_allocations_type",
            codigo_base=pending_variant.get("codigo_base"),
            type_received=type(raw_allocations).__name__,
        )
        return None

    # Guard: reject any allocation with quantity <= 0 before Pydantic construction.
    # This catches LLMs that return 0 or 0.0 for a variant they couldn't resolve
    # (a known failure pattern). Treat as parsing failure so the caller escalates
    # to cloud or requests clarification rather than silently accepting bad data.
    for raw_alloc in raw_allocations:
        if not isinstance(raw_alloc, dict):
            continue
        raw_qty = raw_alloc.get("quantity")
        try:
            qty_value = float(raw_qty) if raw_qty is not None else 0.0
        except (ValueError, TypeError):
            qty_value = 0.0
        if qty_value <= 0:
            logger.warning(
                "variant_allocation_invalid_quantity",
                codigo_base=pending_variant.get("codigo_base"),
                variant_code=raw_alloc.get("variant_code"),
                quantity=raw_qty,
                reason="quantity must be > 0; treating as parse failure",
            )
            return None

    try:
        allocations = [
            VariantAllocation(
                variant_code=str(a.get("variant_code", "")),
                quantity=int(a.get("quantity", 0)),
                confidence=float(a.get("confidence", 0.5)),
            )
            for a in raw_allocations
            if isinstance(a, dict)
        ]
    except (ValueError, TypeError) as e:
        logger.warning(
            "variant_interpretation_allocation_parse_error",
            codigo_base=pending_variant.get("codigo_base"),
            error=str(e),
        )
        return None

    if not allocations:
        return None

    return VariantInterpretationResult(
        allocations=allocations,
        needs_clarification=False,
        clarification_reason=None,
        raw_response=content,
        has_explicit_evidence=has_explicit_evidence,
    )


def _fuzzy_match_option(variant_code: str, opciones: list[str]) -> str | None:
    """
    Match a variant_code against the available options using fuzzy matching.

    Tries (in order):
    1. Exact match (case-insensitive).
    2. Substring containment (either direction).
    3. Normalized comparison (strip accents, lowercase).

    Args:
        variant_code: The code from the LLM allocation.
        opciones: Available option strings.

    Returns:
        The matched option string, or None if no match.
    """
    code_lower = variant_code.lower().strip()
    code_normalized = _normalize_text(code_lower)

    for opcion in opciones:
        opcion_lower = opcion.lower().strip()
        opcion_normalized = _normalize_text(opcion_lower)

        # Exact match
        if code_lower == opcion_lower or code_normalized == opcion_normalized:
            return opcion

        # Substring containment (either direction)
        if code_normalized in opcion_normalized or opcion_normalized in code_normalized:
            return opcion

    return None


def _normalize_text(text: str) -> str:
    """Strip accents and normalize text for comparison."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _average_confidence(allocations: list[VariantAllocation]) -> float:
    """Calculate the average confidence across allocations."""
    if not allocations:
        return 0.0
    return sum(a.confidence for a in allocations) / len(allocations)


# ---------------------------------------------------------------------------
# Variant selection helpers (moved from agent/tools/element_tools.py — T2.2b)
#
# These helpers are pure (no side-effects, no LLM calls) and operate on
# variant data + user text.  Moving them here keeps element_tools.py thin
# and collocates all variant-resolution logic in one place.
# ---------------------------------------------------------------------------

# Positional letter regex: matches "b", "opción b", "la b", "b.", etc.
_POSITIONAL_LETTER_RE = re.compile(
    r"^\s*(?:(?:la\s+|el\s+)?opci[oó]n\s+|la\s+|el\s+)?([a-eA-E])[.):\s]*$",
    re.IGNORECASE,
)

# Matches a bare single positional letter "a"-"e"
_BARE_LETTER_RE = re.compile(r"^[a-eA-E]$")

# Domain vocabulary for bare-letter confidence gate (REQ-3).
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
_ALL_DOMAIN_VOCABULARY: frozenset[str] = frozenset(
    _GALIBO_VOCABULARY + _REGULADOR_VOCABULARY
)

# Phase 4: Early ambiguity exit threshold (ADR-006)
AMBIGUITY_THRESHOLD = 0.3

# Clause-splitting pattern for combined user responses
_CLAUSE_SPLIT_RE = re.compile(
    r"\s*(?:y\s+(?:el|la|los|las)\s+|y\s+|,\s*|;\s*|/\s*)",
    re.IGNORECASE,
)

# Stop-words for anchor computation
_ANCHOR_STOP_WORDS = frozenset(
    {"de", "del", "el", "la", "los", "las", "un", "una", "y", "con", "para"}
)

# Minimum anchor score for clause matching
_FRAGMENT_MIN_SCORE = 0.25


def has_domain_vocabulary_from_variants(
    user_input: str, variant_options: list[dict]
) -> bool:
    """
    Return True if *user_input* contains vocabulary specific to any variant option.

    Derives domain words dynamically from variant keywords and names (>3 chars).
    Used by the early-ambiguity-exit gate (Phase 4).
    """
    if not variant_options:
        return False

    def _strip(text: str) -> str:
        nfkd = unicodedata.normalize("NFD", text.lower())
        return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")

    domain_words: set[str] = set()
    for v in variant_options:
        for kw in v.get("keywords", []):
            for word in _strip(kw).split():
                if len(word) > 3:
                    domain_words.add(word)
        for word in _strip(v.get("name", "")).split():
            if len(word) > 3:
                domain_words.add(word)

    normalized_input = _strip(user_input)
    return any(w in normalized_input for w in domain_words)


# Backward-compat private alias (used by tests that import the private name)
_has_domain_vocabulary_from_variants = has_domain_vocabulary_from_variants


def has_domain_vocabulary(fragment: str) -> bool:
    """
    Return True if *fragment* contains at least one static domain vocabulary token.

    Used by the bare-letter confidence gate (REQ-3): if the user's message
    contains a domain keyword like "gálibo" or "oculto", bare-letter mapping
    is trusted even with avg_confidence < 0.3.
    """
    def _strip(text: str) -> str:
        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()

    normalized = _strip(fragment)
    return any(_strip(token) in normalized for token in _ALL_DOMAIN_VOCABULARY)


# Backward-compat private alias
_has_domain_vocabulary = has_domain_vocabulary


def normalize_to_canonical_letter(response: str) -> str | None:
    """
    Extract canonical positional letter from decorated user responses.

    Matches: "b", "B", "opción b", "la b", "b.", "b)" etc.
    Returns: lowercase letter "a"-"e", or None.
    """
    m = _POSITIONAL_LETTER_RE.match(response.strip())
    return m.group(1).lower() if m else None


# Backward-compat private alias
_normalize_to_canonical_letter = normalize_to_canonical_letter


def extract_positional_letters(respuesta: str) -> list[str] | None:
    """
    Detect pure multi-letter positional responses like "B y A", "a, b".

    Returns a list of lowercase letters if the entire response is N letters
    separated by conjunctions/commas.  Returns None for single-letter or
    semantic responses.
    """
    stripped = respuesta.strip()
    if not re.search(r"[,;]|\s+(?:y|and)\s+|\s", stripped):
        return None

    candidate = re.sub(r"\s*(?:y|and)\s*|[,;]\s*|\s+", " ", stripped.lower()).strip()
    tokens = candidate.split()

    if not tokens:
        return None
    if not all(len(t) == 1 and t.isalpha() for t in tokens):
        return None
    if len(tokens) < 2:
        return None

    return tokens


# Backward-compat private alias
_extract_positional_letters = extract_positional_letters


def build_element_anchors(
    codigo_elemento_base: str,
    base_element: dict[str, Any] | None,
    current_pending: "PendingVariantGroup | None",
    variants: list[dict[str, Any]],
) -> list[str]:
    """
    Build anchor words from element code, name, and pending question text.

    Used by _extract_element_fragment to score clauses in combined responses.
    """
    from agent.utils.text_utils import normalize_text

    anchors: list[str] = []

    code_words = [
        w
        for w in normalize_text(codigo_elemento_base.replace("_", " ")).split()
        if w not in _ANCHOR_STOP_WORDS and len(w) > 2
    ]
    if code_words:
        anchors.append(" ".join(code_words))
        for w in code_words:
            if len(w) > 3:
                anchors.append(w)

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

    if current_pending:
        pregunta = current_pending.get("pregunta", "")
        if pregunta:
            q_words = [
                w
                for w in normalize_text(pregunta).split()
                if w not in _ANCHOR_STOP_WORDS and len(w) > 3
            ]
            for w in q_words[:5]:
                anchors.append(w)

    seen: set[str] = set()
    unique: list[str] = []
    for a in anchors:
        if a not in seen:
            seen.add(a)
            unique.append(a)
    return unique


# Backward-compat private alias
_build_element_anchors = build_element_anchors


def score_clause_for_element(clause: str, anchors: list[str]) -> float:
    """Score how relevant a normalized clause is to the element anchors (0.0–1.0)."""
    from agent.utils.text_utils import normalize_text

    clause_norm = normalize_text(clause)
    if not clause_norm:
        return 0.0

    score = 0.0
    for anchor in anchors:
        if anchor in clause_norm:
            score += 0.3 + 0.1 * min(len(anchor.split()), 3)
        else:
            anchor_words = set(anchor.split())
            clause_words = set(clause_norm.split())
            overlap = anchor_words & clause_words
            if overlap:
                score += 0.15 * (len(overlap) / len(anchor_words))

    return min(score, 1.0)


# Backward-compat private alias
_score_clause_for_element = score_clause_for_element


def extract_element_fragment(
    respuesta: str,
    codigo_elemento_base: str,
    base_element: dict[str, Any] | None,
    current_pending: "PendingVariantGroup | None",
    variants: list[dict[str, Any]],
    current_pending_idx: int = -1,
    total_pending_count: int = 0,
) -> str:
    """
    Extract the clause from a combined user response relevant to the current element.

    Example: "placa solar opcion b y el toldo A" while resolving PLACA_SOLAR
    returns "placa solar opcion b".

    Algorithm:
    0. Detect pure positional multi-letter responses and assign per index.
    1. Split on conjunctions/punctuation.
    2. If only one clause, return original.
    3. Score each clause against element anchors.
    4. Return the highest-scoring clause above _FRAGMENT_MIN_SCORE.
    5. Fallback: return the full original response.
    """
    respuesta_stripped = respuesta.strip()

    # Phase 0: pure positional multi-letter (e.g. "B y A")
    if current_pending_idx >= 0 and total_pending_count >= 2:
        letters = extract_positional_letters(respuesta_stripped)
        if letters is not None and len(letters) == total_pending_count:
            if current_pending_idx < len(letters):
                return letters[current_pending_idx]

    clauses = _CLAUSE_SPLIT_RE.split(respuesta_stripped)
    clauses = [c.strip() for c in clauses if c.strip()]

    if len(clauses) <= 1:
        return respuesta_stripped

    anchors = build_element_anchors(
        codigo_elemento_base, base_element, current_pending, variants
    )
    if not anchors:
        return respuesta_stripped

    best_clause = respuesta_stripped
    best_score = 0.0
    for clause in clauses:
        s = score_clause_for_element(clause, anchors)
        if s > best_score:
            best_score = s
            best_clause = clause

    if best_score < _FRAGMENT_MIN_SCORE:
        return respuesta_stripped

    return best_clause


# Backward-compat private alias
_extract_element_fragment = extract_element_fragment


def build_single_variant_result(
    variant: dict[str, Any],
    codigo_elemento_base: str,
    confidence: float,
    match_method: str,
) -> dict[str, Any]:
    """
    Build the standard single-variant selection result dict.

    Backward-compatible output shape for calcular_tarifa_con_elementos callers.
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


# Backward-compat private alias
_build_single_variant_result = build_single_variant_result


def apply_single_resolution_to_pending(
    result: dict[str, Any],
    matched_variant: dict[str, Any],
    current_pending: "PendingVariantGroup | None",
    current_pending_idx: int,
    normalized_pending: "list[PendingVariantGroup]",
) -> dict[str, Any]:
    """
    Apply a single-unit resolution to the pending_variants state.

    Updates the matching pending entry and injects _state_update into the result.
    """
    if current_pending is None or current_pending_idx < 0:
        return result

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

    new_pending_list = list(normalized_pending)
    new_pending_list[current_pending_idx] = updated_entry

    unresolved_count = sum(
        1 for pv in new_pending_list if pv.get("status") != "resolved"
    )

    result["resolution_status"] = new_status
    result["pending_count"] = unresolved_count
    result["_state_update"] = {
        "pending_variants": [dict(pv) for pv in new_pending_list],
    }

    return result


# Backward-compat private alias
_apply_single_resolution_to_pending = apply_single_resolution_to_pending
