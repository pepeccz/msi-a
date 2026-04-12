"""
WS6 — Fan-out Expediente with flexible routing.

Tests for:
- ExpedienteState completion flags (personal_collected, vehicle_collected, workshop_collected)
- entry_router flexible routing after element_data + base_docs complete
- join_collections_node pure routing to review_summary
- Intent-based routing from user_message keywords
- Workshop skip for non-applicable clients

Test inventory
--------------
1. test_expediente_state_has_completion_flags
2. test_default_order_personal_first
3. test_all_flags_true_routes_to_join_collections
4. test_vehicle_intent_routes_to_vehicle
5. test_join_collections_routes_to_review_summary
6. test_workshop_skip_for_non_applicable
7. test_element_data_unchanged
"""

from __future__ import annotations

import pytest

from agent.modes.expediente_state import ExpedienteState
from agent.modes.expediente_nodes import entry_router, join_collections_node
from agent.graph.expediente_subgraph import EXPECTED_NODES, NODE_JOIN_COLLECTIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_after_base_docs(**kwargs) -> ExpedienteState:
    """
    Minimal ExpedienteState that simulates post-base_docs completion:
    - case_id present (no initialization needed)
    - expediente_sub_mode not matching element_data or base_docs
    - element_data_all_collected = True
    - base_docs_received = True
    """
    base: dict = {
        "conversation_id": "test-fanout",
        "case_id": "case-123",
        "user_message": "",
        "expediente_sub_mode": "collect_personal",
        "element_data_all_collected": True,
        "base_docs_received": True,
        "personal_collected": False,
        "vehicle_collected": False,
        "workshop_collected": False,
    }
    base.update(kwargs)
    return ExpedienteState(**base)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test 1: ExpedienteState has completion flags
# ---------------------------------------------------------------------------

def test_expediente_state_has_completion_flags():
    """personal_collected, vehicle_collected, workshop_collected must exist in ExpedienteState annotations."""
    import typing
    hints = typing.get_type_hints(ExpedienteState)
    assert "personal_collected" in hints, "personal_collected missing from ExpedienteState"
    assert "vehicle_collected" in hints, "vehicle_collected missing from ExpedienteState"
    assert "workshop_collected" in hints, "workshop_collected missing from ExpedienteState"
    assert hints["personal_collected"] is bool
    assert hints["vehicle_collected"] is bool
    assert hints["workshop_collected"] is bool


# ---------------------------------------------------------------------------
# Test 2: Default order — personal first (all flags False)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_default_order_personal_first():
    """When all collection flags are False, entry_router routes to collect_personal_node."""
    state = _state_after_base_docs(
        personal_collected=False,
        vehicle_collected=False,
        workshop_collected=False,
    )
    cmd = await entry_router(state)
    assert cmd.goto == "collect_personal_node", (
        f"Expected collect_personal_node, got {cmd.goto}"
    )


# ---------------------------------------------------------------------------
# Test 3: All flags True → routes to join_collections_node
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_flags_true_routes_to_join_collections():
    """When all 3 collection flags are True, entry_router routes to join_collections_node."""
    state = _state_after_base_docs(
        personal_collected=True,
        vehicle_collected=True,
        workshop_collected=True,
    )
    cmd = await entry_router(state)
    assert cmd.goto == "join_collections_node", (
        f"Expected join_collections_node, got {cmd.goto}"
    )


# ---------------------------------------------------------------------------
# Test 4: Vehicle intent from user_message keyword
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vehicle_intent_routes_to_vehicle():
    """user_message containing 'matrícula' with vehicle_collected=False → collect_vehicle_node."""
    state = _state_after_base_docs(
        user_message="mi matrícula es 1234ABC",
        personal_collected=False,
        vehicle_collected=False,
        workshop_collected=False,
    )
    cmd = await entry_router(state)
    assert cmd.goto == "collect_vehicle_node", (
        f"Expected collect_vehicle_node, got {cmd.goto}"
    )


# ---------------------------------------------------------------------------
# Test 5: join_collections_node routes to review_summary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_join_collections_routes_to_review_summary():
    """join_collections_node is a pure routing node that goes to review_summary_node."""
    state = _state_after_base_docs(
        personal_collected=True,
        vehicle_collected=True,
        workshop_collected=True,
    )
    cmd = await join_collections_node(state, None)
    assert cmd.goto == "review_summary_node", (
        f"Expected review_summary_node, got {cmd.goto}"
    )
    # Must also set expediente_sub_mode
    assert cmd.update is not None
    assert cmd.update.get("expediente_sub_mode") == "review_summary"


# ---------------------------------------------------------------------------
# Test 6: Workshop skipped for non-applicable client (particular)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workshop_skip_for_non_applicable():
    """For particular client type with workshop not applicable, workshop can be skipped."""
    # particular client: taller_propio is False/None → workshop not needed
    state = _state_after_base_docs(
        client_type="particular",
        taller_propio=False,
        personal_collected=True,
        vehicle_collected=True,
        workshop_collected=False,  # not yet marked done
    )
    # With personal + vehicle done, workshop not applicable → should set workshop_collected
    # The entry_router should recognize taller_propio=False and mark workshop as complete,
    # then route to join_collections_node.
    cmd = await entry_router(state)
    # Either workshop is auto-skipped (workshop_collected set, route to join_collections)
    # OR it routes to collect_workshop which will immediately skip.
    # The key assertion: we don't get routed to collect_vehicle again (already done)
    # and we don't loop back to personal (already done).
    assert cmd.goto in ("join_collections_node", "collect_workshop_node"), (
        f"Unexpected goto: {cmd.goto}"
    )


# ---------------------------------------------------------------------------
# Test 7: Element data routing unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_element_data_unchanged():
    """collect_element_data sub_mode still routes normally via _SUB_MODE_TO_NODE."""
    state = ExpedienteState(  # type: ignore[misc]
        conversation_id="test-elem",
        case_id="case-456",
        user_message="aquí tienes la foto",
        expediente_sub_mode="collect_element_data",
        element_phase="data",
        element_data_all_collected=False,
        base_docs_received=False,
    )
    cmd = await entry_router(state)
    assert cmd.goto == "collect_element_data_node", (
        f"Expected collect_element_data_node, got {cmd.goto}"
    )


# ---------------------------------------------------------------------------
# Test: join_collections_node is registered in EXPECTED_NODES
# ---------------------------------------------------------------------------

def test_join_collections_node_in_expected_nodes():
    """NODE_JOIN_COLLECTIONS must be registered in EXPECTED_NODES."""
    assert NODE_JOIN_COLLECTIONS in EXPECTED_NODES, (
        f"NODE_JOIN_COLLECTIONS ({NODE_JOIN_COLLECTIONS!r}) not in EXPECTED_NODES"
    )
