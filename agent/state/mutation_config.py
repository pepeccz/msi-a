"""Helpers for safe LangGraph state mutation configs."""

from collections.abc import Mapping
from typing import Any

STATE_MUTATION_AS_NODE = "preprocess"
"""Anchor node for out-of-band ``graph.aupdate_state`` writes.

Must always name a real node in the compiled conversation graph
(``agent.graph.conversation_graph.NODE_PREPROCESS``). Passing ``as_node``
explicitly makes LangGraph skip its ambiguous-update inference branches
entirely, so out-of-band writes (e.g. admin resume-bot state restoration)
succeed regardless of the checkpoint's existing ``versions_seen`` map.

Kept as a literal — not imported from ``agent.graph.conversation_graph`` —
so this module stays a dependency-free leaf: that module transitively
imports the intent router, the LLM router, and the full mode/tool stack,
which would make every fast unit test (and this module's callers, e.g.
``api/services/state_snapshot_service.py``) pay that import cost.

Pinned to the graph by
``tests/unit/test_agent_state_mutation_config_guardrails.py::test_state_mutation_as_node_matches_graph_entry_node``.
"""


def build_state_mutation_config(config: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Build a thread-scoped config safe for ``graph.aupdate_state``.

    LangGraph mutation APIs should not receive invoke-time routing fields like
    ``checkpoint_ns``. This helper enforces a minimal contract that carries only
    ``thread_id``.
    """
    configurable = config.get("configurable") if isinstance(config, Mapping) else None
    if not isinstance(configurable, Mapping):
        raise ValueError("Missing configurable config for state mutation")

    thread_id = configurable.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise ValueError("Missing thread_id for state mutation")

    return {"configurable": {"thread_id": thread_id}}
