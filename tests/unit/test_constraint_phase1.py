"""
Constraint System Refactor — Phase 1 Tests.

Tests for:
1A. Fast-path break on transition signal (_transition_to)
1B. Current mode_context passed to constraint validation (stale state fix)

These tests are PURE UNIT TESTS — no DB, no Redis, no LLM, no network.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.services.constraint_service import (
    _should_skip_constraint,
    validate_response,
)


# ============================================================================
# Phase 1A: Fast-path break tests (via _apply_tool_flags)
# ============================================================================


class TestFastPathBreak:
    """Test that _apply_tool_flags correctly sets _transition_to in mode_context."""

    def test_apply_tool_flags_sets_transition(self):
        """When a tool returns _transition_to, it should be set in mode_context."""
        from agent.modes.presupuesto_mode import _apply_tool_flags

        mode_context = {"conversation_id": "test"}
        tool_result = {
            "success": True,
            "message": "Perfecto, vamos a abrir tu expediente.",
            "_internal_flags": {
                "_transition_to": "EXPEDIENTE_MODE",
                "presupuesto_confirmado": True,
            },
        }

        logger_mock = MagicMock()
        _apply_tool_flags(mode_context, tool_result, logger_mock)

        assert mode_context["_transition_to"] == "EXPEDIENTE_MODE"
        assert mode_context["presupuesto_confirmado"] is True

    def test_apply_tool_flags_no_transition(self):
        """When tool has no _transition_to, mode_context should not have it."""
        from agent.modes.presupuesto_mode import _apply_tool_flags

        mode_context = {"conversation_id": "test"}
        tool_result = {
            "success": True,
            "message": "Precio calculado.",
            "_internal_flags": {
                "precio_comunicado": True,
            },
        }

        logger_mock = MagicMock()
        _apply_tool_flags(mode_context, tool_result, logger_mock)

        assert "_transition_to" not in mode_context
        assert mode_context["precio_comunicado"] is True

    def test_apply_tool_flags_from_json_string(self):
        """_apply_tool_flags should handle JSON string input (real production case)."""
        from agent.modes.presupuesto_mode import _apply_tool_flags

        mode_context = {"conversation_id": "test"}
        tool_result_str = json.dumps(
            {
                "success": True,
                "message": "Expediente finalizado.",
                "_internal_flags": {
                    "_transition_to": "COMPLETED",
                },
            }
        )

        logger_mock = MagicMock()
        _apply_tool_flags(mode_context, tool_result_str, logger_mock)

        assert mode_context["_transition_to"] == "COMPLETED"

    def test_transition_signal_causes_break_in_presupuesto_loop(self):
        """
        Verify the fast-path break logic pattern:
        After _apply_tool_flags sets _transition_to, the check
        `if mode_context.get("_transition_to")` should be True.
        """
        from agent.modes.presupuesto_mode import _apply_tool_flags

        mode_context = {"conversation_id": "test"}
        tool_result = {
            "success": True,
            "message": "Perfecto, vamos con el expediente.",
            "_internal_flags": {
                "_transition_to": "EXPEDIENTE_MODE",
            },
        }

        logger_mock = MagicMock()
        _apply_tool_flags(mode_context, tool_result, logger_mock)

        # This is the condition that triggers the fast-path break
        assert mode_context.get("_transition_to") is not None
        assert mode_context.get("_transition_to") == "EXPEDIENTE_MODE"

        # The tool's message should be usable as ai_response
        assert tool_result["message"] == "Perfecto, vamos con el expediente."

    def test_transition_message_extraction_from_tool(self):
        """Test extracting the transition message from different tool result formats."""
        # Format 1: "message" key
        result1 = {"success": True, "message": "Vamos al gateway."}
        assert (
            result1.get("message", "")
            or result1.get("texto", "") == "Vamos al gateway."
        )

        # Format 2: "texto" key (some tools use this)
        result2 = {"success": True, "texto": "Expediente listo."}
        assert (
            result2.get("message", "")
            or result2.get("texto", "") == "Expediente listo."
        )

        # Format 3: neither key → empty string (LLM would have generated something)
        result3 = {"success": True}
        extracted = result3.get("message", "") or result3.get("texto", "")
        assert extracted == ""


# ============================================================================
# Phase 1B: Stale state fix tests
# ============================================================================


class TestStaleStateFix:
    """Test that _should_skip_constraint uses current mode_context, not stale state."""

    def test_skip_price_constraint_when_tarifa_calculated_this_turn(self):
        """
        Key scenario: tarifa was calculated in THIS turn.
        mode_context has tarifa_calculada, but old state didn't.
        Should skip price_requires_tool.
        """
        # Current turn's mode_context (has tarifa_calculada)
        current_context = {
            "tarifa_calculada": {"datos": {"price": 410.0}},
            "precio_comunicado": True,
        }

        assert _should_skip_constraint("price_requires_tool", current_context) is True

    def test_no_skip_price_constraint_when_no_tarifa(self):
        """No tarifa calculated → should NOT skip price_requires_tool."""
        context = {"tarifa_calculada": None}
        assert _should_skip_constraint("price_requires_tool", context) is False

    def test_no_skip_price_constraint_with_empty_context(self):
        """Empty context → should NOT skip."""
        assert _should_skip_constraint("price_requires_tool", {}) is False
        assert _should_skip_constraint("price_requires_tool", None) is False

    def test_skip_price_in_expediente_with_tariff(self):
        """In expediente sub-mode with tariff → should skip."""
        context = {
            "expediente_sub_mode": "collect_personal",
            "tariff_amount": 410.0,
        }
        assert _should_skip_constraint("price_requires_tool", context) is True

    def test_skip_price_when_presupuesto_done(self):
        """Presupuesto completed → should skip."""
        context = {"presupuesto_completado": True}
        assert _should_skip_constraint("price_requires_tool", context) is True

    def test_no_skip_other_constraints(self):
        """Non-price constraints should never be skipped by this logic."""
        context = {"tarifa_calculada": {"datos": {"price": 410.0}}}
        assert _should_skip_constraint("images_narration_blocked", context) is False
        assert _should_skip_constraint("variant_requires_tool", context) is False
        assert _should_skip_constraint("docs_from_tool_only", context) is False


class TestImagesNarrationSkip:
    """
    BUG #1 regression: images_narration_blocked constraint must be skipped
    when imagenes_enviadas=True in fsm_state.

    Design ref: sdd/fix-finalize-lock-image-flow/design (FIX 2)
    Spec ref:   sdd/fix-finalize-lock-image-flow/spec (REQ-2)

    RED: All 3 tests fail before the fix is applied to constraint_service.py.
    GREEN: Passes after the `if constraint_type == "images_narration_blocked"` block
           is added before the final `return False` (~L192).
    """

    def test_images_narration_blocked_skipped_when_imagenes_enviadas_true(self):
        """
        When imagenes_enviadas=True, the images_narration_blocked constraint
        MUST be skipped — the constraint's purpose (prevent narrating image
        sending without calling the tool) is already fulfilled.

        RED: Fails before fix — no skip condition exists for this constraint.
        """
        state = {"imagenes_enviadas": True}
        result = _should_skip_constraint("images_narration_blocked", state)
        assert result is True, (
            "_should_skip_constraint('images_narration_blocked', {'imagenes_enviadas': True}) "
            "must return True when imagenes_enviadas is truthy. "
            "FIX: Add `if constraint_type == 'images_narration_blocked': "
            "if fsm_state.get('imagenes_enviadas'): return True` "
            "before the final `return False` in constraint_service.py ~L192."
        )

    def test_images_narration_blocked_not_skipped_when_imagenes_enviadas_false(self):
        """
        When imagenes_enviadas=False, the images_narration_blocked constraint
        MUST NOT be skipped — images haven't been sent yet, constraint must enforce.

        This is existing correct behavior — test ensures it doesn't regress.
        """
        state = {"imagenes_enviadas": False}
        result = _should_skip_constraint("images_narration_blocked", state)
        assert result is False, (
            "_should_skip_constraint('images_narration_blocked', {'imagenes_enviadas': False}) "
            "must return False when imagenes_enviadas is falsy."
        )

    def test_images_narration_blocked_not_skipped_when_key_missing(self):
        """
        When imagenes_enviadas key is absent from fsm_state, the constraint
        MUST NOT be skipped — backward compatibility with state that lacks the key.

        This is existing correct behavior — test ensures it doesn't regress.
        """
        state = {}
        result = _should_skip_constraint("images_narration_blocked", state)
        assert result is False, (
            "_should_skip_constraint('images_narration_blocked', {}) "
            "must return False when imagenes_enviadas key is missing from state."
        )


class TestValidateResponseWithContext:
    """Test validate_response with fsm_state parameter (the actual integration point)."""

    def test_price_regex_matches_but_skipped_by_context(self):
        """
        Regex matches price mention, but fsm_state has tarifa_calculada
        → constraint should be SKIPPED → response is VALID.
        """
        constraints = [
            {
                "constraint_type": "price_requires_tool",
                "detection_pattern": r"\d+\s*€|\d+\s*EUR|presupuesto.*\d+|\d+.*\+\s*IVA",
                "required_tool": "calcular_tarifa_con_elementos",
                "error_injection": "Debes calcular el precio con la herramienta.",
                "priority": 100,
            }
        ]

        # Response mentions price (regex WILL match)
        response = "Tu presupuesto es de 410€ +IVA."
        tools_called = set()  # No tools called this turn

        # But context says tarifa was already calculated
        fsm_state = {"tarifa_calculada": {"datos": {"price": 410.0}}}

        is_valid, error = validate_response(
            response, tools_called, constraints, fsm_state
        )
        assert is_valid is True
        assert error is None

    def test_price_regex_matches_and_triggers_without_context(self):
        """
        Regex matches price mention, no context has tarifa →
        constraint FIRES → response is INVALID.
        """
        constraints = [
            {
                "constraint_type": "price_requires_tool",
                "detection_pattern": r"\d+\s*€|\d+\s*EUR|presupuesto.*\d+|\d+.*\+\s*IVA",
                "required_tool": "calcular_tarifa_con_elementos",
                "error_injection": "Debes calcular el precio con la herramienta.",
                "priority": 100,
            }
        ]

        response = "El precio es 500€ +IVA."
        tools_called = set()
        fsm_state = {}  # No tarifa in context

        is_valid, error = validate_response(
            response, tools_called, constraints, fsm_state
        )
        assert is_valid is False
        assert error == "Debes calcular el precio con la herramienta."

    def test_price_regex_matches_but_tool_was_called(self):
        """
        Regex matches AND tool was called → VALID (tool provides legitimacy).
        """
        constraints = [
            {
                "constraint_type": "price_requires_tool",
                "detection_pattern": r"\d+\s*€|\d+\s*EUR|presupuesto.*\d+|\d+.*\+\s*IVA",
                "required_tool": "calcular_tarifa_con_elementos",
                "error_injection": "Debes calcular el precio con la herramienta.",
                "priority": 100,
            }
        ]

        response = "El presupuesto es 410€ +IVA."
        tools_called = {"calcular_tarifa_con_elementos"}

        is_valid, error = validate_response(response, tools_called, constraints)
        assert is_valid is True
        assert error is None

    def test_no_regex_match_always_valid(self):
        """When regex doesn't match at all, response is always valid."""
        constraints = [
            {
                "constraint_type": "price_requires_tool",
                "detection_pattern": r"\d+\s*€|\d+\s*EUR|presupuesto.*\d+|\d+.*\+\s*IVA",
                "required_tool": "calcular_tarifa_con_elementos",
                "error_injection": "Debes calcular el precio con la herramienta.",
                "priority": 100,
            }
        ]

        response = "Hola, ¿en qué puedo ayudarte?"
        tools_called = set()

        is_valid, error = validate_response(response, tools_called, constraints)
        assert is_valid is True

    def test_multiple_constraints_first_violation_wins(self):
        """With multiple constraints, the first violation (by priority) wins."""
        constraints = [
            {
                "constraint_type": "price_requires_tool",
                "detection_pattern": r"\d+\s*€",
                "required_tool": "calcular_tarifa_con_elementos",
                "error_injection": "Error precio.",
                "priority": 100,
            },
            {
                "constraint_type": "images_narration_blocked",
                "detection_pattern": r"imagenes.*se.*enviar",
                "required_tool": "enviar_imagenes_ejemplo",
                "error_injection": "Error imagenes.",
                "priority": 95,
            },
        ]

        response = "El precio es 410€. Las imagenes se enviarán ahora."
        tools_called = set()

        is_valid, error = validate_response(response, tools_called, constraints)
        assert is_valid is False
        assert error == "Error precio."  # Higher priority wins

    def test_empty_constraints_always_valid(self):
        """No constraints loaded → always valid."""
        is_valid, error = validate_response("anything", set(), [])
        assert is_valid is True

    def test_empty_response_always_valid(self):
        """Empty response → always valid."""
        constraints = [
            {
                "constraint_type": "price_requires_tool",
                "detection_pattern": r"\d+\s*€",
                "required_tool": "calcular_tarifa_con_elementos",
                "error_injection": "Error.",
                "priority": 100,
            }
        ]
        is_valid, error = validate_response("", set(), constraints)
        assert is_valid is True
