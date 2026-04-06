"""
MSI Automotive - Case Management Tools for LangGraph Agent.

Thin wrappers over agent.services.case_service.  Each tool:
  1. Reads conversation state from the ContextVar
  2. Delegates ALL business logic to the service
  3. Returns the service result unchanged

Tool LLM descriptions, parameter names, and return shapes are UNCHANGED
from the pre-refactor version so no prompts need to be updated.
"""

from typing import Any

from langchain_core.tools import tool

from agent.services import case_service
from agent.state.helpers import get_current_state
from agent.tools.schemas import (
    ActualizarDatosExpedienteInput,
    ActualizarDatosTallerInput,
    CancelarExpedienteInput,
    ConsultaDuranteExpedienteInput,
    EditarExpedienteInput,
    FinalizarExpedienteInput,
    IniciarExpedienteInput,
    ObtenerEstadoExpedienteInput,
)
from agent.utils.errors import ErrorCategory
from agent.utils.tool_helpers import tool_error_response


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool(args_schema=IniciarExpedienteInput)
async def iniciar_expediente(
    categoria_vehiculo: str,
    codigos_elementos: list[str],
    tarifa_calculada: float | None = None,
    tier_id: str | None = None,
) -> dict[str, Any]:
    """
    Inicia la recolección de datos para abrir un expediente de homologación.

    Usa esta herramienta cuando el usuario acepta abrir un expediente después
    de recibir un presupuesto. Crea un nuevo caso en la base de datos y
    comienza la recolección de datos personales.

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        codigos_elementos: Lista de códigos de elementos a homologar (ej: ["ESCAPE", "ALUMBRADO"])
        tarifa_calculada: Precio calculado sin IVA (opcional)
        tier_id: UUID del tier de tarifa (opcional)

    Returns:
        Dict con:
        - success: bool
        - message: str (prompt para el usuario)
        - case_id: str (si éxito)
        - error: str (si fallo)

    Note: This tool uses defensive validation to ensure categoria_vehiculo and user_id
    are present in state before proceeding, preventing NULL case records.
    """
    state = get_current_state()
    if not state:
        return {"success": False, "error": "No se pudo obtener el contexto de la conversación"}

    return await case_service.initiate_case(
        categoria_vehiculo=categoria_vehiculo,
        codigos_elementos=codigos_elementos,
        tarifa_calculada=tarifa_calculada,
        tier_id=tier_id,
        conversation_id=state.get("conversation_id", ""),
        user_id=state.get("user_id"),
        client_type=state.get("client_type"),
        fsm_state=state.get("fsm_state"),
        state=state,
        mode_context=state.get("mode_context", {}),
    )


@tool(args_schema=ObtenerEstadoExpedienteInput)
async def obtener_estado_expediente() -> dict[str, Any]:
    """
    Obtiene el estado actual del expediente activo.

    Usa esta herramienta para consultar en qué paso se encuentra
    la recolección de datos y qué información falta.

    **Lo que devuelve**: estado de los pasos (current_step), completitud de
    datos personales y del vehículo, estado del taller, precio del expediente,
    y los códigos de los elementos (element_codes).  NO devuelve los datos
    técnicos específicos de cada elemento (fotos, medidas, materiales) — esos
    están en CaseElementData y se gestionan mediante las herramientas de
    element_data_tools.

    Returns:
        Dict con:
        - has_active_case: bool
        - current_step: str (collect_element_data / collect_base_docs / etc.)
        - personal_data_complete: bool
        - vehicle_data_complete: bool
        - taller_propio: bool | None
        - taller_data_complete: bool
        - images_received: int
        - elements: list[str] (códigos de elementos, p. ej. ["ESCAPE", "MANILLAR"])
        - element_status: list[dict] (per-element status: code + status where status is "pending_photos" | "pending_data" | "completed")
        - tariff_amount: float | None
        - precio_certificado: float | None
        - precio_total: float | None
        - data_source: "db" | "fallback"
    """
    state = get_current_state()
    if not state:
        return tool_error_response(
            message="No se pudo obtener el contexto",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_STATE",
        )

    return await case_service.get_case_status(
        fsm_state=state.get("fsm_state"),
        state=state,
    )


@tool(args_schema=ActualizarDatosExpedienteInput)
async def actualizar_datos_expediente(
    datos_personales: dict[str, str] | None = None,
    datos_vehiculo: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Actualiza los datos del expediente activo con informacion del usuario.

    **Cuándo llamarla**: SOLO después de que el usuario haya proporcionado
    datos accionables (nombre, DNI, matrícula, etc.).  No la llames en el
    turno de bienvenida/kickoff al sub-modo — espera a que el usuario
    responda con datos concretos.  Llamarla en un turno sin payload real
    (p. ej. el primer turno de collect_personal donde el LLM solo pregunta
    "¿cuál es tu nombre?") produciría un error de campos faltantes innecesario.

    Args:
        datos_personales: Dict con campos (todos obligatorios):
            - nombre: str
            - apellidos: str
            - dni_cif: str (DNI, NIE o CIF)
            - email: str
            - domicilio_calle: str
            - domicilio_localidad: str
            - domicilio_provincia: str
            - domicilio_cp: str (codigo postal)
            - itv_nombre: str (nombre de la estacion ITV donde se realizara la homologacion)
            NOTA: NO incluir telefono — ya lo tenemos del numero de WhatsApp del usuario.
        datos_vehiculo: Dict con campos opcionales:
            - marca: str
            - modelo: str
            - anio: str (año del vehiculo)
            - matricula: str
            - bastidor: str (opcional)

    Returns:
        Dict con:
        - success: bool
        - message: str (siguiente prompt o confirmacion)
        - next_step: str (siguiente paso del FSM)
        - missing_fields: list[str] (campos que faltan)

    Note: This tool uses defensive decorators to validate email, phone, and DNI formats
    before processing, preventing corrupted data from reaching the database.
    """
    state = get_current_state()
    if not state:
        return tool_error_response(
            message="No se pudo obtener el contexto",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_STATE",
        )

    return await case_service.update_personal_data(
        datos_personales=datos_personales,
        datos_vehiculo=datos_vehiculo,
        fsm_state=state.get("fsm_state"),
        state=state,
    )


@tool(args_schema=ActualizarDatosTallerInput)
async def actualizar_datos_taller(
    taller_propio: bool | None = None,
    datos_taller: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Actualiza los datos del taller/certificado en el expediente.

    MSI NO tiene talleres propios. El "certificado del taller" es un documento legal
    requerido para la ITV que certifica que la instalación fue realizada por un taller
    registrado. MSI puede gestionar este certificado por CERT_SUPPLEMENT_EUR€ +IVA, o el cliente puede
    aportar su propio taller registrado.

    Usa esta herramienta cuando el usuario decide sobre el certificado del taller:
    - taller_propio=False → MSI gestiona el certificado (CERT_SUPPLEMENT_EUR€ +IVA adicional)
    - taller_propio=True → El cliente aporta taller propio (sin coste adicional)

    Args:
        taller_propio: None para preguntar, False si MSI aporta certificado,
                       True si el cliente usa su propio taller
        datos_taller: Dict con datos del taller (TODOS son obligatorios si taller_propio=True):
            - nombre: Nombre del taller (ej: "Taller García")
            - responsable: Nombre del responsable (ej: "Luis Martínez")
            - domicilio: Dirección completa (ej: "C/ Industrial 10, Polígono Norte")
            - provincia: Provincia (ej: "Madrid")
            - ciudad: Ciudad (ej: "Alcobendas")
            - telefono: Teléfono de contacto (ej: "912345678")
            - registro_industrial: Número de registro industrial (ej: "TAL-12345")
            - actividad: Actividad del taller (ej: "reparación de motocicletas")

    Ejemplo de llamada completa:
        actualizar_datos_taller(
            taller_propio=True,
            datos_taller={
                "nombre": "Taller García",
                "responsable": "Luis Martínez",
                "domicilio": "C/ Industrial 10",
                "provincia": "Madrid",
                "ciudad": "Alcobendas",
                "telefono": "912345678",
                "registro_industrial": "TAL-12345",
                "actividad": "reparación de motocicletas"
            }
        )

    Returns:
        Dict con resultado y siguiente paso
    """
    state = get_current_state()
    if not state:
        return tool_error_response(
            message="No se pudo obtener el contexto",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_STATE",
        )

    return await case_service.update_workshop_data(
        taller_propio=taller_propio,
        datos_taller=datos_taller,
        fsm_state=state.get("fsm_state"),
        state=state,
    )


@tool(args_schema=ConsultaDuranteExpedienteInput)
async def consulta_durante_expediente(
    consulta: str | None = None,
    accion: str = "responder",
) -> dict[str, Any]:
    """
    Maneja consultas y acciones del usuario durante un expediente activo.

    Usa esta herramienta cuando el usuario:
    - Hace una pregunta no relacionada con el paso actual del expediente
    - Quiere cancelar el expediente
    - Necesita pausar para hacer algo más
    - Quiere reanudar después de una pausa

    Args:
        consulta: La pregunta o solicitud del usuario (opcional)
        accion: Tipo de acción:
            - "responder": Responder consulta sin perder el contexto del expediente
            - "cancelar": Cancelar el expediente (delega a cancelar_expediente)
            - "pausar": Pausar temporalmente para atender otra cosa
            - "reanudar": Continuar con el expediente después de una pausa

    Returns:
        Dict con instrucciones sobre cómo proceder
    """
    state = get_current_state()
    if not state:
        return tool_error_response(
            message="No se pudo obtener el contexto",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_STATE",
        )

    return await case_service.handle_query_during_case(
        consulta=consulta,
        accion=accion,
        fsm_state=state.get("fsm_state"),
        state=state,
    )


@tool(args_schema=CancelarExpedienteInput)
async def cancelar_expediente(
    motivo: str = "Cancelado por el usuario",
) -> dict[str, Any]:
    """
    Cancela el expediente activo.

    Usa esta herramienta cuando el usuario quiere cancelar el proceso
    de recolección de datos.

    Args:
        motivo: Razón de la cancelación

    Returns:
        Dict con confirmación
    """
    state = get_current_state()
    if not state:
        return tool_error_response(
            message="No se pudo obtener el contexto",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_STATE",
        )

    return await case_service.cancel_case(
        motivo=motivo,
        fsm_state=state.get("fsm_state"),
        state=state,
    )


@tool(args_schema=EditarExpedienteInput)
async def editar_expediente(
    seccion: str,
) -> dict[str, Any]:
    """
    Permite al usuario volver a editar una sección anterior del expediente.

    Solo funciona durante la revisión del resumen (REVIEW_SUMMARY).
    El usuario puede volver a editar datos personales, del vehículo, del taller,
    o la documentación base. NO permite volver a la recolección de datos de elementos.

    Args:
        seccion: Sección a editar. Valores válidos:
            - "personal": Volver a datos personales
            - "vehiculo": Volver a datos del vehículo
            - "taller": Volver a datos del taller
            - "documentacion" o "docs": Volver a documentación base

    Returns:
        Dict con:
        - success: bool
        - message: str (instrucciones para la sección)
        - next_step: str
        - case_collection_update: dict (nuevo estado FSM)

    Ejemplo de uso:
        Usuario: "Quiero cambiar mi email"
        -> editar_expediente(seccion="personal")

        Usuario: "La matrícula está mal"
        -> editar_expediente(seccion="vehiculo")
    """
    state = get_current_state()
    if not state:
        return tool_error_response(
            message="No se pudo obtener el contexto",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_STATE",
        )

    return await case_service.edit_case(
        seccion=seccion,
        fsm_state=state.get("fsm_state"),
        state=state,
    )


@tool(args_schema=FinalizarExpedienteInput)
async def finalizar_expediente() -> dict[str, Any]:
    """
    Completa el expediente y escala a un agente humano para revisión.

    Usa esta herramienta cuando el usuario confirma el resumen del expediente.
    El expediente se marca como pendiente de revisión, se crea una escalación
    y se deshabilita el bot para que un agente humano atienda al cliente.

    Returns:
        Dict con confirmación y ID de escalación
    """
    state = get_current_state()
    if not state:
        return tool_error_response(
            message="No se pudo obtener el contexto",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_STATE",
        )

    return await case_service.finalize_case(
        fsm_state=state.get("fsm_state"),
        state=state,
    )


# ---------------------------------------------------------------------------
# Tool list (public API — consumed by tool_manager.py and graph setup)
# ---------------------------------------------------------------------------

# NOTE: procesar_imagen* tools were removed - images are now handled silently
# in main.py with batching and timeout confirmation
CASE_TOOLS = [
    iniciar_expediente,
    actualizar_datos_expediente,
    actualizar_datos_taller,
    editar_expediente,
    finalizar_expediente,
    cancelar_expediente,
    obtener_estado_expediente,
    consulta_durante_expediente,
]


def get_case_tools() -> list:
    """Get all case management tools."""
    return CASE_TOOLS
