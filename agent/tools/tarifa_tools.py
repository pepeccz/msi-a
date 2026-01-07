"""
MSI Automotive - Tariff Tools for LangGraph Agent.

These tools allow the conversational agent to calculate tariffs
and retrieve documentation for vehicle homologations.
"""

import logging
from typing import Any

from langchain_core.tools import tool

from agent.services.tarifa_service import get_tarifa_service

logger = logging.getLogger(__name__)


@tool
async def listar_categorias() -> str:
    """
    Lista las categorías de vehículos disponibles para homologación.

    Use this tool when the user asks what types of vehicles can be homologated,
    or when you need to know what categories are available.

    Returns:
        List of available vehicle categories with their descriptions.
    """
    service = get_tarifa_service()
    categories = await service.get_active_categories()

    if not categories:
        return "No hay categorías de vehículos disponibles en este momento."

    lines = ["**Categorías de vehículos disponibles:**", ""]
    for cat in categories:
        lines.append(f"• **{cat['name']}** (`{cat['slug']}`)")
        if cat.get("description"):
            lines.append(f"  {cat['description']}")

    return "\n".join(lines)


@tool
async def calcular_tarifa(
    categoria_vehiculo: str,
    descripcion_elementos: str,
    tipo_cliente: str = "particular",
) -> str:
    """
    Calcula el precio de homologación según la categoría de vehículo y los elementos a modificar.

    Use this tool when the user wants to know the price for homologating specific modifications.
    IMPORTANT: Always use this tool before providing a price estimate.

    Args:
        categoria_vehiculo: Categoría del vehículo. Usa el slug exacto:
                           - "aseicars" para autocaravanas (códigos 32xx, 33xx)
                           - "motos" para motocicletas
        descripcion_elementos: Descripción en lenguaje natural de los elementos a homologar.
                              Ejemplo: "escalera mecánica y toldo lateral"
                                       "placas solares en el techo y antena parabólica"
        tipo_cliente: "particular" o "professional" (profesional/taller)

    Returns:
        Calculated tariff with price, tier, breakdown, and warnings.
        IMPORTANT: Los precios NO incluyen IVA. Siempre indicar "+IVA" al usuario.
    """
    service = get_tarifa_service()

    if not descripcion_elementos.strip():
        return "Error: Debes especificar los elementos a homologar."

    # Count elements roughly from description
    # This is a simple heuristic - the AI should have already identified elements
    separators = [",", " y ", " e ", " + "]
    element_count = 1
    desc_lower = descripcion_elementos.lower()
    for sep in separators:
        if sep in desc_lower:
            element_count = max(element_count, desc_lower.count(sep) + 1)

    result = await service.select_tariff_by_rules(
        category_slug=categoria_vehiculo,
        elements_description=descripcion_elementos,
        element_count=element_count,
        client_type=tipo_cliente,
    )

    return service.format_tariff_response(result)


@tool
async def obtener_documentacion(
    categoria_vehiculo: str,
    descripcion_elementos: str = "",
) -> dict[str, Any]:
    """
    Obtiene la documentación necesaria para homologar elementos específicos.

    Use this tool when the user asks what photos or documents they need to provide.
    Returns both text descriptions and image URLs that should be sent to the user.

    Args:
        categoria_vehiculo: Categoría del vehículo. Usa el slug exacto:
                           - "aseicars" para autocaravanas (códigos 32xx, 33xx)
                           - "motos" para motocicletas
        descripcion_elementos: Descripción de los elementos a homologar.
                              Usado para buscar documentación específica por keyword.
                              Ejemplo: "escalera y toldo" buscará docs de escalera y toldo.

    Returns:
        Dictionary with:
        - "texto": Text description of required documentation
        - "imagenes": List of example image URLs to send to user
    """
    service = get_tarifa_service()

    result = await service.get_documentation(
        categoria_vehiculo,
        descripcion_elementos if descripcion_elementos.strip() else None,
    )
    text, images = service.format_documentation_response(result)

    return {
        "texto": text,
        "imagenes": images,
    }


@tool
async def listar_tarifas(categoria_vehiculo: str, tipo_cliente: str = "particular") -> str:
    """
    Lista las tarifas disponibles para una categoría de vehículo.

    Use this tool when the user wants to know what pricing tiers exist
    or what types of homologations are available.

    Args:
        categoria_vehiculo: Categoría del vehículo. Usa el slug exacto:
                           - "aseicars" para autocaravanas (códigos 32xx, 33xx)
                           - "motos" para motocicletas
        tipo_cliente: "particular" o "professional"

    Returns:
        List of tariff tiers with prices and conditions.
    """
    service = get_tarifa_service()
    data = await service.get_category_data(categoria_vehiculo, tipo_cliente)

    if not data:
        categories = await service.get_active_categories()
        return f"Categoría '{categoria_vehiculo}' no encontrada. Categorías disponibles: {', '.join(c['slug'] for c in categories)}"

    lines = [
        f"**Tarifas para {data['category']['name']}** ({tipo_cliente.capitalize()}):",
        "",
        "Precios SIN IVA:",
        "",
    ]

    for tier in data["tiers"]:
        lines.append(f"• **{tier['code']} - {tier['name']}**: {tier['price']}€ + IVA")
        if tier.get("conditions"):
            lines.append(f"  {tier['conditions']}")

        # Show keywords if available
        rules = tier.get("classification_rules") or {}
        keywords = rules.get("applies_if_any", [])
        if keywords:
            lines.append(f"  Aplica para: {', '.join(keywords[:5])}" + ("..." if len(keywords) > 5 else ""))

        lines.append("")

    return "\n".join(lines)


@tool
async def obtener_servicios_adicionales(categoria_vehiculo: str = "") -> str:
    """
    Obtiene los servicios adicionales disponibles (certificados, urgencias, etc.).

    Use this tool when the user asks about additional services like:
    - Workshop certificates
    - Rush processing
    - Brake testing

    Args:
        categoria_vehiculo: Opcional. Categoría para ver servicios específicos.

    Returns:
        List of available additional services with prices.
    """
    service = get_tarifa_service()

    if categoria_vehiculo:
        data = await service.get_category_data(categoria_vehiculo)
        if data:
            services = data.get("additional_services", [])
        else:
            services = []
    else:
        # Get services from any category (they're global anyway)
        categories = await service.get_active_categories()
        if categories:
            data = await service.get_category_data(categories[0]["slug"])
            services = data.get("additional_services", []) if data else []
        else:
            services = []

    if not services:
        return "No hay servicios adicionales disponibles en este momento."

    lines = ["**Servicios adicionales disponibles:**", ""]
    for s in services:
        lines.append(f"• **{s['name']}**: {s['price']}€")
        if s.get("description"):
            lines.append(f"  {s['description']}")

    return "\n".join(lines)


@tool
async def escalar_a_humano(motivo: str) -> str:
    """
    Escala la conversación a un agente humano.

    Use this tool when:
    - The user explicitly asks to speak with a human
    - You cannot answer the user's question
    - The user needs special assistance not covered by standard processes
    - There's a complex case that requires human judgment

    Args:
        motivo: Brief reason for escalation (in Spanish).

    Returns:
        Confirmation message that the conversation will be escalated.
    """
    logger.info(f"Conversation escalation requested. Reason: {motivo}")

    # In a real implementation, this would:
    # 1. Update Chatwoot custom attributes to disable auto-reply
    # 2. Assign the conversation to a human agent
    # 3. Send notification to the support team

    return (
        "He registrado tu solicitud de atención personalizada. "
        "Un agente de MSI Automotive se pondrá en contacto contigo lo antes posible. "
        f"Motivo de la consulta: {motivo}"
    )


# Export all tools
ALL_TOOLS = [
    listar_categorias,
    calcular_tarifa,
    obtener_documentacion,
    listar_tarifas,
    obtener_servicios_adicionales,
    escalar_a_humano,
]


def get_tarifa_tools() -> list:
    """Get all tariff-related tools for the agent."""
    return ALL_TOOLS
