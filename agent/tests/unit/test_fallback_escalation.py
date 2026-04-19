"""
Unit tests for agent.services.fallback_escalation.perform_fallback_escalation().

Strict TDD — RED first: module doesn't exist yet.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# These imports will fail (RED) until task 0.4 creates the module.
from agent.services.fallback_escalation import perform_fallback_escalation


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ESCALATION_SERVICE_PATH = "agent.services.fallback_escalation.perform_escalation"


def _make_escalation_result(message: str = "Un agente te ayudará.") -> dict:
    return {
        "success": True,
        "escalation_id": "abc123",
        "message": message,
        "duplicate_prevented": False,
        "terminate_processing": False,
    }


# ---------------------------------------------------------------------------
# Test: canonical result dict shape (S2 — Tier 3 boundary contract)
# ---------------------------------------------------------------------------

class TestPerformFallbackEscalation:
    """perform_fallback_escalation must return the canonical result dict."""

    @pytest.mark.asyncio
    async def test_returns_ai_response_key(self):
        """Result must contain ai_response (non-empty)."""
        with patch(ESCALATION_SERVICE_PATH, new=AsyncMock(return_value=_make_escalation_result())):
            result = await perform_fallback_escalation(
                conversation_id="conv-001",
                user_id="user-001",
                user_phone="+34600000001",
                reason="expediente_retry_limit_3",
            )
        assert "ai_response" in result
        assert result["ai_response"]  # non-empty

    @pytest.mark.asyncio
    async def test_returns_escalation_mode(self):
        """current_mode must be ESCALATION."""
        with patch(ESCALATION_SERVICE_PATH, new=AsyncMock(return_value=_make_escalation_result())):
            result = await perform_fallback_escalation(
                conversation_id="conv-001",
                user_id=None,
                user_phone="+34600000002",
                reason="expediente_retry_limit_3",
            )
        assert result["current_mode"] == "ESCALATION"

    @pytest.mark.asyncio
    async def test_returns_escalation_triggered_true(self):
        """escalation_triggered must be True."""
        with patch(ESCALATION_SERVICE_PATH, new=AsyncMock(return_value=_make_escalation_result())):
            result = await perform_fallback_escalation(
                conversation_id="conv-002",
                user_id="user-002",
                user_phone="+34600000003",
                reason="expediente_retry_limit_3",
            )
        assert result["escalation_triggered"] is True

    @pytest.mark.asyncio
    async def test_returns_retry_state_key(self):
        """Result must contain retry_state (reset to empty)."""
        with patch(ESCALATION_SERVICE_PATH, new=AsyncMock(return_value=_make_escalation_result())):
            result = await perform_fallback_escalation(
                conversation_id="conv-003",
                user_id=None,
                user_phone="+34600000004",
                reason="expediente_retry_limit_3",
            )
        assert "retry_state" in result

    @pytest.mark.asyncio
    async def test_ai_response_uses_service_message(self):
        """ai_response must come from the escalation service message."""
        custom_msg = "Te paso con un especialista ahora mismo."
        with patch(
            ESCALATION_SERVICE_PATH,
            new=AsyncMock(return_value=_make_escalation_result(message=custom_msg)),
        ):
            result = await perform_fallback_escalation(
                conversation_id="conv-004",
                user_id="user-004",
                user_phone="+34600000005",
                reason="expediente_retry_limit_3",
            )
        assert result["ai_response"] == custom_msg

    @pytest.mark.asyncio
    async def test_calls_escalation_service_with_correct_args(self):
        """perform_escalation must be called with the right conversation_id."""
        mock_escalation = AsyncMock(return_value=_make_escalation_result())
        with patch(ESCALATION_SERVICE_PATH, new=mock_escalation):
            await perform_fallback_escalation(
                conversation_id="conv-999",
                user_id="user-999",
                user_phone="+34699999999",
                reason="expediente_retry_limit_3",
            )
        mock_escalation.assert_called_once()
        call_kwargs = mock_escalation.call_args.kwargs
        assert call_kwargs["conversation_id"] == "conv-999"
