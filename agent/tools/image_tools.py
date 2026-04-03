"""
MSI Automotive - Image Tools for Agent.

Tools for sending example images to users during conversations.
"""

import logging
import uuid as uuid_mod
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Literal

from langchain_core.tools import tool

from agent.utils.expediente_types import CollectionStep
from agent.services.element_service import get_element_service
from agent.tools.element_tools import get_or_fetch_category_id
from agent.utils.errors import ErrorCategory, handle_tool_errors
from agent.utils.tool_helpers import tool_error_response
from agent.state.helpers import (
    get_current_state,
    set_current_state,
    clear_current_state,
)

logger = logging.getLogger(__name__)

IMAGE_DELIVERY_CONTRACT_VERSION = "v1"

# Ephemeral per-turn dedup guard for tipo="elemento" image sends.
# Keyed by "{conversation_id}:{element_code.upper()}".
# Reset at the start of each COLLECT_ELEMENT_DATA handler turn.
_element_images_sent_this_turn: set[str] = set()


def _clear_element_images_sent_this_turn() -> None:
    """Reset the intra-turn dedup set. Called at the start of each agent turn by expediente_mode."""
    _element_images_sent_this_turn.clear()


# T2.5: _current_state ContextVar removed — image_tools now uses the shared
# ContextVar from agent.state.helpers (get_current_state / set_current_state).
# This eliminates the dual-ContextVar pattern (REQ-P2-2).

# _pending_images_result remains here: it is specific to image tools and
# carries queued image payloads between tool execution and the main loop.
_pending_images_result: ContextVar[dict[str, Any] | None] = ContextVar(
    "image_tools_pending_result", default=None
)


def set_current_state_for_image_tools(state: dict[str, Any]) -> None:
    """
    Backward-compat alias — delegates to the shared set_current_state().

    T2.5: This function is retained so that existing call sites in the OLD
    (non-generic) loop paths (loop_engine.py, review_summary.py, old mode
    paths) continue to work without modification. Callers in the generic path
    (generic_loop.py, _process_with_generic_loop methods) are cleaned up in
    T2.5b and no longer call this function.

    New code should call set_current_state() from agent.state.helpers directly.
    """
    set_current_state(state)


def get_pending_images_result() -> dict[str, Any] | None:
    """Get the pending images result after tool execution."""
    result = _pending_images_result.get()
    _pending_images_result.set(None)  # Clear after reading
    return result


def set_pending_images_result(result: dict[str, Any]) -> None:
    """
    Set the pending images result to be sent after tool execution.

    Used by tools that need to queue images for sending (e.g., reenviar_imagenes_elemento).

    Args:
        result: Dict containing 'images' list and optional 'follow_up_message'
    """
    _pending_images_result.set(result)


def clear_image_tools_state() -> None:
    """Clear the image tools state after processing."""
    clear_current_state()
    _pending_images_result.set(None)


def _build_delivery_intent_outcome(
    *,
    delivery_request_id: str,
    delivery_scope: str,
    requested_count: int,
) -> dict[str, Any]:
    """Build explicit intent-only outcome state for mode_context."""
    return {
        "status": "intent_created",
        "request_id": delivery_request_id,
        "scope": delivery_scope,
        "requested_count": requested_count,
        "attempted_count": 0,
        "sent_count": 0,
        "failed_count": requested_count,
        "transport_error": None,
        "updated_at": datetime.now(UTC).isoformat(),
    }


@tool
@handle_tool_errors(
    error_category=ErrorCategory.DATABASE_ERROR,
    error_code="IMAGE_SEND_FAILED",
    user_message="Lo siento, hubo un problema al preparar las imágenes. ¿Puedes intentarlo de nuevo?",
)
async def enviar_imagenes_ejemplo(
    tipo: Literal["presupuesto", "elemento", "documentacion_base"] = "presupuesto",
    codigo_elemento: str | None = None,
    categoria: str | None = None,
    follow_up_message: str | None = None,
) -> dict[str, Any]:
    """
    Encola imagenes de ejemplo para enviar al usuario.

    CUANDO USAR:
    - tipo="presupuesto": Despues de calcular_tarifa_con_elementos, para enviar TODAS
      las imagenes del presupuesto (base + elementos).
    - tipo="elemento": Cuando el usuario pregunta especificamente por un elemento
      (ej: "como debe ser la foto del escape?")
    - tipo="documentacion_base": Durante COLLECT_BASE_DOCS, para enviar imagenes de ejemplo
      de la documentacion obligatoria (ficha tecnica, permiso, etc.)

    PARAMETROS:
    - tipo: "presupuesto" (todas del presupuesto), "elemento" (especificas), o "documentacion_base"
    - codigo_elemento: Requerido si tipo="elemento" (ej: "ESCAPE", "SUBCHASIS")
    - categoria: Requerido si tipo="elemento" o tipo="documentacion_base" (ej: "motos-part", "aseicars-prof")
    - follow_up_message: Mensaje a enviar DESPUES de las imagenes.
      Util para preguntar si quiere abrir expediente despues de mostrar las fotos.

    FLUJO DE ENVIO:
    1. Tu mensaje de texto se envia primero
    2. Luego se envian las imagenes (una por una)
    3. Por ultimo se envia el follow_up_message (si lo especificaste)

    EJEMPLO PRESUPUESTO:
    Despues de calcular tarifa, llama:
    enviar_imagenes_ejemplo(
        tipo="presupuesto",
        follow_up_message="Te gustaria que te abriera un expediente para gestionar tu homologacion?"
    )

    EJEMPLO ELEMENTO ESPECIFICO:
    Si usuario pregunta por fotos del escape:
    enviar_imagenes_ejemplo(
        tipo="elemento",
        codigo_elemento="ESCAPE",
        categoria="motos-part"
    )

    EJEMPLO DOCUMENTACION BASE:
    Durante COLLECT_BASE_DOCS, si usuario pide ejemplos:
    enviar_imagenes_ejemplo(
        tipo="documentacion_base",
        categoria="motos-part"
    )

    REFACTOR-001 Note: This tool assumes precio_comunicado=True because it should
    only be called AFTER calcular_tarifa_con_elementos (which sets that flag). The
    LLM is prompted to follow this sequence. Safety is enforced by the system prompt,
    not by explicit validation in the tool.

    Returns:
        Confirmacion con numero de imagenes encoladas, o mensaje de error/info
    """
    # Get state from the shared ContextVar (async-safe, no globals).
    # T2.5: Uses get_current_state() from agent.state.helpers (shared ContextVar).
    state = get_current_state()

    conversation_id = state.get("conversation_id", "unknown") if state else "unknown"

    logger.info(
        f"[enviar_imagenes_ejemplo] Called | tipo={tipo} | elemento={codigo_elemento} | "
        f"categoria={categoria} | has_follow_up={bool(follow_up_message)}",
        extra={"conversation_id": conversation_id},
    )

    # PROTECTION: Check if images were already sent for current quote
    if tipo == "presupuesto" and state:
        mode_context = state.get("mode_context", {})
        if mode_context.get("imagenes_enviadas"):
            logger.warning(
                f"[enviar_imagenes_ejemplo] Images already sent for this quote, blocking duplicate | "
                f"conversation_id={conversation_id}",
                extra={"conversation_id": conversation_id},
            )
            return {
                "success": False,
                "message": (
                    "Las imagenes de ejemplo ya fueron enviadas para este presupuesto. "
                    "Si el usuario quiere abrir un expediente, usa iniciar_expediente(). "
                    "NO vuelvas a enviar imagenes."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

    images_to_queue: list[dict[str, Any]] = []

    if tipo == "presupuesto":
        # Get images from last calculated tarifa
        if not state:
            logger.warning("[enviar_imagenes_ejemplo] No state available")
            return {
                "success": False,
                "message": "Error interno: no hay estado disponible.",
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        # Get mode_context from state (passed by PRESUPUESTO/EXPEDIENTE via full_state pattern)
        mode_context = state.get("mode_context", {})

        # EXPEDIENTE_MODE guard: tipo='presupuesto' is invalid in EXPEDIENTE_MODE.
        # Price and example images were already handled in PRESUPUESTO_MODE.
        # The LLM should use iniciar_expediente() or tipo='elemento' instead.
        if state.get("current_mode") == "EXPEDIENTE_MODE":
            logger.warning(
                "[enviar_imagenes_ejemplo] blocked_in_expediente_mode | "
                "tipo='presupuesto' called from EXPEDIENTE_MODE",
                extra={"conversation_id": conversation_id},
            )
            return {
                "success": False,
                "message": (
                    "El precio ya fue comunicado durante el presupuesto y las imágenes de ejemplo "
                    "ya fueron enviadas. Estás en EXPEDIENTE_MODE: usa iniciar_expediente() para "
                    "crear el expediente de homologación, o tipo='elemento' con codigo_elemento "
                    "para fotos de un elemento específico. No uses tipo='presupuesto' en esta fase."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        if not mode_context.get("precio_comunicado"):
            logger.warning(
                "[enviar_imagenes_ejemplo] blocked_without_price_communication",
                extra={"conversation_id": conversation_id},
            )
            return {
                "success": False,
                "message": (
                    "Aun no se ha comunicado el precio del presupuesto actual. "
                    "Primero comunica el precio y luego envia imagenes de ejemplo."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        # DEBUG: Log detailed state information
        logger.info(
            "[enviar_imagenes_ejemplo] State inspection",
            extra={
                "conversation_id": conversation_id,
                "mode_context_keys": list(mode_context.keys()) if mode_context else [],
                "precio_comunicado": mode_context.get("precio_comunicado"),
                "precio_comunicado_type": type(
                    mode_context.get("precio_comunicado")
                ).__name__
                if mode_context
                else None,
                "tarifa_calculada_exists": bool(mode_context.get("tarifa_calculada")),
                "state_keys": list(state.keys()) if state else [],
            },
        )

        # Check tarifa_calculada in mode_context (NOT root state)
        tarifa_calculada = mode_context.get("tarifa_calculada")
        if not tarifa_calculada:
            logger.warning(
                f"[enviar_imagenes_ejemplo] No tarifa_calculada in mode_context",
                extra={"conversation_id": conversation_id},
            )
            return {
                "success": False,
                "message": (
                    "⚠️ CRITICAL INSTRUCTION FOR LLM ⚠️\n"
                    "No hay presupuesto calculado todavia.\n\n"
                    "DO NOT generate fake URLs or image links.\n"
                    "DO NOT list URLs like 'storage.chatwoot.com/...' or any other invented links.\n\n"
                    "Instead, tell the user:\n"
                    "'Primero necesito calcular el presupuesto para poder mostrarte las fotos de ejemplo. "
                    "¿Me confirmas los elementos que quieres homologar?'"
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        # Guardrail: presupuesto images must match the currently active budget scope.
        # If selected element codes differ from the current mode context, reject sending
        # to avoid leaking stale images from a previous quote.
        current_codes_raw = mode_context.get("element_codes", [])
        tarifa_codes_raw = (tarifa_calculada.get("datos") or {}).get(
            "element_codes"
        ) or []
        current_codes = {str(code).upper() for code in current_codes_raw if code}
        tarifa_codes = {str(code).upper() for code in tarifa_codes_raw if code}
        if current_codes and tarifa_codes and current_codes != tarifa_codes:
            logger.warning(
                "[enviar_imagenes_ejemplo] blocked_stale_budget_scope",
                extra={
                    "conversation_id": conversation_id,
                    "current_codes": sorted(current_codes),
                    "tarifa_codes": sorted(tarifa_codes),
                },
            )
            return {
                "success": False,
                "message": (
                    "El presupuesto disponible no coincide con los elementos activos de esta conversación. "
                    "Recalcula el presupuesto actual antes de enviar imágenes."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        imagenes = tarifa_calculada.get("imagenes_ejemplo", [])
        if not imagenes:
            logger.info(
                f"[enviar_imagenes_ejemplo] Tarifa has no example images (likely already sent)",
                extra={"conversation_id": conversation_id},
            )
            return {
                "success": False,
                "message": (
                    "Las imagenes de ejemplo ya fueron enviadas anteriormente en esta conversacion. "
                    "NO las envies de nuevo - el usuario ya las vio arriba en el chat. "
                    "Si el usuario acepto abrir expediente, usa iniciar_expediente(). "
                    "Si el usuario pregunta por las fotos, dile que las revise en los mensajes anteriores."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        # Filter: only queue images with status "active" (not placeholder/unavailable)
        images_to_queue = [
            img for img in imagenes if img.get("status", "placeholder") == "active"
        ]
        if not images_to_queue:
            logger.info(
                f"[enviar_imagenes_ejemplo] All {len(imagenes)} images are placeholder/unavailable",
                extra={"conversation_id": conversation_id},
            )
            return {
                "success": False,
                "message": (
                    "⚠️ CRITICAL INSTRUCTION FOR LLM ⚠️\n"
                    "No hay imagenes de ejemplo disponibles para esta homologacion "
                    "(las imagenes aun no han sido configuradas por el administrador).\n\n"
                    "DO NOT generate fake URLs or image links.\n"
                    "DO NOT list URLs like 'storage.chatwoot.com/...' or any other invented links.\n\n"
                    "Instead, tell the user:\n"
                    "'En este momento no tengo fotos de ejemplo disponibles para esta homologación, "
                    "pero puedo explicarte qué documentación necesitarás basándome en el presupuesto. "
                    "¿Te parece?'\n\n"
                    "Then describe the required documentation using ONLY the data from the 'documentacion' "
                    "field in the calculated tariff. DO NOT invent documentation requirements."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        logger.info(
            f"[enviar_imagenes_ejemplo] Queuing {len(images_to_queue)} active images from tarifa "
            f"(filtered from {len(imagenes)} total)",
            extra={"conversation_id": conversation_id},
        )

    elif tipo == "elemento":
        if not codigo_elemento:
            return {
                "success": False,
                "message": "Para tipo='elemento' debes especificar el codigo_elemento (ej: 'ESCAPE', 'SUBCHASIS').",
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        if not categoria:
            return {
                "success": False,
                "message": "Para tipo='elemento' debes especificar la categoria (ej: 'motos-part', 'aseicars-prof').",
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        # ── EXPEDIENTE_MODE category override ───────────────────────────────
        # In EXPEDIENTE_MODE the active case category is stored in
        # mode_context["categoria_slug"] and is authoritative.  The LLM
        # sometimes passes the wrong category (e.g. "motos-part" when the
        # case is "aseicars-prof"), causing the element look-up to fail and
        # the conversation to escalate unnecessarily.
        # Fix: when we're in EXPEDIENTE_MODE and state carries the correct
        # category, silently override the LLM-supplied value.
        if state and state.get("current_mode") == "EXPEDIENTE_MODE":
            _state_categoria = state.get("mode_context", {}).get("categoria_slug")
            if _state_categoria and _state_categoria != categoria:
                logger.warning(
                    "imagen_categoria_override_from_state | "
                    f"llm_categoria={categoria} → state_categoria={_state_categoria}",
                    extra={
                        "conversation_id": conversation_id,
                        "llm_categoria": categoria,
                        "state_categoria": _state_categoria,
                    },
                )
                categoria = _state_categoria
        # ────────────────────────────────────────────────────────────────────

        # ── Intra-turn dedup guard ───────────────────────────────────────────
        # Prevent the same element's images being sent twice in a single turn.
        # This can happen when a constraint retry causes the LLM to call this
        # tool again after it already fired successfully earlier in the same turn.
        _dedup_key = f"{conversation_id}:{(codigo_elemento or '').upper()}"
        if _dedup_key in _element_images_sent_this_turn:
            logger.warning(
                "[enviar_imagenes_ejemplo] duplicate_elemento_blocked | "
                f"element={codigo_elemento} already sent this turn",
                extra={"conversation_id": conversation_id},
            )
            return {
                "success": False,
                "message": (
                    f"Las imágenes del elemento {codigo_elemento} ya fueron enviadas en este turno. "
                    "El usuario las verá en el chat. Continúa con el siguiente paso del flujo "
                    "(confirmar_fotos_elemento si el usuario ya las envió, o esperar a que las envíe)."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        # Register BEFORE queuing so any exception path doesn't leak through
        _element_images_sent_this_turn.add(_dedup_key)
        # ────────────────────────────────────────────────────────────────────

        # Initialize code_upper early for consistent logging (prevents UnboundLocalError)
        code_upper = codigo_elemento.upper()

        # Get element service and find element
        element_service = get_element_service()
        category_id = await get_or_fetch_category_id(categoria)

        if not category_id:
            logger.warning(
                f"[enviar_imagenes_ejemplo] Category not found: {categoria}",
                extra={"conversation_id": conversation_id},
            )
            return {
                "success": False,
                "message": f"Categoria '{categoria}' no encontrada en el sistema.",
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        # Get all elements to find by code
        elements = await element_service.get_elements_by_category(
            category_id, is_active=True
        )
        element_by_code = {e["code"].upper(): e for e in elements}

        # Use fuzzy matching to auto-correct common LLM errors (ASIDERO → ASIDEROS)
        from agent.tools.element_tools import normalize_element_code

        valid_codes_set = set(element_by_code.keys())
        matched_code, was_corrected = normalize_element_code(
            codigo_elemento, valid_codes_set
        )

        if matched_code and was_corrected:
            logger.info(
                f"[enviar_imagenes_ejemplo] Auto-corrected element code: '{codigo_elemento}' → '{matched_code}'",
                extra={
                    "conversation_id": conversation_id,
                    "original": codigo_elemento,
                    "corrected": matched_code,
                },
            )
            # Update code_upper to the corrected code for consistent logging
            code_upper = matched_code

        if not matched_code:
            logger.warning(
                f"[enviar_imagenes_ejemplo] Element not found: {codigo_elemento} in {categoria}",
                extra={"conversation_id": conversation_id},
            )
            # Build full valid codes list (sorted, capped at 20) for LLM self-correction
            available_codes = sorted(element_by_code.keys())
            valid_codes_list = available_codes[:20]
            truncated = len(available_codes) > 20
            codes_display = ", ".join(valid_codes_list)
            if truncated:
                codes_display += f" ... ({len(available_codes)} codigos en total, mostrando los primeros 20)"
            return {
                "success": False,
                "message": (
                    f"Error: El codigo '{codigo_elemento}' no es un codigo valido en la categoria '{categoria}'. "
                    f"Los codigos validos son: [{codes_display}]. "
                    "DEBES usar uno de estos codigos EXACTOS. "
                    "NO escales a humano por este error, reintenta con un codigo de la lista anterior."
                ),
                "valid_codes": valid_codes_list,
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        element = element_by_code[matched_code]
        # code_upper already set (either original or corrected)
        element_details = await element_service.get_element_with_images(element["id"])

        if not element_details:
            logger.warning(
                f"[enviar_imagenes_ejemplo] Could not get element details for {code_upper}",
                extra={"conversation_id": conversation_id},
            )
            return {
                "success": False,
                "message": f"No se pudo obtener informacion del elemento {codigo_elemento}.",
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        if not element_details.get("images"):
            # No images but element exists - return text info
            description = (
                element_details.get("description")
                or "Foto del elemento con matricula visible"
            )
            logger.info(
                f"[enviar_imagenes_ejemplo] Element {code_upper} has no images, returning text info",
                extra={"conversation_id": conversation_id},
            )
            element_name = element_details.get("name", codigo_elemento)
            return {
                "success": False,
                "message": (
                    f"⚠️ CRITICAL INSTRUCTION FOR LLM ⚠️\n"
                    f"No hay imagenes de ejemplo disponibles para '{element_name}' "
                    f"(las imagenes aun no han sido configuradas).\n\n"
                    f"DO NOT generate fake URLs or image links.\n"
                    f"DO NOT list URLs like 'storage.chatwoot.com/...' or any other invented links.\n\n"
                    f"Instead, tell the user:\n"
                    f"'En este momento no tengo fotos de ejemplo disponibles para {element_name}, "
                    f"pero puedo explicarte qué documentación necesitarás: {description}. "
                    f"¿Tienes alguna duda?'"
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        # Build images list from element (only active status)
        for img in element_details["images"]:
            if img.get("status", "placeholder") == "active":
                images_to_queue.append(
                    {
                        "url": img["image_url"],
                        "tipo": img["image_type"],
                        "elemento": element_details["name"],
                        "descripcion": img.get("description") or img.get("title", ""),
                        "instruccion_usuario": img.get("user_instruction", ""),
                        "status": "active",
                    }
                )

        if not images_to_queue:
            logger.info(
                f"[enviar_imagenes_ejemplo] Element {code_upper} has no active images",
                extra={"conversation_id": conversation_id},
            )
            element_name = element_details.get("name", code_upper)
            return {
                "success": False,
                "message": (
                    f"⚠️ CRITICAL INSTRUCTION FOR LLM ⚠️\n"
                    f"No hay imagenes de ejemplo disponibles para '{element_name}' "
                    f"(las imagenes aun no han sido configuradas).\n\n"
                    f"DO NOT generate fake URLs or image links.\n"
                    f"DO NOT list URLs like 'storage.chatwoot.com/...' or any other invented links.\n\n"
                    f"Instead, tell the user:\n"
                    f"'En este momento no tengo fotos de ejemplo disponibles para {element_name}, "
                    f"pero puedo explicarte qué documentación necesitarás. ¿Te parece?'"
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        logger.info(
            f"[enviar_imagenes_ejemplo] Queuing {len(images_to_queue)} active images for element {code_upper}",
            extra={"conversation_id": conversation_id},
        )

    elif tipo == "documentacion_base":
        if not categoria:
            return {
                "success": False,
                "message": "Para tipo='documentacion_base' debes especificar la categoria (ej: 'motos-part', 'aseicars-prof').",
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        # FSM Guard: Only callable from COLLECT_BASE_DOCS (defense-in-depth)
        if state:
            _mc = state.get("mode_context", {})
            _step_val = _mc.get("expediente_sub_mode", CollectionStep.IDLE.value)
            try:
                current_step = CollectionStep(_step_val)
            except ValueError:
                current_step = CollectionStep.IDLE
            if current_step != CollectionStep.COLLECT_BASE_DOCS:
                logger.warning(
                    f"[enviar_imagenes_ejemplo] tipo='documentacion_base' called from wrong phase | "
                    f"step={current_step.value}",
                    extra={
                        "conversation_id": conversation_id,
                        "current_step": current_step.value,
                    },
                )
                return tool_error_response(
                    message="No puedes enviar imágenes de documentación base fuera de la fase de recolección.",
                    error_category=ErrorCategory.FSM_STATE_ERROR,
                    error_code="FSM_WRONG_PHASE_FOR_BASE_DOCS",
                    guidance=(
                        f"Estás en '{current_step.value}'. "
                        f"Solo puedes enviar documentación base durante COLLECT_BASE_DOCS. "
                        f"Si el usuario pidió ejemplos de documentación, dile que esa fase ya pasó."
                    ),
                    context={"current_step": current_step.value},
                )

        # Sanitize follow_up_message: Block inappropriate messages about "expediente"
        # The case is already open in COLLECT_BASE_DOCS, so asking about opening it is confusing
        if follow_up_message and "expediente" in follow_up_message.lower():
            logger.warning(
                "[enviar_imagenes_ejemplo] Blocking inappropriate follow_up_message in COLLECT_BASE_DOCS | "
                f"message='{follow_up_message}'",
                extra={
                    "conversation_id": conversation_id,
                    "blocked_message": follow_up_message,
                },
            )
            follow_up_message = None  # Clear inappropriate message

        # Get base documentation for the category
        from agent.services.tarifa_service import get_tarifa_service

        tarifa_service = get_tarifa_service()
        category_data = await tarifa_service.get_category_data(categoria)

        if not category_data:
            logger.warning(
                f"[enviar_imagenes_ejemplo] Category not found: {categoria}",
                extra={"conversation_id": conversation_id},
            )
            return {
                "success": False,
                "message": f"Categoria '{categoria}' no encontrada en el sistema.",
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        base_documentation = category_data.get("base_documentation", [])
        if not base_documentation:
            logger.info(
                f"[enviar_imagenes_ejemplo] No base documentation defined for category {categoria}",
                extra={"conversation_id": conversation_id},
            )
            return {
                "success": False,
                "message": (
                    f"No hay documentacion base definida para la categoria '{categoria}'. "
                    "Pide al usuario que envie la ficha tecnica y el permiso de circulacion."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        # Build images list from base documentation (only those with image_url)
        docs_with_images = []
        docs_without_images = []

        for base_doc in base_documentation:
            if base_doc.get("image_url"):
                images_to_queue.append(
                    {
                        "url": base_doc["image_url"],
                        "tipo": "base",
                        "descripcion": base_doc["description"],
                        "status": "active",
                    }
                )
                docs_with_images.append(base_doc["description"])
            else:
                docs_without_images.append(base_doc["description"])

        if not images_to_queue:
            # No images configured, return text description of required docs
            logger.info(
                f"[enviar_imagenes_ejemplo] No images configured for base docs in {categoria}",
                extra={"conversation_id": conversation_id},
            )
            docs_list = "\n".join(
                f"- {doc['description']}" for doc in base_documentation
            )
            return {
                "success": False,
                "message": (
                    f"No hay imagenes de ejemplo disponibles para la documentacion base, "
                    f"pero estos son los documentos requeridos:\n\n{docs_list}\n\n"
                    "Pide al usuario que envie fotos o PDFs de estos documentos."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        logger.info(
            f"[enviar_imagenes_ejemplo] Queuing {len(images_to_queue)} base documentation images for {categoria}",
            extra={"conversation_id": conversation_id, "category": categoria},
        )

        # If some docs don't have images, add note to follow-up message
        if docs_without_images and not follow_up_message:
            docs_list = "\n".join(f"- {doc}" for doc in docs_without_images)
            follow_up_message = f"Tambien necesitaras enviar:\n{docs_list}"

    else:
        return {
            "success": False,
            "message": f"Tipo '{tipo}' no valido. Usa 'presupuesto', 'elemento', o 'documentacion_base'.",
            "data": None,
            "tool_name": "enviar_imagenes_ejemplo",
        }

    delivery_request_id = uuid_mod.uuid4().hex
    delivery_contract = {
        "version": IMAGE_DELIVERY_CONTRACT_VERSION,
        "delivery_request_id": delivery_request_id,
        "delivery_scope": tipo,
        "delivery_source_tool": "enviar_imagenes_ejemplo",
        "delivery_intent_created_at": datetime.now(UTC).isoformat(),
        "delivery_conversation_id": str(conversation_id),
        "delivery_requested_count": len(images_to_queue),
        "delivery_has_follow_up": bool(follow_up_message),
        "delivery_category": categoria,
        "delivery_element_code": codigo_elemento,
    }
    delivery_intent_outcome = _build_delivery_intent_outcome(
        delivery_request_id=delivery_request_id,
        delivery_scope=tipo,
        requested_count=len(images_to_queue),
    )

    logger.info(
        "image_delivery_intent_created",
        extra=delivery_contract,
    )

    # Build pending images payload
    pending_payload: dict[str, Any] = {
        "images": images_to_queue,
        "delivery_contract": delivery_contract,
    }

    if follow_up_message:
        pending_payload["follow_up_message"] = follow_up_message
        logger.info(
            f"[enviar_imagenes_ejemplo] Including follow_up message",
            extra={"conversation_id": conversation_id},
        )

    # Return confirmation
    # NOTE: Images are returned in _pending_images instead of using ContextVar.
    # LangChain's ainvoke() runs tools in a copied context (copy_context() + create_task),
    # so ContextVar.set() inside the tool is invisible to the caller node.

    # Option B (Bug 4): Enrich the message with real photo descriptions from DB so the
    # LLM does NOT invent what photos to request.  We extract instruccion_usuario first
    # (the human-facing instruction), falling back to descripcion, then titulo.
    desc_lines: list[str] = []
    for img in images_to_queue:
        desc = (
            img.get("instruccion_usuario")
            or img.get("descripcion")
            or img.get("titulo", "")
        )
        if desc:
            desc_lines.append(desc)

    if desc_lines:
        desc_block = " | ".join(desc_lines)
        message = (
            f"OK: {len(images_to_queue)} imagenes encoladas para envio. "
            f"INSTRUCCIONES DE FOTOS (usa ESTAS descripciones, no inventes): {desc_block}"
        )
        if follow_up_message:
            message += (
                f" | Despues de las imagenes se enviara el mensaje de seguimiento."
            )
    else:
        message = (
            f"OK: {len(images_to_queue)} imagenes encoladas para envio."
            if not follow_up_message
            else f"OK: {len(images_to_queue)} imagenes encoladas. Despues de las imagenes se enviara el mensaje de seguimiento."
        )

    return {
        "success": True,
        "message": message,
        "data": {
            "images_count": len(images_to_queue),
            "has_follow_up": bool(follow_up_message),
        },
        "tool_name": "enviar_imagenes_ejemplo",
        "_pending_images": pending_payload,
        "_internal_flags": {
            # Legacy keys — kept for backward compat with existing normalizer reads.
            "imagenes_enviadas": False,
            "imagenes_envio_intent_creado": True,
            "imagenes_delivery_request_id": delivery_request_id,
            "imagenes_delivery_outcome": delivery_intent_outcome,
            # Phase 2 canonical certainty flags.
            # Tools only own delivery *intent*, not outcome. Outcome is set by agent/main.py.
            "delivery_intent_created": True,
            "delivery_scope": tipo,
            "delivery_outcome_status": "pending",
            # ALWAYS False here — narrating delivery success is the runtime's job.
            "can_narrate_delivery_success": False,
        },
    }


# List of all image tools
IMAGE_TOOLS = [enviar_imagenes_ejemplo]


def get_image_tools() -> list:
    """Get all image-related tools."""
    return IMAGE_TOOLS


__all__ = [
    "enviar_imagenes_ejemplo",
    "get_image_tools",
    "IMAGE_TOOLS",
    "set_current_state_for_image_tools",
    "get_pending_images_result",
    "set_pending_images_result",
    "clear_image_tools_state",
    "_element_images_sent_this_turn",
    "_clear_element_images_sent_this_turn",
]
