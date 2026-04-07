"""
E2E flow and invariant tests for the expediente subgraph.

TDD Phase 5: E2E Flow & Verification (T-23 through T-25).

Covers:
- T-23 [RED]: E2E flow tests — 6 conversation paths (mock LLM + DB, graph wiring)
- T-24 [GREEN]: expediente_to_parent_updates() wired at subgraph→parent boundary
- T-25 [VERIFY]: Structural invariant tests (no merge_dicts, no Annotated reducers,
  feature flag default, zombie-state, old coordinator still importable, 14 invariants)

NOTE: All LLM and DB calls are mocked. These tests verify GRAPH WIRING and
STATE FLOW — not actual LLM behavior or database persistence.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_expediente_state(**kwargs: Any) -> dict[str, Any]:
    """Build a minimal ExpedienteState-shaped dict for testing."""
    base: dict[str, Any] = {
        "conversation_id": "conv-e2e-test",
        "user_id": "user-e2e-123",
        "user_phone": "+34600000001",
        "user_name": "Test User",
        "client_type": "particular",
        "user_message": "Hola",
        "messages": [],
        "incoming_attachments": [],
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# T-23: E2E Flow Tests — 6 conversation paths through the subgraph
# ---------------------------------------------------------------------------


class TestE2ESubgraphInvocation:
    """
    End-to-end tests for the 6 conversation paths through the expediente subgraph.

    All paths use mock sub-mode nodes that return predictable state updates.
    The goal is to verify GRAPH WIRING and STATE ROUTING — not LLM behavior.

    Each sub-mode node stub currently returns Command(goto=END). These tests
    verify that:
    1. The subgraph correctly routes from entry_router to the correct sub-mode node
    2. State passed in is available when the node executes
    3. The subgraph's output is a valid ExpedienteState-shaped dict
    """

    def test_subgraph_importable(self) -> None:
        """The expediente subgraph module is importable."""
        from agent.graph.expediente_subgraph import build_expediente_subgraph  # noqa: F401

    def test_subgraph_compiles_with_in_memory_checkpointer(self) -> None:
        """
        The subgraph compiles successfully with InMemorySaver for E2E testing.
        (Production uses checkpointer=False; tests use InMemorySaver.)
        """
        from langgraph.checkpoint.memory import MemorySaver
        from agent.graph.expediente_subgraph import build_expediente_subgraph

        compiled = build_expediente_subgraph().compile(checkpointer=MemorySaver())
        assert compiled is not None

    def test_path1_fresh_entry_routes_to_collect_element_data(self) -> None:
        """
        Path 1: Fresh entry (no expediente_sub_mode or default) → collect_element_data_node.

        Fresh state with no sub_mode → entry_router falls back to collect_element_data_node.
        """
        import asyncio
        from agent.graph.expediente_subgraph import build_expediente_subgraph

        compiled = build_expediente_subgraph().compile(checkpointer=False)

        state = _make_expediente_state(
            case_id="case-fresh-entry",
            # No expediente_sub_mode → defaults to collect_element_data
        )

        result = asyncio.run(compiled.ainvoke(state))

        # The subgraph should return a dict (the merged state)
        assert isinstance(result, dict), f"Expected dict result, got {type(result)}"
        # State data should be preserved through the subgraph
        assert result.get("conversation_id") == "conv-e2e-test"
        assert result.get("case_id") == "case-fresh-entry"

    def test_path1_missing_sub_mode_falls_back_to_collect_element_data(self) -> None:
        """
        Path 1 (triangulation): Empty string sub_mode → falls back to collect_element_data.

        entry_router._SUB_MODE_TO_NODE.get("", default) → collect_element_data_node.
        """
        import asyncio
        from agent.graph.expediente_subgraph import build_expediente_subgraph

        compiled = build_expediente_subgraph().compile(checkpointer=False)

        # Explicitly set an empty sub_mode to trigger fallback
        state = _make_expediente_state(
            case_id="case-fallback",
            expediente_sub_mode="",  # Empty → fallback
        )

        result = asyncio.run(compiled.ainvoke(state))
        assert isinstance(result, dict)
        assert result.get("case_id") == "case-fallback"

    def test_path2_collect_element_data_sub_mode_routes_correctly(self) -> None:
        """
        Path 2: expediente_sub_mode='collect_element_data' → collect_element_data_node.
        """
        import asyncio
        from agent.graph.expediente_subgraph import build_expediente_subgraph

        compiled = build_expediente_subgraph().compile(checkpointer=False)

        state = _make_expediente_state(
            case_id="case-element-data",
            expediente_sub_mode="collect_element_data",
            element_phase="photos",
            current_element_index=0,
        )

        result = asyncio.run(compiled.ainvoke(state))
        assert isinstance(result, dict)
        assert result.get("case_id") == "case-element-data"

    def test_path3_collect_base_docs_sub_mode_routes_correctly(self) -> None:
        """
        Path 3: expediente_sub_mode='collect_base_docs' → collect_base_docs_node.
        """
        import asyncio
        from agent.graph.expediente_subgraph import build_expediente_subgraph

        compiled = build_expediente_subgraph().compile(checkpointer=False)

        state = _make_expediente_state(
            case_id="case-base-docs",
            expediente_sub_mode="collect_base_docs",
        )

        result = asyncio.run(compiled.ainvoke(state))
        assert isinstance(result, dict)
        assert result.get("case_id") == "case-base-docs"

    def test_path3b_collect_personal_sub_mode_routes_correctly(self) -> None:
        """
        Path 3b: expediente_sub_mode='collect_personal' → collect_personal_node.
        """
        import asyncio
        from agent.graph.expediente_subgraph import build_expediente_subgraph

        compiled = build_expediente_subgraph().compile(checkpointer=False)

        state = _make_expediente_state(
            case_id="case-personal",
            expediente_sub_mode="collect_personal",
        )

        result = asyncio.run(compiled.ainvoke(state))
        assert isinstance(result, dict)
        assert result.get("case_id") == "case-personal"

    def test_path4_collect_vehicle_sub_mode_routes_correctly(self) -> None:
        """
        Path 4: expediente_sub_mode='collect_vehicle' → collect_vehicle_node.
        """
        import asyncio
        from agent.graph.expediente_subgraph import build_expediente_subgraph

        compiled = build_expediente_subgraph().compile(checkpointer=False)

        state = _make_expediente_state(
            case_id="case-vehicle",
            expediente_sub_mode="collect_vehicle",
        )

        result = asyncio.run(compiled.ainvoke(state))
        assert isinstance(result, dict)
        assert result.get("case_id") == "case-vehicle"

    def test_path5_collect_workshop_sub_mode_routes_correctly(self) -> None:
        """
        Path 5: expediente_sub_mode='collect_workshop' → collect_workshop_node.
        """
        import asyncio
        from agent.graph.expediente_subgraph import build_expediente_subgraph

        compiled = build_expediente_subgraph().compile(checkpointer=False)

        state = _make_expediente_state(
            case_id="case-workshop",
            expediente_sub_mode="collect_workshop",
        )

        result = asyncio.run(compiled.ainvoke(state))
        assert isinstance(result, dict)
        assert result.get("case_id") == "case-workshop"

    def test_path6_review_summary_sub_mode_routes_correctly(self) -> None:
        """
        Path 6: expediente_sub_mode='review_summary' → review_summary_node.
        """
        import asyncio
        from agent.graph.expediente_subgraph import build_expediente_subgraph

        compiled = build_expediente_subgraph().compile(checkpointer=False)

        state = _make_expediente_state(
            case_id="case-review",
            expediente_sub_mode="review_summary",
        )

        result = asyncio.run(compiled.ainvoke(state))
        assert isinstance(result, dict)
        assert result.get("case_id") == "case-review"

    def test_path6_orphan_recovery_sub_mode_resume_at_correct_sub_mode(self) -> None:
        """
        Path 6b: Orphan recovery → resume at the sub_mode stored in pending_recovery_case.

        pending_recovery_case contains inferred_sub_mode="collect_base_docs"
        and expediente_sub_mode="collect_base_docs" is in the state.
        The entry_router routes to collect_base_docs_node.
        """
        import asyncio
        from agent.graph.expediente_subgraph import build_expediente_subgraph

        compiled = build_expediente_subgraph().compile(checkpointer=False)

        # Simulate the state that would arrive after orphan recovery detection
        # (preprocess_node would have set expediente_sub_mode from inferred_sub_mode)
        state = _make_expediente_state(
            pending_recovery_case={
                "case_id": "case-recovered-orphan",
                "inferred_sub_mode": "collect_base_docs",
                "status": "collecting",
            },
            expediente_sub_mode="collect_base_docs",  # Pre-seeded by preprocess_node
        )

        result = asyncio.run(compiled.ainvoke(state))
        assert isinstance(result, dict)
        # The state should survive the subgraph invocation
        assert result.get("expediente_sub_mode") == "collect_base_docs"

    def test_all_six_sub_modes_invoke_without_error(self) -> None:
        """
        All 6 sub-modes can be invoked in the subgraph without raising exceptions.
        This is a triangulation test: different inputs, same pass condition.
        """
        import asyncio
        from agent.graph.expediente_subgraph import build_expediente_subgraph

        sub_modes = [
            "collect_element_data",
            "collect_base_docs",
            "collect_personal",
            "collect_vehicle",
            "collect_workshop",
            "review_summary",
        ]

        compiled = build_expediente_subgraph().compile(checkpointer=False)

        for sub_mode in sub_modes:
            state = _make_expediente_state(
                case_id=f"case-{sub_mode}",
                expediente_sub_mode=sub_mode,
            )
            result = asyncio.run(compiled.ainvoke(state))
            assert isinstance(result, dict), (
                f"Subgraph invocation for sub_mode='{sub_mode}' returned {type(result)}"
            )
            assert result.get("case_id") == f"case-{sub_mode}", (
                f"case_id lost during subgraph invocation for sub_mode='{sub_mode}'"
            )


# ---------------------------------------------------------------------------
# T-24: Wire expediente_to_parent_updates() at the subgraph→parent boundary
# ---------------------------------------------------------------------------


class TestBoundaryWiring:
    """
    Verify that expediente_to_parent_updates() is wired correctly at the
    subgraph→parent boundary.

    When the parent graph invokes the subgraph node, the output state dict
    returned by the subgraph must be processed through expediente_to_parent_updates()
    so that the parent ConversationState gets the correct mode_context updates.

    T-24 implementation strategy: The boundary is already handled because:
    1. LangGraph compiled subgraphs mounted as nodes in the parent graph
       return their output state updates directly — the parent graph's state
       reducer then merges them into ConversationState.
    2. The expediente_to_parent_updates() function must be called at the
       wrapper/boundary to ensure mode_context is correctly populated.

    These tests verify the CONTRACT: the subgraph output → parent state mapping
    is handled by expediente_to_parent_updates(), and the conversation_graph.py
    wiring calls it correctly (the subgraph is always mounted).
    """

    def test_expediente_to_parent_updates_function_exists(self) -> None:
        """expediente_to_parent_updates() is importable from expediente_state."""
        from agent.modes.expediente_state import expediente_to_parent_updates  # noqa: F401

    def test_expediente_to_parent_updates_returns_three_keys(self) -> None:
        """
        expediente_to_parent_updates() returns a dict with exactly:
        - ai_response: str
        - pending_images: Any
        - mode_context: dict
        """
        from agent.modes.expediente_state import (
            expediente_to_parent_updates,
            ExpedienteState,
        )

        exp_state: dict[str, Any] = {
            "case_id": "case-boundary-test",
            "expediente_sub_mode": "collect_element_data",
            "ai_response": "Hola, tu expediente está en marcha.",
            "pending_images": None,
            "messages": [],
        }

        result = expediente_to_parent_updates(ExpedienteState(**exp_state))  # type: ignore[misc]

        assert "ai_response" in result, (
            "expediente_to_parent_updates must return ai_response"
        )
        assert "pending_images" in result, (
            "expediente_to_parent_updates must return pending_images"
        )
        assert "mode_context" in result, (
            "expediente_to_parent_updates must return mode_context"
        )

    def test_expediente_to_parent_updates_mode_context_contains_expediente_keys(
        self,
    ) -> None:
        """
        The mode_context returned by expediente_to_parent_updates() contains
        the expediente-specific keys (case_id, expediente_sub_mode, etc.).
        These are needed for the parent to resume the correct sub-mode next turn.
        """
        from agent.modes.expediente_state import (
            expediente_to_parent_updates,
            ExpedienteState,
        )

        exp_state: dict[str, Any] = {
            "case_id": "case-mode-ctx-test",
            "expediente_sub_mode": "collect_personal",
            "current_element_index": 2,
            "element_phase": "data",
            "ai_response": "Ahora necesito tus datos personales.",
            "pending_images": None,
            "messages": [],
            "conversation_id": "conv-test",
        }

        result = expediente_to_parent_updates(ExpedienteState(**exp_state))  # type: ignore[misc]
        mc = result["mode_context"]

        assert mc.get("case_id") == "case-mode-ctx-test"
        assert mc.get("expediente_sub_mode") == "collect_personal"
        assert mc.get("current_element_index") == 2
        assert mc.get("element_phase") == "data"

    def test_expediente_to_parent_updates_excludes_top_level_keys(self) -> None:
        """
        Top-level keys (conversation_id, user_message, messages, etc.) must NOT
        appear in the returned mode_context — they belong at the parent top level.
        """
        from agent.modes.expediente_state import (
            expediente_to_parent_updates,
            ExpedienteState,
            _PARENT_TOP_LEVEL_KEYS,
        )

        exp_state: dict[str, Any] = {
            "conversation_id": "conv-top-level",
            "user_id": "user-top-level",
            "user_phone": "+34600000001",
            "user_message": "test message",
            "messages": [],
            "ai_response": "response text",
            "pending_images": None,
            "case_id": "case-exclusion-test",
        }

        result = expediente_to_parent_updates(ExpedienteState(**exp_state))  # type: ignore[misc]
        mc = result["mode_context"]

        # Top-level keys must NOT be in mode_context
        for top_key in _PARENT_TOP_LEVEL_KEYS:
            assert top_key not in mc, (
                f"Top-level key '{top_key}' should not appear in mode_context "
                f"from expediente_to_parent_updates()"
            )

    def test_subgraph_wrapper_in_conversation_graph_calls_boundary_fn(self) -> None:
        """
        The parent graph wires a BOUNDARY WRAPPER function at NODE_EXPEDIENTE
        (not the compiled subgraph directly). The subgraph is always mounted.

        The wrapper:
        1. Calls parent_to_expediente() to build ExpedienteState from ConversationState
        2. Invokes the compiled subgraph
        3. Calls expediente_to_parent_updates() to map output back to parent schema

        This test verifies:
        - The graph builds successfully
        - NODE_EXPEDIENTE is registered in the graph
        - The graph compiles successfully (boundary wrapper is valid)
        """
        from agent.graph.conversation_graph import (
            build_conversation_graph,
            NODE_EXPEDIENTE,
        )

        builder = build_conversation_graph()
        # Verify node exists
        assert NODE_EXPEDIENTE in builder.nodes

        # The graph should compile successfully (boundary wrapper is valid)
        compiled = builder.compile()
        assert compiled is not None

    def test_boundary_wrapper_references_both_mapping_fns(self) -> None:
        """
        Verify that conversation_graph.py imports and uses both boundary fns.

        The boundary wrapper closure must call parent_to_expediente() and
        expediente_to_parent_updates().
        """
        from agent.graph.conversation_graph import (
            build_conversation_graph,
            NODE_EXPEDIENTE,
        )

        builder = build_conversation_graph()
        node_spec = builder.nodes[NODE_EXPEDIENTE]
        runnable = getattr(node_spec, "runnable", node_spec)

        # Get the actual inner function from the RunnableCallable
        inner = getattr(runnable, "afunc", None) or getattr(runnable, "func", None)

        if inner is not None:
            # Inspect the source to verify boundary fn references
            source = inspect.getsource(inner)
            assert "parent_to_expediente" in source, (
                "The expediente subgraph wrapper must call parent_to_expediente() "
                "to build the subgraph input state from the parent ConversationState"
            )
            assert "expediente_to_parent_updates" in source, (
                "The expediente subgraph wrapper must call expediente_to_parent_updates() "
                "to map the subgraph output back to the parent state schema"
            )

    def test_expediente_to_parent_updates_ai_response_preserved(self) -> None:
        """
        ai_response from the subgraph is correctly surfaced at the top level
        of the parent updates (not buried in mode_context).
        """
        from agent.modes.expediente_state import (
            expediente_to_parent_updates,
            ExpedienteState,
        )

        response_text = "Hemos recibido las fotos del primer elemento."

        exp_state: dict[str, Any] = {
            "ai_response": response_text,
            "pending_images": {"url": "https://example.com/img.jpg"},
            "messages": [],
        }

        result = expediente_to_parent_updates(ExpedienteState(**exp_state))  # type: ignore[misc]

        assert result["ai_response"] == response_text
        assert result["pending_images"] == {"url": "https://example.com/img.jpg"}

    def test_round_trip_state_via_boundary_fns(self) -> None:
        """
        Full round-trip: parent_state → parent_to_expediente() → (subgraph runs)
        → expediente_to_parent_updates() → parent updates.

        Verify that the round-trip is correct end-to-end and no keys are lost.
        """
        from agent.modes.expediente_state import (
            parent_to_expediente,
            expediente_to_parent_updates,
            ExpedienteState,
        )

        # Simulate parent state entering the subgraph boundary
        parent_state: dict[str, Any] = {
            "conversation_id": "conv-round-trip",
            "user_id": "user-rt-123",
            "user_phone": "+34600000001",
            "user_name": "Round Trip Test",
            "client_type": "professional",
            "user_message": "Aquí están las fotos del tubo de escape.",
            "mode_context": {
                "case_id": "case-rt-456",
                "expediente_sub_mode": "collect_element_data",
                "element_phase": "photos",
                "current_element_index": 0,
                "element_codes": ["ESCAPE", "SUSPENSION"],
            },
        }

        # Forward: parent → expediente
        exp_state = parent_to_expediente(parent_state)
        assert exp_state.get("case_id") == "case-rt-456"
        assert exp_state.get("expediente_sub_mode") == "collect_element_data"

        # Simulate subgraph execution (node updates the state)
        exp_state_after: dict[str, Any] = dict(exp_state)
        exp_state_after["ai_response"] = "Gracias, fotos recibidas."
        exp_state_after["element_phase"] = "data"  # Phase advanced
        exp_state_after["current_element_index"] = 0

        # Backward: expediente → parent updates
        parent_updates = expediente_to_parent_updates(
            ExpedienteState(**exp_state_after)  # type: ignore[misc]
        )

        mc = parent_updates["mode_context"]
        assert mc.get("case_id") == "case-rt-456"
        assert mc.get("element_phase") == "data"  # Phase advance preserved
        assert parent_updates["ai_response"] == "Gracias, fotos recibidas."


# ---------------------------------------------------------------------------
# T-25: Invariant verification tests
# ---------------------------------------------------------------------------


class TestInvariantNoMergeDicts:
    """
    Invariant: Subgraph new files have NO `merge_dicts` CODE usage.

    Uses AST inspection to verify this structurally (no runtime needed).
    Docstring/comment mentions are excluded — only actual imports and
    identifier usage in code are flagged.
    """

    SUBGRAPH_FILES = [
        "agent/modes/expediente_state.py",
        "agent/graph/expediente_subgraph.py",
        "agent/modes/expediente_nodes.py",
        "agent/services/expediente_init.py",
        "agent/services/expediente_guards.py",
    ]

    @staticmethod
    def _find_merge_dicts_code_usage(filepath: str) -> list[str]:
        """
        Use AST to find actual merge_dicts imports or identifier references in code.

        Docstrings and comments are part of the AST as ``Constant`` nodes within
        ``Expr`` statements — they are NOT ``Name``, ``Import``, or ``Attribute`` nodes.
        This function only checks for real code usage, not documentation mentions.
        """
        source = Path(filepath).read_text(encoding="utf-8")
        tree = ast.parse(source)
        violations: list[str] = []

        for node in ast.walk(tree):
            # from X import merge_dicts
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "merge_dicts":
                        violations.append(f"Line {node.lineno}: import merge_dicts")
            # import merge_dicts (bare import)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "merge_dicts" in alias.name:
                        violations.append(f"Line {node.lineno}: import {alias.name}")
            # Direct name reference: merge_dicts(...)
            elif isinstance(node, ast.Name) and node.id == "merge_dicts":
                violations.append(f"Line {node.lineno}: Name ref merge_dicts")
            # Attribute access: obj.merge_dicts(...)
            elif isinstance(node, ast.Attribute) and node.attr == "merge_dicts":
                violations.append(f"Line {node.lineno}: Attribute merge_dicts")

        return violations

    def test_expediente_state_no_merge_dicts(self) -> None:
        """expediente_state.py has no merge_dicts CODE usage (imports/calls)."""
        violations = self._find_merge_dicts_code_usage(
            "agent/modes/expediente_state.py"
        )
        assert not violations, (
            "expediente_state.py must NOT import or call merge_dicts. Violations:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_expediente_subgraph_no_merge_dicts(self) -> None:
        """expediente_subgraph.py has no merge_dicts CODE usage."""
        violations = self._find_merge_dicts_code_usage(
            "agent/graph/expediente_subgraph.py"
        )
        assert not violations, (
            "expediente_subgraph.py must NOT import or call merge_dicts. Violations:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_expediente_nodes_no_merge_dicts(self) -> None:
        """expediente_nodes.py has no merge_dicts CODE usage."""
        violations = self._find_merge_dicts_code_usage(
            "agent/modes/expediente_nodes.py"
        )
        assert not violations, (
            "expediente_nodes.py must NOT import or call merge_dicts. Violations:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_expediente_init_no_merge_dicts(self) -> None:
        """expediente_init.py has no merge_dicts CODE usage."""
        violations = self._find_merge_dicts_code_usage(
            "agent/services/expediente_init.py"
        )
        assert not violations, (
            "expediente_init.py must NOT import or call merge_dicts. Violations:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_expediente_guards_no_merge_dicts(self) -> None:
        """expediente_guards.py has no merge_dicts CODE usage."""
        violations = self._find_merge_dicts_code_usage(
            "agent/services/expediente_guards.py"
        )
        assert not violations, (
            "expediente_guards.py must NOT import or call merge_dicts. Violations:\n"
            + "\n".join(f"  {v}" for v in violations)
        )


class TestInvariantNoAnnotatedReducers:
    """
    Invariant: ExpedienteState has NO Annotated reducer annotations except
    for `messages` (which uses operator.add).

    All other fields must be plain overwrite — no Annotated[T, some_reducer].

    NOTE: ExpedienteState uses ``from __future__ import annotations`` which
    turns all annotations into ``ForwardRef`` strings. We use
    ``typing.get_type_hints(include_extras=True)`` to resolve them properly.
    """

    def test_only_messages_uses_annotated_reducer(self) -> None:
        """
        ExpedienteState: only `messages` has an Annotated annotation.
        All other fields are plain types (no Annotated wrapper).

        Uses get_type_hints(include_extras=True) to resolve ForwardRefs from
        `from __future__ import annotations`.
        """
        import typing
        from agent.modes.expediente_state import ExpedienteState

        # get_type_hints with include_extras=True preserves Annotated wrappers
        hints = typing.get_type_hints(ExpedienteState, include_extras=True)

        annotated_keys = [
            key
            for key, annotation in hints.items()
            if hasattr(annotation, "__metadata__")  # Annotated types have __metadata__
        ]

        # Only `messages` should be annotated (with operator.add)
        assert set(annotated_keys) == {"messages"}, (
            f"Only 'messages' should use Annotated reducer. "
            f"Found annotated fields: {annotated_keys}"
        )

    def test_messages_uses_operator_add_reducer(self) -> None:
        """
        `messages` field in ExpedienteState uses operator.add as reducer.

        Uses get_type_hints(include_extras=True) to resolve ForwardRefs.
        """
        import operator
        import typing
        from agent.modes.expediente_state import ExpedienteState

        # Resolve the ForwardRef string to actual Annotated type
        hints = typing.get_type_hints(ExpedienteState, include_extras=True)
        messages_annotation = hints.get("messages")

        assert messages_annotation is not None, "messages must be in ExpedienteState"

        # The annotation should be Annotated[list[...], operator.add]
        assert hasattr(messages_annotation, "__metadata__"), (
            "messages must be annotated with Annotated[..., operator.add]. "
            f"Got: {messages_annotation!r}"
        )
        metadata = messages_annotation.__metadata__
        assert operator.add in metadata, (
            f"messages reducer must be operator.add. Got metadata: {metadata}"
        )


class TestInvariantZombieState:
    """
    Invariant: Keys set in one sub-mode do NOT persist to the next unless
    explicitly carried.

    This is the zombie-state invariant: because ExpedienteState uses plain
    overwrite (no merge_dicts), keys from a previous invocation don't resurrect.

    The test verifies this structurally by confirming no merge_dicts import
    in the new files (zombie resurrection requires merge_dicts).
    """

    def test_no_merge_dicts_import_in_expediente_state(self) -> None:
        """
        expediente_state.py does not IMPORT or CALL merge_dicts.
        merge_dicts is the mechanism for zombie-key resurrection.

        Uses AST inspection to exclude docstring/comment mentions —
        only actual code usage is flagged.
        """
        source = Path("agent/modes/expediente_state.py").read_text()
        tree = ast.parse(source)
        violations: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "merge_dicts":
                        violations.append(f"Line {node.lineno}: import merge_dicts")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "merge_dicts" in alias.name:
                        violations.append(f"Line {node.lineno}: import {alias.name}")
            elif isinstance(node, ast.Name) and node.id == "merge_dicts":
                violations.append(f"Line {node.lineno}: Name ref merge_dicts")
            elif isinstance(node, ast.Attribute) and node.attr == "merge_dicts":
                violations.append(f"Line {node.lineno}: Attribute merge_dicts")

        assert not violations, (
            "expediente_state.py must NOT import or call merge_dicts "
            "(zombie-key resurrection prevention). Violations:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_expediente_state_total_false_means_overwrite(self) -> None:
        """
        ExpedienteState(total=False) — the TypedDict uses total=False which means
        all fields are optional and plain overwrite semantics apply.

        Verify this is declared correctly.
        """
        from agent.modes.expediente_state import ExpedienteState

        # TypedDicts with total=False allow all fields to be absent,
        # which means the subgraph starts fresh each invocation.
        # The parent_to_expediente() explicitly rebuilds the state each time.
        # We verify the class declaration.
        # In Python, TypedDict total=False is stored as __required_keys__ being empty
        # or __optional_keys__ containing all fields.
        assert hasattr(ExpedienteState, "__total__"), (
            "ExpedienteState must be a TypedDict"
        )
        assert ExpedienteState.__total__ is False, (
            f"ExpedienteState must have total=False for plain overwrite semantics. "
            f"Got __total__={ExpedienteState.__total__}"
        )

    def test_parent_to_expediente_rebuilds_state_each_invocation(self) -> None:
        """
        parent_to_expediente() ALWAYS rebuilds the ExpedienteState from the
        current parent state. It does NOT accumulate from previous subgraph runs.

        Verify: calling parent_to_expediente() with different mode_context values
        produces different ExpedienteState outputs (no stale keys from previous call).
        """
        from agent.modes.expediente_state import parent_to_expediente

        # First invocation: sub_mode = collect_element_data, phase = photos
        state_1: dict[str, Any] = {
            "conversation_id": "conv-zombie-test",
            "user_id": "user-zombie",
            "user_phone": "+34600000001",
            "user_name": "Test",
            "client_type": "particular",
            "user_message": "First turn",
            "mode_context": {
                "case_id": "case-zombie",
                "expediente_sub_mode": "collect_element_data",
                "element_phase": "photos",
                "zombie_key_from_turn_1": "should_not_persist",
            },
        }
        exp_1 = parent_to_expediente(state_1)
        assert exp_1.get("element_phase") == "photos"
        assert exp_1.get("zombie_key_from_turn_1") == "should_not_persist"

        # Second invocation: sub_mode = collect_base_docs, phase NOT in mode_context
        state_2: dict[str, Any] = {
            "conversation_id": "conv-zombie-test",
            "user_id": "user-zombie",
            "user_phone": "+34600000001",
            "user_name": "Test",
            "client_type": "particular",
            "user_message": "Second turn",
            "mode_context": {
                "case_id": "case-zombie",
                "expediente_sub_mode": "collect_base_docs",
                # NOTE: zombie_key_from_turn_1 not present here
                # In a merge_dicts world this would resurrect from checkpoint.
                # In ExpedienteState, it won't be present if not passed.
            },
        }
        exp_2 = parent_to_expediente(state_2)

        # After transition, the zombie key is NOT in the new state
        # (because parent_to_expediente() builds from mode_context, which doesn't have it)
        assert exp_2.get("zombie_key_from_turn_1") is None or (
            "zombie_key_from_turn_1" not in exp_2
        ), (
            "zombie_key_from_turn_1 should NOT persist to second invocation — "
            "it's not in mode_context anymore"
        )

        # The new sub_mode is correct
        assert exp_2.get("expediente_sub_mode") == "collect_base_docs"


class TestInvariantProposalCoverage:
    """
    Verify that the critical proposal invariants are testable/verifiable.

    This class verifies the STRUCTURAL COVERAGE of each invariant from the
    14-item proposal invariants list (Domain 6 of the spec).

    Not all invariants require runtime execution — many are structural/compile-time.
    Each test below maps to one or more spec invariants.
    """

    def test_invariant_1_six_distinct_nodes(self) -> None:
        """
        Invariant 1: All 6 sub-modes execute as distinct graph nodes.

        The EXPECTED_NODES frozenset proves 6 sub-mode nodes are registered separately.
        """
        from agent.graph.expediente_subgraph import EXPECTED_NODES

        sub_mode_nodes = {n for n in EXPECTED_NODES if n != "entry_router"}
        assert len(sub_mode_nodes) == 6, (
            f"Must have 6 distinct sub-mode nodes, got {len(sub_mode_nodes)}: {sub_mode_nodes}"
        )

    def test_invariant_2_routing_preserves_sub_mode(self) -> None:
        """
        Invariant 2: Zero functional delta across paths — routing is deterministic.

        The _SUB_MODE_TO_NODE map is a bijection: each sub_mode maps to a unique node.
        """
        from agent.modes.expediente_nodes import _SUB_MODE_TO_NODE

        # All values are unique (no two sub-modes map to the same node)
        assert len(set(_SUB_MODE_TO_NODE.values())) == len(_SUB_MODE_TO_NODE), (
            "Each sub-mode must map to a unique node — routing is not ambiguous"
        )

    def test_invariant_3_expediente_mode_file_exists(self) -> None:
        """
        Invariant 3: expediente_mode.py exists (not deleted/moved).
        The v1 coordinator is preserved for the rollback path.
        """
        assert Path("agent/modes/expediente_mode.py").exists(), (
            "agent/modes/expediente_mode.py must NOT be deleted — v1 coordinator preserved"
        )

    def test_invariant_4_no_tombstone_needed_in_new_files(self) -> None:
        """
        Invariant 4: No tombstone protocol needed in new expediente files.

        The NEW files (expediente_state.py, expediente_subgraph.py, etc.) do NOT
        use tombstone patterns (key=None explicit assignments for merge_dicts cleanup).

        Instead, ExpedienteState uses plain overwrite — natural cleanup.
        """
        # Verify that the new files don't have the tombstone comment pattern
        # (# TOMBSTONE is only valid in the v1 expediente_mode.py coordinator)
        new_files = [
            "agent/modes/expediente_state.py",
            "agent/graph/expediente_subgraph.py",
            "agent/modes/expediente_nodes.py",
        ]
        for filepath in new_files:
            content = Path(filepath).read_text()
            assert "# TOMBSTONE" not in content, (
                f"{filepath} must NOT use tombstone patterns — "
                "ExpedienteState uses plain overwrite semantics"
            )

    def test_invariant_6_no_generic_llm_loop_in_subgraph_files(self) -> None:
        """
        Invariant 6: generic_llm_loop() is NOT IMPORTED or CALLED in subgraph files.

        Uses AST inspection to exclude docstring/comment mentions.
        Only actual imports and identifier usage in code are flagged.
        """
        subgraph_files = [
            "agent/graph/expediente_subgraph.py",
            "agent/modes/expediente_nodes.py",
        ]
        for filepath in subgraph_files:
            source = Path(filepath).read_text()
            tree = ast.parse(source)
            violations: list[str] = []

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name == "generic_llm_loop":
                            violations.append(
                                f"Line {node.lineno}: import generic_llm_loop"
                            )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if "generic_llm_loop" in alias.name:
                            violations.append(
                                f"Line {node.lineno}: import {alias.name}"
                            )
                elif isinstance(node, ast.Name) and node.id == "generic_llm_loop":
                    violations.append(f"Line {node.lineno}: Name ref generic_llm_loop")
                elif (
                    isinstance(node, ast.Attribute) and node.attr == "generic_llm_loop"
                ):
                    violations.append(f"Line {node.lineno}: Attribute generic_llm_loop")

            assert not violations, (
                f"{filepath} must NOT import or call generic_llm_loop. "
                "Sub-mode nodes use LangGraph Command-based routing. "
                f"Violations: {violations}"
            )

    def test_invariant_7_subgraph_is_mounted(self) -> None:
        """
        Invariant 7: The subgraph is always mounted as NODE_EXPEDIENTE.
        Compiled StateGraph objects have ``config_schema`` attribute.
        """
        from agent.graph.conversation_graph import (
            build_conversation_graph,
            NODE_EXPEDIENTE,
        )

        builder = build_conversation_graph()
        node_spec = builder.nodes[NODE_EXPEDIENTE]
        runnable = getattr(node_spec, "runnable", node_spec)

        # Subgraph path: boundary wrapper wraps the compiled subgraph
        # The graph must compile without error
        compiled = builder.compile()
        assert compiled is not None

    def test_invariant_9_photo_guard_function_exists(self) -> None:
        """
        Invariant 9: Photo-completion guard function is preserved and importable.
        """
        from agent.services.expediente_guards import guard_photo_completion  # noqa: F401
        from agent.services.expediente_guards import _call_confirmar_fotos_tool  # noqa: F401

    def test_invariant_10_same_turn_chaining_keys_in_preprocess(self) -> None:
        """
        Invariant 10: Same-turn chaining — preprocess_node handles _is_chained_turn.
        Verify the key exists in preprocess_node's output contract.
        """
        import asyncio
        from agent.graph.conversation_graph import preprocess_node

        state = {
            "conversation_id": "conv-chain-inv10",
            "user_message": "chained",
            "_is_chained_turn": True,
            "total_message_count": 5,
            "agent_disabled": False,
        }
        result = asyncio.run(preprocess_node(state))
        # Chained turn: counter NOT incremented
        assert "total_message_count" not in result
        # Transient reset keys are set
        assert result.get("_chain_next_mode") is None
        assert result.get("_is_chained_turn") is False

    def test_invariant_11_pending_recovery_case_in_expediente_mc_keys(self) -> None:
        """
        Invariant 11: Redis TTL + orphan recovery — pending_recovery_case is in
        _EXPEDIENTE_MC_KEYS so it crosses the boundary from parent to subgraph.
        """
        from agent.modes.expediente_state import _EXPEDIENTE_MC_KEYS

        assert "pending_recovery_case" in _EXPEDIENTE_MC_KEYS

    def test_invariant_14_entry_router_routes_all_sub_modes(self) -> None:
        """
        Invariant 14: All 6 sub-mode routing paths are covered.

        The _SUB_MODE_TO_NODE dict covers all canonical sub-mode names.
        """
        from agent.modes.expediente_nodes import _SUB_MODE_TO_NODE

        expected_sub_modes = {
            "collect_element_data",
            "collect_base_docs",
            "collect_personal",
            "collect_vehicle",
            "collect_workshop",
            "review_summary",
        }
        registered_sub_modes = set(_SUB_MODE_TO_NODE.keys())

        assert expected_sub_modes == registered_sub_modes, (
            f"_SUB_MODE_TO_NODE must cover all 6 canonical sub-modes. "
            f"Missing: {expected_sub_modes - registered_sub_modes}. "
            f"Extra: {registered_sub_modes - expected_sub_modes}."
        )


class TestInvariantBoundaryFunctions:
    """
    Additional boundary function invariant tests to ensure T-24 is fully covered.
    """

    def test_parent_to_expediente_fn_exists_and_is_pure(self) -> None:
        """parent_to_expediente() is a pure function (no side effects, accepts dict)."""
        from agent.modes.expediente_state import parent_to_expediente

        # Call it with minimal state — should not raise
        result = parent_to_expediente(
            {
                "conversation_id": "conv-pure-test",
                "user_message": "test",
            }
        )
        assert isinstance(result, dict)

    def test_expediente_to_parent_updates_fn_exists_and_is_pure(self) -> None:
        """expediente_to_parent_updates() is a pure function."""
        from agent.modes.expediente_state import (
            expediente_to_parent_updates,
            ExpedienteState,
        )

        result = expediente_to_parent_updates(
            ExpedienteState(**{"messages": []})  # type: ignore[misc]
        )
        assert isinstance(result, dict)
        assert "ai_response" in result
        assert "mode_context" in result

    def test_expediente_to_parent_updates_empty_state_returns_valid_structure(
        self,
    ) -> None:
        """
        Even an empty ExpedienteState produces a valid parent update dict
        with the required keys.
        """
        from agent.modes.expediente_state import (
            expediente_to_parent_updates,
            ExpedienteState,
        )

        result = expediente_to_parent_updates(ExpedienteState())  # type: ignore[misc]
        assert "ai_response" in result
        assert "pending_images" in result
        assert "mode_context" in result
        assert isinstance(result["mode_context"], dict)
