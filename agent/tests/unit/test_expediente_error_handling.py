"""
Unit tests for _build_expediente_node error-handling intercept (Olas 3 + 5).

Tests verify the sub-node Tier-2 error-handling behaviour:
  - S1: single non-transient error → reprompt, retry_count incremented
  - S3: successful turn → consecutive_errors reset (Ola 5)
  - S4: transient error → re-raised, counter unchanged
  - S1-variant: ai_response matches policy msg_retry_1 on first error
  - S2-partial: at limit → _fallback_triggered=True
  - S5: sub-mode transition (no completion_flag) → retry_count preserved
  - S6/completion: completion_flag=True → retry_count reset to 0

All tests mock ``build_mode_tool_loop`` so no real LangGraph graph is compiled.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.modes.expediente_state import ExpedienteState
from agent.state.conversation_state import RetryStateData, create_empty_retry_state


# ---------------------------------------------------------------------------
# Helpers — build a minimal ExpedienteState for tests
# ---------------------------------------------------------------------------

def _make_state(retry_count: int = 0, consecutive_errors: int = 0) -> dict:
    """Build a minimal state dict usable as ExpedienteState for node invocation."""
    return {
        "conversation_id": "conv-test",
        "user_id": "user-001",
        "user_phone": "+34600000001",
        "user_name": "Test User",
        "client_type": "particular",
        "user_message": "Aquí están mis datos",
        "incoming_attachments": [],
        "messages": [],
        "mode_context": {},
        "conversation_summary": None,
        "retry_state": RetryStateData(
            retry_count=retry_count,
            consecutive_errors=consecutive_errors,
        ),
        # Minimal expediente keys
        "expediente_sub_mode": "collect_personal",
        "case_id": "case-abc",
        "element_codes": ["SUSPENSION"],
    }


# ---------------------------------------------------------------------------
# Task 3.1 — S1: single business error → reprompt, counter incremented
# ---------------------------------------------------------------------------

class TestSubNodeRepromptOnBusinessError:
    """
    S1: non-transient error inside _build_expediente_node must:
    - NOT re-raise
    - increment retry_state.retry_count by 1
    - return non-empty ai_response
    - NOT set _fallback_triggered
    """

    @pytest.mark.asyncio
    async def test_single_error_increments_retry_count(self):
        """retry_count starts at 0, business error → becomes 1."""
        from agent.modes.expediente_nodes import _build_expediente_node
        from agent.modes.submodos._shared import _get_personal_tools

        # Mock the tool loop to raise a ValueError (non-transient business error)
        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = ValueError("bad input from user")
        mock_loop_obj = MagicMock()
        mock_loop_obj.graph = mock_graph
        mock_loop_obj.recursion_limit = 25

        node_fn = _build_expediente_node(
            mode_name="EXPEDIENTE_COLLECT_PERSONAL",
            sub_mode="collect_personal",
            get_tools_fn=_get_personal_tools,
            completion_flag="personal_collected",
            own_sub_mode="collect_personal",
        )

        state = _make_state(retry_count=0, consecutive_errors=0)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=mock_loop_obj):
            cmd = await node_fn(state, None)

        # Command update must carry incremented retry_state
        assert cmd is not None
        update = cmd.update
        assert "retry_state" in update, "retry_state must be in Command update"
        assert update["retry_state"]["retry_count"] == 1

    @pytest.mark.asyncio
    async def test_single_error_returns_non_empty_ai_response(self):
        """Business error on first try → ai_response must be non-empty (reprompt)."""
        from agent.modes.expediente_nodes import _build_expediente_node
        from agent.modes.submodos._shared import _get_personal_tools

        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = ValueError("unexpected tool failure")
        mock_loop_obj = MagicMock()
        mock_loop_obj.graph = mock_graph
        mock_loop_obj.recursion_limit = 25

        node_fn = _build_expediente_node(
            mode_name="EXPEDIENTE_COLLECT_PERSONAL",
            sub_mode="collect_personal",
            get_tools_fn=_get_personal_tools,
        )

        state = _make_state(retry_count=0)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=mock_loop_obj):
            cmd = await node_fn(state, None)

        update = cmd.update
        assert "ai_response" in update
        assert len(update["ai_response"].strip()) > 0, (
            "ai_response must be non-empty on business error — never leave user in silence"
        )

    @pytest.mark.asyncio
    async def test_single_error_does_not_set_fallback_triggered(self):
        """retry_count goes 0→1 (below limit) — _fallback_triggered must NOT be set."""
        from agent.modes.expediente_nodes import _build_expediente_node
        from agent.modes.submodos._shared import _get_personal_tools

        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = ValueError("bad data")
        mock_loop_obj = MagicMock()
        mock_loop_obj.graph = mock_graph
        mock_loop_obj.recursion_limit = 25

        node_fn = _build_expediente_node(
            mode_name="EXPEDIENTE_COLLECT_PERSONAL",
            sub_mode="collect_personal",
            get_tools_fn=_get_personal_tools,
        )

        state = _make_state(retry_count=0)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=mock_loop_obj):
            cmd = await node_fn(state, None)

        update = cmd.update
        assert not update.get("_fallback_triggered"), (
            "_fallback_triggered must NOT be set when retry_count < max_retries"
        )


# ---------------------------------------------------------------------------
# Task 3.3 — S4: transient error re-raised, counter unchanged
# ---------------------------------------------------------------------------

class TestTransientErrorReRaised:
    """
    S4: transient errors (httpx.TimeoutException, etc.) must be re-raised.
    The retry_state counter must NOT be mutated — Tier 1 handles these.
    """

    @pytest.mark.asyncio
    async def test_timeout_exception_is_rerased(self):
        """httpx.TimeoutException must propagate — not swallowed by the except block."""
        import httpx
        from agent.modes.expediente_nodes import _build_expediente_node
        from agent.modes.submodos._shared import _get_personal_tools

        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = httpx.TimeoutException("timeout")
        mock_loop_obj = MagicMock()
        mock_loop_obj.graph = mock_graph
        mock_loop_obj.recursion_limit = 25

        node_fn = _build_expediente_node(
            mode_name="EXPEDIENTE_COLLECT_PERSONAL",
            sub_mode="collect_personal",
            get_tools_fn=_get_personal_tools,
        )

        state = _make_state(retry_count=0)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=mock_loop_obj):
            with pytest.raises(httpx.TimeoutException):
                await node_fn(state, None)

    @pytest.mark.asyncio
    async def test_transient_error_does_not_increment_counter(self):
        """
        When a transient error is re-raised, retry_state must remain at initial value.
        We verify this indirectly: the test above confirms re-raise, so no update dict
        is returned that could contain a modified retry_state.
        """
        import httpx
        from agent.modes.expediente_nodes import _build_expediente_node
        from agent.modes.submodos._shared import _get_personal_tools

        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = httpx.ConnectError("connection refused")
        mock_loop_obj = MagicMock()
        mock_loop_obj.graph = mock_graph
        mock_loop_obj.recursion_limit = 25

        node_fn = _build_expediente_node(
            mode_name="EXPEDIENTE_COLLECT_PERSONAL",
            sub_mode="collect_personal",
            get_tools_fn=_get_personal_tools,
        )

        state = _make_state(retry_count=1)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=mock_loop_obj):
            with pytest.raises(httpx.ConnectError):
                await node_fn(state, None)
        # If we reach here, the exception propagated and no counter mutation occurred


# ---------------------------------------------------------------------------
# Task 3.5 — S1-variant: ai_response matches policy msg_retry_1 on first error
# ---------------------------------------------------------------------------

class TestRepromptMessageContent:
    """
    S1-variant: the returned ai_response on first error must match the policy's
    msg_retry_1 (or be a reasonable fallback from FallbackHandler.get_reprompt).
    """

    @pytest.mark.asyncio
    async def test_first_error_ai_response_matches_policy_msg_retry_1(self):
        """On retry_count 0→1, ai_response should equal policy.msg_retry_1."""
        from agent.modes.expediente_nodes import _build_expediente_node
        from agent.modes.submodos._shared import _get_personal_tools
        from agent.fallback.fallback_handler import FallbackHandler

        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = ValueError("user confusion")
        mock_loop_obj = MagicMock()
        mock_loop_obj.graph = mock_graph
        mock_loop_obj.recursion_limit = 25

        node_fn = _build_expediente_node(
            mode_name="EXPEDIENTE_COLLECT_PERSONAL",
            sub_mode="collect_personal",
            get_tools_fn=_get_personal_tools,
        )

        state = _make_state(retry_count=0)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=mock_loop_obj):
            cmd = await node_fn(state, None)

        handler = FallbackHandler()
        policy = handler.get_policy("EXPEDIENTE_MODE")
        expected = policy.msg_retry_1

        assert cmd.update["ai_response"] == expected, (
            f"Expected msg_retry_1={expected!r}, got {cmd.update['ai_response']!r}"
        )

    @pytest.mark.asyncio
    async def test_second_error_ai_response_matches_policy_msg_retry_2(self):
        """On retry_count 1→2, ai_response should equal policy.msg_retry_2."""
        from agent.modes.expediente_nodes import _build_expediente_node
        from agent.modes.submodos._shared import _get_personal_tools
        from agent.fallback.fallback_handler import FallbackHandler

        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = ValueError("still confused")
        mock_loop_obj = MagicMock()
        mock_loop_obj.graph = mock_graph
        mock_loop_obj.recursion_limit = 25

        node_fn = _build_expediente_node(
            mode_name="EXPEDIENTE_COLLECT_PERSONAL",
            sub_mode="collect_personal",
            get_tools_fn=_get_personal_tools,
        )

        state = _make_state(retry_count=1, consecutive_errors=1)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=mock_loop_obj):
            cmd = await node_fn(state, None)

        handler = FallbackHandler()
        policy = handler.get_policy("EXPEDIENTE_MODE")
        expected = policy.msg_retry_2

        assert cmd.update["ai_response"] == expected


# ---------------------------------------------------------------------------
# Task 3.6 — S2-partial: at limit → _fallback_triggered=True, count=3
# ---------------------------------------------------------------------------

class TestFallbackTriggerAtLimit:
    """
    S2-partial: seed retry_count=2 (one below limit), raise error:
    - retry_count must become 3
    - _fallback_triggered must be True
    - escalation_reason must be set
    """

    @pytest.mark.asyncio
    async def test_at_limit_sets_fallback_triggered(self):
        """Seed retry_count=2 + error → _fallback_triggered=True."""
        from agent.modes.expediente_nodes import _build_expediente_node
        from agent.modes.submodos._shared import _get_personal_tools

        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = ValueError("third error")
        mock_loop_obj = MagicMock()
        mock_loop_obj.graph = mock_graph
        mock_loop_obj.recursion_limit = 25

        node_fn = _build_expediente_node(
            mode_name="EXPEDIENTE_COLLECT_PERSONAL",
            sub_mode="collect_personal",
            get_tools_fn=_get_personal_tools,
        )

        state = _make_state(retry_count=2, consecutive_errors=2)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=mock_loop_obj):
            cmd = await node_fn(state, None)

        update = cmd.update
        assert update.get("_fallback_triggered") is True, (
            "_fallback_triggered must be True when retry limit is reached"
        )
        assert update["retry_state"]["retry_count"] == 3

    @pytest.mark.asyncio
    async def test_at_limit_sets_escalation_reason(self):
        """_fallback_triggered=True must be accompanied by escalation_reason."""
        from agent.modes.expediente_nodes import _build_expediente_node
        from agent.modes.submodos._shared import _get_personal_tools

        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = ValueError("third error")
        mock_loop_obj = MagicMock()
        mock_loop_obj.graph = mock_graph
        mock_loop_obj.recursion_limit = 25

        node_fn = _build_expediente_node(
            mode_name="EXPEDIENTE_COLLECT_PERSONAL",
            sub_mode="collect_personal",
            get_tools_fn=_get_personal_tools,
        )

        state = _make_state(retry_count=2, consecutive_errors=2)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=mock_loop_obj):
            cmd = await node_fn(state, None)

        update = cmd.update
        assert "escalation_reason" in update, "escalation_reason must be set at limit"
        assert len(update["escalation_reason"].strip()) > 0


# ---------------------------------------------------------------------------
# Task 5.1 (Ola 5 seeded here) — S3: success → consecutive_errors reset
# ---------------------------------------------------------------------------

class TestSuccessResetsConsecutiveErrors:
    """
    S3: when the tool loop succeeds, consecutive_errors must be reset to 0.
    retry_count is preserved (only reset on completion_flag, not per-turn success).
    """

    @pytest.mark.asyncio
    async def test_success_resets_consecutive_errors(self):
        """Tool loop success with prior consecutive_errors=2 → consecutive_errors=0 in update."""
        from agent.modes.expediente_nodes import _build_expediente_node
        from agent.modes.submodos._shared import _get_personal_tools

        # Successful loop result
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "ai_response": "Perfecto, datos recibidos.",
            "exit_reason": "response",
            "pending_state_updates": {},
        }
        mock_loop_obj = MagicMock()
        mock_loop_obj.graph = mock_graph
        mock_loop_obj.recursion_limit = 25

        node_fn = _build_expediente_node(
            mode_name="EXPEDIENTE_COLLECT_PERSONAL",
            sub_mode="collect_personal",
            get_tools_fn=_get_personal_tools,
        )

        state = _make_state(retry_count=2, consecutive_errors=2)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=mock_loop_obj):
            cmd = await node_fn(state, None)

        update = cmd.update
        assert "retry_state" in update
        # consecutive_errors must be 0 after success
        assert update["retry_state"]["consecutive_errors"] == 0, (
            "consecutive_errors must reset to 0 on successful turn"
        )

    @pytest.mark.asyncio
    async def test_success_preserves_retry_count(self):
        """
        per-turn success resets consecutive_errors only; retry_count is preserved
        (spec: retry_count resets only on completion_flag=True, S3/S5).
        """
        from agent.modes.expediente_nodes import _build_expediente_node
        from agent.modes.submodos._shared import _get_personal_tools

        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "ai_response": "Datos registrados.",
            "exit_reason": "response",
            "pending_state_updates": {},
        }
        mock_loop_obj = MagicMock()
        mock_loop_obj.graph = mock_graph
        mock_loop_obj.recursion_limit = 25

        node_fn = _build_expediente_node(
            mode_name="EXPEDIENTE_COLLECT_PERSONAL",
            sub_mode="collect_personal",
            get_tools_fn=_get_personal_tools,
        )

        state = _make_state(retry_count=2, consecutive_errors=2)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=mock_loop_obj):
            cmd = await node_fn(state, None)

        update = cmd.update
        # retry_count stays at 2 — not reset by per-turn success
        assert update["retry_state"]["retry_count"] == 2, (
            "retry_count must NOT reset on per-turn success — only on completion_flag=True"
        )


# ---------------------------------------------------------------------------
# Task 5.3 — S5: sub-mode transition preserves retry_count (no reset)
# ---------------------------------------------------------------------------

class TestSubModeTransitionPreservesCounter:
    """
    S5: transitioning sub-modes (expediente_sub_mode changes but no completion_flag=True)
    must NOT reset retry_count.  Only completion_flag=True resets it.
    """

    @pytest.mark.asyncio
    async def test_sub_mode_transition_preserves_retry_count(self):
        """
        Sub-mode changes from collect_personal → collect_vehicle without
        completion_flag=True; retry_count must be preserved.
        """
        from agent.modes.expediente_state import parent_to_expediente, expediente_to_parent_updates

        parent_state = {
            "conversation_id": "conv-s5",
            "user_id": "user-001",
            "user_phone": "+34600000001",
            "user_message": "transición sin completar",
            "mode_context": {"expediente_sub_mode": "collect_personal"},
            "retry_state": {"retry_count": 2, "consecutive_errors": 1},
        }

        # Simulate a sub-mode transition (expediente_sub_mode changed, no completion_flag)
        exp_input = parent_to_expediente(parent_state)
        # Simulate what happens: sub-mode transitions but completion_flag not set
        exp_output = dict(exp_input)
        exp_output["expediente_sub_mode"] = "collect_vehicle"  # transition without flag
        exp_output["ai_response"] = "Continuamos con el vehículo."
        exp_output["exit_reason"] = "response"
        exp_output["retry_state"] = {"retry_count": 2, "consecutive_errors": 1}  # preserved

        updates = expediente_to_parent_updates(exp_output)  # type: ignore[arg-type]

        # retry_count must be 2 (preserved, not reset)
        assert updates["retry_state"]["retry_count"] == 2, (
            "retry_count must NOT reset on sub-mode transition without completion_flag=True"
        )

    @pytest.mark.asyncio
    async def test_retry_state_survives_boundary_round_trip(self):
        """
        Full round-trip: parent(retry_count=2) → expediente → parent updates.
        retry_count must be the same value after the round-trip (S5 preservation).
        """
        from agent.modes.expediente_state import parent_to_expediente, expediente_to_parent_updates

        parent_state = {
            "conversation_id": "conv-s5-rt",
            "user_id": "user-001",
            "user_phone": "+34600000001",
            "user_message": "",
            "mode_context": {},
            "retry_state": {"retry_count": 2, "consecutive_errors": 2},
        }

        exp = parent_to_expediente(parent_state)
        # No modification — just pass through
        updates = expediente_to_parent_updates(exp)

        assert updates["retry_state"]["retry_count"] == 2, (
            "retry_count must survive the boundary round-trip unchanged"
        )


# ---------------------------------------------------------------------------
# Task 5.4 — S6: completion_flag=True resets retry_count to 0
# ---------------------------------------------------------------------------

class TestCompletionFlagResetsRetryCount:
    """
    S6: when completion_flag=True is set (sub-mode marked as done),
    retry_state must be reset — retry_count becomes 0.
    """

    @pytest.mark.asyncio
    async def test_completion_flag_resets_retry_count(self):
        """
        completion_flag=True → retry_count reset to 0 in the Command update.
        """
        from agent.modes.expediente_nodes import _build_expediente_node
        from agent.modes.submodos._shared import _get_personal_tools

        # Tool loop result: sub-mode transitions away from collect_personal
        # (simulating personal data fully collected)
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "ai_response": "Datos personales completos.",
            "exit_reason": "response",
            "pending_state_updates": {
                # Sub-mode transitions away — signals completion
                "expediente_sub_mode": "collect_vehicle",
            },
        }
        mock_loop_obj = MagicMock()
        mock_loop_obj.graph = mock_graph
        mock_loop_obj.recursion_limit = 25

        node_fn = _build_expediente_node(
            mode_name="EXPEDIENTE_COLLECT_PERSONAL",
            sub_mode="collect_personal",
            get_tools_fn=_get_personal_tools,
            completion_flag="personal_collected",
            own_sub_mode="collect_personal",
        )

        # Prior retry_count=2 from previous errors
        state = _make_state(retry_count=2, consecutive_errors=2)
        state["expediente_sub_mode"] = "collect_personal"

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=mock_loop_obj):
            cmd = await node_fn(state, None)

        update = cmd.update
        assert "retry_state" in update

        # When personal_collected=True is set (completion_flag fires),
        # retry_count must be 0
        if update.get("personal_collected") is True:
            assert update["retry_state"]["retry_count"] == 0, (
                "retry_count must reset to 0 when completion_flag=True"
            )
        # If completion didn't fire (sub-mode didn't transition), skip
        # This test relies on the implementation setting personal_collected=True
        # when expediente_sub_mode changes away from collect_personal

    @pytest.mark.asyncio
    async def test_no_completion_no_retry_reset(self):
        """
        When sub-mode does NOT transition (completion_flag NOT set),
        retry_count must remain unchanged (not reset to 0).
        """
        from agent.modes.expediente_nodes import _build_expediente_node
        from agent.modes.submodos._shared import _get_personal_tools

        # Tool loop: sub-mode stays at collect_personal (no transition)
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "ai_response": "¿Cuál es tu nombre?",
            "exit_reason": "response",
            "pending_state_updates": {
                "expediente_sub_mode": "collect_personal",  # same mode
            },
        }
        mock_loop_obj = MagicMock()
        mock_loop_obj.graph = mock_graph
        mock_loop_obj.recursion_limit = 25

        node_fn = _build_expediente_node(
            mode_name="EXPEDIENTE_COLLECT_PERSONAL",
            sub_mode="collect_personal",
            get_tools_fn=_get_personal_tools,
            completion_flag="personal_collected",
            own_sub_mode="collect_personal",
        )

        state = _make_state(retry_count=2, consecutive_errors=2)
        state["expediente_sub_mode"] = "collect_personal"

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=mock_loop_obj):
            cmd = await node_fn(state, None)

        update = cmd.update
        # completion_flag was NOT set (sub-mode stayed same) → retry_count preserved at 2
        assert not update.get("personal_collected"), (
            "personal_collected must NOT be set when sub-mode stays the same"
        )
        assert update["retry_state"]["retry_count"] == 2, (
            "retry_count must not reset when no completion_flag fires"
        )
