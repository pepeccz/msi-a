"""
Unit tests for _parse_tool_result in presupuesto_mode.py.

Covers VARIANT-COMBINED-2: PRESUPUESTO_MODE must NOT raise JSONDecodeError
when calcular_tarifa_con_elementos (or any tool) returns plain-text output.

Scenarios tested:
1. Valid JSON string          → parsed dict, unchanged behaviour
2. Plain-text error string    → safe fallback dict, no exception
3. Empty string               → safe fallback dict, no exception
4. Already a dict             → returned as-is, no copy
5. Non-dict valid JSON        → safe fallback dict
6. _apply_tool_flags with plain-text → no crash, no flags applied
7. _parse_tool_result + downstream calcular_tarifa guard → success=False, no crash
"""

import json
import pytest

from agent.modes.presupuesto_mode import _parse_tool_result, _apply_tool_flags


# =============================================================================
# Task 1.1 / 1.3: _parse_tool_result helper
# =============================================================================


class TestParseToolResult:
    """Tests for the _parse_tool_result helper function."""

    # ------------------------------------------------------------------
    # 1. Valid JSON string → parsed dict (happy path, unchanged behaviour)
    # ------------------------------------------------------------------

    def test_valid_json_string_returns_parsed_dict(self):
        """Valid JSON string is parsed into a dict — existing behaviour preserved."""
        payload = {
            "success": True,
            "precio_final": 410.0,
            "elementos": ["ESCAPE"],
        }
        result = _parse_tool_result(json.dumps(payload), "calcular_tarifa_con_elementos")

        assert result == payload
        assert result["success"] is True
        assert result["precio_final"] == 410.0

    def test_valid_json_with_internal_flags_preserved(self):
        """_internal_flags survive the round-trip through the helper."""
        payload = {
            "success": True,
            "precio_final": 350.0,
            "_internal_flags": {
                "precio_comunicado": True,
                "imagenes_enviadas": False,
            },
        }
        result = _parse_tool_result(json.dumps(payload), "calcular_tarifa_con_elementos")

        assert result["_internal_flags"]["precio_comunicado"] is True

    # ------------------------------------------------------------------
    # 2. Plain-text error string → safe fallback, no JSONDecodeError
    # ------------------------------------------------------------------

    def test_plain_text_error_does_not_raise(self):
        """Plain-text tool output must NOT raise JSONDecodeError (VARIANT-COMBINED-2)."""
        plain_error = "Error: No se encontró la categoría 'motos-part' en la base de datos."

        # This must never raise
        result = _parse_tool_result(plain_error, "calcular_tarifa_con_elementos")

        assert isinstance(result, dict)
        assert result["success"] is False

    def test_plain_text_error_preserves_original_text(self):
        """The original plain-text error is stored so the LLM can surface it."""
        plain_error = "Tariff service unavailable"

        result = _parse_tool_result(plain_error, "calcular_tarifa_con_elementos")

        assert result["error"] == plain_error
        assert result["raw_message"] == plain_error

    def test_plain_text_error_has_result_format_marker(self):
        """result_format='plain_text' is set so callers can distinguish from JSON errors."""
        result = _parse_tool_result("some error message", "any_tool")

        assert result.get("result_format") == "plain_text"

    # ------------------------------------------------------------------
    # 3. Empty string → safe fallback dict, no exception
    # ------------------------------------------------------------------

    def test_empty_string_returns_safe_fallback(self):
        """Empty string must not raise and must return a valid error dict."""
        result = _parse_tool_result("", "calcular_tarifa_con_elementos")

        assert isinstance(result, dict)
        assert result["success"] is False
        assert result["error"] == "empty_result"

    def test_whitespace_only_string_treated_as_empty(self):
        """A whitespace-only string is treated as empty."""
        result = _parse_tool_result("   \n\t  ", "calcular_tarifa_con_elementos")

        assert result["error"] == "empty_result"

    def test_empty_fallback_has_spanish_user_message(self):
        """Empty-string fallback includes a user-facing Spanish message."""
        result = _parse_tool_result("", "calcular_tarifa_con_elementos")

        assert "message" in result
        assert result["message"]  # non-empty

    # ------------------------------------------------------------------
    # 4. Already a dict → returned as-is
    # ------------------------------------------------------------------

    def test_dict_is_returned_unchanged(self):
        """A dict input is returned as-is without copying or mutation."""
        payload = {"success": True, "precio_final": 200.0}
        result = _parse_tool_result(payload, "calcular_tarifa_con_elementos")

        assert result is payload  # same object

    # ------------------------------------------------------------------
    # 5. Non-dict valid JSON (e.g. a bare list or number)
    # ------------------------------------------------------------------

    def test_json_array_returns_safe_fallback(self):
        """JSON arrays are not valid tool-result dicts; treated as errors."""
        result = _parse_tool_result(json.dumps([1, 2, 3]), "some_tool")

        assert isinstance(result, dict)
        assert result["success"] is False

    def test_json_number_returns_safe_fallback(self):
        """A bare JSON number is not a valid tool dict; treated as error."""
        result = _parse_tool_result("42", "some_tool")

        assert isinstance(result, dict)
        assert result["success"] is False


# =============================================================================
# Task 1.2 / 1.3: Integration with _apply_tool_flags
# =============================================================================


class TestApplyToolFlagsWithPlainText:
    """
    Ensures that _apply_tool_flags (which calls json.loads internally) also
    handles plain text safely — and that the _parse_tool_result → _apply_tool_flags
    chain never crashes.
    """

    def test_apply_tool_flags_with_plain_text_does_not_crash(self):
        """_apply_tool_flags must not crash when given a plain-text string."""
        from unittest.mock import MagicMock
        logger = MagicMock()
        mode_context: dict = {}
        plain_error = "service error: timeout connecting to tariff DB"

        # Must not raise
        _apply_tool_flags(mode_context, plain_error, logger)

        # mode_context untouched — no flags applied
        assert mode_context == {}

    def test_apply_tool_flags_with_parsed_error_dict_does_not_crash(self):
        """_apply_tool_flags with a pre-parsed error dict (no _internal_flags) is a no-op."""
        from unittest.mock import MagicMock
        logger = MagicMock()
        mode_context: dict = {}

        error_dict = _parse_tool_result("plain error text", "calcular_tarifa_con_elementos")
        _apply_tool_flags(mode_context, error_dict, logger)

        assert mode_context == {}


# =============================================================================
# Task 1.3: Downstream calcular_tarifa guard correctness
# =============================================================================


class TestCalcularTarifaGuardWithErrorResult:
    """
    Validates that the ``calcular_tarifa_con_elementos`` success guard
    (which sets _tarifa_called_this_turn) stays False when the tool returns
    a plain-text error — exactly the scenario in VARIANT-COMBINED-2.
    """

    def test_calcular_tarifa_plain_text_error_success_is_false(self):
        """Plain-text tool output → success=False → tarifa guard never triggers."""
        plain_error = "Error interno del servicio de tarifas"
        result_dict = _parse_tool_result(plain_error, "calcular_tarifa_con_elementos")

        # This is the exact guard condition from presupuesto_mode.py ~line 744-748
        tarifa_guard_triggered = (
            isinstance(result_dict, dict)
            and result_dict.get("success")
        )
        assert tarifa_guard_triggered is False

    def test_calcular_tarifa_valid_json_success_triggers_guard(self):
        """Valid JSON with success=True → tarifa guard triggers as before."""
        valid_result = json.dumps({"success": True, "precio_final": 410.0})
        result_dict = _parse_tool_result(valid_result, "calcular_tarifa_con_elementos")

        tarifa_guard_triggered = (
            isinstance(result_dict, dict)
            and result_dict.get("success")
        )
        assert tarifa_guard_triggered is True
