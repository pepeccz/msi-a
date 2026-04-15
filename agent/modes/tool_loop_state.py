"""
MSI-a — ToolLoopState TypedDict (AD-3).

Dedicated state schema for the inner tool-calling loop.
Separate from ConversationState to avoid reducer conflicts with the outer graph.

Design decisions (AD-3):
- messages uses operator.add reducer so each node appends (not replaces)
- pending_state_updates accumulates _state_update dicts from ToolMessages
- tool_results / tools_called track execution metadata for post_tool_node
- _mode_context/_conversation_id carry outer-graph context into the inner loop
  so tools can read them via RunnableConfig.configurable["state"]
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Any

from typing_extensions import TypedDict


def _merge_dicts(current: dict | None, update: dict | None) -> dict:
    """
    Shallow merge two dicts (last-write-wins on conflicting keys).

    Used as the reducer for pending_state_updates so multiple tool results
    in the same turn accumulate properly.

    Args:
        current: Value from checkpoint (previous turn or previous tool).
        update:  Value from current node output.

    Returns:
        Merged dict (empty if both are None).
    """
    if update is None:
        return current or {}
    if current is None:
        return update or {}
    return {**current, **update}


class ToolLoopState(TypedDict, total=False):
    """
    State for the inner LLM + tool-call loop (one per mode turn).

    Fields:
        messages:
            Conversation messages for this turn: system + user + AI + tool messages.
            Uses ``operator.add`` reducer — each node appends rather than replaces.
            This is critical for maintaining the AIMessage → ToolMessage pairing
            invariant required by LangChain message validators.

        pending_state_updates:
            Accumulated _state_update dicts extracted from ToolMessage contents.
            Uses ``_merge_dicts`` reducer so multiple tools in one turn merge.
            post_tool_node reads this and applies it via the post_tool_hook.

        tool_results:
            Raw result dicts from all tool executions (in call order).
            Uses ``operator.add`` reducer so each tool appends its result.
            Available to post_tool_node and the mode node for post-processing.

        tools_called:
            List of tool names called this turn (for dedup and logging).
            Uses ``operator.add`` reducer for accumulation.

        ai_response:
            Final text response from the LLM (set when loop exits normally).
            Empty string if loop exited due to max_iterations or error.

        exit_reason:
            Why the loop stopped:
            - "response"       → LLM produced a plain text (no tool calls).
            - "max_iterations" → recursion_limit reached.
            - "error"          → unexpected exception in llm_node.

        _mode_context:
            Snapshot of the outer ConversationState["mode_context"] at turn start.
            Injected into RunnableConfig.configurable["state"] for tool access.
            Tools read mode_context via get_tool_state(config) — no ContextVar.

        _conversation_id:
            Conversation identifier forwarded from ConversationState.
            Used by tool_logging_service for persistent tool call logging.

        _mode_name:
            Name of the outer mode (e.g. "PRE_EXPEDIENTE_MODE").
            Used in structured logs and for TOOLNODE_ENABLED_MODES checks.
    """

    messages: Annotated[list, add]
    pending_state_updates: Annotated[dict, _merge_dicts]
    tool_results: Annotated[list, add]
    tools_called: Annotated[list, add]
    ai_response: str
    exit_reason: str
    _mode_context: dict
    _conversation_id: str
    _mode_name: str
