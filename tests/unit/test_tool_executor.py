"""
Unit tests for agent/modes/tool_executor.py — T3.1 (RED phase).

Tests validate the standalone execute_and_log_tool() function:
1. test_tool_log_row_written — verifica que tool_logs recibe un entry cuando la tool ejecuta
2. test_validation_error_logs_result_type_error — error de validación → result_type="error"
3. test_dedup_prevents_double_log — mismo tool_call_id no se loguea dos veces
4. test_base_mode_wrapper_produces_identical_output — BaseModeNode wrapper produce output idéntico
5. test_generic_loop_uses_standalone_executor — USE_GENERIC_LOOP=True, tool_logs recibe entries

All tests use pure mocks — no DB, no Redis, no real LLM.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SimpleArgs(BaseModel):
    param1: str = Field(..., description="Required param")


def _make_mock_tool(name: str, return_value):
    """Create a mock LangChain tool that returns return_value from ainvoke."""
    tool = MagicMock()
    tool.name = name
    tool.args_schema = _SimpleArgs
    tool.args_schema.model_fields = _SimpleArgs.model_fields
    if isinstance(return_value, dict):
        tool.ainvoke = AsyncMock(
            return_value=json.dumps(return_value, ensure_ascii=False)
        )
    else:
        tool.ainvoke = AsyncMock(return_value=return_value)
    return tool


# ---------------------------------------------------------------------------
# Test 1 — tool_log row is written when tool executes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_log_row_written():
    """
    execute_and_log_tool should write a tool_logs entry with correct fields
    when a tool executes successfully.
    """
    from agent.modes.tool_executor import execute_and_log_tool

    mock_tool = _make_mock_tool("test_tool", {"success": True, "value": 42})

    log_calls = []

    async def mock_log_tool_call(**kwargs):
        log_calls.append(kwargs)

    with (
        patch(
            "agent.modes.tool_executor.log_tool_call", side_effect=mock_log_tool_call
        ),
        patch("agent.modes.tool_executor.get_tool_validator") as mock_get_validator,
        patch("agent.modes.tool_executor.get_current_state", return_value={}),
    ):
        # Make validator always pass
        mock_validator = AsyncMock()
        mock_validator.validate = AsyncMock(return_value=(True, [], None))
        mock_get_validator.return_value = mock_validator

        result = await execute_and_log_tool(
            conversation_id="conv-test-1",
            tool_name="test_tool",
            tool_args={"param1": "value"},
            tools=[mock_tool],
            tool_call_id="call_001",
            iteration=1,
        )

    # Should have written exactly one log entry
    assert len(log_calls) == 1
    log = log_calls[0]
    assert log["tool_name"] == "test_tool"
    assert log["conversation_id"] == "conv-test-1"
    assert log["result_type"] == "success"
    assert log["execution_time_ms"] is not None
    assert log["execution_time_ms"] >= 0
    # Result should contain the tool output
    result_data = json.loads(result)
    assert result_data["success"] is True


# ---------------------------------------------------------------------------
# Test 2 — validation error → result_type="error" in log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validation_error_logs_result_type_error():
    """
    When a tool call has a missing required parameter, execute_and_log_tool
    should log result_type="error" and return an error JSON.
    """
    from agent.modes.tool_executor import execute_and_log_tool

    mock_tool = _make_mock_tool("test_tool", {"success": True})
    mock_tool.args_schema = _SimpleArgs
    mock_tool.args_schema.model_fields = _SimpleArgs.model_fields

    log_calls = []

    async def mock_log_tool_call(**kwargs):
        log_calls.append(kwargs)

    with (
        patch(
            "agent.modes.tool_executor.log_tool_call", side_effect=mock_log_tool_call
        ),
        patch("agent.modes.tool_executor.get_tool_validator") as mock_get_validator,
        patch("agent.modes.tool_executor.get_current_state", return_value={}),
        patch("agent.modes.tool_executor.structured_validation_error") as mock_sve,
    ):
        # Make validator FAIL — missing required param
        mock_validator = AsyncMock()
        mock_validator.validate = AsyncMock(
            return_value=(False, ["Missing required parameter: param1"], "pydantic")
        )
        mock_get_validator.return_value = mock_validator

        # structured_validation_error returns a dict
        mock_sve.return_value = {
            "success": False,
            "error_type": "parameter_validation",
            "validation_errors": ["Missing required parameter: param1"],
        }

        result = await execute_and_log_tool(
            conversation_id="conv-test-2",
            tool_name="test_tool",
            tool_args={},  # Missing param1
            tools=[mock_tool],
            tool_call_id="call_002",
            iteration=1,
        )

    # Should have written exactly one log entry with result_type="error"
    assert len(log_calls) == 1
    log = log_calls[0]
    assert log["result_type"] == "error"
    assert log["execution_time_ms"] == 0  # No execution time when validation fails

    # Result should be a JSON error
    result_data = json.loads(result)
    assert result_data["success"] is False
    assert result_data["error_type"] == "parameter_validation"


# ---------------------------------------------------------------------------
# Test 3 — dedup prevents double log when same tool_call_id is used
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dedup_prevents_double_log():
    """
    When the same tool_call_id is logged twice in the same turn,
    only the first log should be written. The second call should be
    skipped (dedup guard active).
    """
    from agent.modes.tool_executor import execute_and_log_tool

    mock_tool = _make_mock_tool("dedup_tool", {"success": True, "result": "first"})

    log_calls = []

    async def mock_log_tool_call(**kwargs):
        log_calls.append(kwargs)

    dedup_cache: dict[str, str] = {}

    with (
        patch(
            "agent.modes.tool_executor.log_tool_call", side_effect=mock_log_tool_call
        ),
        patch("agent.modes.tool_executor.get_tool_validator") as mock_get_validator,
        patch("agent.modes.tool_executor.get_current_state", return_value={}),
    ):
        mock_validator = AsyncMock()
        mock_validator.validate = AsyncMock(return_value=(True, [], None))
        mock_get_validator.return_value = mock_validator

        # First call
        result1 = await execute_and_log_tool(
            conversation_id="conv-test-3",
            tool_name="dedup_tool",
            tool_args={"param1": "value"},
            tools=[mock_tool],
            tool_call_id="call_same_id",
            iteration=1,
            dedup_cache=dedup_cache,
        )

        # Second call with SAME tool_call_id — should be deduped
        result2 = await execute_and_log_tool(
            conversation_id="conv-test-3",
            tool_name="dedup_tool",
            tool_args={"param1": "value"},
            tools=[mock_tool],
            tool_call_id="call_same_id",
            iteration=1,
            dedup_cache=dedup_cache,
        )

    # Only one log entry should have been written (the first call)
    assert len(log_calls) == 1, f"Expected 1 log entry (dedup), got {len(log_calls)}"

    # Both calls should return the same result (cached)
    assert result1 == result2


# ---------------------------------------------------------------------------
# Test 4 — BaseModeNode wrapper produces identical output to standalone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_mode_wrapper_produces_identical_output():
    """
    BaseModeNode._execute_and_log_tool (thin wrapper) should produce
    identical output to the standalone execute_and_log_tool function
    for the same inputs.
    """
    from agent.modes.tool_executor import execute_and_log_tool
    from agent.modes.base_mode import BaseModeNode

    class _DummyMode(BaseModeNode):
        def __init__(self):
            super().__init__("TEST_MODE")

        async def _process_message(self, message: str, state: dict) -> dict:
            return {"ai_response": "test"}

        def get_tools(self, mode_context=None) -> list:
            return []

    # Tool that returns a known result
    mock_tool = _make_mock_tool("wrapper_tool", {"success": True, "wrapper_test": True})

    log_calls_standalone = []
    log_calls_wrapper = []

    async def mock_log_standalone(**kwargs):
        log_calls_standalone.append(kwargs)

    async def mock_log_wrapper(**kwargs):
        log_calls_wrapper.append(kwargs)

    with (
        patch("agent.modes.tool_executor.get_tool_validator") as mock_validator_factory,
        patch("agent.modes.tool_executor.get_current_state", return_value={}),
    ):
        mock_validator = AsyncMock()
        mock_validator.validate = AsyncMock(return_value=(True, [], None))
        mock_validator_factory.return_value = mock_validator

        # 1. Call standalone directly
        with patch(
            "agent.modes.tool_executor.log_tool_call", side_effect=mock_log_standalone
        ):
            standalone_result = await execute_and_log_tool(
                conversation_id="conv-wrapper-test",
                tool_name="wrapper_tool",
                tool_args={"param1": "v"},
                tools=[mock_tool],
                tool_call_id="call_standalone",
                iteration=1,
            )

        # Reset mock tool to allow second call
        mock_tool.ainvoke = AsyncMock(
            return_value=json.dumps(
                {"success": True, "wrapper_test": True}, ensure_ascii=False
            )
        )

        # 2. Call via BaseModeNode wrapper
        # The wrapper injects self._log_tool_call as log_fn.
        # Patch _log_tool_call on the instance so the injection picks it up.
        mode_node = _DummyMode()
        mode_node._tool_dedup_cache = {}  # Initialize dedup cache
        with patch.object(mode_node, "_log_tool_call", side_effect=mock_log_wrapper):
            wrapper_result = await mode_node._execute_and_log_tool(
                conversation_id="conv-wrapper-test",
                tool_name="wrapper_tool",
                tool_args={"param1": "v"},
                tools=[mock_tool],
                iteration=1,
            )

    # Results should be identical (same JSON)
    standalone_data = json.loads(standalone_result)
    wrapper_data = json.loads(wrapper_result)
    assert standalone_data["success"] == wrapper_data["success"]
    assert standalone_data["wrapper_test"] == wrapper_data["wrapper_test"]

    # Both should have written exactly 1 log entry
    assert len(log_calls_standalone) == 1
    assert len(log_calls_wrapper) == 1

    # Both log entries should have same key fields
    sl = log_calls_standalone[0]
    wl = log_calls_wrapper[0]
    assert sl["tool_name"] == wl["tool_name"]
    assert sl["result_type"] == wl["result_type"]


# ---------------------------------------------------------------------------
# Test 5 — generic_loop uses standalone executor when USE_GENERIC_LOOP=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generic_loop_uses_standalone_executor():
    """
    When USE_GENERIC_LOOP=True, tool calls via generic_llm_loop should
    produce tool_logs entries (via execute_and_log_tool).
    """
    from agent.modes.generic_loop import generic_llm_loop

    # A mock tool that returns success
    mock_tool = MagicMock()
    mock_tool.name = "loop_tool"
    mock_tool.args_schema = _SimpleArgs
    mock_tool.ainvoke = AsyncMock(
        return_value=json.dumps({"success": True, "loop_ran": True}, ensure_ascii=False)
    )

    # LLM: iteration 1 → tool call; iteration 2 → plain response
    def _make_ai_message(content="", tool_calls=None):
        msg = MagicMock()
        msg.content = content
        msg.tool_calls = tool_calls or []
        return msg

    ai_with_tool = _make_ai_message(
        content="",
        tool_calls=[
            {"id": "call_loop_001", "name": "loop_tool", "args": {"param1": "x"}}
        ],
    )
    ai_plain = _make_ai_message(content="Loop done.")

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=[ai_with_tool, ai_plain])

    log_calls = []

    async def mock_log_tool_call(**kwargs):
        log_calls.append(kwargs)

    with (
        patch(
            "agent.modes.tool_executor.log_tool_call", side_effect=mock_log_tool_call
        ),
        patch("agent.modes.tool_executor.get_tool_validator") as mock_validator_factory,
        patch("agent.modes.tool_executor.get_current_state", return_value={}),
    ):
        mock_validator = AsyncMock()
        mock_validator.validate = AsyncMock(return_value=(True, [], None))
        mock_validator_factory.return_value = mock_validator

        result = await generic_llm_loop(
            system_prompt="System prompt.",
            messages=[{"role": "user", "content": "Run loop"}],
            tools=[mock_tool],
            max_iterations=5,
            conversation_id="conv-loop-test",
            mode_name="TEST_MODE",
            state={"conversation_id": "conv-loop-test"},
            llm=mock_llm,
        )

    # The loop should have produced a tool_logs entry
    assert len(log_calls) >= 1, (
        f"Expected at least 1 tool log entry from generic loop, got {len(log_calls)}"
    )
    assert log_calls[0]["tool_name"] == "loop_tool"
    assert log_calls[0]["conversation_id"] == "conv-loop-test"
    assert result.exit_reason == "response"
