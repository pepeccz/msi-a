"""
MSI Automotive - Tools module.

LangGraph tools for the conversational agent:
- General tools: Categories, tariffs, services, escalation
- Element tools: Element identification, pricing, documentation
"""

from agent.tools.tarifa_tools import (
    listar_categorias,
    listar_tarifas,
    obtener_servicios_adicionales,
    escalar_a_humano,
    get_tarifa_tools,
    ALL_TOOLS as GENERAL_TOOLS,
)

from agent.tools.element_tools import (
    listar_elementos,
    identificar_elementos,
    validar_elementos,
    calcular_tarifa_con_elementos,
    obtener_documentacion_elemento,
    get_element_tools,
    ELEMENT_TOOLS,
)

# Combined tools list
ALL_TOOLS = GENERAL_TOOLS + ELEMENT_TOOLS


def get_all_tools() -> list:
    """Get all available tools for the agent."""
    return ALL_TOOLS


__all__ = [
    # General tools
    "listar_categorias",
    "listar_tarifas",
    "obtener_servicios_adicionales",
    "escalar_a_humano",
    "get_tarifa_tools",
    "GENERAL_TOOLS",
    # Element tools
    "listar_elementos",
    "identificar_elementos",
    "validar_elementos",
    "calcular_tarifa_con_elementos",
    "obtener_documentacion_elemento",
    "get_element_tools",
    "ELEMENT_TOOLS",
    # Combined
    "ALL_TOOLS",
    "get_all_tools",
]
