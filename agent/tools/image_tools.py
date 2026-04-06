"""
MSI Automotive - Image Tools for Agent.

Thin wrapper tool around ImageService.  All delivery-scope business logic
lives in ``agent.services.image_service``.  This module owns only:

- The per-process ephemeral dedup set (``_element_images_sent_this_turn``).
- The ``_pending_images_result`` ContextVar that carries queued payloads
  between tool execution and the main loop.
- Backward-compat aliases for the old ContextVar helpers.
- The @tool-decorated wrapper ``enviar_imagenes_ejemplo``.
"""

import logging
import uuid as uuid_mod
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Literal

from langchain_core.tools import tool

from agent.tools.schemas import EnviarImagenesEjemploInput
from agent.utils.errors import ErrorCategory, handle_tool_errors
from agent.state.helpers import (
    get_current_state,
    set_current_state,
    clear_current_state,
)

logger = logging.getLogger(__name__)

IMAGE_DELIVERY_CONTRACT_VERSION = "v1"

# ---------------------------------------------------------------------------
# Ephemeral per-turn dedup guard for tipo="elemento" image sends.
# Keyed by "{conversation_id}:{element_code.upper()}".
# Reset at the start of each COLLECT_ELEMENT_DATA handler turn.
# ---------------------------------------------------------------------------

_element_images_sent_this_turn: set[str] = set()


def _clear_element_images_sent_this_turn() -> None:
    """Reset the intra-turn dedup set. Called at the start of each agent turn by expediente_mode."""
    _element_images_sent_this_turn.clear()


# ---------------------------------------------------------------------------
# _pending_images_result ContextVar — carries queued payloads to the main loop.
# ---------------------------------------------------------------------------

_pending_images_result: ContextVar[dict[str, Any] | None] = ContextVar(
    "image_tools_pending_result", default=None
)


def set_current_state_for_image_tools(state: dict[str, Any]) -> None:
    """
    Backward-compat alias — delegates to the shared set_current_state().

    Retained so that existing call sites in old loop paths continue to work.
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
    """
    _pending_images_result.set(result)


def clear_image_tools_state() -> None:
    """Clear the image tools state after processing."""
    clear_current_state()
    _pending_images_result.set(None)


# ---------------------------------------------------------------------------
# Delivery-intent helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@tool(args_schema=EnviarImagenesEjemploInput)
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
    from agent.services.image_service import get_image_service

    # Get state from the shared ContextVar (async-safe, no globals).
    state = get_current_state()
    conversation_id = state.get("conversation_id", "unknown") if state else "unknown"

    logger.info(
        "[enviar_imagenes_ejemplo] Called | tipo=%s | elemento=%s | categoria=%s | has_follow_up=%s",
        tipo,
        codigo_elemento,
        categoria,
        bool(follow_up_message),
        extra={"conversation_id": conversation_id},
    )

    # ── Intra-turn dedup guard for tipo="elemento" ───────────────────────────
    if tipo == "elemento" and codigo_elemento:
        _dedup_key = f"{conversation_id}:{codigo_elemento.upper()}"
        if _dedup_key in _element_images_sent_this_turn:
            logger.warning(
                "[enviar_imagenes_ejemplo] duplicate_elemento_blocked | element=%s",
                codigo_elemento,
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
        # Register BEFORE delegating so any exception path doesn't leak through
        _element_images_sent_this_turn.add(_dedup_key)
    # ────────────────────────────────────────────────────────────────────────

    image_svc = get_image_service()
    svc_result = await image_svc.queue_example_images(
        tipo=tipo,
        codigo_elemento=codigo_elemento,
        categoria=categoria,
        follow_up_message=follow_up_message,
        state_context=state or {},
    )

    # Propagate error responses unchanged
    if not svc_result["success"]:
        error_response: dict[str, Any] = {
            "success": False,
            "message": svc_result["message"],
            "data": None,
            "tool_name": "enviar_imagenes_ejemplo",
        }
        # Preserve valid_codes if present (elemento branch)
        if "valid_codes" in svc_result:
            error_response["valid_codes"] = svc_result["valid_codes"]
        if "guidance" in svc_result:
            error_response["guidance"] = svc_result["guidance"]
        return error_response

    # ── Happy path: build delivery contract and pending payload ──────────────
    images_to_queue: list[dict[str, Any]] = svc_result["images_to_queue"] or []
    resolved_follow_up = svc_result["follow_up_message"]

    delivery_request_id = uuid_mod.uuid4().hex
    delivery_contract = {
        "version": IMAGE_DELIVERY_CONTRACT_VERSION,
        "delivery_request_id": delivery_request_id,
        "delivery_scope": tipo,
        "delivery_source_tool": "enviar_imagenes_ejemplo",
        "delivery_intent_created_at": datetime.now(UTC).isoformat(),
        "delivery_conversation_id": str(conversation_id),
        "delivery_requested_count": len(images_to_queue),
        "delivery_has_follow_up": bool(resolved_follow_up),
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

    pending_payload: dict[str, Any] = {
        "images": images_to_queue,
        "delivery_contract": delivery_contract,
    }
    if resolved_follow_up:
        pending_payload["follow_up_message"] = resolved_follow_up
        logger.info(
            "[enviar_imagenes_ejemplo] Including follow_up message",
            extra={"conversation_id": conversation_id},
        )

    # Build the message for the LLM (enriched with photo descriptions from DB)
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
        if resolved_follow_up:
            message += " | Despues de las imagenes se enviara el mensaje de seguimiento."
    else:
        message = (
            f"OK: {len(images_to_queue)} imagenes encoladas para envio."
            if not resolved_follow_up
            else f"OK: {len(images_to_queue)} imagenes encoladas. Despues de las imagenes se enviara el mensaje de seguimiento."
        )

    return {
        "success": True,
        "message": message,
        "data": {
            "images_count": len(images_to_queue),
            "has_follow_up": bool(resolved_follow_up),
        },
        "tool_name": "enviar_imagenes_ejemplo",
        "_pending_images": pending_payload,
        "_state_update": {
            # Legacy keys — kept for backward compat with existing normalizer reads.
            "imagenes_enviadas": False,
            "imagenes_envio_intent_creado": True,
            "imagenes_delivery_request_id": delivery_request_id,
            "imagenes_delivery_outcome": delivery_intent_outcome,
            # Phase 2 canonical certainty flags.
            "delivery_intent_created": True,
            "delivery_scope": tipo,
            "delivery_outcome_status": "pending",
            # ALWAYS False here — narrating delivery success is the runtime's job.
            "can_narrate_delivery_success": False,
        },
    }


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

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
