"""
MSI-a — Conversation summarization and message trimming node.

Deterministic summarization (NO LLM calls) that extracts structured data
from state fields and trims old messages via RemoveMessage.

Part of WS2: refactor-memory-system.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.messages import RemoveMessage

from shared.config import get_settings

logger = structlog.get_logger(__name__)


def build_structured_summary(state: dict[str, Any]) -> str:
    """
    Build a deterministic summary from state fields.

    Extracts mode, user info, business context (elements, tariff, case)
    without any LLM call. Cost: zero tokens.

    Args:
        state: Current ConversationState dict.

    Returns:
        Structured summary string.
    """
    parts: list[str] = []

    # User identity
    user_name = state.get("user_name")
    if user_name:
        parts.append(f"Cliente: {user_name}")

    client_type = state.get("client_type")
    if client_type:
        parts.append(f"Tipo: {client_type}")

    user_phone = state.get("user_phone")
    if user_phone:
        parts.append(f"Teléfono: {user_phone}")

    # Current mode
    current_mode = state.get("current_mode")
    if current_mode:
        parts.append(f"Modo actual: {current_mode}")

    # Mode history
    mode_history = state.get("mode_history", [])
    if mode_history:
        parts.append(f"Modos visitados: {' → '.join(mode_history)}")

    # Mode context details
    mc = state.get("mode_context") or {}

    # Presupuesto context
    elementos = mc.get("elementos_confirmados")
    if elementos:
        codes = [e.get("codigo", e.get("code", "?")) for e in elementos]
        parts.append(f"Elementos confirmados: {', '.join(codes)}")

    element_codes = mc.get("element_codes")
    if element_codes and not elementos:
        parts.append(f"Elementos: {', '.join(element_codes)}")

    tarifa = mc.get("tarifa_calculada")
    if tarifa:
        datos = tarifa.get("datos", tarifa)
        price = datos.get("price") or datos.get("precio")
        if price:
            parts.append(f"Tarifa calculada: {price}€")

    if mc.get("precio_comunicado"):
        parts.append("Precio comunicado: sí")

    if mc.get("imagenes_enviadas"):
        parts.append("Imágenes ejemplo enviadas: sí")

    # Expediente context
    case_id = mc.get("case_id")
    if case_id:
        parts.append(f"Expediente: {case_id}")

    current_element_index = mc.get("current_element_index")
    if current_element_index is not None and element_codes:
        total = len(element_codes)
        parts.append(f"Progreso elementos: {current_element_index + 1}/{total}")

    element_phase = mc.get("element_phase")
    if element_phase:
        parts.append(f"Fase elemento actual: {element_phase}")

    personal_data = mc.get("personal_data")
    if personal_data:
        filled = [k for k, v in personal_data.items() if v]
        if filled:
            parts.append(f"Datos personales recogidos: {', '.join(filled)}")

    vehicle_data = mc.get("vehicle_data")
    if vehicle_data:
        filled = [k for k, v in vehicle_data.items() if v]
        if filled:
            parts.append(f"Datos vehículo recogidos: {', '.join(filled)}")

    # Escalation
    if state.get("escalation_triggered"):
        reason = state.get("escalation_reason", "no especificada")
        parts.append(f"Escalación: sí (razón: {reason})")

    # Message count
    total_count = state.get("total_message_count")
    if total_count:
        parts.append(f"Mensajes totales: {total_count}")

    if not parts:
        return "Conversación sin contexto relevante registrado."

    return " | ".join(parts)


async def maybe_summarize(
    state: dict[str, Any],
    *,
    store=None,
    threshold: int | None = None,
    window: int | None = None,
) -> dict[str, Any]:
    """
    Conditional summarization node for the conversation graph.

    Checks if the message count exceeds the configured threshold. If so:
    1. Builds a deterministic structured summary from state fields
    2. Emits RemoveMessage for old messages beyond the retention window
    3. Stores the summary in conversation_summary
    4. Saves user profile to Store (WS3: cross-thread memory)

    If the threshold is not reached, still saves profile on every 5th message.

    Args:
        state: Current ConversationState.
        store: LangGraph Store instance (injected by framework, None in tests).
        threshold: Override for MEMORY_SUMMARIZATION_THRESHOLD (testing).
        window: Override for MEMORY_MESSAGES_WINDOW (testing).

    Returns:
        State update dict (may include messages with RemoveMessage, conversation_summary).
    """
    settings = get_settings()
    if threshold is None:
        threshold = settings.MEMORY_SUMMARIZATION_THRESHOLD
    if window is None:
        window = settings.MEMORY_MESSAGES_WINDOW

    messages = state.get("messages", [])
    total_count = state.get("total_message_count", len(messages))

    # ── Profile persistence (WS3) — save periodically ───────────────────
    # Save on every 5th message to keep profile up-to-date without
    # saving every single turn. Also saves on summarization triggers.
    if store is not None and total_count > 0 and total_count % 5 == 0:
        user_phone = state.get("user_phone", "")
        if user_phone:
            from agent.graph.user_profile_store import save_user_profile  # noqa: PLC0415

            await save_user_profile(store, user_phone, state)

    # Only trigger summarization when threshold is reached
    if total_count < threshold:
        return {}

    # Only trigger periodically (every `threshold` messages)
    if total_count % threshold != 0:
        return {}

    msg_count = len(messages)
    if msg_count <= window:
        # Not enough messages to trim
        return {}

    # Build structured summary
    summary = build_structured_summary(state)

    # Determine which messages to remove (keep last `window`)
    messages_to_remove = messages[:-window]
    remove_ops: list[RemoveMessage] = []

    for msg in messages_to_remove:
        msg_id = getattr(msg, "id", None)
        if msg_id is None and isinstance(msg, dict):
            msg_id = msg.get("id")
        if msg_id:
            remove_ops.append(RemoveMessage(id=msg_id))

    if not remove_ops:
        # Messages don't have IDs (shouldn't happen with add_messages, but safety)
        logger.warning(
            "summarize_no_message_ids",
            msg_count=msg_count,
            window=window,
        )
        # Still save the summary even if we can't trim
        return {"conversation_summary": summary}

    removed_count = len(remove_ops)
    logger.info(
        "conversation_summarized",
        total_messages=msg_count,
        removed=removed_count,
        retained=msg_count - removed_count,
        summary_length=len(summary),
        total_message_count=total_count,
    )

    return {
        "messages": remove_ops,
        "conversation_summary": summary,
    }
