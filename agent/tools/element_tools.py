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

import logging
import unicodedata
from typing import Any

from langchain_core.tools import tool

from agent.services.element_service import get_element_service
from agent.services.tarifa_service import get_tarifa_service
from agent.state.helpers import get_current_state
from agent.utils.validation import validate_category_slug
from database.connection import get_async_session
from database.models import VehicleCategory

logger = logging.getLogger(__name__)

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
                "Category ID cache hit",
                extra={"category_slug": category_slug}
            )
            # Handle both str (decode_responses=True) and bytes (decode_responses=False)
            if isinstance(cached, bytes):
                return cached.decode('utf-8')
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
                extra={"category_slug": category_slug}
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
                "error": str(e)
            }
        )
        return None
    except Exception as e:
        logger.error(
            "Unexpected error fetching category by slug",
            exc_info=True,
            extra={
                "category_slug": category_slug,
                "error_type": type(e).__name__
            }
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
            extra={"original": code, "corrected": with_s}
        )
        return with_s, True
    
    # 3. Try removing 'S' (plural → singular): ESCAPESS → ESCAPES edge case
    if normalized.endswith("S") and len(normalized) > 1:
        without_s = normalized[:-1]
        if without_s in valid_codes:
            logger.info(
                f"[normalize_element_code] Auto-corrected '{code}' → '{without_s}' (removed S)",
                extra={"original": code, "corrected": without_s}
            )
            return without_s, True
    
    # 4. Try adding 'ES' for words ending in consonant: MOTOR → MOTORES
    if not normalized.endswith(("A", "E", "I", "O", "U", "S")):
        with_es = normalized + "ES"
        if with_es in valid_codes:
            logger.info(
                f"[normalize_element_code] Auto-corrected '{code}' → '{with_es}' (added ES)",
                extra={"original": code, "corrected": with_es}
            )
            return with_es, True
    
    return None, False


def normalize_element_codes(
    codes: list[str], 
    valid_codes: set[str]
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
    category = next(
        (c for c in categories if c["slug"] == categoria_vehiculo),
        None
    )

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
                parent_elements_rejected.append({
                    "code": code_upper,
                    "name": elem["name"],
                    "children": [{"code": c["code"], "name": c["name"]} for c in children],
                    "question_hint": elem.get("question_hint") or f"¿Qué tipo de {elem['name'].lower()}?",
                })
                continue  # DO NOT add to valid_elements

            valid_elements.append(elem)

            # Check confidence if provided
            if confianzas:
                conf = confianzas.get(code_upper) or confianzas.get(code)
                if conf is not None and conf < CONFIDENCE_THRESHOLD:
                    low_confidence.append({
                        "code": code_upper,
                        "name": elem["name"],
                        "confidence": conf
                    })
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
        lines.append("IMPORTANTE: Los elementos padre NO son homologables directamente.")
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
        lines.append(f'  "Sobre {low_confidence[0]["name"].lower()}, ¿podrías confirmarme exactamente qué modificación has hecho?"')
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
async def listar_elementos(categoria_vehiculo: str) -> str:
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
        return f"Error: {str(e)}"
    
    element_service = get_element_service()

    # Get category ID from slug (cached)
    category_id = await get_or_fetch_category_id(categoria_vehiculo)
    if not category_id:
        tarifa_service = get_tarifa_service()
        categories = await tarifa_service.get_active_categories()
        available = ", ".join(c["slug"] for c in categories)
        return f"Categoría '{categoria_vehiculo}' no encontrada. Categorías disponibles: {available}"

    # Get elements for category
    elements = await element_service.get_elements_by_category(category_id, is_active=True)

    if not elements:
        return f"No hay elementos configurados para la categoría '{categoria_vehiculo}'."

    lines = [
        f"ELEMENTOS HOMOLOGABLES PARA {categoria_vehiculo.upper()}:",
        "",
    ]

    for elem in elements:
        lines.append(f"- {elem['name']}")

    lines.append("")
    lines.append(f"Total: {len(elements)} elementos disponibles.")

    return "\n".join(lines)


@tool
async def seleccionar_variante_por_respuesta(
    categoria_vehiculo: str,
    codigo_elemento_base: str,
    respuesta_usuario: str,
) -> str:
    """
    Mapea la respuesta del usuario a un código de variante específico.

    USA ESTA TOOL después de preguntar al usuario sobre la variante que necesita.
    La herramienta analiza la respuesta y determina qué variante corresponde.

    Soporta MULTI-SELECCIÓN: Si el usuario responde "ambos", "todos", "los dos", etc.,
    y el elemento base tiene configurado multi_select_keywords, retorna TODAS las variantes.

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        codigo_elemento_base: Código del elemento base (ej: "BOLA_REMOLQUE")
        respuesta_usuario: Texto de respuesta del usuario (ej: "sí, aumenta MMR", "ambos", "delantera")

    Returns:
        JSON con UNO de estos formatos:

        Selección única:
        {"selected_variant": "BOLA_CON_MMR", "confidence": 0.95, "name": "..."}

        Multi-selección (usuario quiere todas):
        {"selected_variants": ["INTERMITENTES_DEL", "INTERMITENTES_TRAS"], "mode": "multi_select", "names": [...]}

    Si confidence < 0.7, pregunta al usuario de forma más específica.
    """
    import json

    # Normalize category slug (LLM may send uppercase)
    categoria_vehiculo = categoria_vehiculo.lower().strip()
    
    # Validate category slug for security
    try:
        validate_category_slug(categoria_vehiculo)
    except ValueError as e:
        logger.error(f"Invalid category slug rejected in seleccionar_variante_por_respuesta: {e}")
        return json.dumps({
            "error": str(e)
        }, ensure_ascii=False)

    element_service = get_element_service()

    # Get category ID from slug (cached)
    category_id = await get_or_fetch_category_id(categoria_vehiculo)
    if not category_id:
        return json.dumps({
            "error": f"Categoría '{categoria_vehiculo}' no encontrada"
        }, ensure_ascii=False)

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
        all_elements = await element_service.get_elements_by_category(category_id, is_active=True)
        
        # Normalize search term
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
            if search_term in elem_name_normalized or elem_name_normalized in search_term:
                best_match_elem = elem
                break
            if search_term in elem_code_normalized:
                best_match_elem = elem
                break
        
        if best_match_elem:
            # Log the correction
            logger.info(
                f"[seleccionar_variante] Fuzzy match: '{codigo_elemento_base}' -> '{best_match_elem['code']}'",
                extra={"original": codigo_elemento_base, "matched": best_match_elem['code']}
            )
            codigo_normalizado = best_match_elem['code']
            # Try getting variants again with corrected code
            variants = await element_service.get_element_variants(
                element_code=codigo_normalizado,
                category_id=category_id,
            )
    
    if not variants:
        # Still no variants - return helpful error
        all_elements = await element_service.get_elements_by_category(category_id, is_active=True)
        base_elements = [e for e in all_elements if not e.get("parent_element_id")]
        available_codes = ", ".join(e["code"] for e in base_elements[:10])
        return json.dumps({
            "error": f"No se encontraron variantes para '{codigo_elemento_base}'",
            "hint": f"Elementos base disponibles: {available_codes}",
            "instrucciones": "Verifica que el código sea correcto. Usa identificar_y_resolver_elementos para obtener los códigos."
        }, ensure_ascii=False)

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
    multi_select_kw = base_element.get("multi_select_keywords", []) if base_element else []

    if multi_select_kw:
        for kw in multi_select_kw:
            kw_normalized = normalize_text(kw)
            if kw_normalized in respuesta_normalized or respuesta_normalized in kw_normalized:
                # User wants ALL variants - return them all
                return json.dumps({
                    "selected_variants": [v["code"] for v in variants],
                    "mode": "multi_select",
                    "matched_keyword": kw,
                    "names": [v["name"] for v in variants],
                    "instrucciones": (
                        f"El usuario quiere TODAS las variantes. "
                        f"Usa todos los códigos: {[v['code'] for v in variants]} "
                        f"en calcular_tarifa_con_elementos."
                    ),
                }, ensure_ascii=False, indent=2)

    # === SINGLE VARIANT MATCHING (existing logic) ===
    # Match user response to variant using DATA-DRIVEN keywords
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
            # Full keyword match in response
            if kw_normalized in respuesta_normalized:
                score += 0.8
            # Partial word overlap for multi-word keywords
            elif " " in kw:
                kw_words = set(kw_normalized.split())
                resp_words = set(respuesta_normalized.split())
                overlap = len(kw_words & resp_words)
                if overlap > 0:
                    score += 0.4 * (overlap / len(kw_words))

        # === PHASE 2: Variant code matching (fallback) ===
        if variant_code_lower:
            variant_code_normalized = normalize_text(variant_code_lower.replace("_", " "))
            if variant_code_normalized in respuesta_normalized:
                score += 0.7

        # === PHASE 3: Name word overlap (secondary fallback) ===
        name_words = [w for w in normalize_text(variant_name_lower).split() if len(w) > 3]
        matching_words = sum(1 for word in name_words if word in respuesta_normalized)
        if matching_words > 0 and name_words:
            score += 0.3 * (matching_words / len(name_words))

        if score > best_score:
            best_score = score
            best_match = variant

    if not best_match or best_score < 0.5:
        available_options = [
            f"- {v['name']}" for v in variants
        ]
        return json.dumps({
            "error": "No se pudo determinar la variante con certeza.",
            "sugerencia": "Pregunta al usuario de forma más específica.",
            "opciones_disponibles": available_options,
        }, ensure_ascii=False, indent=2)

    return json.dumps({
        "selected_variant": best_match["code"],
        "confidence": round(best_score, 2),
        "name": best_match["name"],
        "variant_code": best_match.get("variant_code", ""),
        "instrucciones": (
            f"Usa el código '{best_match['code']}' en lugar de '{codigo_elemento_base}' "
            "para calcular_tarifa_con_elementos y validar_elementos."
        ) if best_score >= 0.7 else (
            "Confidence bajo. Pregunta al usuario para confirmar la selección."
        ),
    }, ensure_ascii=False, indent=2)


@tool
async def calcular_tarifa_con_elementos(
    categoria_vehiculo: str,
    codigos_elementos: list[str],
    skip_validation: bool = False,
) -> str:
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

    Returns:
        Tarifa seleccionada, precio, elementos incluidos y advertencias.
        Los precios son SIN IVA.
    """
    # Normalize category slug (LLM may send uppercase)
    categoria_vehiculo = categoria_vehiculo.lower().strip()
    
    # Validate category slug for security
    try:
        validate_category_slug(categoria_vehiculo)
    except ValueError as e:
        logger.error(f"Invalid category slug rejected in calcular_tarifa_con_elementos: {e}")
        return f"Error: {str(e)}"
    
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
            return (
                f"❌ ERROR: No puedo calcular tarifa con códigos inválidos.\n\n"
                f"{validation['message']}\n\n"
                f"Debes usar `identificar_elementos` primero para obtener códigos válidos."
            )
    # === FIN VALIDACIÓN ===

    # Log codes being used for tariff calculation
    logger.info(
        f"[calcular_tarifa] Calculating with validated codes | category={categoria_vehiculo}",
        extra={"codes": codigos_elementos}
    )

    # Get category ID from slug (cached)
    category_id = await get_or_fetch_category_id(categoria_vehiculo)
    if not category_id:
        categories = await tarifa_service.get_active_categories()
        available = ", ".join(c["slug"] for c in categories)
        return f"Categoría '{categoria_vehiculo}' no encontrada. Categorías disponibles: {available}"

    if not codigos_elementos:
        return "Error: Debes especificar al menos un código de elemento."

    # Get element details for each code
    elements = await element_service.get_elements_by_category(category_id, is_active=True)
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
            extra={"corrections": corrections, "category": categoria_vehiculo}
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
        return (
            f"Error: Códigos no encontrados: {', '.join(invalid_codes)}\n\n"
            f"Códigos válidos para {categoria_vehiculo}: {available_codes}\n\n"
            "Usa `identificar_elementos` para obtener los códigos correctos."
        )

    if not valid_elements:
        return "Error: No se encontraron elementos válidos."

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
        return f"Error: {result['error']}"

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
        }
    )

    # === DOCUMENTACIÓN E IMÁGENES ===
    # Get base documentation for the category
    category_data = await tarifa_service.get_category_data(categoria_vehiculo)
    base_documentation = []
    base_images = []
    
    if category_data and category_data.get("base_documentation"):
        for base_doc in category_data["base_documentation"]:
            base_documentation.append({
                "descripcion": base_doc["description"],
                "imagen_url": base_doc.get("image_url"),
            })
            if base_doc.get("image_url"):
                base_images.append({
                    "url": base_doc["image_url"],
                    "tipo": "base",
                    "descripcion": base_doc["description"],
                    "status": "active",  # BaseDocumentation images are admin-set
                })

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
                element_images.append({
                    "url": img["image_url"],
                    "tipo": img["image_type"],
                    "elemento": elem["name"],
                    "descripcion": img.get("description") or img.get("title", ""),
                    "status": img_status,
                })
        
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
            extra={"warnings": [w.get("code") for w in result["warnings"]]}
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
                        "🔴" if w.get("severity") == "error"
                        else "⚠️" if w.get("severity") == "warning"
                        else "ℹ️"
                    )
                    lines.append(f"    {severity_icon} {w['message']}")

        # Then: general warnings (rule-based, without element association)
        general_warnings = [
            w for w in result["warnings"] if not w.get("element_code")
        ]
        if general_warnings:
            if element_warnings_grouped:
                lines.append("\n  General:")
            for w in general_warnings:
                severity_icon = (
                    "🔴" if w.get("severity") == "error"
                    else "⚠️" if w.get("severity") == "warning"
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
                    desc = img.get("descripcion") or img.get("titulo") or "Foto del elemento"
                    lines.append(f"    - {desc}")
            else:
                lines.append(f"  {elem_doc['nombre']}: Foto del elemento con matricula visible")
        lines.append("")

    # User instructions for required documents (from DB, NOT to be invented)
    user_instructions = []
    for elem_doc in element_documentation:
        for img in elem_doc.get("imagenes", []):
            if img.get("requerida") and img.get("instruccion_usuario"):
                user_instructions.append({
                    "elemento": elem_doc["nombre"],
                    "instruccion": img["instruccion_usuario"],
                })

    if user_instructions:
        lines.append("INSTRUCCIONES PARA EL USUARIO (datos oficiales de la DB, NO inventes):")
        for instr in user_instructions:
            lines.append(f"  [{instr['elemento']}]: {instr['instruccion']}")
        lines.append("")
        lines.append("Cuando el usuario pregunte que fotos necesita, usa EXACTAMENTE estas instrucciones.")
        lines.append("")
    
    # Image count summary (only count active images)
    active_images = [
        img for img in (base_images + element_images)
        if img.get("status") == "active"
    ]
    active_base_images = [img for img in base_images if img.get("status") == "active"]
    active_element_images = [img for img in element_images if img.get("status") == "active"]
    
    # Check which elements have NO active images
    elements_without_images = []
    for elem_doc in element_documentation:
        elem_active_images = [
            img for img in elem_doc.get("imagenes", [])
            if img.get("status") == "active"
        ]
        if not elem_active_images:
            elements_without_images.append(elem_doc["nombre"])
    
    if active_images:
        lines.append(f"IMAGENES DE EJEMPLO DISPONIBLES: {len(active_images)}")
        lines.append(f"  - Base (ficha técnica, permiso): {len(active_base_images)}")
        lines.append(f"  - Elementos específicos: {len(active_element_images)}")
        
        if elements_without_images:
            lines.append("")
            lines.append(f"⚠️ ELEMENTOS SIN IMAGENES DE EJEMPLO: {', '.join(elements_without_images)}")
            lines.append("  Para estos elementos, describe la documentación requerida sin prometer fotos de ejemplo.")
        lines.append("")
    elif base_images or element_images:
        lines.append("IMAGENES DE EJEMPLO: No disponibles en este momento (pendientes de configuracion).")
        lines.append("NO prometas imagenes al usuario. Describele la documentacion usando SOLO los datos de arriba.")
        lines.append("")

    # Build structured response for case creation
    import json

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
    }

    return json.dumps(response, ensure_ascii=False, indent=2)


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
        logger.error(f"Invalid category slug rejected in obtener_documentacion_elemento: {e}")
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
    elements = await element_service.get_elements_by_category(category_id, is_active=True)
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
                images.append({
                    "url": base_doc["image_url"],
                    "tipo": "base",  # Estandarizado para coincidir con condición en main.py
                    "descripcion": base_doc["description"],
                })

    return {
        "texto": "\n".join(lines),
        "imagenes": images,
    }


@tool
async def identificar_y_resolver_elementos(
    categoria_vehiculo: str,
    descripcion: str,
) -> str:
    """
    Identifica elementos Y detecta variantes en UNA sola llamada.

    Esta herramienta CONSOLIDA las funciones de:
    - identificar_elementos()
    - verificar_si_tiene_variantes() para cada elemento

    Usa esta herramienta como PRIMER PASO cuando el usuario describe qué quiere homologar.
    Es más eficiente que llamar a identificar_elementos + verificar_si_tiene_variantes por separado.

    IMPORTANTE: Usa el slug de categoría correcto:
    - "motos-part" para motocicletas de particulares
    - "aseicars-prof" para autocaravanas de profesionales

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
    
    # Validate category slug for security
    try:
        validate_category_slug(categoria_vehiculo)
    except ValueError as e:
        logger.error(f"Invalid category slug rejected in identificar_y_resolver_elementos: {e}")
        return json.dumps({
            "error": str(e),
            "elementos_listos": [],
            "elementos_con_variantes": [],
        }, ensure_ascii=False)

    element_service = get_element_service()

    # Get category ID from slug (cached)
    category_id = await get_or_fetch_category_id(categoria_vehiculo)
    if not category_id:
        return json.dumps({
            "error": f"Categoría '{categoria_vehiculo}' no encontrada",
            "elementos_listos": [],
            "elementos_con_variantes": [],
        }, ensure_ascii=False)

    # Get all elements for this category
    elements = await element_service.get_elements_by_category(category_id, is_active=True)
    if not elements:
        return json.dumps({
            "error": f"No hay elementos configurados para la categoría '{categoria_vehiculo}'",
            "elementos_listos": [],
            "elementos_con_variantes": [],
        }, ensure_ascii=False)

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
        }
    )

    # 2. Check each matched element for variants
    elementos_listos = []
    elementos_con_variantes = []
    preguntas_variantes = []

    for elem in matched_elements:
        elem_code = elem.get("code")
        elem_name = elem.get("name")
        
        if not elem_code:
            continue

        # Get variants for this element
        variants = await element_service.get_element_variants(
            element_code=elem_code,
            category_id=category_id,
        )

        if variants:
            # Element has variants - needs clarification
            # Get question_hint from base element
            base_element = await element_service.get_element_by_code(
                element_code=elem_code,
                category_id=category_id,
            )
            question_hint = (
                base_element.get("question_hint")
                if base_element and base_element.get("question_hint")
                else f"¿Qué tipo de {elem_name.lower()}?"
            )

            elementos_con_variantes.append({
                "codigo_base": elem_code,
                "nombre": elem_name,
                "variantes": [
                    {"codigo": v["code"], "nombre": v["name"]}
                    for v in variants
                ],
            })
            preguntas_variantes.append({
                "codigo_base": elem_code,
                "pregunta": question_hint,
                "opciones": [v["name"] for v in variants],
            })
        else:
            # Element is ready (no variants)
            elementos_listos.append({
                "codigo": elem_code,
                "nombre": elem_name,
                "cantidad": quantities.get(elem_code, 1),
            })

    # 3. Build response
    response = {
        "elementos_listos": elementos_listos,
        "elementos_con_variantes": elementos_con_variantes,
        "preguntas_variantes": preguntas_variantes,
        "terminos_no_reconocidos": unmatched_terms,
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

    # Log detailed result for debugging (Fase 3)
    response_json = json.dumps(response, ensure_ascii=False, indent=2)
    logger.info(
        f"[identificar_y_resolver_elementos] Result | category={categoria_vehiculo}",
        extra={
            "description_input": descripcion[:100],
            "elementos_listos_count": len(elementos_listos),
            "elementos_listos": [e["codigo"] for e in elementos_listos],
            "elementos_con_variantes_count": len(elementos_con_variantes),
            "elementos_con_variantes": [e["codigo_base"] for e in elementos_con_variantes],
            "terminos_no_reconocidos": unmatched_terms,
            "tiene_instrucciones": "instrucciones" in response,
            "response_preview": response_json[:500] if len(response_json) > 500 else response_json,
        }
    )

    return response_json


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
