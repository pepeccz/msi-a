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
from typing import Any

from langchain_core.tools import tool

from agent.services.element_service import get_element_service
from agent.services.tarifa_service import get_tarifa_service
from agent.state.helpers import get_current_state
from database.connection import get_async_session
from database.models import VehicleCategory

logger = logging.getLogger(__name__)


async def _get_category_id_by_slug(category_slug: str) -> str | None:
    """Get category ID from slug."""
    from sqlalchemy import select

    async with get_async_session() as session:
        result = await session.execute(
            select(VehicleCategory)
            .where(VehicleCategory.slug == category_slug)
            .where(VehicleCategory.is_active == True)
        )
        category = result.scalar_one_or_none()
        return str(category.id) if category else None


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

    # Validate codes
    valid_elements = []
    invalid_codes = []
    low_confidence = []

    # Confidence threshold (60%)
    CONFIDENCE_THRESHOLD = 0.6

    for code in codigos_elementos:
        code_upper = code.upper()
        if code_upper in element_by_code:
            elem = element_by_code[code_upper]
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
                "valid_codes_available": list(element_by_code.keys())[:20]
            }
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
    element_service = get_element_service()

    # Get category ID from slug
    category_id = await _get_category_id_by_slug(categoria_vehiculo)
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
async def identificar_elementos(
    categoria_vehiculo: str,
    descripcion: str,
) -> str:
    """
    Identifica elementos BASE del catálogo a partir de una descripción del usuario.

    Usa SIEMPRE esta herramienta ANTES de calcular precio para identificar exactamente
    qué elementos quiere homologar el usuario.

    IMPORTANTE: Esta herramienta identifica solo elementos BASE (sin variantes).
    DESPUÉS de usar esta herramienta, DEBES usar `verificar_si_tiene_variantes()`
    para cada elemento identificado para detectar si tiene variantes disponibles.

    La herramienta usa matching por keywords y devuelve una puntuación de confianza.
    Si la confianza es baja (<0.5), pide al usuario que especifique mejor.

    IMPORTANTE: Usa el slug de categoría correcto:
    - "motos-part" para motocicletas de particulares
    - "aseicars-prof" para autocaravanas de profesionales

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        descripcion: Descripción del usuario con elementos a homologar.
                    Ejemplo: "quiero homologar el escape y el manillar"
                             "escalera mecánica y toldo lateral"

    Returns:
        Lista de elementos BASE identificados con códigos, nombres y scores de matching.
        También incluye términos no identificados que requieren clarificación del usuario.
        Incluye los códigos que debes usar con `verificar_si_tiene_variantes()` primero.
    """
    element_service = get_element_service()

    # Get category ID from slug
    category_id = await _get_category_id_by_slug(categoria_vehiculo)
    if not category_id:
        tarifa_service = get_tarifa_service()
        categories = await tarifa_service.get_active_categories()
        available = ", ".join(c["slug"] for c in categories)
        return f"Categoría '{categoria_vehiculo}' no encontrada. Categorías disponibles: {available}"

    # Match elements from description WITH unmatched term detection
    result = await element_service.match_elements_with_unmatched(
        description=descripcion,
        category_id=category_id,
    )

    matches = result["matches"]
    unmatched_terms = result.get("unmatched_terms", [])

    # Log matched elements and unmatched terms for debugging
    logger.info(
        f"[identificar_elementos] Matched elements | category={categoria_vehiculo}",
        extra={
            "matched_codes": [e["code"] for e, _ in matches] if matches else [],
            "matched_scores": [s for _, s in matches] if matches else [],
            "unmatched_terms": unmatched_terms,
            "description": descripcion,
        }
    )

    # Handle case where nothing matched but there are unmatched terms
    if not matches and unmatched_terms:
        lines = [
            "=== NO SE IDENTIFICARON ELEMENTOS ===",
            "",
            f"No encontré elementos que coincidan exactamente con '{descripcion}'.",
            "",
            "⚠️ TÉRMINOS QUE REQUIEREN CLARIFICACIÓN:",
            "",
        ]
        for term in unmatched_terms:
            lines.append(f"  • '{term}'")
        lines.append("")
        lines.append("ACCIÓN REQUERIDA:")
        lines.append("Pregunta al usuario de forma NATURAL qué quiere decir con estos términos.")
        lines.append("")
        lines.append("Ejemplos de cómo preguntar:")
        if "luces" in [t.lower() for t in unmatched_terms]:
            lines.append('  "Cuando dices luces, ¿te refieres a faros delanteros, intermitentes, piloto trasero...?"')
        else:
            lines.append(f'  "¿Podrías especificar a qué te refieres con \'{unmatched_terms[0]}\'?"')
        lines.append("")
        lines.append("NO procedas a calcular tarifa hasta aclarar estos términos.")

        return "\n".join(lines)

    if not matches:
        return (
            f"No se identificaron elementos en el catálogo que coincidan con '{descripcion}'.\n\n"
            "Sugerencias:\n"
            "1. Pide al usuario que especifique los elementos con más detalle\n"
            "2. Usa `listar_elementos` para mostrar el catálogo completo\n"
            "3. Escala a un humano si el usuario necesita ayuda personalizada"
        )

    # Build response with STRONGER emphasis on codes
    lines = [
        "=== RESULTADO DE IDENTIFICACIÓN ===",
        "",
        "⚠️ IMPORTANTE: Usa EXACTAMENTE estos códigos (NO los modifiques):",
        "",
    ]

    element_codes = []
    elements_to_confirm = []
    elements_confirmed = []

    for element, score in matches:
        confidence_pct = min(score / 2, 1.0) * 100  # Normalize score to percentage
        needs_confirmation = confidence_pct < 50

        element_codes.append(element["code"])

        if needs_confirmation:
            elements_to_confirm.append(element["name"])
        else:
            elements_confirmed.append(element["name"])

        # More prominent format
        lines.append(f"  CÓDIGO: {element['code']}")
        lines.append(f"  Nombre: {element['name']}")
        lines.append(f"  Match: {confidence_pct:.0f}%")
        lines.append("")

    # === CRITICAL: Report unmatched terms ===
    if unmatched_terms:
        lines.append("=== ⚠️ TÉRMINOS NO IDENTIFICADOS ===")
        lines.append("")
        lines.append("Los siguientes términos del usuario NO coincidieron con ningún elemento:")
        lines.append("")
        for term in unmatched_terms:
            lines.append(f"  • '{term}'")
        lines.append("")
        lines.append("⚠️ ACCIÓN OBLIGATORIA:")
        lines.append("DEBES preguntar al usuario qué quiere decir con estos términos ANTES de calcular tarifa.")
        lines.append("")
        lines.append("Ejemplo de cómo preguntar (natural, sin códigos):")
        if "luces" in [t.lower() for t in unmatched_terms]:
            lines.append('  "He identificado subchasis y suspensión trasera. Sobre las luces,')
            lines.append('   ¿te refieres a faros delanteros, intermitentes, piloto trasero u otro tipo?"')
        else:
            lines.append(f'  "He identificado los elementos anteriores. Sobre \'{unmatched_terms[0]}\',')
            lines.append(f'   ¿podrías especificar exactamente qué modificación quieres homologar?"')
        lines.append("")

    lines.append("=== PRÓXIMO PASO OBLIGATORIO ===")
    lines.append("")

    if unmatched_terms:
        lines.append("1. PRIMERO: Pregunta al usuario sobre los términos no identificados")
        lines.append("2. DESPUÉS: Cuando tengas clarificación, vuelve a usar identificar_elementos")
        lines.append("   con la descripción completa (incluyendo los términos aclarados)")
        lines.append("")
        lines.append("⚠️ NO procedas a validar_elementos ni calcular_tarifa hasta aclarar TODO")
    else:
        lines.append("Llama a validar_elementos() con EXACTAMENTE estos códigos:")
        lines.append(f"  validar_elementos(")
        lines.append(f"    categoria_vehiculo='{categoria_vehiculo}',")
        lines.append(f"    codigos_elementos={element_codes}")
        lines.append(f"  )")
        lines.append("")
        lines.append("⚠️ NO uses otros códigos, NO inventes códigos nuevos")

    if elements_to_confirm:
        lines.append("")
        lines.append("ACCIÓN ADICIONAL - Pregunta al usuario sobre:")
        for name in elements_to_confirm:
            lines.append(f"  - {name}")
        lines.append("")
        lines.append("Ejemplo de cómo preguntar (usa tono natural y cercano):")
        lines.append(f'  "Sobre {elements_to_confirm[0].lower()}, ¿podrías darme más detalles?"')

    lines.append("")
    lines.append("RECORDATORIO:")
    lines.append("- NO menciones códigos internos al usuario")
    lines.append("- NO menciones porcentajes ni 'confianza'")
    lines.append("- Usa nombres descriptivos en español")
    lines.append("- NUNCA omitas elementos de esta lista en el cálculo final")

    return "\n".join(lines)


@tool
async def verificar_si_tiene_variantes(
    categoria_vehiculo: str,
    codigo_elemento: str,
) -> str:
    """
    Verifica si un elemento base tiene variantes disponibles.

    USA ESTA TOOL DESPUÉS de identificar_elementos() para CADA elemento identificado.
    Si detecta variantes, DEBES preguntar al usuario cuál necesita ANTES de calcular tarifa.

    IMPORTANTE: Usa el slug de categoría correcto:
    - "motos-part" para motocicletas de particulares
    - "aseicars-prof" para autocaravanas de profesionales

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        codigo_elemento: Código del elemento a verificar (ej: "BOLA_REMOLQUE")

    Returns:
        JSON string con:
        - has_variants: bool - indica si tiene variantes
        - variant_type: str - tipo de variante (ej: "mmr_option", "installation_type")
        - variants: lista de variantes disponibles
        - question_hint: sugerencia de pregunta para el usuario

    Ejemplo de retorno cuando tiene variantes:
    {
        "has_variants": true,
        "variant_type": "mmr_option",
        "variants": [
            {"code": "BOLA_SIN_MMR", "name": "Bola sin aumento MMR", "variant_code": "SIN_MMR"},
            {"code": "BOLA_CON_MMR", "name": "Bola con aumento MMR", "variant_code": "CON_MMR"}
        ],
        "question_hint": "¿La instalación aumenta la masa máxima del remolque (MMR) o no?"
    }
    """
    import json

    element_service = get_element_service()

    # Get category ID from slug
    category_id = await _get_category_id_by_slug(categoria_vehiculo)
    if not category_id:
        return json.dumps({
            "has_variants": False,
            "error": f"Categoría '{categoria_vehiculo}' no encontrada"
        }, ensure_ascii=False)

    # Get variants for this element
    variants = await element_service.get_element_variants(
        element_code=codigo_elemento.upper(),
        category_id=category_id,
    )

    if not variants:
        return json.dumps({
            "has_variants": False,
            "message": f"El elemento '{codigo_elemento}' no tiene variantes"
        }, ensure_ascii=False)

    # Get question_hint from base element (data-driven, not hardcoded)
    base_element = await element_service.get_element_by_code(
        element_code=codigo_elemento.upper(),
        category_id=category_id,
    )

    variant_type = variants[0].get("variant_type", "unknown")

    # Use question_hint from DB, fallback to generic question
    question_hint = (
        base_element.get("question_hint")
        if base_element and base_element.get("question_hint")
        else f"¿Qué tipo de {codigo_elemento.lower().replace('_', ' ')} necesitas?"
    )

    # Format variants for response
    formatted_variants = [
        {
            "code": v["code"],
            "name": v["name"],
            "variant_code": v["variant_code"],
            "description": v.get("description", ""),
        }
        for v in variants
    ]

    return json.dumps({
        "has_variants": True,
        "variant_type": variant_type,
        "variants": formatted_variants,
        "question_hint": question_hint,
        "instrucciones": (
            "DEBES preguntar al usuario cuál variante necesita ANTES de calcular tarifa. "
            "Usa el question_hint como guía para formular la pregunta de forma natural. "
            "NO menciones códigos internos al usuario."
        ),
    }, ensure_ascii=False, indent=2)


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

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        codigo_elemento_base: Código del elemento base (ej: "BOLA_REMOLQUE")
        respuesta_usuario: Texto de respuesta del usuario (ej: "sí, aumenta MMR", "2 faros")

    Returns:
        JSON con:
        - selected_variant: código de la variante seleccionada
        - confidence: nivel de confianza del matching (0.0-1.0)
        - name: nombre descriptivo de la variante

    Ejemplo:
    {
        "selected_variant": "BOLA_CON_MMR",
        "confidence": 0.95,
        "name": "Bola de remolque con aumento MMR"
    }

    Si confidence < 0.7, pregunta al usuario de forma más específica.
    """
    import json

    element_service = get_element_service()

    # Get category ID from slug
    category_id = await _get_category_id_by_slug(categoria_vehiculo)
    if not category_id:
        return json.dumps({
            "error": f"Categoría '{categoria_vehiculo}' no encontrada"
        }, ensure_ascii=False)

    # Get variants for this element
    variants = await element_service.get_element_variants(
        element_code=codigo_elemento_base.upper(),
        category_id=category_id,
    )

    if not variants:
        return json.dumps({
            "error": f"No se encontraron variantes para '{codigo_elemento_base}'"
        }, ensure_ascii=False)

    # Normalize user response (remove accents for matching)
    import unicodedata

    def normalize_text(text: str) -> str:
        """Normalize text: lowercase and remove accents."""
        text = unicodedata.normalize('NFD', text.lower())
        return ''.join(c for c in text if unicodedata.category(c) != 'Mn')

    respuesta_lower = respuesta_usuario.lower().strip()
    respuesta_normalized = normalize_text(respuesta_usuario)

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
) -> str:
    """
    Calcula el precio de homologación basándose en elementos específicos del catálogo.

    ⚠️ IMPORTANTE:
    - USA EXACTAMENTE los códigos retornados por `identificar_elementos`
    - NO inventes códigos nuevos
    - DEBES llamar `validar_elementos` ANTES de esta herramienta

    Esta herramienta valida que los elementos existan y busca la tarifa que los cubra.
    La tarifa seleccionada es la más económica que incluye TODOS los elementos especificados.

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        codigos_elementos: Lista de códigos EXACTOS retornados por identificar_elementos
                          Ejemplo: ["ESCAPE", "MANILLAR"] (NO uses variaciones)

    Returns:
        Tarifa seleccionada, precio, elementos incluidos y advertencias.
        Los precios son SIN IVA.
    """
    tarifa_service = get_tarifa_service()
    element_service = get_element_service()

    # === VALIDACIÓN PREVIA ===
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

    # Get category ID from slug
    category_id = await _get_category_id_by_slug(categoria_vehiculo)
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
    valid_elements = []
    invalid_codes = []

    for code in codigos_elementos:
        code_upper = code.upper()
        if code_upper in element_by_code:
            valid_elements.append(element_by_code[code_upper])
        else:
            invalid_codes.append(code)

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

    result = await tarifa_service.select_tariff_by_rules(
        category_slug=categoria_vehiculo,
        elements_description=description,
        element_count=len(valid_elements),
    )

    if "error" in result:
        return f"Error: {result['error']}"

    # Get warnings from ElementWarningAssociation for matched elements
    element_ids = [e["id"] for e in valid_elements]
    element_warnings = await element_service.get_warnings_for_elements(element_ids)

    # Merge element association warnings with rule-based warnings
    existing_warning_codes = {w.get("code") for w in result.get("warnings", [])}
    for ew in element_warnings:
        if ew["code"] not in existing_warning_codes:
            result.setdefault("warnings", []).append({
                "code": ew["code"],
                "message": ew["message"],
                "severity": ew["severity"],
            })
            existing_warning_codes.add(ew["code"])

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

    # Add warnings if any
    if result.get("warnings"):
        lines.append("ADVERTENCIAS:")
        for w in result["warnings"]:
            severity_icon = (
                "\U0001F534" if w.get("severity") == "error"
                else "\u26A0\uFE0F" if w.get("severity") == "warning"
                else "\u2139\uFE0F"
            )
            lines.append(f"{severity_icon} {w['message']}")
        lines.append("")

    # Add additional services if available
    if result.get("additional_services"):
        lines.append("Servicios adicionales disponibles:")
        for s in result["additional_services"][:3]:  # Show first 3
            lines.append(f"- {s['name']}: {s['price']} EUR")
        if len(result.get("additional_services", [])) > 3:
            lines.append(f"  ... y {len(result['additional_services']) - 3} mas")

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
        }
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
    element_service = get_element_service()

    # Get category ID from slug
    category_id = await _get_category_id_by_slug(categoria_vehiculo)
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
async def validar_elementos(
    categoria_vehiculo: str,
    codigos_elementos: list[str],
    confianzas: dict[str, float] | None = None,
) -> str:
    """
    Valida elementos identificados antes de calcular tarifa.

    DEBES usar esta herramienta SIEMPRE después de identificar_elementos
    y ANTES de calcular_tarifa_con_elementos.

    Esta herramienta verifica:
    - Que los códigos de elementos sean válidos
    - Que los elementos no tengan baja confianza
    - Si el usuario necesita confirmar la selección

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part")
        codigos_elementos: Lista de códigos identificados (ej: ["ESCAPE", "MANILLAR"])
        confianzas: Diccionario opcional con confianzas (ej: {"ESCAPE": 0.95, "MANILLAR": 0.45})

    Returns:
        Estado de validación:
        - "OK": Puedes proceder a calcular_tarifa_con_elementos
        - "CONFIRMAR": Debes preguntar al usuario antes de continuar
        - "ERROR": Hay códigos inválidos
    """
    # Use internal validation function (shared with calcular_tarifa_con_elementos)
    result = await _validate_element_codes(
        categoria_vehiculo=categoria_vehiculo,
        codigos_elementos=codigos_elementos,
        confianzas=confianzas,
    )
    return result["message"]


# Export all element tools
ELEMENT_TOOLS = [
    listar_elementos,
    identificar_elementos,
    verificar_si_tiene_variantes,
    seleccionar_variante_por_respuesta,
    validar_elementos,
    calcular_tarifa_con_elementos,
    obtener_documentacion_elemento,
]


def get_element_tools() -> list:
    """Get all element-related tools for the agent."""
    return ELEMENT_TOOLS
