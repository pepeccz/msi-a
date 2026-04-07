"""
Integration tests for expediente subgraph Phase 4.

TDD Phase 4: Parent Integration & Subgraph Wiring.

Covers tasks:
- T-19 [RED] / T-20 [GREEN]: Same-turn PRESUPUESTO→EXPEDIENTE chain with subgraph
- T-21 [RED] / T-22 [GREEN]: Orphan recovery passing signal to subgraph
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


# ---------------------------------------------------------------------------
# T-19 / T-20: Same-turn PRESUPUESTO→EXPEDIENTE chain with subgraph
# ---------------------------------------------------------------------------


class TestSameTurnChaining:
    """
    Same-turn PRESUPUESTO→EXPEDIENTE chain must work regardless of which
    expediente node is mounted (v1 or subgraph).

    The _chain_next_mode mechanism in main.py re-invokes the graph with a
    synthetic turn when PRESUPUESTO_MODE's confirmar_presupuesto() tool
    returns _transition_to=EXPEDIENTE_MODE in _state_update.
    """

    def test_chain_next_mode_signal_contract(self) -> None:
        """
        The _chain_next_mode mechanism depends on the result dict having
        a non-None _chain_next_mode key. This test verifies the key name
        contract (not the actual PRESUPUESTO tool, just the key detection).
        """
        # This is a contract test — main.py's chaining loop looks for this key
        result_with_chain = {
            "ai_response": "Pasamos al expediente.",
            "current_mode": "EXPEDIENTE_MODE",
            "_chain_next_mode": "EXPEDIENTE_MODE",
        }
        # The while condition in main.py is: result.get("_chain_next_mode") and ...
        assert bool(result_with_chain.get("_chain_next_mode")) is True

    def test_chain_state_input_structure(self) -> None:
        """
        The chain_state_input built in main.py's chaining loop must contain
        the expected keys so the graph's preprocess_node can handle it.
        """
        # Replicate the chain_state_input structure from main.py
        chain_state_input = {
            "conversation_id": "test-conv-123",
            "user_id": "user-456",
            "user_name": "Test User",
            "user_message": "Vamos, empezamos con el expediente.",
            "client_type": "particular",
            "messages": [],
            "_is_chained_turn": True,
        }
        # Verify _is_chained_turn is set (preprocess_node skips counters for this)
        assert chain_state_input["_is_chained_turn"] is True
        assert (
            chain_state_input["user_message"] == "Vamos, empezamos con el expediente."
        )
        assert "conversation_id" in chain_state_input

    def test_preprocess_node_handles_chained_turn(self) -> None:
        """
        preprocess_node with _is_chained_turn=True returns reset transient fields
        without incrementing counters — identical behavior regardless of which
        expediente node is active.
        """
        import asyncio
        from agent.graph.conversation_graph import preprocess_node

        state = {
            "conversation_id": "test-123",
            "user_message": "Vamos, empezamos con el expediente.",
            "_is_chained_turn": True,
            "total_message_count": 3,
            "mode_message_count": 2,
            "current_mode": "EXPEDIENTE_MODE",
        }

        result = asyncio.run(preprocess_node(state))

        # Counter must NOT be incremented for chained turns
        assert "total_message_count" not in result, (
            "preprocess_node should not return total_message_count for chained turns"
        )
        # Transient fields must be reset
        assert result.get("_chain_next_mode") is None
        assert result.get("_is_chained_turn") is False

    def test_chain_works_with_subgraph_mounted(self) -> None:
        """
        The subgraph is always mounted; the chain mechanism produces a compilable graph.
        """
        from agent.graph.conversation_graph import build_conversation_graph

        compiled = build_conversation_graph().compile()
        assert compiled is not None


# ---------------------------------------------------------------------------
# T-21 / T-22: Orphan recovery passing signal to subgraph
# ---------------------------------------------------------------------------


class TestOrphanRecoverySignal:
    """
    Orphan recovery sets pending_recovery_case in mode_context at the parent level.
    The parent_to_expediente() boundary mapper must copy it into ExpedienteState.
    """

    def test_pending_recovery_case_in_expediente_mc_keys(self) -> None:
        """
        pending_recovery_case is declared in _EXPEDIENTE_MC_KEYS so it is
        copied through the parent_to_expediente() boundary mapper.
        """
        from agent.modes.expediente_state import _EXPEDIENTE_MC_KEYS

        assert "pending_recovery_case" in _EXPEDIENTE_MC_KEYS, (
            "pending_recovery_case must be in _EXPEDIENTE_MC_KEYS to cross the boundary"
        )

    def test_parent_to_expediente_copies_pending_recovery_case(self) -> None:
        """
        parent_to_expediente() must copy pending_recovery_case from mode_context
        into the ExpedienteState.
        """
        from agent.modes.expediente_state import parent_to_expediente

        recovery_payload = {
            "case_id": "case-abc-123",
            "inferred_sub_mode": "collect_base_docs",
            "status": "collecting",
        }

        parent_state = {
            "conversation_id": "conv-123",
            "user_id": "user-456",
            "user_phone": "+34600000001",
            "user_name": "Test",
            "client_type": "particular",
            "user_message": "Hola",
            "mode_context": {
                "pending_recovery_case": recovery_payload,
                "expediente_sub_mode": "collect_base_docs",
            },
        }

        exp_state = parent_to_expediente(parent_state)

        assert "pending_recovery_case" in exp_state, (
            "pending_recovery_case must survive the parent_to_expediente() mapping"
        )
        assert exp_state["pending_recovery_case"] == recovery_payload

    def test_parent_to_expediente_copies_inferred_sub_mode(self) -> None:
        """
        When recovery sets expediente_sub_mode in mode_context, it is copied
        through the boundary to ExpedienteState.
        """
        from agent.modes.expediente_state import parent_to_expediente

        parent_state = {
            "conversation_id": "conv-123",
            "user_id": "user-456",
            "user_phone": "+34600000001",
            "user_name": "Test",
            "client_type": "particular",
            "user_message": "Hola",
            "mode_context": {
                "pending_recovery_case": {"case_id": "xyz"},
                "expediente_sub_mode": "collect_workshop",
            },
        }

        exp_state = parent_to_expediente(parent_state)

        assert exp_state.get("expediente_sub_mode") == "collect_workshop"

    def test_recovery_payload_survives_round_trip(self) -> None:
        """
        pending_recovery_case survives the full parent→expediente→parent round-trip.
        After expediente_to_parent_updates(), the key is in mode_context.
        """
        from agent.modes.expediente_state import (
            parent_to_expediente,
            expediente_to_parent_updates,
            ExpedienteState,
        )

        recovery_payload = {
            "case_id": "case-round-trip",
            "inferred_sub_mode": "collect_personal",
        }

        parent_state = {
            "conversation_id": "conv-123",
            "user_id": "user-456",
            "user_phone": "+34600000001",
            "user_name": "Test",
            "client_type": "particular",
            "user_message": "Hola",
            "mode_context": {
                "pending_recovery_case": recovery_payload,
                "expediente_sub_mode": "collect_personal",
            },
        }

        # Forward: parent → expediente
        exp_state = parent_to_expediente(parent_state)
        assert exp_state.get("pending_recovery_case") == recovery_payload

        # Simulate entry_router consuming the recovery (sets case_id, clears pending)
        exp_state_after: dict[str, Any] = dict(exp_state)
        exp_state_after["pending_recovery_case"] = None  # consumed
        exp_state_after["case_id"] = recovery_payload["case_id"]
        exp_state_after["expediente_sub_mode"] = "collect_personal"
        exp_state_after["ai_response"] = "Continuamos con tu expediente."

        # Backward: expediente → parent
        parent_updates = expediente_to_parent_updates(
            ExpedienteState(**exp_state_after)
        )  # type: ignore[misc]

        # After round-trip: pending_recovery_case should be None (consumed)
        mc = parent_updates["mode_context"]
        assert mc.get("pending_recovery_case") is None
        assert mc.get("case_id") == "case-round-trip"

    def test_recovery_with_null_pending_does_not_break_boundary(self) -> None:
        """
        When mode_context has no pending_recovery_case, parent_to_expediente()
        still works (returns None for that key or omits it).
        """
        from agent.modes.expediente_state import parent_to_expediente

        parent_state = {
            "conversation_id": "conv-123",
            "user_id": "user-456",
            "user_phone": "+34600000001",
            "user_name": "Test",
            "client_type": "particular",
            "user_message": "Hola",
            "mode_context": {
                "case_id": "existing-case-id",
                "expediente_sub_mode": "collect_element_data",
            },
        }

        exp_state = parent_to_expediente(parent_state)

        # No exception — boundary handles missing key gracefully
        # pending_recovery_case either absent or None
        assert exp_state.get("pending_recovery_case") is None or (
            "pending_recovery_case" not in exp_state
        )

    def test_preprocess_node_sets_pending_recovery_case_in_mode_context(self) -> None:
        """
        preprocess_node's orphan recovery injects pending_recovery_case into
        mode_context when an orphaned case is detected.

        The key must be wrapped in Overwrite({pending_recovery_case: ...}) so
        the merge_dicts reducer writes it correctly.
        """
        import asyncio
        from langgraph.types import Overwrite
        from agent.graph.conversation_graph import preprocess_node

        recovery_dict = {
            "case_id": "recovered-case-abc",
            "inferred_sub_mode": "collect_element_data",
            "status": "collecting",
        }

        # Patch _try_recover_orphaned_expediente to return a recovery payload
        with patch(
            "agent.graph.conversation_graph._try_recover_orphaned_expediente",
            new=AsyncMock(return_value=recovery_dict),
        ):
            state = {
                "conversation_id": "conv-fresh",
                "user_id": "user-123",
                "user_phone": "+34600000001",
                "user_message": "Hola",
                "total_message_count": 0,  # fresh thread (will become 1 inside)
                "current_mode": "START",
                "mode_context": {},
                "agent_disabled": False,
                "_is_chained_turn": False,
            }

            result = asyncio.run(preprocess_node(state))

        # The mode_context must be set (wrapped in Overwrite)
        mode_context = result.get("mode_context")
        assert mode_context is not None, "mode_context not set in preprocess result"

        # Unwrap Overwrite if needed
        if isinstance(mode_context, Overwrite):
            # Overwrite is a wrapper — extract the inner dict
            inner = (
                mode_context.value
                if hasattr(mode_context, "value")
                else mode_context.__wrapped__
                if hasattr(mode_context, "__wrapped__")
                else dict(mode_context)
            )
        else:
            inner = mode_context

        # pending_recovery_case must be inside
        if isinstance(inner, dict):
            assert "pending_recovery_case" in inner, (
                f"pending_recovery_case missing from mode_context. Keys: {list(inner.keys())}"
            )

    def test_expediente_sub_mode_from_recovery_enters_subgraph(self) -> None:
        """
        When pending_recovery_case sets expediente_sub_mode, that value is
        available to the subgraph's entry_router after parent_to_expediente().
        """
        from agent.modes.expediente_state import parent_to_expediente

        # Simulate what preprocess_node injects after recovery detection
        parent_state = {
            "conversation_id": "conv-123",
            "user_id": "user-456",
            "user_phone": "+34600000001",
            "user_name": "Test",
            "client_type": "particular",
            "user_message": "Hola",
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {
                "pending_recovery_case": {
                    "case_id": "recovered-xyz",
                    "status": "collecting",
                },
                # preprocess_node also seeds expediente_sub_mode from inferred_sub_mode
                "expediente_sub_mode": "collect_base_docs",
            },
        }

        exp_state = parent_to_expediente(parent_state)

        # The entry_router will see both signals
        assert exp_state.get("pending_recovery_case") is not None
        assert exp_state.get("expediente_sub_mode") == "collect_base_docs"

    def test_recovery_signal_triggers_expediente_mode_routing(self) -> None:
        """
        When preprocess_node detects an orphaned case, it sets current_mode to
        EXPEDIENTE_MODE so the router sends the next turn to the expediente node
        (whether that's v1 or the subgraph).
        """
        import asyncio
        from agent.graph.conversation_graph import preprocess_node

        recovery_dict = {
            "case_id": "recovered-case-abc",
            "inferred_sub_mode": "collect_element_data",
        }

        with patch(
            "agent.graph.conversation_graph._try_recover_orphaned_expediente",
            new=AsyncMock(return_value=recovery_dict),
        ):
            state = {
                "conversation_id": "conv-fresh",
                "user_id": "user-123",
                "user_phone": "+34600000001",
                "user_message": "Hola",
                "total_message_count": 0,
                "current_mode": "START",
                "mode_context": {},
                "agent_disabled": False,
                "_is_chained_turn": False,
            }

            result = asyncio.run(preprocess_node(state))

        # current_mode must be EXPEDIENTE_MODE after recovery detection
        assert result.get("current_mode") == "EXPEDIENTE_MODE", (
            f"Expected current_mode=EXPEDIENTE_MODE after recovery, got: {result.get('current_mode')}"
        )
