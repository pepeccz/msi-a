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
from agent.services.expediente_helpers import _STEP_PROMPTS
from langchain_core.runnables import RunnableConfig

from agent.state.helpers import get_tool_state
from agent.tools.schemas import (
    ActualizarDatosPersonalesInput,
    ActualizarDatosVehiculoInput,
    ActualizarDatosTallerInput,
    CancelarExpedienteInput,
    ConsultaDuranteExpedienteInput,
    EditarExpedienteInput,
    FinalizarExpedienteInput,
    IniciarExpedienteInput,
    ObtenerEstadoExpedienteInput,
    ReactivarExpedienteInput,
)
from agent.utils.errors import ErrorCategory
from agent.utils.tool_helpers import tool_error_response


# ---------------------------------------------------------------------------
# Backward-compat helpers (re-exported for tests)
# ---------------------------------------------------------------------------


def _vehicle_data_complete(data: dict[str, Any] | None) -> bool:
    """Return True iff all required vehicle fields are present and truthy.

    Required fields: marca, modelo, matricula, anio, bastidor.
    Returns False for None input or any missing/falsy field.
    """
    if not data:
        return False
    return bool(
        all(data.get(k) for k in ("marca", "modelo", "matricula", "anio", "bastidor"))
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool(args_schema=IniciarExpedienteInput)
async def iniciar_expediente(
    categoria_vehiculo: str,
    codigos_elementos: list[str],
    tarifa_calculada: float | None = None,
    tier_id: str | None = None,
    config: RunnableConfig | None = None,
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
    state = get_tool_state(config)
    if not state:
        return {
            "success": False,
            "error": "No se pudo obtener el contexto de la conversación",
        }

    return await case_service.initiate_case(
        categoria_vehiculo=categoria_vehiculo,
        codigos_elementos=codigos_elementos,
        tarifa_calculada=tarifa_calculada,
        tier_id=tier_id,
        conversation_id=state.get("conversation_id", ""),
        user_id=state.get("user_id"),
        client_type=state.get("client_type"),
        state=state,
        mode_context=state.get("mode_context", {}),
    )


@tool(args_schema=ObtenerEstadoExpedienteInput)
async def obtener_estado_expediente(
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
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
    state = get_tool_state(config)
    if not state:
        return tool_error_response(
            message="No se pudo obtener el contexto",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_STATE",
        )

    return await case_service.get_case_status(
        state=state,
    )


@tool(args_schema=ActualizarDatosPersonalesInput)
async def actualizar_datos_personales(
    nombre: str,
    apellidos: str,
    dni_cif: str,
    email: str,
    domicilio_calle: str,
    domicilio_localidad: str,
    domicilio_provincia: str,
    domicilio_cp: str,
    itv_nombre: str,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """
    Guarda los datos personales del titular en el expediente activo.

    **Cuándo llamarla**: SOLO después de que el usuario haya proporcionado
    datos accionables (nombre, DNI, email, dirección, etc.).  No la llames
    en el turno de bienvenida/kickoff — espera a que el usuario responda
    con datos concretos.
    NOTA: NO incluir telefono — ya lo tenemos del numero de WhatsApp.

    Returns:
        Dict con success, message, next_step, missing_fields.
    """
    state = get_tool_state(config)
    if not state:
        return tool_error_response(
            message="No se pudo obtener el contexto",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_STATE",
        )

    # Repackage explicit fields into dict for the service layer
    datos_personales = {
        "nombre": nombre,
        "apellidos": apellidos,
        "dni_cif": dni_cif,
        "email": email,
        "domicilio_calle": domicilio_calle,
        "domicilio_localidad": domicilio_localidad,
        "domicilio_provincia": domicilio_provincia,
        "domicilio_cp": domicilio_cp,
        "itv_nombre": itv_nombre,
    }

    return await case_service.update_personal_data(
        datos_personales=datos_personales,
        datos_vehiculo=None,
        state=state,
    )


@tool(args_schema=ActualizarDatosVehiculoInput)
async def actualizar_datos_vehiculo(
    marca: str | None = None,
    modelo: str | None = None,
    anio: str | None = None,
    matricula: str | None = None,
    bastidor: str | None = None,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """
    Guarda los datos del vehículo en el expediente activo.

    **Cuándo llamarla**: SOLO después de que el usuario haya proporcionado
    datos del vehículo (marca, modelo, matrícula, etc.).  No la llames
    en el turno de bienvenida/kickoff — espera a que el usuario responda.

    Returns:
        Dict con success, message, next_step, missing_fields.
    """
    import structlog as _structlog
    _log = _structlog.get_logger()

    state = get_tool_state(config)
    if not state:
        return tool_error_response(
            message="No se pudo obtener el contexto",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_STATE",
        )

    # ANTI-LLAMADA-VACIA: build dict from non-None, non-empty fields only
    datos_vehiculo: dict[str, str] = {}
    for _field_name, _value in (
        ("marca", marca),
        ("modelo", modelo),
        ("anio", anio),
        ("matricula", matricula),
        ("bastidor", bastidor),
    ):
        if _value is not None and str(_value).strip():
            datos_vehiculo[_field_name] = str(_value).strip()

    if not datos_vehiculo:
        _log.warning("actualizar_datos_vehiculo_empty_payload_blocked")
        return tool_error_response(
            message=(
                "No has enviado ningún dato del vehículo. "
                "Pregúntale al usuario por marca, modelo, año, matrícula y bastidor — "
                "NO llames esta tool si el usuario no proporcionó datos."
            ),
            error_category=ErrorCategory.VALIDATION_ERROR,
            error_code="EMPTY_VEHICLE_PAYLOAD",
        )

    return await case_service.update_personal_data(
        datos_personales=None,
        datos_vehiculo=datos_vehiculo,
        state=state,
    )


@tool(args_schema=ActualizarDatosTallerInput)
async def actualizar_datos_taller(
    taller_propio: bool,
    taller_nombre: str | None = None,
    taller_responsable: str | None = None,
    taller_domicilio: str | None = None,
    taller_provincia: str | None = None,
    taller_ciudad: str | None = None,
    taller_telefono: str | None = None,
    taller_registro_industrial: str | None = None,
    taller_actividad: str | None = None,
    config: RunnableConfig | None = None,
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

    Si taller_propio=True, TODOS los campos taller_* son obligatorios.

    Returns:
        Dict con resultado y siguiente paso
    """
    state = get_tool_state(config)
    if not state:
        return tool_error_response(
            message="No se pudo obtener el contexto",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_STATE",
        )

    # Repackage explicit taller_ fields into dict for the service layer
    datos_taller: dict[str, str] | None = None
    if taller_propio:
        datos_taller = {}
        _field_map = {
            "nombre": taller_nombre,
            "responsable": taller_responsable,
            "domicilio": taller_domicilio,
            "provincia": taller_provincia,
            "ciudad": taller_ciudad,
            "telefono": taller_telefono,
            "registro_industrial": taller_registro_industrial,
            "actividad": taller_actividad,
        }
        for key, value in _field_map.items():
            if value:
                datos_taller[key] = value

    return await case_service.update_workshop_data(
        taller_propio=taller_propio,
        datos_taller=datos_taller,
        state=state,
    )


@tool(args_schema=ConsultaDuranteExpedienteInput)
async def consulta_durante_expediente(
    consulta: str | None = None,
    accion: str = "responder",
    config: RunnableConfig | None = None,
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
    state = get_tool_state(config)
    if not state:
        return tool_error_response(
            message="No se pudo obtener el contexto",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_STATE",
        )

    return await case_service.handle_query_during_case(
        consulta=consulta,
        accion=accion,
        state=state,
    )


@tool(args_schema=CancelarExpedienteInput)
async def cancelar_expediente(
    motivo: str = "Cancelado por el usuario",
    config: RunnableConfig | None = None,
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
    state = get_tool_state(config)
    if not state:
        return tool_error_response(
            message="No se pudo obtener el contexto",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_STATE",
        )

    return await case_service.cancel_case(
        motivo=motivo,
        state=state,
    )


@tool(args_schema=EditarExpedienteInput)
async def editar_expediente(
    seccion: str,
    config: RunnableConfig | None = None,
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
    state = get_tool_state(config)
    if not state:
        return tool_error_response(
            message="No se pudo obtener el contexto",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_STATE",
        )

    return await case_service.edit_case(
        seccion=seccion,
        state=state,
    )


@tool(args_schema=FinalizarExpedienteInput)
async def finalizar_expediente(config: RunnableConfig | None = None) -> dict[str, Any]:
    """
    Completa el expediente y escala a un agente humano para revisión.

    Usa esta herramienta cuando el usuario confirma el resumen del expediente.
    El expediente se marca como pendiente de revisión, se crea una escalación
    y se deshabilita el bot para que un agente humano atienda al cliente.

    Returns:
        Dict con confirmación y ID de escalación
    """
    state = get_tool_state(config)
    if not state:
        return tool_error_response(
            message="No se pudo obtener el contexto",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_STATE",
        )

    return await case_service.finalize_case(
        state=state,
    )


@tool(args_schema=ReactivarExpedienteInput)
async def reactivar_expediente_abandonado(
    case_id: str,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """
    Reactiva un expediente abandonado para continuar la tramitación.

    Usa esta herramienta cuando el usuario confirma que quiere retomar
    un expediente que había quedado abandonado por inactividad.

    Valida que el expediente existe, está en estado 'abandoned', y que
    no existe otro expediente activo para el mismo usuario.

    Args:
        case_id: UUID del expediente abandonado a reactivar.
                 Extraer de mode_context['pending_abandoned_case']['case_id'].

    Returns:
        Dict con:
        - success: bool
        - message: str (confirmación o error en español)
        - case_id: str (si éxito)
        - element_codes: list[str] (si éxito)
        - category_slug: str (si éxito)
        - error: str (si fallo)
    """
    import uuid as _uuid
    from datetime import UTC, datetime as _datetime

    from database.connection import get_async_session
    from database.models import Case
    from sqlalchemy import select as _select

    from agent.services.case_helpers import ACTIVE_STATUSES

    try:
        _uuid.UUID(case_id)
    except ValueError:
        return {"success": False, "error": "ID de expediente no válido"}

    try:
        async with get_async_session() as session:
            case_result = await session.execute(
                _select(Case).where(Case.id == _uuid.UUID(case_id))
            )
            case = case_result.scalar_one_or_none()

            if case is None:
                return {
                    "success": False,
                    "error": f"No se encontró el expediente {case_id}",
                }

            if case.status != "abandoned":
                return {
                    "success": False,
                    "error": (
                        f"El expediente no está abandonado (estado actual: {case.status})"
                    ),
                }

            active_result = await session.execute(
                _select(Case)
                .where(Case.user_id == case.user_id)
                .where(Case.status.in_(ACTIVE_STATUSES))
                .where(Case.id != case.id)
                .limit(1)
            )
            existing_active = active_result.scalar_one_or_none()

            if existing_active is not None:
                return {
                    "success": False,
                    "error": (
                        "No es posible reactivar el expediente porque ya tienes "
                        "otro expediente activo en curso."
                    ),
                }

            now = _datetime.now(UTC)
            case.status = "collecting"
            case.abandoned_at = None
            case.last_activity_at = now
            await session.commit()

            category_slug = case.category.slug if case.category else None

            return {
                "success": True,
                "message": "Expediente reactivado correctamente. Podemos continuar.",
                "case_id": str(case.id),
                "element_codes": case.element_codes or [],
                "category_slug": category_slug,
            }

    except Exception as exc:
        import structlog as _structlog

        _structlog.get_logger(__name__).error(
            "reactivar_expediente_failed",
            case_id=case_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return {
            "success": False,
            "error": "Error interno al reactivar el expediente",
        }


# ---------------------------------------------------------------------------
# Tool list (public API — consumed by mode nodes and graph setup)
# ---------------------------------------------------------------------------

# NOTE: procesar_imagen* tools were removed - images are now handled silently
# in main.py with batching and timeout confirmation
CASE_TOOLS = [
    iniciar_expediente,
    actualizar_datos_personales,
    actualizar_datos_vehiculo,
    actualizar_datos_taller,
    editar_expediente,
    finalizar_expediente,
    cancelar_expediente,
    obtener_estado_expediente,
    consulta_durante_expediente,
    reactivar_expediente_abandonado,
]


def get_case_tools() -> list:
    """Get all case management tools."""
    return CASE_TOOLS
