"""
MSI Automotive - Image Tools for Agent.

Thin wrapper tool around ImageService.  All delivery-scope business logic
lives in ``agent.services.image_service``.  This module owns only:

- The per-process ephemeral dedup set (``_element_images_sent_this_turn``).
- The ``_pending_images_result`` ContextVar that carries queued payloads
  between tool execution and the main loop.
- The @tool-decorated wrapper ``enviar_imagenes_ejemplo``.
"""

import logging
import uuid as uuid_mod
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from langchain_core.tools import tool
from langchain_core.tools.base import InjectedToolArg

from agent.tools.schemas import EnviarImagenesEjemploInput
from agent.utils.errors import ErrorCategory, handle_tool_errors
from langchain_core.runnables import RunnableConfig

from agent.state.helpers import get_tool_state

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

# _pending_images_result carries queued image delivery payloads from
# enviar_imagenes_ejemplo (and reenviar_imagenes_elemento) to the main loop.
# It is intentionally separate from the conversation state (get_tool_state)
# because image payloads are ephemeral per-tool-call data, not conversation
# state that should be checkpointed.
# The loop reads and clears this ContextVar after each tool execution via
# get_pending_images_result().
_pending_images_result: ContextVar[dict[str, Any] | None] = ContextVar(
    "image_tools_pending_result", default=None
)


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
    """Clear the image tools ephemeral state (pending images) after processing."""
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
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
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
    - codigo_elemento: Requerido si tipo="elemento"
    - categoria: Requerido si tipo="elemento" o tipo="documentacion_base"
    - follow_up_message: DEPRECATED — NO uses este parametro. Escribe el CTA
      directamente en tu ai_response, que llega al usuario DESPUES de las imagenes.

    FLUJO DE ENVIO:
    1. Las imagenes se envian primero (una por una)
    2. Luego llega tu ai_response al usuario como mensaje de seguimiento

    IMPORTANTE: tu ai_response llega DESPUES de las imagenes. NO escribas "te envio
    las fotos" ni "aqui tienes las fotos" — escribe directamente el CTA siguiente.
    Si success=true, las fotos YA se estan enviando antes de tu mensaje.

    EJEMPLO PRESUPUESTO:
    Despues de calcular tarifa, llama:
    enviar_imagenes_ejemplo(tipo="presupuesto")

    EJEMPLO ELEMENTO ESPECIFICO:
    enviar_imagenes_ejemplo(tipo="elemento", codigo_elemento="ESCAPE", categoria="motos-part")

    EJEMPLO DOCUMENTACION BASE:
    enviar_imagenes_ejemplo(tipo="documentacion_base", categoria="motos-part")

    Note: No code-level precio_comunicado gate. The prompt instructs the LLM to
    communicate price before images, but the tool is always callable. Only
    confirmar_presupuesto has a hard price gate.

    Returns:
        Confirmacion con numero de imagenes encoladas, o mensaje de error/info
    """
    from agent.services.image_service import get_image_service

    # Get state (prefer RunnableConfig, fall back to ContextVar).
    state = get_tool_state(config)
    conversation_id = state.get("conversation_id", "unknown")

    # ADR-005: Resolve categoria from state (authoritative source).
    # LLM-supplied categoria is fallback only.
    _state_cat = (state.get("mode_context") or {}).get("categoria_slug") or (
        state.get("shared_context") or {}
    ).get("categoria_slug")
    if _state_cat:
        if categoria and categoria != _state_cat:
            logger.warning(
                "[enviar_imagenes_ejemplo] categoria_override_from_state | llm=%s → state=%s | conv=%s",
                categoria,
                _state_cat,
                conversation_id,
            )
        categoria = _state_cat

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
                    "Emite AHORA el texto de FASE FOTOS (transición fija + lista literal INSTRUCCIONES DE FOTOS + cierre fijo) y TERMINA EL TURNO. "
                    "PROHIBIDO añadir preguntas de datos técnicos, material, medidas ni ningún contenido de FASE DATOS en este mensaje. "
                    "Esperá a que el usuario responda con 'listo' o envíe fotos antes de avanzar a FASE DATOS."
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

    # ── Descriptions-only short-circuit (dual-mode gate, Layer B) ────────────
    # When image_service returns descriptions_only=True, the gate has already built
    # the INSTRUCCIONES DE FOTOS text block. No images to queue, no delivery contract.
    if svc_result.get("descriptions_only"):
        logger.info(
            "[enviar_imagenes_ejemplo] descriptions_only short-circuit | conv=%s",
            conversation_id,
        )
        return {
            "success": True,
            "message": svc_result["message"],
            "data": None,
            "tool_name": "enviar_imagenes_ejemplo",
            "_state_update": svc_result.get("_state_update", {}),
        }

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

    # R3 — Phase-gated message: if POST_PRICE (precio_comunicado=True) and tipo=presupuesto,
    # emit a compact message without desc_block to prevent the LLM from re-narrating
    # the full budget (price + docs) that was already communicated in the previous turn.
    # For all other combinations, preserve the existing desc_block behaviour.
    _mc = (state.get("mode_context") or {})
    _sc = (state.get("shared_context") or {})
    _precio_comunicado = bool(_mc.get("precio_comunicado") or _sc.get("precio_comunicado"))

    if tipo == "presupuesto" and _precio_comunicado:
        # Compact gate fires — no desc_block, no instructions.
        message = (
            f"OK: {len(images_to_queue)} imágenes encoladas para envio. "
            "Responde EXACTAMENTE {{CTA_5}} — "
            "la narración del presupuesto ya se comunicó en turno anterior."
        )
    else:
        # Existing behaviour: build enriched message with photo descriptions.
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
                message += (
                    " | Despues de las imagenes se enviara el mensaje de seguimiento."
                )
        else:
            message = (
                f"OK: {len(images_to_queue)} imagenes encoladas para envio."
                if not resolved_follow_up
                else f"OK: {len(images_to_queue)} imagenes encoladas. Despues de las imagenes se enviara el mensaje de seguimiento."
            )

    # T-08: Build sent_codes from svc_result (primary) or images_to_queue (fallback)
    sent_codes: list[str] = []
    if svc_result.get("sent_element_codes") is not None:
        sent_codes = list(svc_result["sent_element_codes"])
        if svc_result.get("sent_base_docs"):
            sent_codes.append("_BASE_DOCS")
    else:
        # Fallback: derive from images_to_queue
        seen: set[str] = set()
        for img in images_to_queue:
            code = img.get("element_code")
            if code:
                upper = str(code).upper()
                if upper not in seen:
                    sent_codes.append(upper)
                    seen.add(upper)
            elif img.get("tipo") == "base" and "_BASE_DOCS" not in seen:
                sent_codes.append("_BASE_DOCS")
                seen.add("_BASE_DOCS")

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
            # Cross-mode keys go into shared_context (WS4).
            "shared_context": {
                # T-08: Still False at intent time — delivery confirmation is runtime's job.
                # imagenes_enviadas_codigos_pending carries the codes to append on success.
                "imagenes_enviadas": False,
                "imagenes_enviadas_codigos_pending": sent_codes,
            },
            # Mode-private / transient keys stay flat.
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
    "get_pending_images_result",
    "set_pending_images_result",
    "clear_image_tools_state",
    "_element_images_sent_this_turn",
    "_clear_element_images_sent_this_turn",
]
