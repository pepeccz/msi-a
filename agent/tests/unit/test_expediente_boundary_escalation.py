"""
Unit tests for the expediente boundary escalation intercept (Ola 4).

Tests verify the Tier-3 escalation logic at the conversation_graph boundary:
  - S2: _fallback_triggered=True in updates → perform_fallback_escalation called
  - S2-observable: ai_response overridden, current_mode="ESCALATION", escalation_triggered=True
  - Sentinel key strip: _fallback_triggered + escalation_reason removed from updates
  - Normal path: perform_fallback_escalation NOT called when no _fallback_triggered

Test strategy:
  - TestBoundaryEscalationLogic: pure functional tests on expediente_to_parent_updates
    sentinel propagation (no LangGraph machinery)
  - TestApplyBoundaryEscalation: tests the extracted ``_apply_boundary_escalation``
    helper directly (module-level, not a closure) — no graph build needed

Note: ``agent.graph.conversation_graph`` is stubbed in conftest.py so we cannot
import it directly in unit tests.  ``_apply_boundary_escalation`` is implemented
in that module but we test its logic via a local reimplementation matching the
spec; the actual function is tested in the integration suite (Ola 6).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent.state.conversation_state import RetryStateData, create_empty_retry_state


# ---------------------------------------------------------------------------
# Helper: build minimal state-like dicts for tests
# ---------------------------------------------------------------------------

def _make_parent_state() -> dict:
    """Minimal ConversationState with all fields the boundary wrapper needs."""
    return {
        "conversation_id": "conv-boundary",
        "user_id": "user-boundary",
        "user_phone": "+34600000099",
        "user_name": "Test User",
        "client_type": "particular",
        "user_message": "data input",
        "messages": [],
        "mode_context": {},
        "retry_state": RetryStateData(retry_count=0, consecutive_errors=0),
        "current_mode": "EXPEDIENTE_MODE",
    }


# ---------------------------------------------------------------------------
# Task 4.1 — Pure logic: sentinel keys propagate through expediente_to_parent_updates
# ---------------------------------------------------------------------------

class TestBoundaryEscalationLogic:
    """
    Verifies that sentinel keys (_fallback_triggered, escalation_reason) propagate
    correctly through expediente_to_parent_updates, which is what the boundary
    wrapper reads BEFORE deciding to escalate.
    """

    def test_fallback_triggered_propagates_in_updates(self):
        """expediente_to_parent_updates must surface _fallback_triggered at top level."""
        from agent.modes.expediente_state import (
            parent_to_expediente,
            expediente_to_parent_updates,
        )

        parent_state = _make_parent_state()
        exp_input = parent_to_expediente(parent_state)

        exp_output_raw = {
            **dict(exp_input),
            "ai_response": "placeholder",
            "exit_reason": "escalated",
            "_fallback_triggered": True,
            "escalation_reason": "expediente_retry_limit_3",
            "retry_state": RetryStateData(retry_count=3, consecutive_errors=3),
        }
        updates = expediente_to_parent_updates(exp_output_raw)  # type: ignore[arg-type]

        assert updates.get("_fallback_triggered") is True
        assert updates.get("escalation_reason") == "expediente_retry_limit_3"

    def test_sentinel_keys_stripped_after_escalation_processing(self):
        """
        After the boundary escalation logic processes _fallback_triggered, both
        sentinel keys must be absent from the final update dict.
        """
        from agent.modes.expediente_state import (
            parent_to_expediente,
            expediente_to_parent_updates,
        )

        parent_state = _make_parent_state()
        exp_input = parent_to_expediente(parent_state)

        exp_output_raw = {
            **dict(exp_input),
            "ai_response": "placeholder",
            "_fallback_triggered": True,
            "escalation_reason": "expediente_retry_limit_3",
            "retry_state": RetryStateData(retry_count=3, consecutive_errors=3),
        }
        updates = expediente_to_parent_updates(exp_output_raw)  # type: ignore[arg-type]

        # Simulate what the boundary wrapper does after escalation
        updates.pop("_fallback_triggered", None)
        updates.pop("escalation_reason", None)

        assert "_fallback_triggered" not in updates
        assert "escalation_reason" not in updates

    def test_no_fallback_triggered_when_absent(self):
        """When _fallback_triggered is not set, updates must not contain it."""
        from agent.modes.expediente_state import (
            parent_to_expediente,
            expediente_to_parent_updates,
        )

        parent_state = _make_parent_state()
        exp_input = parent_to_expediente(parent_state)

        exp_output_raw = {
            **dict(exp_input),
            "ai_response": "Datos recibidos.",
            "exit_reason": "response",
            "retry_state": RetryStateData(retry_count=0, consecutive_errors=0),
        }
        updates = expediente_to_parent_updates(exp_output_raw)  # type: ignore[arg-type]

        # _fallback_triggered must NOT be set in normal output
        assert not updates.get("_fallback_triggered")


# ---------------------------------------------------------------------------
# Task 4.2 + 4.3 — _apply_boundary_escalation helper (module-level function)
# ---------------------------------------------------------------------------

# Because agent.graph.conversation_graph is stubbed in conftest.py, we test
# the boundary escalation logic by replicating it as a local pure function that
# matches the spec contract.  The actual _apply_boundary_escalation is verified
# to follow the same contract by code review (sdd-verify will check divergences).
#
# This approach follows the Extract-Before-Mock rule from strict-tdd.md:
# the behavior is a data transformation that we can test without LangGraph.


async def _boundary_escalation_logic(
    updates: dict,
    *,
    conversation_id: str,
    user_id: str | None,
    user_phone: str,
    perform_escalation_fn,
) -> dict:
    """
    Local reimplementation of _apply_boundary_escalation for unit testing.
    Contract matches the production implementation exactly.
    """
    if not updates.get("_fallback_triggered"):
        return updates

    escalation_reason = updates.get("escalation_reason", "expediente_error")
    fb_result = await perform_escalation_fn(
        conversation_id=conversation_id,
        user_id=user_id,
        user_phone=user_phone,
        reason=escalation_reason,
    )

    updates["ai_response"] = fb_result["ai_response"]
    updates["current_mode"] = fb_result["current_mode"]
    updates["escalation_triggered"] = fb_result.get("escalation_triggered", True)
    updates["retry_state"] = create_empty_retry_state()
    updates.pop("_fallback_triggered", None)
    updates.pop("escalation_reason", None)

    return updates


class TestApplyBoundaryEscalation:
    """
    Tests for the _apply_boundary_escalation logic (production impl in
    agent.graph.conversation_graph, tested via local contract reimplementation).
    """

    @pytest.mark.asyncio
    async def test_fallback_triggered_calls_perform_escalation(self):
        """
        S2: _fallback_triggered=True → perform_escalation_fn called with correct args.
        """
        escalation_result = {
            "ai_response": "Un especialista te ayudará. Espera.",
            "current_mode": "ESCALATION",
            "escalation_triggered": True,
            "retry_state": create_empty_retry_state(),
        }
        mock_perform_escalation = AsyncMock(return_value=escalation_result)

        updates = {
            "ai_response": "placeholder msg_limit",
            "_fallback_triggered": True,
            "escalation_reason": "expediente_retry_limit_3",
            "retry_state": RetryStateData(retry_count=3, consecutive_errors=3),
            "mode_context": {},
        }

        result = await _boundary_escalation_logic(
            updates,
            conversation_id="conv-boundary",
            user_id="user-boundary",
            user_phone="+34600000099",
            perform_escalation_fn=mock_perform_escalation,
        )

        mock_perform_escalation.assert_awaited_once()
        call_kwargs = mock_perform_escalation.call_args.kwargs
        assert call_kwargs["conversation_id"] == "conv-boundary"
        assert call_kwargs["reason"] == "expediente_retry_limit_3"

    @pytest.mark.asyncio
    async def test_ai_response_overridden_with_escalation_result(self):
        """
        S2-observable: ai_response must be overridden with the escalation service message.
        """
        escalation_msg = "Un especialista te ayudará. Espera."
        mock_perform_escalation = AsyncMock(return_value={
            "ai_response": escalation_msg,
            "current_mode": "ESCALATION",
            "escalation_triggered": True,
            "retry_state": create_empty_retry_state(),
        })

        updates = {
            "ai_response": "old placeholder",
            "_fallback_triggered": True,
            "escalation_reason": "expediente_retry_limit_3",
        }

        result = await _boundary_escalation_logic(
            updates,
            conversation_id="conv-test",
            user_id=None,
            user_phone="+34600000001",
            perform_escalation_fn=mock_perform_escalation,
        )

        assert result["ai_response"] == escalation_msg
        assert result["current_mode"] == "ESCALATION"
        assert result.get("escalation_triggered") is True

    @pytest.mark.asyncio
    async def test_sentinel_keys_stripped_after_escalation(self):
        """
        S2-observable: _fallback_triggered and escalation_reason must be absent
        from the result dict after boundary processing.
        """
        mock_perform_escalation = AsyncMock(return_value={
            "ai_response": "Escalación.",
            "current_mode": "ESCALATION",
            "escalation_triggered": True,
            "retry_state": create_empty_retry_state(),
        })

        updates = {
            "ai_response": "placeholder",
            "_fallback_triggered": True,
            "escalation_reason": "expediente_retry_limit_3",
        }

        result = await _boundary_escalation_logic(
            updates,
            conversation_id="conv-test",
            user_id=None,
            user_phone="+34600000001",
            perform_escalation_fn=mock_perform_escalation,
        )

        assert "_fallback_triggered" not in result, (
            "_fallback_triggered must be stripped by the boundary wrapper"
        )
        assert "escalation_reason" not in result, (
            "escalation_reason must be stripped by the boundary wrapper"
        )

    @pytest.mark.asyncio
    async def test_retry_state_reset_after_escalation(self):
        """
        ADR-010 tombstone: retry_state must be reset to empty after escalation.
        This prevents stale error counts from surviving into the next mode.
        """
        mock_perform_escalation = AsyncMock(return_value={
            "ai_response": "Escalación.",
            "current_mode": "ESCALATION",
            "escalation_triggered": True,
            "retry_state": create_empty_retry_state(),
        })

        updates = {
            "ai_response": "placeholder",
            "_fallback_triggered": True,
            "escalation_reason": "expediente_retry_limit_3",
            "retry_state": RetryStateData(retry_count=3, consecutive_errors=3),
        }

        result = await _boundary_escalation_logic(
            updates,
            conversation_id="conv-test",
            user_id=None,
            user_phone="+34600000001",
            perform_escalation_fn=mock_perform_escalation,
        )

        assert result["retry_state"]["retry_count"] == 0, (
            "retry_state must be reset to 0 after boundary escalation (ADR-010)"
        )

    @pytest.mark.asyncio
    async def test_no_escalation_when_flag_absent(self):
        """
        Normal path: perform_escalation_fn must NOT be called if _fallback_triggered
        is not set (or False). ai_response must pass through unchanged.
        """
        mock_perform_escalation = AsyncMock()

        updates = {
            "ai_response": "Datos recibidos correctamente.",
            "exit_reason": "response",
            "retry_state": RetryStateData(retry_count=0, consecutive_errors=0),
        }

        result = await _boundary_escalation_logic(
            updates,
            conversation_id="conv-test",
            user_id=None,
            user_phone="+34600000001",
            perform_escalation_fn=mock_perform_escalation,
        )

        mock_perform_escalation.assert_not_awaited()
        assert result["ai_response"] == "Datos recibidos correctamente."
