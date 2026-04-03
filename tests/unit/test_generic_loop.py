"""
Unit tests for agent/modes/generic_loop.py — T2.1 (RED phase).

Tests validate:
1. Loop exits when LLM returns no tool_calls
2. Loop exits after max_iterations
3. on_tool_result callback is invoked correctly
4. _internal_flags from tool result are applied to context_updates
5. ToolMessage protocol is correct (role="tool", tool_call_id matches)

All tests use pure mocks — no DB, no Redis, no real LLM.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to build mock LLM responses
# ---------------------------------------------------------------------------


def _make_ai_message(content: str = "", tool_calls: list | None = None) -> MagicMock:
    """Build a mock AIMessage (similar to LangChain's AIMessage)."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    # Make the message behave like a dict-serializable LangChain message
    return msg


def _make_tool_call(
    name: str,
    args: dict,
    call_id: str = "call_abc123",
) -> dict:
    """Build a tool_call dict as LangChain produces them."""
    return {
        "id": call_id,
        "name": name,
        "args": args,
    }


# ---------------------------------------------------------------------------
# Test 1 — Loop exits on no tool calls (exit_reason="response")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_exits_on_no_tool_calls():
    """
    When the LLM returns an AIMessage without tool_calls, the loop should
    exit immediately with exit_reason="response" and ai_response = message content.
    """
    from agent.modes.generic_loop import generic_llm_loop

    # LLM returns a plain text response (no tool calls)
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=_make_ai_message(content="Hola, el presupuesto es 450€.")
    )

    result = await generic_llm_loop(
        system_prompt="You are a helpful assistant.",
        messages=[{"role": "user", "content": "Cuánto cuesta?"}],
        tools=[],
        max_iterations=5,
        conversation_id="conv-001",
        mode_name="TEST_MODE",
        state={"conversation_id": "conv-001"},
        llm=mock_llm,
    )

    assert result.exit_reason == "response"
    assert result.ai_response == "Hola, el presupuesto es 450€."
    assert len(result.tools_called) == 0
    # LLM should have been invoked exactly once
    mock_llm.ainvoke.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2 — Loop exits after max_iterations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_exits_on_max_iterations():
    """
    When the LLM ALWAYS returns tool_calls (never a plain text response),
    the loop should exit after max_iterations with exit_reason="max_iterations".
    """
    from agent.modes.generic_loop import generic_llm_loop

    # Mock tool that always returns success
    mock_tool = MagicMock()
    mock_tool.name = "my_tool"
    mock_tool.ainvoke = AsyncMock(return_value={"success": True})

    # LLM that always returns a tool call (never exits)
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=_make_ai_message(
            content="",
            tool_calls=[_make_tool_call("my_tool", {"param": "value"})],
        )
    )

    result = await generic_llm_loop(
        system_prompt="You are a helpful assistant.",
        messages=[{"role": "user", "content": "Do something"}],
        tools=[mock_tool],
        max_iterations=3,  # Small limit for test speed
        conversation_id="conv-002",
        mode_name="TEST_MODE",
        state={"conversation_id": "conv-002"},
        llm=mock_llm,
    )

    assert result.exit_reason == "max_iterations"
    # LLM should have been invoked exactly max_iterations times
    assert mock_llm.ainvoke.call_count == 3


# ---------------------------------------------------------------------------
# Test 3 — on_tool_result callback is called correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_tool_result_callback_called():
    """
    When a tool is called, on_tool_result callback should be invoked with
    (tool_name, result_dict, context_updates) after each tool execution.
    """
    from agent.modes.generic_loop import generic_llm_loop

    # Mock tool returns a simple success dict
    mock_tool = MagicMock()
    mock_tool.name = "test_tool"
    mock_tool.ainvoke = AsyncMock(return_value={"success": True, "value": "test"})

    # LLM: iteration 1 → tool call; iteration 2 → plain response
    ai_with_tool = _make_ai_message(
        content="",
        tool_calls=[_make_tool_call("test_tool", {"q": "hello"}, "call_xyz")],
    )
    ai_plain = _make_ai_message(content="Todo listo.")

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=[ai_with_tool, ai_plain])

    # Track callback invocations
    callback_calls: list[tuple] = []

    async def on_tool_result(
        tool_name: str, result: dict, tool_args: dict, context_updates: dict
    ) -> None:
        callback_calls.append((tool_name, result, tool_args, context_updates))

    result = await generic_llm_loop(
        system_prompt="You are a helpful assistant.",
        messages=[{"role": "user", "content": "Do something"}],
        tools=[mock_tool],
        max_iterations=5,
        conversation_id="conv-003",
        mode_name="TEST_MODE",
        state={"conversation_id": "conv-003"},
        llm=mock_llm,
        on_tool_result=on_tool_result,
    )

    # Callback must have been called once (one tool call in iteration 1)
    assert len(callback_calls) == 1
    cb_tool_name, cb_result, cb_tool_args, cb_context = callback_calls[0]
    assert cb_tool_name == "test_tool"
    assert cb_result.get("success") is True
    assert cb_result.get("value") == "test"
    # tool_args should be the args passed to the tool call
    assert isinstance(cb_tool_args, dict)
    assert cb_tool_args == {"q": "hello"}
    # context_updates is a dict (may be empty or contain flags)
    assert isinstance(cb_context, dict)

    # Loop should exit cleanly after the plain response
    assert result.exit_reason == "response"
    assert result.ai_response == "Todo listo."


# ---------------------------------------------------------------------------
# Test 4 — _internal_flags from tool result applied to context_updates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_internal_flags_applied_from_tool_result():
    """
    When a tool returns _internal_flags, those flags should be applied to
    context_updates so downstream code can read them.
    """
    from agent.modes.generic_loop import generic_llm_loop

    # Tool that returns _internal_flags
    mock_tool = MagicMock()
    mock_tool.name = "tarifa_tool"
    mock_tool.ainvoke = AsyncMock(
        return_value={
            "success": True,
            "precio": 450.0,
            "_internal_flags": {
                "precio_comunicado": True,
                "imagenes_enviadas": False,
            },
        }
    )

    # LLM: iteration 1 → tool call; iteration 2 → plain response
    ai_with_tool = _make_ai_message(
        content="",
        tool_calls=[_make_tool_call("tarifa_tool", {}, "call_tarifa")],
    )
    ai_plain = _make_ai_message(content="El precio es 450€.")

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=[ai_with_tool, ai_plain])

    result = await generic_llm_loop(
        system_prompt="You are a helpful assistant.",
        messages=[{"role": "user", "content": "Precio?"}],
        tools=[mock_tool],
        max_iterations=5,
        conversation_id="conv-004",
        mode_name="TEST_MODE",
        state={"conversation_id": "conv-004"},
        llm=mock_llm,
    )

    # _internal_flags must be reflected in context_updates
    assert result.context_updates.get("precio_comunicado") is True
    assert result.context_updates.get("imagenes_enviadas") is False

    # Tool was called
    assert "tarifa_tool" in result.tools_called

    # Final response is the plain text
    assert result.ai_response == "El precio es 450€."


# ---------------------------------------------------------------------------
# Test 5 — ToolMessage protocol: role="tool" + correct tool_call_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_message_protocol_correct():
    """
    After a tool is executed, the loop must append a ToolMessage with:
    - role == "tool"
    - tool_call_id matching the original tool_call["id"]

    This verifies correct LangChain tool message protocol.
    """
    from agent.modes.generic_loop import generic_llm_loop

    EXPECTED_TOOL_CALL_ID = "call_proto_test_999"

    mock_tool = MagicMock()
    mock_tool.name = "proto_tool"
    mock_tool.ainvoke = AsyncMock(return_value={"success": True})

    ai_with_tool = _make_ai_message(
        content="",
        tool_calls=[_make_tool_call("proto_tool", {"x": 1}, EXPECTED_TOOL_CALL_ID)],
    )
    ai_plain = _make_ai_message(content="Done.")

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=[ai_with_tool, ai_plain])

    # Capture the messages list that the LLM receives on the second call
    captured_messages: list[list[dict]] = []

    original_ainvoke = mock_llm.ainvoke.side_effect

    call_count = 0
    responses = [ai_with_tool, ai_plain]

    async def capturing_ainvoke(messages):
        nonlocal call_count
        captured_messages.append(list(messages))
        resp = responses[call_count]
        call_count += 1
        return resp

    mock_llm.ainvoke = AsyncMock(side_effect=capturing_ainvoke)

    result = await generic_llm_loop(
        system_prompt="System.",
        messages=[{"role": "user", "content": "Test"}],
        tools=[mock_tool],
        max_iterations=5,
        conversation_id="conv-005",
        mode_name="TEST_MODE",
        state={"conversation_id": "conv-005"},
        llm=mock_llm,
    )

    assert result.exit_reason == "response"

    # The second LLM call should contain a ToolMessage
    assert len(captured_messages) == 2, "LLM should have been called twice"
    second_call_messages = captured_messages[1]

    # Find the tool message in the second call's message list
    tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
    assert len(tool_messages) >= 1, (
        "At least one tool message must be in second LLM call"
    )

    tool_msg = tool_messages[0]
    assert tool_msg["role"] == "tool"
    assert tool_msg.get("tool_call_id") == EXPECTED_TOOL_CALL_ID, (
        f"Expected tool_call_id={EXPECTED_TOOL_CALL_ID!r}, "
        f"got {tool_msg.get('tool_call_id')!r}"
    )
