"""
Unit tests for Phase 3 — Tool Call Log Observability.

Covers VARIANT-COMBINED-4: _execute_and_log_tool must pass an explicit
result_type ("success" | "error" | "blocked") and error_message to
log_tool_call instead of always defaulting to "success".

Scenarios tested
----------------
1. _classify_tool_result — JSON success dict → "success", None
2. _classify_tool_result — JSON failure dict (success=False) → "error", message
3. _classify_tool_result — JSON dict with "error" key → "error", message
4. _classify_tool_result — Non-JSON plain-text string → "error", raw text
5. _classify_tool_result — Empty string → "success", None
6. _classify_tool_result — Blocked duplicate phrase → "blocked", None
7. _classify_tool_result — Valid non-dict JSON (list) → "success", None
8. _execute_and_log_tool — success result calls log_tool_call with result_type="success"
9. _execute_and_log_tool — failure result calls log_tool_call with result_type="error"
10. _execute_and_log_tool — plain-text result calls log_tool_call with result_type="error"
11. _log_tool_call — passes result_type and error_message through to service
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from pydantic import BaseModel, Field

from agent.modes.base_mode import BaseModeNode


# =============================================================================
# Test helpers
# =============================================================================


class _DummyModeNode(BaseModeNode):
    """Minimal concrete BaseModeNode for testing."""

    def __init__(self):
        super().__init__("TEST_MODE")

    async def _process_message(self, message: str, state: dict) -> dict:
        return {"ai_response": "test"}

    def get_tools(self) -> list:
        return []


class _SimpleArgs(BaseModel):
    param1: str = Field(..., description="Required")


def _make_mock_tool(name: str, return_value: dict | str):
    """Create a mock LangChain tool that returns *return_value* from ainvoke."""
    tool = MagicMock()
    tool.name = name
    tool.args_schema = _SimpleArgs
    tool.args_schema.model_fields = _SimpleArgs.model_fields
    if isinstance(return_value, dict):
        tool.ainvoke = AsyncMock(return_value=return_value)
    else:
        # Plain string — tool returns it directly
        tool.ainvoke = AsyncMock(return_value=return_value)
    return tool


# =============================================================================
# Task 3.1 — _classify_tool_result unit tests
# =============================================================================


class TestClassifyToolResult:
    """Tests for BaseModeNode._classify_tool_result (static method)."""

    def _classify(self, result):
        return BaseModeNode._classify_tool_result(result)

    # ------------------------------------------------------------------
    # Happy path: JSON success dict
    # ------------------------------------------------------------------

    def test_success_dict_returns_success_type(self):
        """JSON dict with success=True → result_type='success', error=None."""
        payload = json.dumps({"success": True, "precio_final": 410.0})
        result_type, error_message = self._classify(payload)

        assert result_type == "success"
        assert error_message is None

    def test_success_dict_without_success_key_returns_success(self):
        """JSON dict that has no 'success' or 'error' key → success."""
        payload = json.dumps({"data": "some_value", "count": 5})
        result_type, error_message = self._classify(payload)

        assert result_type == "success"
        assert error_message is None

    # ------------------------------------------------------------------
    # Error cases: success=False
    # ------------------------------------------------------------------

    def test_success_false_returns_error_type(self):
        """JSON dict with success=False → result_type='error'."""
        payload = json.dumps({"success": False, "error": "Elemento no encontrado"})
        result_type, error_message = self._classify(payload)

        assert result_type == "error"

    def test_success_false_extracts_error_field(self):
        """error_message extracted from the 'error' key."""
        payload = json.dumps({"success": False, "error": "No se pudo calcular"})
        result_type, error_message = self._classify(payload)

        assert error_message == "No se pudo calcular"

    def test_success_false_falls_back_to_message_field(self):
        """error_message falls back to 'message' when 'error' key absent."""
        payload = json.dumps({"success": False, "message": "Fallo interno"})
        result_type, error_message = self._classify(payload)

        assert result_type == "error"
        assert error_message == "Fallo interno"

    def test_success_false_no_error_field_uses_default(self):
        """error_message has a default when neither 'error' nor 'message' present."""
        payload = json.dumps({"success": False})
        result_type, error_message = self._classify(payload)

        assert result_type == "error"
        assert error_message == "Tool returned failure"

    # ------------------------------------------------------------------
    # Error cases: 'error' key present without explicit success=False
    # ------------------------------------------------------------------

    def test_dict_with_error_key_returns_error_type(self):
        """JSON dict containing 'error' key → result_type='error'."""
        payload = json.dumps({"error": "timeout", "code": 503})
        result_type, error_message = self._classify(payload)

        assert result_type == "error"
        assert error_message == "timeout"

    # ------------------------------------------------------------------
    # Blocked phrases
    # ------------------------------------------------------------------

    def test_blocked_phrase_in_message_returns_blocked(self):
        """When 'bloqueando duplicado' phrase present → result_type='blocked'."""
        payload = json.dumps(
            {"success": False, "message": "bloqueando duplicado de imágenes"}
        )
        result_type, error_message = self._classify(payload)

        assert result_type == "blocked"
        assert error_message is None

    def test_ya_fueron_enviadas_returns_blocked(self):
        """'ya fueron enviadas' phrase → blocked."""
        payload = json.dumps(
            {"success": False, "error": "Las imágenes ya fueron enviadas"}
        )
        result_type, error_message = self._classify(payload)

        assert result_type == "blocked"

    # ------------------------------------------------------------------
    # Non-JSON plain-text
    # ------------------------------------------------------------------

    def test_plain_text_string_returns_error(self):
        """Non-JSON plain text → result_type='error'."""
        result_type, error_message = self._classify("Error de conexión con la base de datos")

        assert result_type == "error"

    def test_plain_text_string_uses_raw_text_as_error_message(self):
        """error_message = the raw plain text (truncated)."""
        raw = "Algo salió muy mal en el servidor"
        result_type, error_message = self._classify(raw)

        assert error_message == raw

    def test_plain_text_truncated_at_500_chars(self):
        """Long plain text is truncated to 500 chars."""
        long_text = "x" * 600
        _, error_message = self._classify(long_text)

        assert len(error_message) == 500

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_empty_string_returns_success(self):
        """Empty string → success (not an error)."""
        result_type, error_message = self._classify("")

        assert result_type == "success"
        assert error_message is None

    def test_valid_json_list_returns_success(self):
        """Valid JSON that is a list (not dict) → success."""
        payload = json.dumps(["item1", "item2"])
        result_type, error_message = self._classify(payload)

        assert result_type == "success"
        assert error_message is None

    def test_valid_json_integer_returns_success(self):
        """Valid JSON integer → success."""
        result_type, error_message = self._classify("42")

        assert result_type == "success"
        assert error_message is None

    def test_error_message_truncated_at_500_chars(self):
        """Long error messages are capped at 500 chars."""
        long_error = "e" * 600
        payload = json.dumps({"success": False, "error": long_error})
        _, error_message = BaseModeNode._classify_tool_result(payload)

        assert len(error_message) == 500


# =============================================================================
# Task 3.2 — _execute_and_log_tool integration tests
# =============================================================================


class TestExecuteAndLogToolResultType:
    """
    Verify _execute_and_log_tool passes correct result_type to _log_tool_call.
    """

    @pytest.mark.asyncio
    async def test_success_result_logs_success_type(self):
        """Tool returning success=True → _log_tool_call called with result_type='success'."""
        mode = _DummyModeNode()
        tool = _make_mock_tool("my_tool", {"success": True, "data": "ok"})

        mock_state = {"conversation_id": "conv-1", "mode_context": {}}

        with patch("agent.state.helpers.get_current_state", return_value=mock_state):
            with patch.object(mode, "_log_tool_call", new_callable=AsyncMock) as mock_log:
                await mode._execute_and_log_tool(
                    conversation_id="conv-1",
                    tool_name="my_tool",
                    tool_args={"param1": "hello"},
                    tools=[tool],
                    iteration=1,
                )

        assert mock_log.called
        kwargs = mock_log.call_args[1]
        assert kwargs["result_type"] == "success"
        assert kwargs["error_message"] is None

    @pytest.mark.asyncio
    async def test_failure_result_logs_error_type(self):
        """Tool returning success=False → _log_tool_call called with result_type='error'."""
        mode = _DummyModeNode()
        tool = _make_mock_tool(
            "my_tool", {"success": False, "error": "Elemento no reconocido"}
        )

        mock_state = {"conversation_id": "conv-2", "mode_context": {}}

        with patch("agent.state.helpers.get_current_state", return_value=mock_state):
            with patch.object(mode, "_log_tool_call", new_callable=AsyncMock) as mock_log:
                await mode._execute_and_log_tool(
                    conversation_id="conv-2",
                    tool_name="my_tool",
                    tool_args={"param1": "hello"},
                    tools=[tool],
                    iteration=1,
                )

        assert mock_log.called
        kwargs = mock_log.call_args[1]
        assert kwargs["result_type"] == "error"
        assert kwargs["error_message"] == "Elemento no reconocido"

    @pytest.mark.asyncio
    async def test_plain_text_result_logs_error_type(self):
        """Tool returning plain-text (non-JSON) → _log_tool_call called with result_type='error'."""
        mode = _DummyModeNode()
        tool = _make_mock_tool("my_tool", "Error de conexión con la DB")

        mock_state = {"conversation_id": "conv-3", "mode_context": {}}

        with patch("agent.state.helpers.get_current_state", return_value=mock_state):
            with patch.object(mode, "_log_tool_call", new_callable=AsyncMock) as mock_log:
                await mode._execute_and_log_tool(
                    conversation_id="conv-3",
                    tool_name="my_tool",
                    tool_args={"param1": "hello"},
                    tools=[tool],
                    iteration=1,
                )

        assert mock_log.called
        kwargs = mock_log.call_args[1]
        assert kwargs["result_type"] == "error"
        assert "Error de conexión" in (kwargs["error_message"] or "")

    @pytest.mark.asyncio
    async def test_blocked_result_logs_blocked_type(self):
        """Tool returning blocked phrase → _log_tool_call called with result_type='blocked'."""
        mode = _DummyModeNode()
        tool = _make_mock_tool(
            "my_tool",
            {"success": False, "message": "bloqueando duplicado de imágenes"},
        )

        mock_state = {"conversation_id": "conv-4", "mode_context": {}}

        with patch("agent.state.helpers.get_current_state", return_value=mock_state):
            with patch.object(mode, "_log_tool_call", new_callable=AsyncMock) as mock_log:
                await mode._execute_and_log_tool(
                    conversation_id="conv-4",
                    tool_name="my_tool",
                    tool_args={"param1": "hello"},
                    tools=[tool],
                    iteration=1,
                )

        kwargs = mock_log.call_args[1]
        assert kwargs["result_type"] == "blocked"
        assert kwargs["error_message"] is None


# =============================================================================
# Task 3.2 — _log_tool_call passes through to service
# =============================================================================


class TestLogToolCallPassthrough:
    """
    Verify _log_tool_call correctly passes result_type and error_message
    through to the tool_logging_service.log_tool_call function.
    """

    @pytest.mark.asyncio
    async def test_log_tool_call_passes_result_type_to_service(self):
        """_log_tool_call must forward result_type to log_tool_call service."""
        mode = _DummyModeNode()

        with patch(
            "agent.services.tool_logging_service.log_tool_call",
            new_callable=AsyncMock,
        ) as mock_service:
            await mode._log_tool_call(
                conversation_id="conv-10",
                tool_name="test_tool",
                parameters={"a": 1},
                result_summary="ok",
                execution_time_ms=42,
                iteration=1,
                result_type="error",
                error_message="Something went wrong",
            )

        assert mock_service.called
        kwargs = mock_service.call_args[1]
        assert kwargs["result_type"] == "error"
        assert kwargs["error_message"] == "Something went wrong"

    @pytest.mark.asyncio
    async def test_log_tool_call_default_result_type_is_success(self):
        """_log_tool_call defaults result_type='success' for backward compat."""
        mode = _DummyModeNode()

        with patch(
            "agent.services.tool_logging_service.log_tool_call",
            new_callable=AsyncMock,
        ) as mock_service:
            await mode._log_tool_call(
                conversation_id="conv-11",
                tool_name="test_tool",
                parameters={},
                result_summary="all good",
            )

        kwargs = mock_service.call_args[1]
        assert kwargs["result_type"] == "success"
        assert kwargs["error_message"] is None

    @pytest.mark.asyncio
    async def test_log_tool_call_never_raises_on_service_error(self):
        """_log_tool_call swallows exceptions — never blocks the agent."""
        mode = _DummyModeNode()

        with patch(
            "agent.services.tool_logging_service.log_tool_call",
            new_callable=AsyncMock,
            side_effect=Exception("DB connection lost"),
        ):
            # Must not raise
            await mode._log_tool_call(
                conversation_id="conv-12",
                tool_name="test_tool",
                parameters={},
                result_summary="data",
                result_type="success",
            )
