"""
Expediente subgraph builder.

Defines a 7-node ``StateGraph(ExpedienteState)`` that replaces the
monolithic ``ExpedienteModeNode`` coordinator.

Graph structure:
  START → entry_router
  entry_router → (conditional on expediente_sub_mode) → <sub_mode_node>
  <sub_mode_node> → END

The compiled subgraph is mounted as a single node named ``expediente_mode_node``
in the parent ``ConversationState`` graph (see ``agent/graph/conversation_graph.py``).

Checkpointer: ``False`` — the parent graph's Redis checkpointer already persists
all state. No interrupts are needed inside the subgraph (WhatsApp is async
event-driven). Using ``checkpointer=False`` avoids checkpoint namespace overhead.
See AD-1 for the rationale.

Design reference: AD-1 (Subgraph Wiring Pattern), AD-2 (State Boundary Design)
"""

from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from agent.modes.expediente_state import ExpedienteState
from agent.modes.expediente_nodes import (
    entry_router,
    collect_element_data_node,
    collect_base_docs_node,
    collect_personal_node,
    collect_vehicle_node,
    collect_workshop_node,
    review_summary_node,
    join_collections_node,
)

# ---------------------------------------------------------------------------
# Node name constants (avoids typos in edge wiring)
# ---------------------------------------------------------------------------

NODE_ENTRY_ROUTER = "entry_router"
NODE_COLLECT_ELEMENT_DATA = "collect_element_data_node"
NODE_COLLECT_BASE_DOCS = "collect_base_docs_node"
NODE_COLLECT_PERSONAL = "collect_personal_node"
NODE_COLLECT_VEHICLE = "collect_vehicle_node"
NODE_COLLECT_WORKSHOP = "collect_workshop_node"
NODE_REVIEW_SUMMARY = "review_summary_node"
NODE_JOIN_COLLECTIONS = "join_collections_node"  # WS6 — flexible routing join point

# All 8 expected node names — used by tests to verify registration
EXPECTED_NODES: frozenset[str] = frozenset(
    {
        NODE_ENTRY_ROUTER,
        NODE_COLLECT_ELEMENT_DATA,
        NODE_COLLECT_BASE_DOCS,
        NODE_COLLECT_PERSONAL,
        NODE_COLLECT_VEHICLE,
        NODE_COLLECT_WORKSHOP,
        NODE_REVIEW_SUMMARY,
        NODE_JOIN_COLLECTIONS,
    }
)


def build_expediente_subgraph() -> StateGraph:
    """
    Build and return the expediente ``StateGraph`` (uncompiled).

    Returns a ``StateGraph(ExpedienteState)`` with 7 nodes wired as follows:

    - START → entry_router (static edge — always enter via router)
    - entry_router → <sub_mode_node> (via ``Command(goto=...)`` returned by
      ``entry_router``; no static conditional edges needed because Command
      handles dynamic routing internally)

    Each sub-mode node returns ``Command(goto=END)`` in Phase 2 stubs.
    Phase 3 will update them to return ``Command(goto="entry_router", ...)``
    on sub-mode transitions, or ``Command(goto=END)`` when done.

    Note: Do NOT call ``.compile()`` here — the caller is responsible for
    compiling with the appropriate checkpointer (``False`` for subgraph use,
    or ``InMemorySaver`` for integration tests).

    Returns:
        Un-compiled ``StateGraph(ExpedienteState)`` ready for ``.compile()``.
    """
    builder = StateGraph(ExpedienteState)

    # ── Register all 8 nodes ──────────────────────────────────────────────
    builder.add_node(NODE_ENTRY_ROUTER, entry_router)
    builder.add_node(NODE_COLLECT_ELEMENT_DATA, collect_element_data_node)
    builder.add_node(NODE_COLLECT_BASE_DOCS, collect_base_docs_node)
    builder.add_node(NODE_COLLECT_PERSONAL, collect_personal_node)
    builder.add_node(NODE_COLLECT_VEHICLE, collect_vehicle_node)
    builder.add_node(NODE_COLLECT_WORKSHOP, collect_workshop_node)
    builder.add_node(NODE_REVIEW_SUMMARY, review_summary_node)
    # WS6 — pure routing join point; no static exit edges needed (Command-driven)
    builder.add_node(NODE_JOIN_COLLECTIONS, join_collections_node)

    # ── Entry edge: START → entry_router ─────────────────────────────────
    builder.add_edge(START, NODE_ENTRY_ROUTER)

    # ── Sub-mode exit edges: each node → END ─────────────────────────────
    # These static END edges coexist with the Command(goto=END) returned by
    # stubs.  In Phase 3, nodes returning Command(goto="entry_router") will
    # re-enter the router; nodes completing the session will use Command(goto=END).
    # NOTE: Command-only routing is used — we do NOT add static conditional edges
    # from entry_router to sub-mode nodes because entry_router returns Command(goto=...)
    # which handles the routing dynamically.  Static edges from sub-mode nodes to
    # END are NOT needed when using Command(goto=END), but we add them here for
    # explicitness and to satisfy LangGraph's graph validation that every node
    # has at least one exit path declared.
    # (LangGraph accepts Command nodes without static exit edges, so these are
    #  documentation-only; remove if they cause validation issues.)

    return builder
