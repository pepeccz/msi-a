"""
Standard contract for tools to declare mode_context updates.

This provides a unified format for tools to communicate state changes
to mode nodes.

Usage in tools:
    from agent.utils.tool_context_contract import context_update

    return {
        "success": True,
        "message": "...",
        **context_update(
            element_phase="data",
            element_data_status=updated_status,
            expediente_sub_mode="collect_base_docs",
        ),
    }

The mode node's _extract_context_from_tool() reads "_context_updates"
and applies them to mode_context.

Migration path:
    1. New tools use context_update() exclusively
    2. Existing v1 tools keep case_collection_update AND add context_update()
    3. Eventually deprecate case_collection_update when all tools are migrated
"""

from typing import Any


def context_update(**kwargs: Any) -> dict[str, dict[str, Any]]:
    """
    Wrap context updates in standard format for mode nodes.

    Args:
        **kwargs: Key-value pairs to update in mode_context.
            Common keys:
            - element_phase: "photos" | "data"
            - element_data_status: dict mapping element codes to statuses
            - expediente_sub_mode: target sub-mode string
            - current_element_index: int
            - base_docs_received: bool

    Returns:
        Dict with "_context_updates" key containing the updates.

    Example:
        >>> context_update(element_phase="data", current_element_index=1)
        {"_context_updates": {"element_phase": "data", "current_element_index": 1}}
    """
    return {"_context_updates": kwargs}
