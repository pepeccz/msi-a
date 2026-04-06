"""
MSI Automotive - Element Data Collection Tools for LangGraph Agent.

Thin wrappers over agent.services.element_data_service.
Each function extracts context from state and delegates to the service;
all business logic lives in the service.

Flow per element:
1. Show example images for the element
2. User sends photos (can be batched)
3. User says "listo" -> confirmar_fotos_elemento()
4. Ask required data fields (one by one or multiple)
5. Validate and save with guardar_datos_elemento()
6. Move to next element with completar_elemento_actual()
"""

from typing import Any

import structlog
from langchain_core.tools import tool

from agent.services.element_data_service import (
    get_element_fields,
    save_element_data,
    confirm_element_photos,
    complete_current_element,
    get_element_progress,
    confirm_base_documentation,
    resend_element_images,
)
from agent.state.helpers import get_current_state
from agent.tools.schemas import (
    ObtenerCamposElementoInput,
    GuardarDatosElementoInput,
    ConfirmarFotosElementoInput,
    CompletarElementoActualInput,
    ObtenerProgresoElementosInput,
    ConfirmarDocumentacionBaseInput,
    ReenviarImagenesElementoInput,
)
from agent.utils.expediente_types import CollectionStep
from agent.utils.tool_helpers import tool_error_response

logger = structlog.get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Turn-level idempotency guard for confirmar_fotos_elemento (REQ-IMG-3).
#
# Key format: "{case_id}:{element_code}"
# Intentionally NOT Redis-backed — guard is per-turn (in-memory).
# ─────────────────────────────────────────────────────────────────────────────
_photos_confirmed_this_turn: set[str] = set()


# =============================================================================
# Helpers
# =============================================================================


def _require_state() -> dict[str, Any] | None:
    """Return current state or None."""
    return get_current_state()


def _get_mode_context(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("mode_context") or {}


def _require_expediente(
    state: dict[str, Any],
) -> tuple[str | None, str | None, list[str]]:
    """Extract case_id, category_id, element_codes from mode_context."""
    mc = _get_mode_context(state)
    return (
        mc.get("case_id"),
        mc.get("category_id"),
        mc.get("element_codes") or [],
    )


# =============================================================================
# Tools
# =============================================================================


@tool(args_schema=ObtenerCamposElementoInput)
async def obtener_campos_elemento(element_code: str | None = None) -> dict[str, Any]:
    """
    Obtener los campos requeridos para el elemento actual o especificado.

    Usa esta herramienta para saber qué datos técnicos necesitas recoger
    del usuario para un elemento específico.

    Args:
        element_code: Código del elemento (opcional, usa el actual si no se especifica)

    Returns:
        Lista de campos requeridos con sus tipos, etiquetas e instrucciones.
    """
    state = _require_state()
    if not state:
        return tool_error_response("No hay estado de conversación activo")

    case_id, category_id, element_codes = _require_expediente(state)
    if not case_id:
        return tool_error_response("No hay expediente activo")

    current_step_val = _get_mode_context(state).get(
        "expediente_sub_mode", CollectionStep.IDLE.value
    )
    if current_step_val != CollectionStep.COLLECT_ELEMENT_DATA.value:
        # V2 path bypasses the step check — delegate unconditionally
        pass

    return await get_element_fields(
        element_code=element_code,
        case_id=case_id,
        category_id=category_id or "",
        element_codes=element_codes,
        mode_context=_get_mode_context(state),
    )


@tool(args_schema=GuardarDatosElementoInput)
async def guardar_datos_elemento(
    datos: dict[str, Any],
    element_code: str | None = None,
) -> dict[str, Any]:
    """
    Guardar datos técnicos para el elemento actual.

    IMPORTANTE: TÚ (el agente) debes extraer los valores del mensaje del usuario
    y mapearlos a los field_key correctos ANTES de llamar a esta herramienta.
    La herramienta NO extrae datos del mensaje - solo valida y guarda lo que le pases.

    Args:
        datos: Diccionario {field_key: valor} con los datos ya extraídos.
               Los field_key DEBEN ser los devueltos por obtener_campos_elemento().
        element_code: Código del elemento (opcional, usa el actual si no se especifica)
    """
    state = _require_state()
    if not state:
        return tool_error_response("No hay estado de conversación activo")

    mc = _get_mode_context(state)
    case_id = mc.get("case_id")
    category_id = mc.get("category_id")

    if not case_id or not category_id:
        return tool_error_response("Expediente no configurado correctamente")

    current_step_val = mc.get("expediente_sub_mode", CollectionStep.IDLE.value)
    if current_step_val != CollectionStep.COLLECT_ELEMENT_DATA.value:
        return tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_ELEMENT_DATA. "
            f"Paso actual: {current_step_val}",
        )

    return await save_element_data(
        datos=datos,
        element_code=element_code,
        case_id=case_id,
        category_id=category_id,
        mode_context=mc,
    )


@tool(args_schema=ConfirmarFotosElementoInput)
async def confirmar_fotos_elemento(
    usuario_confirma: bool | None = None,
) -> dict[str, Any]:
    """
    Confirmar que el usuario ha enviado todas las fotos del elemento actual.

    Usa esta herramienta cuando el usuario diga "listo" o similar
    después de enviar las fotos de un elemento.

    Después de confirmar, automáticamente pasamos a recoger los datos
    técnicos del elemento (si tiene campos requeridos).

    Args:
        usuario_confirma: True si el usuario confirma explícitamente que ya envió
                         las fotos. Solo usa este parámetro si preguntaste al
                         usuario y respondió afirmativamente.

    Returns:
        Estado actualizado y próximo paso.
    """
    state = _require_state()
    if not state:
        return tool_error_response("No hay estado de conversación activo")

    mc = _get_mode_context(state)
    case_id = mc.get("case_id")
    category_id = mc.get("category_id")
    conversation_id = state.get("conversation_id")

    if not case_id or not category_id:
        return tool_error_response("Expediente no configurado correctamente")

    current_step_val = mc.get("expediente_sub_mode", CollectionStep.IDLE.value)
    if current_step_val != CollectionStep.COLLECT_ELEMENT_DATA.value:
        return tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_ELEMENT_DATA. "
            f"Paso actual: {current_step_val}",
        )

    # Resolve element code for idempotency key
    element_codes = mc.get("element_codes") or []
    current_idx = mc.get("current_element_index", 0)
    current_element_code = (
        element_codes[current_idx] if element_codes and current_idx < len(element_codes) else None
    )

    idempotency_key = f"{case_id}:{current_element_code}" if current_element_code else ""
    already_confirmed = idempotency_key in _photos_confirmed_this_turn

    # Resolve active batch
    active_batch_id: str | None = None
    try:
        from agent.services.case_image_batch_service import (
            build_upload_scope,
            get_case_image_batch_service,
        )

        active_scope = build_upload_scope(
            case_id=case_id,
            expediente_sub_mode="collect_element_data",
            element_code=current_element_code,
        )
        active_batch = (
            await get_case_image_batch_service().resolve_for_scope(
                active_scope, allow_create=False
            )
            if active_scope
            else None
        )
        active_batch_id = active_batch.batch_id if active_batch else None
    except Exception:
        pass

    result = await confirm_element_photos(
        case_id=case_id,
        category_id=category_id,
        mode_context=mc,
        usuario_confirma=usuario_confirma,
        conversation_id=conversation_id,
        active_batch_id=active_batch_id,
        idempotency_key=idempotency_key,
        already_confirmed_this_turn=already_confirmed,
    )

    # Register idempotency key if photos were freshly confirmed
    if result.get("success") and result.get("photos_confirmed") and not already_confirmed:
        _photos_confirmed_this_turn.add(idempotency_key)

    return result


@tool(args_schema=CompletarElementoActualInput)
async def completar_elemento_actual() -> dict[str, Any]:
    """
    Marcar el elemento actual como completo y pasar al siguiente.

    Usa esta herramienta cuando todos los datos requeridos del elemento
    han sido recogidos y validados.

    Returns:
        Información sobre el siguiente elemento o paso.
    """
    state = _require_state()
    if not state:
        return tool_error_response("No hay estado de conversación activo")

    mc = _get_mode_context(state)
    case_id = mc.get("case_id")
    category_id = mc.get("category_id")

    if not case_id or not category_id:
        return tool_error_response("Expediente no configurado correctamente")

    current_step_val = mc.get("expediente_sub_mode", CollectionStep.IDLE.value)
    if current_step_val != CollectionStep.COLLECT_ELEMENT_DATA.value:
        return tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_ELEMENT_DATA. "
            f"Paso actual: {current_step_val}",
        )

    return await complete_current_element(
        case_id=case_id,
        category_id=category_id,
        mode_context=mc,
    )


@tool(args_schema=ObtenerProgresoElementosInput)
async def obtener_progreso_elementos() -> dict[str, Any]:
    """
    Obtener el progreso actual de la recolección de elementos.

    Returns:
        Información sobre el progreso de cada elemento.
    """
    state = _require_state()
    if not state:
        return tool_error_response("No hay estado de conversación activo")

    return await get_element_progress(mode_context=_get_mode_context(state))


@tool(args_schema=ConfirmarDocumentacionBaseInput)
async def confirmar_documentacion_base(
    usuario_confirma: bool | None = None,
) -> dict[str, Any]:
    """
    Confirmar que el usuario ha enviado la documentación base.

    **Fuente de verdad única**: esta es la ÚNICA herramienta que puede
    certificar que la documentación base ha sido recibida.  Nunca declares
    "he recibido tu documentación" ni "documentación completa/confirmada"
    sin que esta herramienta devuelva ``success=True``.

    La documentación base incluye:
    - Ficha técnica del vehículo
    - Permiso de circulación
    - Vistas del vehículo (frontal, laterales, trasera)

    Usa esta herramienta SOLO cuando el usuario confirme en tiempo pasado
    que ya los envió ("ya los mandé", "listo", "enviado").  No la llames
    en el turno de bienvenida/kickoff al sub-modo collect_base_docs —
    espera a que el usuario confirme el envío primero.

    Args:
        usuario_confirma: True si el usuario confirma explícitamente que ya envió
                         las imágenes. Solo usa este parámetro si preguntaste al
                         usuario y respondió afirmativamente.

    Returns:
        Estado actualizado, siguiente paso es COLLECT_PERSONAL.
    """
    state = _require_state()
    if not state:
        return tool_error_response("No hay estado de conversación activo")

    mc = _get_mode_context(state)
    case_id = mc.get("case_id")
    conversation_id = state.get("conversation_id")

    if not case_id:
        return tool_error_response("No hay expediente activo")

    return await confirm_base_documentation(
        usuario_confirma=usuario_confirma,
        case_id=case_id,
        conversation_id=conversation_id,
        mode_context=mc,
    )


@tool(args_schema=ReenviarImagenesElementoInput)
async def reenviar_imagenes_elemento(element_code: str | None = None) -> dict[str, Any]:
    """
    Reenviar las imágenes de ejemplo para el elemento actual o especificado.

    Usa esta herramienta cuando el usuario pide ver las imágenes de
    ejemplo de nuevo.

    Args:
        element_code: Código del elemento (opcional, usa el actual si no se especifica)

    Returns:
        Información del elemento para que puedas mostrar sus imágenes de ejemplo.
    """
    state = _require_state()
    if not state:
        return tool_error_response("No hay estado de conversación activo")

    mc = _get_mode_context(state)
    case_id = mc.get("case_id")
    category_id = mc.get("category_id")
    conversation_id = state.get("conversation_id", "unknown")

    if not case_id:
        return tool_error_response("No hay expediente activo")

    current_step_val = mc.get("expediente_sub_mode", CollectionStep.IDLE.value)
    if current_step_val != CollectionStep.COLLECT_ELEMENT_DATA.value:
        return tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_ELEMENT_DATA. "
            f"Paso actual: {current_step_val}",
        )

    if not category_id:
        return tool_error_response("No hay categoría definida en el expediente")

    return await resend_element_images(
        element_code=element_code,
        case_id=case_id,
        category_id=category_id,
        mode_context=mc,
        conversation_id=conversation_id,
    )


# =============================================================================
# Export all tools
# =============================================================================

element_data_tools = [
    obtener_campos_elemento,
    guardar_datos_elemento,
    confirmar_fotos_elemento,
    completar_elemento_actual,
    obtener_progreso_elementos,
    confirmar_documentacion_base,
    reenviar_imagenes_elemento,
]
