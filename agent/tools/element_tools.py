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
        f"**Elementos homologables para {categoria_vehiculo}:**",
        "",
        f"Total: {len(elements)} elementos",
        "",
    ]

    for elem in elements:
        keywords_preview = ", ".join(elem.get("keywords", [])[:3])
        lines.append(f"• **{elem['code']}** - {elem['name']}")
        if keywords_preview:
            lines.append(f"  Keywords: {keywords_preview}")
        lines.append("")

    lines.append("---")
    lines.append("Usa `identificar_elementos` para encontrar elementos específicos en una descripción.")

    return "\n".join(lines)


@tool
async def identificar_elementos(
    categoria_vehiculo: str,
    descripcion: str,
) -> str:
    """
    Identifica elementos específicos del catálogo a partir de una descripción del usuario.

    Usa SIEMPRE esta herramienta ANTES de calcular precio para identificar exactamente
    qué elementos quiere homologar el usuario.

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
        Lista de elementos identificados con códigos, nombres y scores de matching.
        Incluye los códigos que debes usar con `calcular_tarifa_con_elementos`.
    """
    element_service = get_element_service()

    # Get category ID from slug
    category_id = await _get_category_id_by_slug(categoria_vehiculo)
    if not category_id:
        tarifa_service = get_tarifa_service()
        categories = await tarifa_service.get_active_categories()
        available = ", ".join(c["slug"] for c in categories)
        return f"Categoría '{categoria_vehiculo}' no encontrada. Categorías disponibles: {available}"

    # Match elements from description
    matches = await element_service.match_elements_from_description(
        description=descripcion,
        category_id=category_id,
    )

    if not matches:
        return (
            f"No se identificaron elementos en el catálogo que coincidan con '{descripcion}'.\n\n"
            "Sugerencias:\n"
            "1. Pide al usuario que especifique los elementos con más detalle\n"
            "2. Usa `listar_elementos` para mostrar el catálogo completo\n"
            "3. Escala a un humano si el usuario necesita ayuda personalizada"
        )

    # Build response for LLM (internal format - NOT to show to user)
    lines = [
        "=== INFORMACIÓN INTERNA (NO mostrar al usuario) ===",
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

        # Internal line for LLM reference
        lines.append(f"[código:{element['code']}] {element['name']}")

    lines.append("")
    lines.append("=== INSTRUCCIONES PARA TI (el asistente) ===")
    lines.append("")

    if elements_confirmed:
        lines.append(f"Elementos identificados con seguridad: {', '.join(elements_confirmed)}")

    if elements_to_confirm:
        lines.append("")
        lines.append("ACCIÓN REQUERIDA - Pregunta al usuario sobre:")
        for name in elements_to_confirm:
            lines.append(f"  - {name}")
        lines.append("")
        lines.append("Ejemplo de cómo preguntar (usa tono natural y cercano):")
        lines.append(f'  "Sobre {elements_to_confirm[0].lower()}, ¿podrías darme más detalles?"')

    lines.append("")
    lines.append("IMPORTANTE:")
    lines.append("- NO menciones códigos internos al usuario")
    lines.append("- NO menciones porcentajes ni 'confianza'")
    lines.append("- Usa nombres descriptivos en español")
    lines.append("- Sé conciso, no repitas información")
    lines.append("")
    lines.append(f"Códigos para siguiente paso: {', '.join(element_codes)}")

    return "\n".join(lines)


@tool
async def calcular_tarifa_con_elementos(
    categoria_vehiculo: str,
    codigos_elementos: list[str],
) -> str:
    """
    Calcula el precio de homologación basándose en elementos específicos del catálogo.

    IMPORTANTE: Usa `identificar_elementos` PRIMERO para obtener los códigos correctos.
    Esta herramienta valida que los elementos existan y busca la tarifa que los cubra.

    La tarifa seleccionada es la más económica que incluye TODOS los elementos especificados.
    Si no existe una tarifa que cubra todos los elementos, se indica cuáles quedan fuera.

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        codigos_elementos: Lista de códigos de elementos del catálogo.
                          Ejemplo: ["ESCAPE", "MANILLAR"] para motos
                                   ["ESC_MEC", "TOLDO_LAT"] para autocaravanas

    Returns:
        Tarifa seleccionada, precio, elementos incluidos y advertencias.
        Los precios son SIN IVA.
    """
    tarifa_service = get_tarifa_service()
    element_service = get_element_service()

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
        f"**Tarifa Recomendada: {result['tier_name']} ({result['tier_code']})**",
        f"**Precio: {result['price']}EUR** (IVA no incluido)",
        "",
    ]

    if result.get("conditions"):
        lines.append(f"Condiciones: {result['conditions']}")
        lines.append("")

    lines.append(f"**Elementos incluidos ({len(valid_elements)}):**")
    for elem in valid_elements:
        lines.append(f"• {elem['code']} - {elem['name']}")
    lines.append("")

    # Add warnings if any
    if result.get("warnings"):
        lines.append("**Advertencias:**")
        for w in result["warnings"]:
            severity_icon = (
                "!!!" if w.get("severity") == "error"
                else "!!" if w.get("severity") == "warning"
                else "!"
            )
            lines.append(f"{severity_icon} {w['message']}")
        lines.append("")

    # Add additional services if available
    if result.get("additional_services"):
        lines.append("**Servicios adicionales disponibles:**")
        for s in result["additional_services"][:3]:  # Show first 3
            lines.append(f"• {s['name']}: {s['price']}EUR")
        if len(result.get("additional_services", [])) > 3:
            lines.append(f"  ... y {len(result['additional_services']) - 3} más")

    return "\n".join(lines)


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
        f"**Documentación para {element_details['name']} ({code_upper}):**",
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
            lines.append("**Documentos requeridos:**")
            for doc in required_docs:
                lines.append(f"• {doc['title']}")
                if doc.get("description"):
                    lines.append(f"  {doc['description']}")
            lines.append("")

        if example_docs:
            lines.append("**Fotos de ejemplo:**")
            for doc in example_docs:
                lines.append(f"• {doc['title']}")
                if doc.get("description"):
                    lines.append(f"  {doc['description']}")
            lines.append("")
    else:
        lines.append("No hay documentación específica configurada para este elemento.")
        lines.append("Documentación general requerida:")
        lines.append("• Foto del elemento con matrícula visible")
        lines.append("• Certificado o placa del fabricante (si aplica)")

    # Get warnings for this element
    warnings = await element_service.get_element_warnings(element["id"])
    if warnings:
        lines.append("")
        lines.append("**Advertencias:**")
        for w in warnings:
            lines.append(f"• {w['description']}")

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
    from agent.services.tarifa_service import get_tarifa_service

    tarifa_service = get_tarifa_service()
    element_service = get_element_service()

    # Get category ID from slug
    categories = await tarifa_service.get_active_categories()
    category = next(
        (c for c in categories if c["slug"] == categoria_vehiculo),
        None
    )

    if not category:
        return f"ERROR: Categoría '{categoria_vehiculo}' no encontrada."

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
        lines.append(f"ERROR: Códigos no válidos: {', '.join(invalid_codes)}")
        lines.append("")
        lines.append("Códigos disponibles:")
        for code, elem in sorted(element_by_code.items())[:10]:
            lines.append(f"  - {code}: {elem['name']}")
        if len(element_by_code) > 10:
            lines.append(f"  ... y {len(element_by_code) - 10} más")
        return "\n".join(lines)

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
        return "\n".join(lines)

    lines.append("")
    lines.append("Estado: OK - Puedes calcular tarifa")
    return "\n".join(lines)


# Export all element tools
ELEMENT_TOOLS = [
    listar_elementos,
    identificar_elementos,
    validar_elementos,
    calcular_tarifa_con_elementos,
    obtener_documentacion_elemento,
]


def get_element_tools() -> list:
    """Get all element-related tools for the agent."""
    return ELEMENT_TOOLS
