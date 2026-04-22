"""
Unit test for tool_not_found WARNING observability.

Regression: tool_executor.py:267-273 returned the error dict silently, using
early-return BEFORE the `_log.info("tool_call")` block. Missing tool calls
were invisible in INFO-level production logs. This test asserts a
`logger.warning("tool_not_found", ...)` event IS emitted with structured
fields when the lookup fails.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.asyncio
async def test_tool_not_found_emits_warning_with_structured_fields():
    from agent.modes import tool_executor

    fake_tool = MagicMock()
    fake_tool.name = "some_other_tool"

    with patch.object(tool_executor, "logger") as mock_logger:
        result_str = await tool_executor.execute_and_log_tool(
            conversation_id="conv-xyz",
            tool_name="missing_tool",
            tool_args={"foo": "bar"},
            tools=[fake_tool],
            tool_call_id="call_test_missing",
        )

    import json as _j
    result = _j.loads(result_str)
    assert result["success"] is False
    assert result["error_type"] == "tool_not_found"

    # Warning emitted with structured fields
    warning_calls = [
        c for c in mock_logger.warning.call_args_list
        if c.args and c.args[0] == "tool_not_found"
    ]
    assert len(warning_calls) == 1, (
        f"Expected exactly one logger.warning('tool_not_found', ...). "
        f"Got: {mock_logger.warning.call_args_list}"
    )
    kw = warning_calls[0].kwargs
    assert kw["tool_name"] == "missing_tool"
    assert kw["call_id"] == "call_test_missing"
    assert kw["conversation_id"] == "conv-xyz"
    assert kw["tools_in_registry_count"] == 1
    assert kw["tool_names_in_registry"] == ["some_other_tool"]


@pytest.mark.asyncio
async def test_tool_found_does_not_emit_tool_not_found_warning():
    """Triangulation: when tool IS present, no tool_not_found warning fires."""
    from langchain_core.tools import tool
    from agent.modes import tool_executor

    @tool
    async def echo_tool(msg: str) -> dict:
        """echo."""
        return {"success": True, "msg": msg}

    with patch.object(tool_executor, "logger") as mock_logger:
        await tool_executor.execute_and_log_tool(
            conversation_id="conv-xyz",
            tool_name="echo_tool",
            tool_args={"msg": "hi"},
            tools=[echo_tool],
            tool_call_id="call_test_echo",
        )

    tnf_calls = [
        c for c in mock_logger.warning.call_args_list
        if c.args and c.args[0] == "tool_not_found"
    ]
    assert len(tnf_calls) == 0, (
        f"tool_not_found warning must NOT fire when tool is present. "
        f"Got: {mock_logger.warning.call_args_list}"
    )
