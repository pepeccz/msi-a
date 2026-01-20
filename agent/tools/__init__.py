"""
MSI Automotive - Tools module.

LangGraph tools for the conversational agent:
- General tools: Categories, tariffs, services, escalation
- Element tools: Element identification, pricing, documentation
- Case tools: Case/expediente management and data collection
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
    verificar_si_tiene_variantes,
    seleccionar_variante_por_respuesta,
    validar_elementos,
    calcular_tarifa_con_elementos,
    obtener_documentacion_elemento,
    get_element_tools,
    ELEMENT_TOOLS,
)

from agent.tools.case_tools import (
    iniciar_expediente,
    actualizar_datos_expediente,
    actualizar_datos_taller,
    procesar_imagen_expediente,
    procesar_imagenes_expediente,
    continuar_a_datos_personales,
    finalizar_expediente,
    cancelar_expediente,
    obtener_estado_expediente,
    get_case_tools,
    CASE_TOOLS,
)

from agent.tools.vehicle_tools import (
    identificar_tipo_vehiculo,
    get_vehicle_tools,
    VEHICLE_TOOLS,
)

# Combined tools list
ALL_TOOLS = GENERAL_TOOLS + ELEMENT_TOOLS + CASE_TOOLS + VEHICLE_TOOLS


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
    "verificar_si_tiene_variantes",
    "seleccionar_variante_por_respuesta",
    "validar_elementos",
    "calcular_tarifa_con_elementos",
    "obtener_documentacion_elemento",
    "get_element_tools",
    "ELEMENT_TOOLS",
    # Case tools
    "iniciar_expediente",
    "actualizar_datos_expediente",
    "actualizar_datos_taller",
    "procesar_imagen_expediente",
    "procesar_imagenes_expediente",
    "continuar_a_datos_personales",
    "finalizar_expediente",
    "cancelar_expediente",
    "obtener_estado_expediente",
    "get_case_tools",
    "CASE_TOOLS",
    # Vehicle tools
    "identificar_tipo_vehiculo",
    "get_vehicle_tools",
    "VEHICLE_TOOLS",
    # Combined
    "ALL_TOOLS",
    "get_all_tools",
]
