"""
Expediente guard functions — used by the subgraph's entry_router node.

These are pure async functions (not class methods) used by the subgraph's
``entry_router`` node to run pre-LLM guards before dispatching to a sub-mode.

Design reference:
- AD-4 (Coordinator Logic Distribution): entry_router runs guards before routing
- The guard fires before the LLM loop — deterministically, without LLM involvement

Functions:
- ``guard_photo_completion(state, updates)``: Photo-completion intent guard
- ``_call_confirmar_fotos_tool(state)``: Internal helper to invoke the tool

IMPORTANT: These functions work with ``ExpedienteState``-shaped dicts (not
``ConversationState``).
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from agent.utils.validation import PHOTO_COMPLETION_INTENT_RE

logger = structlog.get_logger(__name__)

# The guard only fires for this sub-mode
_GUARD_SUB_MODE = "collect_element_data"


async def guard_photo_completion(
    state: dict[str, Any],
    updates: dict[str, Any],
) -> bool:
    """
    Deterministic pre-loop guard for photo-completion intent.

    Fires only when ALL conditions hold:
    1. ``expediente_sub_mode == 'collect_element_data'``
    2. ``element_phase == 'photos'`` (waiting for user to confirm photos)
    3. User message matches photo completion intent regex (e.g. "listo", "ya",
       "enviadas", "hechas", …) OR IntentClassifier returns COMPLETION_SIGNAL

    When fired:
    - Calls ``_call_confirmar_fotos_tool()`` directly (bypasses LLM)
    - Sets ``_guard_photo_fired_this_turn = True`` in the ``updates`` dict
    - Returns ``True``

    When not fired:
    - ``updates`` dict is left unchanged
    - Returns ``False``

    Args:
        state: ``ExpedienteState``-shaped dict from the subgraph.
        updates: Mutable dict of pending state updates (populated on fire).

    Returns:
        ``True`` if the guard fired (tool was called), ``False`` otherwise.
    """
    sub_mode: str = state.get("expediente_sub_mode") or ""
    element_phase: str = state.get("element_phase") or ""
    user_message: str = state.get("user_message") or ""
    conversation_id: str = state.get("conversation_id") or ""

    # Condition 1: only fire for collect_element_data sub-mode
    if sub_mode != _GUARD_SUB_MODE:
        return False

    # Condition 2: only fire when waiting for photo confirmation
    if element_phase != "photos":
        return False

    # Condition 3: check for completion intent
    # Try IntentClassifier first (V2); fall back to regex
    intent_confirmed = await _check_photo_completion_intent(
        state, user_message, conversation_id
    )
    if not intent_confirmed:
        return False

    # ── Guard fires ───────────────────────────────────────────────────────────
    logger.info(
        "photo_guard_triggered",
        conversation_id=conversation_id,
        element_code=state.get("current_element_code"),
        element_index=state.get("current_element_index"),
        message_preview=user_message[:60],
    )

    try:
        guard_result = await _call_confirmar_fotos_tool(state)

        if not isinstance(guard_result, dict):
            guard_result = {}

        # Apply tool flags to updates
        from agent.modes.presupuesto_mode import _apply_tool_flags

        _apply_tool_flags(updates, guard_result, logger)

        # Extract context updates (phase advance, sub-mode transition, etc.)
        from agent.modes.post_tool_hooks import _extract_expediente_context

        guard_context = _extract_expediente_context(
            "confirmar_fotos_elemento",
            guard_result if isinstance(guard_result, dict) else {},
            dict(state),
        )
        updates.update(guard_context)

        # Signal that the guard fired this turn
        updates["_guard_photo_fired_this_turn"] = True

        logger.info(
            "photo_guard_completed",
            conversation_id=conversation_id,
            tool_success=guard_result.get("success", False),
            new_element_phase=guard_result.get("element_phase"),
            triggered_transition=bool(guard_context.get("expediente_sub_mode")),
            all_elements_complete=guard_result.get("all_elements_complete", False),
        )

        return True

    except Exception as guard_error:
        logger.warning(
            "photo_guard_failed",
            conversation_id=conversation_id,
            error=str(guard_error),
            exc_info=True,
        )
        return False


async def _check_photo_completion_intent(
    state: dict[str, Any],
    user_message: str,
    conversation_id: str,
) -> bool:
    """
    Check if the user message signals photo completion intent.

    Tries IntentClassifier (V2) first; falls back to PHOTO_COMPLETION_INTENT_RE.
    Returns True if intent is confirmed, False otherwise.
    """
    try:
        from agent.services.intent_classifier import (
            get_intent_classifier,
            ClassificationContext,
            UserIntent,
        )

        _ic = get_intent_classifier()
        if _ic is not None:
            _ic_element_code = state.get("current_element_code") or ""
            _el_states: dict[str, Any] = state.get("element_states") or {}
            _el_entry = _el_states.get(_ic_element_code, {})
            _ic_element_name: str = _el_entry.get("display_name", _ic_element_code)

            # Extract last agent message for context
            _messages_hist = state.get("messages", [])
            _last_agent_msg: str = ""
            for _m in reversed(_messages_hist):
                if isinstance(_m, dict) and _m.get("role") == "assistant":
                    _last_agent_msg = _m.get("content", "")[:200]
                    break
                elif hasattr(_m, "type") and getattr(_m, "type") == "ai":
                    _last_agent_msg = str(getattr(_m, "content", ""))[:200]
                    break

            _has_images = bool(state.get("incoming_attachments"))

            _ic_ctx = ClassificationContext(
                current_phase="photos",
                current_element_name=_ic_element_name,
                pending_fields=[],
                last_agent_message=_last_agent_msg,
            )
            try:
                _ic_result = await _ic.classify(user_message, _ic_ctx, _has_images)

                if _ic_result.intent == UserIntent.REJECTION:
                    logger.info(
                        "photo_guard_skipped_rejection_intent",
                        conversation_id=conversation_id,
                        intent=_ic_result.intent.value,
                        confidence=_ic_result.confidence,
                        message_preview=user_message[:60],
                    )
                    return False
                elif _ic_result.intent == UserIntent.COMPLETION_SIGNAL:
                    return True
                # Not a completion signal → fall through to regex
            except Exception as _ic_err:
                logger.warning(
                    "photo_guard_intent_classifier_failed",
                    conversation_id=conversation_id,
                    error=str(_ic_err),
                )
                # Fall through to regex
    except ImportError:
        pass  # IntentClassifier not available — use regex only

    # Fallback: regex-based detection
    return bool(PHOTO_COMPLETION_INTENT_RE.search(user_message))


async def _call_confirmar_fotos_tool(
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Internal helper: invoke ``confirmar_fotos_elemento`` tool directly.

    Builds a RunnableConfig so the tool can read state via get_tool_state(config),
    then calls the tool with ``usuario_confirma=True``. Parses and returns the
    result as a dict.

    This function is a separate named function (not an inline lambda) so that
    tests can patch it cleanly:
    ``patch('agent.services.expediente_guards._call_confirmar_fotos_tool', ...)``.

    Args:
        state: ``ExpedienteState``-shaped dict (used to build RunnableConfig).

    Returns:
        Tool result as a dict.
    """
    from agent.tools.image_tools import (
        clear_image_tools_state,
    )
    from agent.tools.element_data_tools import confirmar_fotos_elemento

    full_state = dict(state)
    # mode_context equivalent for RunnableConfig tools is the state itself
    # (In the subgraph, ExpedienteState IS mode_context — flat structure)
    full_state["mode_context"] = dict(state)

    tool_config = {"configurable": {"state": full_state}}

    try:
        raw_result = await confirmar_fotos_elemento.ainvoke(
            {"usuario_confirma": True},
            config=tool_config,
        )

        # Parse result (tool may return dict or JSON string)
        if isinstance(raw_result, str):
            try:
                return json.loads(raw_result)
            except (json.JSONDecodeError, ValueError):
                return {}
        elif isinstance(raw_result, dict):
            return raw_result
        else:
            return {}
    finally:
        clear_image_tools_state()
