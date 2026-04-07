"""
Tests for Task 1 — Tool Protocol Fix (fix-agent-antipatterns Batch 1)

Verifies that `_handle_validation_retry` uses proper LangGraph tool protocol:
- Appends ToolMessage (role:"tool" + tool_call_id) instead of system message
- `[VALIDATION ERROR]` string NEVER appears in llm_messages as a role:system msg
- Parallel tool calls each get exactly one ToolMessage with matching tool_call_id

See: docs/decisions/fix-agent-antipatterns (design AD-1)
"""

import pytest
from unittest.mock import Mock, MagicMock

from agent.modes.base_mode import BaseModeNode
from agent.state.conversation_state import create_empty_retry_state
from agent.fallback.fallback_handler import FallbackHandler, RetryPolicy, FallbackAction


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def base_mode_node():
    """Create a concrete BaseModeNode subclass for testing."""

    class TestModeNode(BaseModeNode):
        def __init__(self):
            super().__init__("TEST_MODE")

        async def _process_message(self, message, state):
            return {"ai_response": "test"}

        def get_tools(self):
            return []

    return TestModeNode()


@pytest.fixture
def fallback_handler_fixture():
    """Return a FallbackHandler with a TEST_MODE policy pre-configured."""
    policy = RetryPolicy(
        mode="TEST_MODE",
        max_retries=3,
        action_on_limit=FallbackAction.ESCALATE_TO_HUMAN,
        reprompt_strategy="progressive",
        msg_retry_1="Retry 1",
        msg_retry_2="Retry 2",
    )
    handler = FallbackHandler()
    handler.policies["TEST_MODE"] = policy
    return handler


@pytest.fixture
def configured_node(base_mode_node, fallback_handler_fixture):
    """Return a BaseModeNode with fallback handler and policy set."""
    base_mode_node._fallback = fallback_handler_fixture
    base_mode_node._policy = fallback_handler_fixture.policies["TEST_MODE"]
    return base_mode_node


@pytest.fixture
def simple_error_dict():
    """Minimal validation error dict used across tests."""
    return {
        "error_type": "parameter_validation",
        "validation_layer": "semantic",
        "validation_errors": ["Invalid categoria_slug"],
        "tool_name": "calcular_tarifa",
    }


# =============================================================================
# TASK 1.1 — role:tool message appended, [VALIDATION ERROR] never in system msg
# =============================================================================


class TestToolProtocolFix:
    """
    Spec 1 — Fix Tool Protocol Corruption.

    After fix, _handle_validation_retry MUST:
    - Append a message with role:"tool" (not role:"system") when retrying
    - Include tool_call_id matching the failing call
    - NEVER inject "[VALIDATION ERROR]:" into a role:system message
    """

    def test_appends_tool_role_message_not_system(
        self, configured_node, simple_error_dict
    ):
        """
        RED: _handle_validation_retry must append role:'tool', NOT role:'system'.

        Acceptance criterion 1a from spec:
        No role:system with [VALIDATION ERROR] in llm_messages after tool failure.
        """
        retry_state = create_empty_retry_state()
        llm_messages: list = []
        tool_call_id = "call_abc123"

        should_retry, _ = configured_node._handle_validation_retry(
            tool_name="calcular_tarifa",
            error_dict=simple_error_dict,
            retry_state=retry_state,
            llm_messages=llm_messages,
            tool_call_id=tool_call_id,
        )

        assert should_retry is True
        assert len(llm_messages) == 1

        appended_msg = llm_messages[0]
        # Must be role:tool, NOT role:system
        assert appended_msg["role"] == "tool", (
            f"Expected role='tool', got role='{appended_msg['role']}'. "
            "Validation errors must be sent as ToolMessages, not system messages."
        )

    def test_appended_tool_message_has_matching_tool_call_id(
        self, configured_node, simple_error_dict
    ):
        """
        The ToolMessage appended must carry the tool_call_id of the failing call.

        LangGraph protocol: AIMessage(tool_calls=[...]) → ToolMessage(tool_call_id=...)
        """
        retry_state = create_empty_retry_state()
        llm_messages: list = []
        tool_call_id = "call_xyz789"

        configured_node._handle_validation_retry(
            tool_name="calcular_tarifa",
            error_dict=simple_error_dict,
            retry_state=retry_state,
            llm_messages=llm_messages,
            tool_call_id=tool_call_id,
        )

        appended_msg = llm_messages[0]
        assert appended_msg.get("tool_call_id") == tool_call_id, (
            f"Expected tool_call_id='{tool_call_id}', "
            f"got '{appended_msg.get('tool_call_id')}'. "
            "ToolMessage must carry the matching tool_call_id."
        )

    def test_validation_error_string_never_in_system_message(
        self, configured_node, simple_error_dict
    ):
        """
        '[VALIDATION ERROR]' MUST NOT appear as content of a role:system message.

        The old broken code appended:
          {"role": "system", "content": "[VALIDATION ERROR]: ..."}
        This breaks AIMessage→ToolMessage pairing in LangGraph.
        """
        retry_state = create_empty_retry_state()
        llm_messages: list = []

        configured_node._handle_validation_retry(
            tool_name="calcular_tarifa",
            error_dict=simple_error_dict,
            retry_state=retry_state,
            llm_messages=llm_messages,
            tool_call_id="call_fix_test",
        )

        for msg in llm_messages:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                assert "[VALIDATION ERROR]" not in content, (
                    "Found '[VALIDATION ERROR]' in a role:system message. "
                    "Validation errors must use role:tool, not role:system."
                )

    def test_does_not_append_message_when_at_max_retries(
        self, configured_node, simple_error_dict
    ):
        """
        When max retries is reached, no message must be appended.
        (Existing behaviour that must be preserved.)
        """
        # Put retry state at max
        retry_state = create_empty_retry_state()
        retry_state["retry_count"] = 3  # max_retries = 3

        llm_messages: list = []

        should_retry, _ = configured_node._handle_validation_retry(
            tool_name="calcular_tarifa",
            error_dict=simple_error_dict,
            retry_state=retry_state,
            llm_messages=llm_messages,
            tool_call_id="call_max_retry",
        )

        assert should_retry is False
        assert len(llm_messages) == 0, (
            "No message should be appended when max retries is reached."
        )

    def test_tool_message_content_is_non_empty(
        self, configured_node, simple_error_dict
    ):
        """
        The ToolMessage content must be a non-empty string (the reprompt).
        """
        retry_state = create_empty_retry_state()
        llm_messages: list = []

        configured_node._handle_validation_retry(
            tool_name="calcular_tarifa",
            error_dict=simple_error_dict,
            retry_state=retry_state,
            llm_messages=llm_messages,
            tool_call_id="call_content_check",
        )

        appended_msg = llm_messages[0]
        content = appended_msg.get("content", "")
        assert isinstance(content, str) and len(content) > 0, (
            "ToolMessage content must be a non-empty string (the validation reprompt)."
        )


# =============================================================================
# TASK 1.2 — Parametrized: parallel tool calls, one fails → each gets ToolMessage
# =============================================================================


class TestParallelToolCallsToolProtocol:
    """
    Edge case from spec:
    Parallel tool calls where one fails validation → each call gets exactly
    one ToolMessage with matching tool_call_id.
    """

    @pytest.mark.parametrize(
        "failing_call_id,passing_call_id",
        [
            ("call_fail_001", "call_pass_001"),
            ("call_fail_abc", "call_pass_xyz"),
            ("tc_1111", "tc_2222"),
        ],
    )
    def test_failing_call_gets_tool_message_with_correct_id(
        self,
        configured_node,
        simple_error_dict,
        failing_call_id,
        passing_call_id,
    ):
        """
        When the failing tool call is processed by _handle_validation_retry,
        the appended ToolMessage must carry exactly the failing_call_id.

        The passing call's tool_call_id MUST NOT appear in the error ToolMessage.
        """
        retry_state = create_empty_retry_state()
        llm_messages: list = []

        # Simulate: passing call already has its ToolMessage in llm_messages
        llm_messages.append(
            {
                "role": "tool",
                "content": '{"success": true, "precio": 410.0}',
                "tool_call_id": passing_call_id,
            }
        )

        # Now handle the failing call
        should_retry, _ = configured_node._handle_validation_retry(
            tool_name="calcular_tarifa",
            error_dict=simple_error_dict,
            retry_state=retry_state,
            llm_messages=llm_messages,
            tool_call_id=failing_call_id,
        )

        assert should_retry is True

        # Find the NEW message added by _handle_validation_retry
        error_tool_messages = [
            m for m in llm_messages if m.get("tool_call_id") == failing_call_id
        ]
        assert len(error_tool_messages) == 1, (
            f"Expected exactly 1 ToolMessage for failing_call_id='{failing_call_id}', "
            f"got {len(error_tool_messages)}."
        )

        error_msg = error_tool_messages[0]
        assert error_msg["role"] == "tool", (
            f"The error message for '{failing_call_id}' must have role='tool'."
        )

    @pytest.mark.parametrize(
        "failing_call_id,passing_call_id",
        [
            ("call_fail_001", "call_pass_001"),
            ("call_fail_abc", "call_pass_xyz"),
        ],
    )
    def test_passing_call_tool_message_is_untouched(
        self,
        configured_node,
        simple_error_dict,
        failing_call_id,
        passing_call_id,
    ):
        """
        The pre-existing ToolMessage for the passing call must remain intact.
        _handle_validation_retry must NOT modify other messages.
        """
        passing_content = '{"success": true, "precio": 410.0}'
        retry_state = create_empty_retry_state()
        llm_messages: list = [
            {
                "role": "tool",
                "content": passing_content,
                "tool_call_id": passing_call_id,
            }
        ]

        configured_node._handle_validation_retry(
            tool_name="calcular_tarifa",
            error_dict=simple_error_dict,
            retry_state=retry_state,
            llm_messages=llm_messages,
            tool_call_id=failing_call_id,
        )

        # The passing call message must still be there, untouched
        passing_msgs = [
            m for m in llm_messages if m.get("tool_call_id") == passing_call_id
        ]
        assert len(passing_msgs) == 1, (
            "The passing tool's ToolMessage should still be present."
        )
        assert passing_msgs[0]["content"] == passing_content, (
            "The passing tool's ToolMessage content must not be modified."
        )

    def test_two_failing_calls_each_get_own_tool_message(
        self, configured_node, simple_error_dict
    ):
        """
        If two calls fail (processed sequentially), each gets its own ToolMessage.
        Total messages = 2 tool messages, each with distinct tool_call_id.
        """
        error_dict_1 = {**simple_error_dict, "tool_name": "tool_a"}
        error_dict_2 = {**simple_error_dict, "tool_name": "tool_b"}

        retry_state_1 = create_empty_retry_state()
        retry_state_2 = create_empty_retry_state()
        llm_messages: list = []

        configured_node._handle_validation_retry(
            tool_name="tool_a",
            error_dict=error_dict_1,
            retry_state=retry_state_1,
            llm_messages=llm_messages,
            tool_call_id="call_a_fail",
        )

        configured_node._handle_validation_retry(
            tool_name="tool_b",
            error_dict=error_dict_2,
            retry_state=retry_state_2,
            llm_messages=llm_messages,
            tool_call_id="call_b_fail",
        )

        assert len(llm_messages) == 2

        tool_call_ids_in_msgs = {m.get("tool_call_id") for m in llm_messages}
        assert "call_a_fail" in tool_call_ids_in_msgs
        assert "call_b_fail" in tool_call_ids_in_msgs

        for msg in llm_messages:
            assert msg["role"] == "tool", "Both error messages must have role='tool'."
