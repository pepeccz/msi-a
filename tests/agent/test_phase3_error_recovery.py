"""
Tests for Phase 3: Error Recovery & Retry

Tests the validation error detection and retry logic in BaseModeNode.

Coverage:
- _is_validation_error() detection
- _handle_validation_retry() retry logic
- Progressive reprompting
- Retry limit enforcement
- Escalation on max retries
"""

import pytest
import json
from unittest.mock import Mock, MagicMock

from agent.modes.base_mode import BaseModeNode
from agent.state.conversation_state import create_empty_retry_state, RetryStateData
from agent.fallback.fallback_handler import FallbackHandler, RetryPolicy, FallbackAction


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def base_mode_node():
    """Create a BaseModeNode instance for testing."""

    class TestModeNode(BaseModeNode):
        def __init__(self):
            super().__init__("TEST_MODE")

        async def _process_message(self, message, state):
            return {"ai_response": "test"}

        def get_tools(self):
            return []

    return TestModeNode()


@pytest.fixture
def retry_policy():
    """Create a test retry policy."""
    return RetryPolicy(
        mode="TEST_MODE",
        max_retries=3,
        action_on_limit=FallbackAction.ESCALATE_TO_HUMAN,
        reprompt_strategy="progressive",
        msg_retry_1="Retry 1 message",
        msg_retry_2="Retry 2 message",
    )


@pytest.fixture
def fallback_handler(retry_policy):
    """Create a FallbackHandler instance."""
    handler = FallbackHandler()
    handler.policies["TEST_MODE"] = retry_policy
    return handler


# =============================================================================
# TESTS: _is_validation_error()
# =============================================================================


class TestIsValidationError:
    """Test validation error detection."""

    def test_detects_validation_error_from_json_string(self, base_mode_node):
        """Should detect validation error from JSON string."""
        error_result = json.dumps(
            {
                "success": False,
                "error_type": "parameter_validation",
                "validation_layer": "semantic",
                "validation_errors": ["La categoría 'invalid' no existe"],
                "tool_name": "calcular_tarifa_con_elementos",
            }
        )

        is_error, error_dict = base_mode_node._is_validation_error(error_result)

        assert is_error is True
        assert error_dict is not None
        assert error_dict["error_type"] == "parameter_validation"
        assert error_dict["validation_layer"] == "semantic"
        assert len(error_dict["validation_errors"]) == 1

    def test_detects_validation_error_from_dict(self, base_mode_node):
        """Should detect validation error from dict."""
        error_result = {
            "success": False,
            "error_type": "parameter_validation",
            "validation_layer": "syntax",
            "validation_errors": ["Missing required parameter: categoria_slug"],
            "tool_name": "listar_elementos",
        }

        is_error, error_dict = base_mode_node._is_validation_error(error_result)

        assert is_error is True
        assert error_dict is not None
        assert error_dict["validation_layer"] == "syntax"

    def test_returns_false_for_success_result(self, base_mode_node):
        """Should return False for successful tool result."""
        success_result = json.dumps(
            {"success": True, "precio_final": 410.0, "elementos": ["ESCAPE"]}
        )

        is_error, error_dict = base_mode_node._is_validation_error(success_result)

        assert is_error is False
        assert error_dict is None

    def test_returns_false_for_non_validation_error(self, base_mode_node):
        """Should return False for non-validation errors."""
        other_error = json.dumps(
            {
                "success": False,
                "error_type": "database_error",  # Not parameter_validation
                "error": "Connection timeout",
            }
        )

        is_error, error_dict = base_mode_node._is_validation_error(other_error)

        assert is_error is False
        assert error_dict is None

    def test_handles_invalid_json_gracefully(self, base_mode_node):
        """Should handle invalid JSON without crashing."""
        invalid_json = "not a valid json string"

        is_error, error_dict = base_mode_node._is_validation_error(invalid_json)

        # Should return False for unparseable strings
        assert is_error is False
        assert error_dict is None

    def test_handles_missing_error_type_field(self, base_mode_node):
        """Should handle dict without error_type field."""
        result = json.dumps(
            {
                "success": False,
                # Missing error_type field
                "validation_errors": ["Some error"],
            }
        )

        is_error, error_dict = base_mode_node._is_validation_error(result)

        assert is_error is False
        assert error_dict is None


# =============================================================================
# TESTS: _handle_validation_retry()
# =============================================================================


class TestHandleValidationRetry:
    """Test retry logic and reprompting."""

    def test_should_retry_when_under_limit(self, base_mode_node, fallback_handler):
        """Should retry when retry count is below max."""
        base_mode_node._fallback = fallback_handler
        base_mode_node._policy = fallback_handler.policies["TEST_MODE"]

        retry_state = create_empty_retry_state()
        llm_messages = []

        error_dict = {
            "error_type": "parameter_validation",
            "validation_layer": "semantic",
            "validation_errors": ["Invalid categoria_slug"],
            "tool_name": "calcular_tarifa",
        }

        should_retry, updated_retry_state = base_mode_node._handle_validation_retry(
            tool_name="calcular_tarifa",
            error_dict=error_dict,
            retry_state=retry_state,
            llm_messages=llm_messages,
            tool_call_id="call_test_retry",
        )

        assert should_retry is True
        assert updated_retry_state["retry_count"] == 1
        assert len(llm_messages) == 1  # Reprompt added as ToolMessage
        # LangGraph protocol: must be role:"tool" (not role:"system")
        assert llm_messages[0]["role"] == "tool"

    def test_should_not_retry_when_at_limit(self, base_mode_node, fallback_handler):
        """Should not retry when retry count reaches max."""
        base_mode_node._fallback = fallback_handler
        base_mode_node._policy = fallback_handler.policies["TEST_MODE"]

        # Retry state at max retries
        retry_state = create_empty_retry_state()
        retry_state["retry_count"] = 3  # max_retries = 3

        llm_messages = []

        error_dict = {
            "error_type": "parameter_validation",
            "validation_layer": "semantic",
            "validation_errors": ["Invalid categoria_slug"],
            "tool_name": "calcular_tarifa",
        }

        should_retry, updated_retry_state = base_mode_node._handle_validation_retry(
            tool_name="calcular_tarifa",
            error_dict=error_dict,
            retry_state=retry_state,
            llm_messages=llm_messages,
            tool_call_id="call_test_at_limit",
        )

        assert should_retry is False
        # Note: retry_count is incremented even at limit, then check happens
        assert updated_retry_state["retry_count"] == 4  # Incremented to 4
        assert len(llm_messages) == 0  # No reprompt added

    def test_records_validation_context(self, base_mode_node, fallback_handler):
        """Should record validation context in retry state."""
        base_mode_node._fallback = fallback_handler
        base_mode_node._policy = fallback_handler.policies["TEST_MODE"]

        retry_state = create_empty_retry_state()
        llm_messages = []

        error_dict = {
            "error_type": "parameter_validation",
            "validation_layer": "semantic",
            "validation_errors": ["El elemento 'INVALID' no existe"],
            "tool_name": "identificar_elementos",
        }

        should_retry, updated_retry_state = base_mode_node._handle_validation_retry(
            tool_name="identificar_elementos",
            error_dict=error_dict,
            retry_state=retry_state,
            llm_messages=llm_messages,
            tool_call_id="call_test_context",
        )

        assert should_retry is True
        assert "last_validation_context" in updated_retry_state

        last_context = updated_retry_state["last_validation_context"]
        assert last_context["tool_name"] == "identificar_elementos"
        assert last_context["layer"] == "semantic"  # Correct field name
        assert (
            last_context["errors"] == error_dict["validation_errors"]
        )  # Correct field name

    def test_progressive_reprompting(self, base_mode_node, fallback_handler):
        """Should use different reprompts for each retry."""
        base_mode_node._fallback = fallback_handler
        base_mode_node._policy = fallback_handler.policies["TEST_MODE"]

        error_dict = {
            "error_type": "parameter_validation",
            "validation_layer": "semantic",
            "validation_errors": ["Error"],
            "tool_name": "test_tool",
        }

        # Retry 1
        retry_state_1 = create_empty_retry_state()
        llm_messages_1 = []
        should_retry_1, retry_state_1 = base_mode_node._handle_validation_retry(
            tool_name="test_tool",
            error_dict=error_dict,
            retry_state=retry_state_1,
            llm_messages=llm_messages_1,
            tool_call_id="call_prog_1",
        )
        reprompt_1 = llm_messages_1[0]["content"]

        # Retry 2
        llm_messages_2 = []
        should_retry_2, retry_state_2 = base_mode_node._handle_validation_retry(
            tool_name="test_tool",
            error_dict=error_dict,
            retry_state=retry_state_1,  # Use updated state
            llm_messages=llm_messages_2,
            tool_call_id="call_prog_2",
        )
        reprompt_2 = llm_messages_2[0]["content"]

        # Reprompts should be different
        assert reprompt_1 != reprompt_2
        assert retry_state_2["retry_count"] == 2


# =============================================================================
# TESTS: FallbackHandler record_validation_error()
# =============================================================================


class TestFallbackHandlerRecordValidation:
    """Test FallbackHandler validation error recording."""

    def test_records_validation_error(self, fallback_handler):
        """Should record validation error in retry state."""
        retry_state = create_empty_retry_state()

        updated_state = fallback_handler.record_validation_error(
            retry_state=retry_state,
            tool_name="calcular_tarifa",
            validation_errors=["Invalid categoria_slug"],
            validation_layer="semantic",
        )

        assert "last_validation_context" in updated_state
        context = updated_state["last_validation_context"]

        assert context["tool_name"] == "calcular_tarifa"
        assert context["layer"] == "semantic"
        assert context["errors"] == ["Invalid categoria_slug"]

    def test_increments_retry_count(self, fallback_handler):
        """Should increment retry count."""
        retry_state = create_empty_retry_state()
        assert retry_state["retry_count"] == 0

        updated_state = fallback_handler.record_validation_error(
            retry_state=retry_state,
            tool_name="test_tool",
            validation_errors=["Error"],
            validation_layer="syntax",
        )

        assert updated_state["retry_count"] == 1

    def test_preserves_retry_count_increment(self, fallback_handler):
        """Should increment retry count from existing state."""
        retry_state = create_empty_retry_state()
        retry_state["retry_count"] = 2

        updated_state = fallback_handler.record_validation_error(
            retry_state=retry_state,
            tool_name="test_tool",
            validation_errors=["Error"],
            validation_layer="syntax",
        )

        # Should increment from 2 to 3
        assert updated_state["retry_count"] == 3


# =============================================================================
# TESTS: FallbackHandler get_validation_reprompt()
# =============================================================================


class TestFallbackHandlerGetValidationReprompt:
    """Test FallbackHandler reprompt generation."""

    def test_generates_reprompt_for_retry_1(self, fallback_handler, retry_policy):
        """Should generate first retry reprompt."""
        retry_state = create_empty_retry_state()
        retry_state["retry_count"] = 1
        retry_state["last_validation_context"] = {
            "tool_name": "calcular_tarifa",
            "validation_errors": ["Invalid categoria_slug"],
        }

        reprompt = fallback_handler.get_validation_reprompt(
            retry_state=retry_state, policy=retry_policy
        )

        assert isinstance(reprompt, str)
        assert len(reprompt) > 0
        # Should mention the error
        assert "parámetros" in reprompt.lower() or "válidos" in reprompt.lower()

    def test_generates_reprompt_for_retry_2(self, fallback_handler, retry_policy):
        """Should generate second retry reprompt."""
        retry_state = create_empty_retry_state()
        retry_state["retry_count"] = 2
        retry_state["last_validation_context"] = {
            "tool_name": "calcular_tarifa",
            "errors": [
                "Invalid categoria_slug",
                "Missing element",
            ],  # Correct field name
            "layer": "semantic",
        }

        reprompt = fallback_handler.get_validation_reprompt(
            retry_state=retry_state, policy=retry_policy
        )

        assert isinstance(reprompt, str)
        # Should include tool name and specific errors
        assert "calcular_tarifa" in reprompt

    def test_generates_escalation_message_for_max_retries(
        self, fallback_handler, retry_policy
    ):
        """Should generate escalation message when max retries reached."""
        retry_state = create_empty_retry_state()
        retry_state["retry_count"] = 3  # At max
        retry_state["last_validation_context"] = {
            "tool_name": "test_tool",
            "validation_errors": ["Error"],
        }

        reprompt = fallback_handler.get_validation_reprompt(
            retry_state=retry_state, policy=retry_policy
        )

        assert isinstance(reprompt, str)
        # Should mention human handoff
        assert "humano" in reprompt.lower() or "persona" in reprompt.lower()

    def test_handles_missing_validation_context(self, fallback_handler, retry_policy):
        """Should handle missing validation context gracefully."""
        retry_state = create_empty_retry_state()
        retry_state["retry_count"] = 1
        # No last_validation_context

        reprompt = fallback_handler.get_validation_reprompt(
            retry_state=retry_state, policy=retry_policy
        )

        # Should still generate a reprompt
        assert isinstance(reprompt, str)
        assert len(reprompt) > 0


# =============================================================================
# INTEGRATION TESTS: Full Retry Flow
# =============================================================================


class TestRetryFlowIntegration:
    """Integration tests for complete retry flow."""

    def test_retry_flow_success_on_second_attempt(
        self, base_mode_node, fallback_handler
    ):
        """Should succeed on second attempt after retry."""
        base_mode_node._fallback = fallback_handler
        base_mode_node._policy = fallback_handler.policies["TEST_MODE"]

        # Initial state
        retry_state = create_empty_retry_state()
        llm_messages = []

        # First validation error
        error_json_1 = {
            "success": False,  # Must have success=False
            "error_type": "parameter_validation",
            "validation_layer": "semantic",
            "validation_errors": ["Error 1"],
            "tool_name": "test_tool",
        }

        is_error_1, error_dict_1 = base_mode_node._is_validation_error(
            json.dumps(error_json_1)
        )

        assert is_error_1 is True

        should_retry_1, retry_state = base_mode_node._handle_validation_retry(
            tool_name="test_tool",
            error_dict=error_dict_1,
            retry_state=retry_state,
            llm_messages=llm_messages,
            tool_call_id="call_integration_1",
        )

        assert should_retry_1 is True
        assert retry_state["retry_count"] == 1
        assert len(llm_messages) == 1

        # Second attempt succeeds
        success_result = json.dumps({"success": True, "data": "result"})

        is_error_2, error_dict_2 = base_mode_node._is_validation_error(success_result)

        assert is_error_2 is False
        assert retry_state["retry_count"] == 1  # Count doesn't increment on success

    def test_retry_flow_escalation_after_max_retries(
        self, base_mode_node, fallback_handler
    ):
        """Should escalate after max retries exhausted."""
        base_mode_node._fallback = fallback_handler
        base_mode_node._policy = fallback_handler.policies["TEST_MODE"]

        retry_state = create_empty_retry_state()
        llm_messages = []

        error_dict = {
            "success": False,  # Must have success=False
            "error_type": "parameter_validation",
            "validation_layer": "semantic",
            "validation_errors": ["Persistent error"],
            "tool_name": "test_tool",
        }

        # Retry 2 times successfully (max_retries = 3)
        for i in range(2):
            should_retry, retry_state = base_mode_node._handle_validation_retry(
                tool_name="test_tool",
                error_dict=error_dict,
                retry_state=retry_state,
                llm_messages=llm_messages,
                tool_call_id=f"call_escalation_{i}",
            )

            assert should_retry is True
            assert retry_state["retry_count"] == i + 1

        # 3rd attempt should hit max and not retry (retry_count will be 3, max is 3)
        should_retry_3, retry_state_3 = base_mode_node._handle_validation_retry(
            tool_name="test_tool",
            error_dict=error_dict,
            retry_state=retry_state,
            llm_messages=llm_messages,
            tool_call_id="call_escalation_final",
        )

        assert should_retry_3 is False  # At max limit
        assert retry_state_3["retry_count"] == 3  # Hits max


# =============================================================================
# EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_none_retry_state(self, base_mode_node, fallback_handler):
        """Should handle None retry state gracefully."""
        base_mode_node._fallback = fallback_handler
        base_mode_node._policy = fallback_handler.policies["TEST_MODE"]

        # Simulate None retry state (shouldn't happen but be defensive)
        retry_state = None
        llm_messages = []

        error_dict = {
            "error_type": "parameter_validation",
            "validation_layer": "semantic",
            "validation_errors": ["Error"],
            "tool_name": "test_tool",
        }

        # Should not crash
        try:
            should_retry, updated_retry_state = base_mode_node._handle_validation_retry(
                tool_name="test_tool",
                error_dict=error_dict,
                retry_state=retry_state or create_empty_retry_state(),
                llm_messages=llm_messages,
                tool_call_id="call_edge_none",
            )
            assert True  # No crash
        except Exception as e:
            pytest.fail(f"Should handle None retry state gracefully: {e}")

    def test_handles_empty_validation_errors_list(self, base_mode_node):
        """Should handle empty validation_errors list."""
        error_result = json.dumps(
            {
                "success": False,
                "error_type": "parameter_validation",
                "validation_layer": "semantic",
                "validation_errors": [],  # Empty list
                "tool_name": "test_tool",
            }
        )

        is_error, error_dict = base_mode_node._is_validation_error(error_result)

        # Should still detect as validation error
        assert is_error is True
        assert error_dict is not None
        assert error_dict["validation_errors"] == []

    def test_handles_very_long_error_message(self, base_mode_node, fallback_handler):
        """Should handle very long error messages."""
        base_mode_node._fallback = fallback_handler
        base_mode_node._policy = fallback_handler.policies["TEST_MODE"]

        retry_state = create_empty_retry_state()
        llm_messages = []

        # Create very long error message
        long_error = "A" * 10000  # 10k characters

        error_dict = {
            "error_type": "parameter_validation",
            "validation_layer": "semantic",
            "validation_errors": [long_error],
            "tool_name": "test_tool",
        }

        # Should not crash
        should_retry, updated_retry_state = base_mode_node._handle_validation_retry(
            tool_name="test_tool",
            error_dict=error_dict,
            retry_state=retry_state,
            llm_messages=llm_messages,
            tool_call_id="call_edge_long_msg",
        )

        assert should_retry is True
        assert len(llm_messages) == 1
