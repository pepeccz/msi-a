"""
Tests for Phase 1 of memory system refactor (refactor-memory-system).

Covers:
- WS1: add_messages reducer — dict coercion, deduplication, backward compat
- WS1: format_messages_for_llm — BaseMessage input, mixed list, summary injection

All tests are synchronous — no external services needed.
"""

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph.message import add_messages

from agent.state.helpers import (
    _extract_content,
    _extract_role,
    format_messages_for_llm,
)


# ---------------------------------------------------------------------------
# _extract_role / _extract_content duck-typing helpers
# ---------------------------------------------------------------------------


class TestExtractRole:
    """Tests for _extract_role duck-typing helper."""

    def test_human_message(self):
        msg = HumanMessage(content="hola")
        assert _extract_role(msg) == "user"

    def test_ai_message(self):
        msg = AIMessage(content="respuesta")
        assert _extract_role(msg) == "assistant"

    def test_system_message(self):
        msg = SystemMessage(content="system prompt")
        assert _extract_role(msg) == "system"

    def test_tool_message(self):
        msg = ToolMessage(content="result", tool_call_id="tc_1")
        assert _extract_role(msg) == "tool"

    def test_dict_user(self):
        assert _extract_role({"role": "user", "content": "hi"}) == "user"

    def test_dict_assistant(self):
        assert _extract_role({"role": "assistant", "content": "hi"}) == "assistant"

    def test_dict_tool(self):
        assert _extract_role({"role": "tool", "content": "res"}) == "tool"

    def test_dict_missing_role(self):
        assert _extract_role({"content": "hi"}) == ""

    def test_unknown_type(self):
        assert _extract_role(42) == ""


class TestExtractContent:
    """Tests for _extract_content duck-typing helper."""

    def test_base_message(self):
        msg = HumanMessage(content="hola mundo")
        assert _extract_content(msg) == "hola mundo"

    def test_dict(self):
        assert _extract_content({"role": "user", "content": "test"}) == "test"

    def test_dict_missing_content(self):
        assert _extract_content({"role": "user"}) == ""

    def test_empty_content(self):
        msg = HumanMessage(content="")
        assert _extract_content(msg) == ""


# ---------------------------------------------------------------------------
# add_messages reducer — dict coercion & dedup
# ---------------------------------------------------------------------------


class TestAddMessagesReducer:
    """Verify add_messages works with our existing dict format."""

    def test_dict_messages_accepted(self):
        """add_messages should accept plain dicts and convert them."""
        result = add_messages(
            [],
            [{"role": "user", "content": "hola"}],
        )
        assert len(result) == 1
        assert result[0].content == "hola"
        # Should be converted to HumanMessage
        assert result[0].type == "human"

    def test_dict_assistant_accepted(self):
        result = add_messages(
            [],
            [{"role": "assistant", "content": "respuesta"}],
        )
        assert len(result) == 1
        assert result[0].type == "ai"
        assert result[0].content == "respuesta"

    def test_multiple_dicts_appended(self):
        """Multiple dict messages appended correctly."""
        existing = add_messages([], [{"role": "user", "content": "msg1"}])
        result = add_messages(
            existing,
            [{"role": "assistant", "content": "msg2"}],
        )
        assert len(result) == 2
        assert result[0].content == "msg1"
        assert result[1].content == "msg2"

    def test_base_message_accepted(self):
        """BaseMessage objects work alongside dicts."""
        result = add_messages(
            [],
            [HumanMessage(content="from BaseMessage")],
        )
        assert len(result) == 1
        assert result[0].content == "from BaseMessage"

    def test_mixed_dict_and_base_message(self):
        """Can mix dicts and BaseMessage in the same update."""
        result = add_messages(
            [{"role": "user", "content": "dict msg"}],
            [AIMessage(content="base msg")],
        )
        assert len(result) == 2

    def test_dedup_by_id(self):
        """Messages with the same ID should be deduplicated (replaced)."""
        msg1 = HumanMessage(content="original", id="msg_1")
        msg2 = HumanMessage(content="updated", id="msg_1")
        result = add_messages([msg1], [msg2])
        assert len(result) == 1
        assert result[0].content == "updated"

    def test_remove_message(self):
        """RemoveMessage should delete a message by ID."""
        msg = HumanMessage(content="to delete", id="msg_del")
        result = add_messages([msg], [RemoveMessage(id="msg_del")])
        assert len(result) == 0

    def test_timestamp_in_dict_ignored(self):
        """Extra keys like 'timestamp' in dicts should not cause errors."""
        result = add_messages(
            [],
            [{"role": "user", "content": "hi", "timestamp": "2026-04-09T00:00:00"}],
        )
        assert len(result) == 1
        assert result[0].content == "hi"

    def test_backward_compat_existing_dicts(self):
        """Simulate loading old checkpoint with dicts, then adding new message."""
        # Simulate: checkpoint had dicts, now add_messages processes them
        old_dicts = [
            {"role": "user", "content": "old msg 1"},
            {"role": "assistant", "content": "old msg 2"},
        ]
        # First call converts old dicts
        result = add_messages(old_dicts, [{"role": "user", "content": "new msg"}])
        assert len(result) == 3
        assert result[0].type == "human"
        assert result[1].type == "ai"
        assert result[2].content == "new msg"


# ---------------------------------------------------------------------------
# format_messages_for_llm — BaseMessage + dict + summary
# ---------------------------------------------------------------------------


class TestFormatMessagesForLlm:
    """Tests for format_messages_for_llm with BaseMessage support."""

    def test_base_messages_formatted(self):
        """BaseMessage objects are formatted with correct role mapping."""
        messages = [
            HumanMessage(content="pregunta"),
            AIMessage(content="respuesta"),
        ]
        result = format_messages_for_llm(messages)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert "<USER_MESSAGE>" in result[0]["content"]
        assert "pregunta" in result[0]["content"]
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "respuesta"

    def test_dict_messages_still_work(self):
        """Legacy dict format continues working."""
        messages = [
            {"role": "user", "content": "pregunta"},
            {"role": "assistant", "content": "respuesta"},
        ]
        result = format_messages_for_llm(messages)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_mixed_messages(self):
        """Mix of dicts and BaseMessage objects works without error."""
        messages = [
            {"role": "user", "content": "dict msg"},
            AIMessage(content="base msg"),
        ]
        result = format_messages_for_llm(messages)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_empty_content_skipped(self):
        """Messages with empty content are skipped."""
        messages = [
            HumanMessage(content=""),
            AIMessage(content="visible"),
        ]
        result = format_messages_for_llm(messages)
        assert len(result) == 1
        assert result[0]["content"] == "visible"

    def test_windowing_applied(self):
        """Only last max_messages are returned."""
        messages = [HumanMessage(content=f"msg{i}") for i in range(30)]
        result = format_messages_for_llm(messages, max_messages=10)
        assert len(result) == 10
        # Last message should be msg29
        assert "msg29" in result[-1]["content"]

    def test_user_message_wrapped_in_security_tags(self):
        """User messages get <USER_MESSAGE> security wrapping."""
        messages = [HumanMessage(content="hola")]
        result = format_messages_for_llm(messages)
        assert result[0]["content"] == "<USER_MESSAGE>\nhola\n</USER_MESSAGE>"

    def test_tool_compression_on_old_messages(self):
        """Old tool results are compressed."""
        # Create messages: 8 messages, tool at index 0 (old)
        messages = [
            ToolMessage(content="A" * 500, tool_call_id="tc_1"),
        ] + [HumanMessage(content=f"msg{i}") for i in range(7)]

        result = format_messages_for_llm(messages, recent_threshold=6)
        # First message (tool, old) should be compressed
        assert result[0]["role"] == "tool"
        assert "[RESULTADO RESUMIDO]" in result[0]["content"]

    def test_summary_injected_when_present(self):
        """conversation_summary is prepended as system message."""
        messages = [HumanMessage(content="pregunta")]
        result = format_messages_for_llm(
            messages,
            conversation_summary="Modo: PRESUPUESTO. Tarifa: 410€.",
        )
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert "[Resumen de conversación anterior]" in result[0]["content"]
        assert "410€" in result[0]["content"]
        # Actual message follows
        assert result[1]["role"] == "user"

    def test_summary_not_injected_when_none(self):
        """No summary message when conversation_summary is None."""
        messages = [HumanMessage(content="pregunta")]
        result = format_messages_for_llm(messages, conversation_summary=None)
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_summary_not_injected_when_empty_string(self):
        """No summary message when conversation_summary is empty string."""
        messages = [HumanMessage(content="pregunta")]
        result = format_messages_for_llm(messages, conversation_summary="")
        assert len(result) == 1
        assert result[0]["role"] == "user"
