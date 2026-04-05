"""Tests for preprocess_node chained turn reset."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


class TestPreprocessChainedTurnReset:
    """Verify _is_chained_turn is reset to False on both paths."""

    @pytest.fixture
    def base_state(self):
        return {
            "conversation_id": "test-conv",
            "current_mode": "EXPEDIENTE",
            "messages": [{"role": "user", "content": "test"}],
            "user_message": "test message",
            "total_message_count": 5,
            "mode_message_count": 2,
            "agent_disabled": False,
            "_is_chained_turn": True,
            "_chain_next_mode": None,
            "pending_images": None,
            "tarifa_actual": None,
            "incoming_attachments": [],
        }

    @pytest.mark.asyncio
    async def test_preprocess_chained_path_resets_is_chained_turn(self, base_state):
        """Chained path MUST return _is_chained_turn: False."""
        from agent.graph.conversation_graph import preprocess_node

        base_state["_is_chained_turn"] = True
        result = await preprocess_node(base_state)

        assert result["_is_chained_turn"] is False

    @pytest.mark.asyncio
    async def test_preprocess_non_chained_path_resets_is_chained_turn(self, base_state):
        """Non-chained path MUST return _is_chained_turn: False."""
        from agent.graph.conversation_graph import preprocess_node

        base_state["_is_chained_turn"] = False
        result = await preprocess_node(base_state)

        assert result["_is_chained_turn"] is False

    @pytest.mark.asyncio
    async def test_preprocess_chained_path_still_resets_chain_next_mode(self, base_state):
        """Regression: _chain_next_mode must still be reset."""
        from agent.graph.conversation_graph import preprocess_node

        base_state["_is_chained_turn"] = True
        base_state["_chain_next_mode"] = "EXPEDIENTE"
        result = await preprocess_node(base_state)

        assert result["_chain_next_mode"] is None
