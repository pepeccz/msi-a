"""Helpers for safe LangGraph state mutation configs."""

from collections.abc import Mapping
from typing import Any


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
