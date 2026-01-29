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
    identificar_y_resolver_elementos,
    seleccionar_variante_por_respuesta,
    calcular_tarifa_con_elementos,
    obtener_documentacion_elemento,
    get_element_tools,
    ELEMENT_TOOLS,
)

from agent.tools.case_tools import (
    iniciar_expediente,
    actualizar_datos_expediente,
    actualizar_datos_taller,
    editar_expediente,
    # NOTE: procesar_imagen* tools were removed - images are now handled silently
    # in main.py with batching and timeout confirmation
    finalizar_expediente,
    cancelar_expediente,
    obtener_estado_expediente,
    consulta_durante_expediente,
    get_case_tools,
    CASE_TOOLS,
)

from agent.tools.vehicle_tools import (
    identificar_tipo_vehiculo,
    get_vehicle_tools,
    VEHICLE_TOOLS,
)

from agent.tools.image_tools import (
    enviar_imagenes_ejemplo,
    get_image_tools,
    IMAGE_TOOLS,
)

from agent.tools.element_data_tools import (
    obtener_campos_elemento,
    guardar_datos_elemento,
    confirmar_fotos_elemento,
    completar_elemento_actual,
    obtener_progreso_elementos,
    confirmar_documentacion_base,
    reenviar_imagenes_elemento,
    element_data_tools as ELEMENT_DATA_TOOLS,
)

# Combined tools list
ALL_TOOLS = GENERAL_TOOLS + ELEMENT_TOOLS + CASE_TOOLS + VEHICLE_TOOLS + IMAGE_TOOLS + ELEMENT_DATA_TOOLS


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
    "identificar_y_resolver_elementos",
    "seleccionar_variante_por_respuesta",
    "calcular_tarifa_con_elementos",
    "obtener_documentacion_elemento",
    "get_element_tools",
    "ELEMENT_TOOLS",
    # Case tools
    "iniciar_expediente",
    "actualizar_datos_expediente",
    "actualizar_datos_taller",
    "editar_expediente",
    "finalizar_expediente",
    "cancelar_expediente",
    "obtener_estado_expediente",
    "consulta_durante_expediente",
    "get_case_tools",
    "CASE_TOOLS",
    # Vehicle tools
    "identificar_tipo_vehiculo",
    "get_vehicle_tools",
    "VEHICLE_TOOLS",
    # Image tools
    "enviar_imagenes_ejemplo",
    "get_image_tools",
    "IMAGE_TOOLS",
    # Element data collection tools (new flow)
    "obtener_campos_elemento",
    "guardar_datos_elemento",
    "confirmar_fotos_elemento",
    "completar_elemento_actual",
    "obtener_progreso_elementos",
    "confirmar_documentacion_base",
    "reenviar_imagenes_elemento",
    "ELEMENT_DATA_TOOLS",
    # Combined
    "ALL_TOOLS",
    "get_all_tools",
]
