"""
Tests for WS5 — Native Error Handling.

Verifies:
1. ConversationalRetryPolicy rename (old RetryPolicy name gone)
2. LangGraph RetryPolicy applied on LLM-calling nodes
3. Transient error predicate correctness
"""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# T-WS5-1: ConversationalRetryPolicy rename
# ---------------------------------------------------------------------------


def test_conversational_retry_policy_rename():
    """ConversationalRetryPolicy must be importable from fallback_handler."""
    from agent.fallback.fallback_handler import ConversationalRetryPolicy  # noqa: F401

    assert ConversationalRetryPolicy is not None
    # Verify it's a dataclass with the expected fields
    policy = ConversationalRetryPolicy(mode="TEST_MODE")
    assert policy.mode == "TEST_MODE"
    assert policy.max_retries == 3  # default


def test_old_retry_policy_name_gone():
    """The old 'RetryPolicy' name must NOT be exported from fallback_handler."""
    import agent.fallback.fallback_handler as fh

    # After rename, importing RetryPolicy by that name should fail
    assert "RetryPolicy" not in dir(fh), (
        "RetryPolicy is still exported from fallback_handler — "
        "rename it to ConversationalRetryPolicy"
    )


# ---------------------------------------------------------------------------
# T-WS5-3 / T-WS5-5: Graph nodes have LangGraph RetryPolicy
# ---------------------------------------------------------------------------


def test_langgraph_retry_policy_applied_on_llm_nodes():
    """
    LangGraph's RetryPolicy must be set on presupuesto, consulta, and expediente nodes.

    We build the graph (without compiling — no checkpointer needed) and inspect
    the node metadata stored in the StateGraph builder.
    """
    from agent.graph.conversation_graph import (
        build_conversation_graph,
        NODE_CONSULTA,
        NODE_PRESUPUESTO,
        NODE_EXPEDIENTE,
    )

    graph_builder = build_conversation_graph()

    # StateGraph stores nodes in ._nodes dict (LangGraph internal)
    nodes = graph_builder.nodes

    llm_nodes = [NODE_CONSULTA, NODE_PRESUPUESTO, NODE_EXPEDIENTE]
    for node_name in llm_nodes:
        assert node_name in nodes, f"Node {node_name!r} not found in graph"
        node_spec = nodes[node_name]
        # LangGraph >= 0.5 stores the policy on node_spec.retry_policy
        # (older versions used .retry — both are checked for compatibility)
        has_retry = (
            (hasattr(node_spec, "retry_policy") and node_spec.retry_policy is not None)
            or (hasattr(node_spec, "retry") and node_spec.retry is not None)
        )
        assert has_retry, (
            f"Node {node_name!r} has no RetryPolicy set. "
            "Add retry_policy=_LLM_RETRY to add_node() for LLM-calling nodes."
        )


# ---------------------------------------------------------------------------
# T-WS5-4: Transient error predicate
# ---------------------------------------------------------------------------


def test_transient_error_predicate():
    """_is_transient_error must return True for network errors, False for business errors."""
    from agent.graph.conversation_graph import _is_transient_error
    import httpx

    # Transient errors → should return True
    assert _is_transient_error(httpx.TimeoutException("timeout", request=MagicMock())) is True
    assert _is_transient_error(httpx.ConnectError("connect fail", request=MagicMock())) is True
    assert _is_transient_error(ConnectionError("conn")) is True
    assert _is_transient_error(TimeoutError("timeout")) is True

    # Business / logic errors → should return False
    assert _is_transient_error(ValueError("bad value")) is False
    assert _is_transient_error(KeyError("key")) is False
    assert _is_transient_error(RuntimeError("runtime")) is False
