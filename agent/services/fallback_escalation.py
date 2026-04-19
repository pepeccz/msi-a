"""
MSI-a — Shared fallback escalation helper.

Extracted from ``agent.modes.base_mode._perform_immediate_escalation`` so that
both ``BaseModeNode`` and the expediente subgraph boundary wrapper can call
escalation without coupling to ``BaseModeNode`` (design: Approach 3 hybrid).

The function is intentionally pure-ish:
  - No class state.
  - Delegates all side effects to ``escalation_service.perform_escalation()``.
  - Returns a canonical dict ready to merge into ``ConversationState``.
"""

from __future__ import annotations

from typing import Any

import structlog

from agent.services.escalation_service import perform_escalation
from agent.state.conversation_state import create_empty_retry_state

logger = structlog.get_logger(__name__)


async def perform_fallback_escalation(
    *,
    conversation_id: str,
    user_id: str | None,
    user_phone: str,
    reason: str,
) -> dict[str, Any]:
    """
    Call ``escalation_service.perform_escalation()`` and return a canonical
    result dict ready to merge into the parent ``ConversationState``.

    This helper is used by:
    - ``BaseModeNode._perform_immediate_escalation`` (thin wrapper delegate)
    - ``_expediente_subgraph_node`` boundary wrapper (Tier 3 intercept)

    Args:
        conversation_id: Chatwoot conversation ID.
        user_id: UUID string of the user (may be None for anonymous users).
        user_phone: User phone number for context.
        reason: Human-readable reason string (e.g. "expediente_retry_limit_3").

    Returns:
        Dict with keys:
        - ``ai_response``: User-facing message in Spanish (from escalation service).
        - ``current_mode``: "ESCALATION"
        - ``escalation_triggered``: True
        - ``retry_state``: reset empty RetryStateData
    """
    # Default message — overridden by service result when available
    ai_response = (
        "Te voy a conectar con un especialista que te puede "
        "ayudar mejor. Espera un momento..."
    )

    try:
        result = await perform_escalation(
            conversation_id=str(conversation_id),
            user_id=str(user_id) if user_id else None,
            user_phone=str(user_phone),
            reason=str(reason),
            source="fallback",
            is_technical_error=True,
        )
        if result.get("message"):
            ai_response = result["message"]
    except Exception as exc:
        logger.error(
            "fallback_escalation_failed",
            error=str(exc),
            conversation_id=conversation_id,
            exc_info=True,
        )
        # Don't re-raise — caller still gets the default message and mode transition

    return {
        "ai_response": ai_response,
        "current_mode": "ESCALATION",
        "escalation_triggered": True,
        "retry_state": create_empty_retry_state(),
    }
