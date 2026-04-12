"""Tests for preprocess_node — WS1: chaining removed."""

import pytest


class TestPreprocessNodeBasic:
    """Verify preprocess_node basic behavior after chaining removal."""

    @pytest.fixture
    def base_state(self):
        return {
            "conversation_id": "test-conv",
            "current_mode": "PRESUPUESTO_MODE",
            "messages": [{"role": "user", "content": "test"}],
            "user_message": "test message",
            "total_message_count": 5,
            "mode_message_count": 2,
            "agent_disabled": False,
            "pending_images": None,
            "tarifa_actual": None,
            "incoming_attachments": [],
        }

    @pytest.mark.asyncio
    async def test_preprocess_increments_message_counters(self, base_state):
        """preprocess_node must increment total and mode message counters."""
        from agent.graph.conversation_graph import preprocess_node

        result = await preprocess_node(base_state)

        assert result["total_message_count"] == 6
        assert result["mode_message_count"] == 3

    @pytest.mark.asyncio
    async def test_preprocess_resets_transient_fields(self, base_state):
        """preprocess_node must reset transient fields each turn."""
        from agent.graph.conversation_graph import preprocess_node

        base_state["pending_images"] = {"some": "images"}
        base_state["tarifa_actual"] = {"price": 410}
        result = await preprocess_node(base_state)

        assert result["pending_images"] is None
        assert result["tarifa_actual"] is None
        assert result["ai_response"] is None

    @pytest.mark.asyncio
    async def test_preprocess_no_chaining_fields(self, base_state):
        """preprocess_node must NOT return _chain_next_mode or _is_chained_turn.

        These fields were part of the old external chaining loop (WS1).
        They must not appear in preprocess_node output after the refactor.
        """
        from agent.graph.conversation_graph import preprocess_node

        result = await preprocess_node(base_state)

        assert "_chain_next_mode" not in result, (
            "_chain_next_mode must not be set by preprocess_node after WS1 refactor"
        )
        assert "_is_chained_turn" not in result, (
            "_is_chained_turn must not be set by preprocess_node after WS1 refactor"
        )

    @pytest.mark.asyncio
    async def test_preprocess_disabled_agent_escalates(self, base_state):
        """agent_disabled flag causes immediate escalation routing."""
        from agent.graph.conversation_graph import preprocess_node

        base_state["agent_disabled"] = True
        result = await preprocess_node(base_state)

        assert result["current_mode"] == "ESCALATION"
        assert result["escalation_triggered"] is True
