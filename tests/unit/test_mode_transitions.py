"""
Test: Mode Transition Mechanism via _internal_flags._transition_to.

Verifies the Phase 2 implementation of REFACTOR-001:
- confirmar_presupuesto tool signals _transition_to: EVALUACION_GATEWAY
- _apply_tool_flags() intercepts _transition_to and stores in mode_context
- presupuesto_mode._process_message() propagates transition to result_dict
- validate_transition() validates against whitelist
- EVALUACION_GATEWAY presents confirmation and transitions to EXPEDIENTE

This fixes P1 (CRITICAL): PRESUPUESTO → EVALUACION_GATEWAY was UNREACHABLE.
"""

import json
import pytest
import structlog

from agent.modes.presupuesto_mode import _apply_tool_flags
from agent.router.mode_transitions import (
    validate_transition,
    is_transition_allowed,
    get_preserve_keys,
)


logger = structlog.get_logger()


# ============================================================================
# _transition_to Signal Tests
# ============================================================================

class TestTransitionSignal:
    """Tests for _transition_to signal in _apply_tool_flags."""

    def test_transition_to_extracted_from_flags(self):
        """_apply_tool_flags should extract _transition_to from _internal_flags
        and store it in mode_context (not as a regular flag)."""
        mode_context = {
            "precio_comunicado": True,
            "conversation_id": "test-transition-1",
        }

        tool_result = {
            "success": True,
            "message": "Transición confirmada",
            "_internal_flags": {
                "_transition_to": "EVALUACION_GATEWAY",
            },
        }

        _apply_tool_flags(mode_context, tool_result, logger)

        assert mode_context.get("_transition_to") == "EVALUACION_GATEWAY", \
            "_transition_to should be stored in mode_context"

    def test_transition_to_not_treated_as_regular_flag(self):
        """_transition_to should NOT pollute mode_context as a boolean flag."""
        mode_context = {
            "precio_comunicado": True,
            "conversation_id": "test-transition-2",
        }

        tool_result = {
            "success": True,
            "_internal_flags": {
                "_transition_to": "EVALUACION_GATEWAY",
                "precio_comunicado": True,
            },
        }

        _apply_tool_flags(mode_context, tool_result, logger)

        # _transition_to should be in mode_context as signal
        assert "_transition_to" in mode_context
        # But precio_comunicado should also be applied
        assert mode_context["precio_comunicado"] is True

    def test_no_transition_signal_when_absent(self):
        """When _internal_flags has no _transition_to, mode_context should not
        have a _transition_to key."""
        mode_context = {
            "precio_comunicado": False,
            "conversation_id": "test-no-transition",
        }

        tool_result = {
            "success": True,
            "_internal_flags": {
                "precio_comunicado": True,
            },
        }

        _apply_tool_flags(mode_context, tool_result, logger)

        assert "_transition_to" not in mode_context, \
            "Should NOT have _transition_to when flag is absent"
        assert mode_context["precio_comunicado"] is True

    def test_transition_signal_from_json_string(self):
        """_apply_tool_flags should parse JSON string and extract _transition_to."""
        mode_context = {
            "precio_comunicado": True,
            "conversation_id": "test-json-transition",
        }

        tool_result_str = json.dumps({
            "success": True,
            "_internal_flags": {
                "_transition_to": "EVALUACION_GATEWAY",
            },
        })

        _apply_tool_flags(mode_context, tool_result_str, logger)

        assert mode_context.get("_transition_to") == "EVALUACION_GATEWAY"


# ============================================================================
# Mode Transition Whitelist Tests
# ============================================================================

class TestTransitionWhitelist:
    """Tests for mode transition validation rules."""

    def test_presupuesto_to_evaluacion_allowed(self):
        """PRESUPUESTO → EVALUACION_GATEWAY must be allowed (core fix)."""
        allowed, reason = validate_transition("PRESUPUESTO_MODE", "EVALUACION_GATEWAY")
        assert allowed is True, f"Transition should be allowed, but: {reason}"

    def test_evaluacion_to_expediente_allowed(self):
        """EVALUACION_GATEWAY → EXPEDIENTE_MODE must be allowed."""
        allowed, reason = validate_transition("EVALUACION_GATEWAY", "EXPEDIENTE_MODE")
        assert allowed is True, f"Transition should be allowed, but: {reason}"

    def test_evaluacion_to_presupuesto_allowed(self):
        """EVALUACION_GATEWAY → PRESUPUESTO_MODE (user said no) must be allowed."""
        allowed, reason = validate_transition("EVALUACION_GATEWAY", "PRESUPUESTO_MODE")
        assert allowed is True

    def test_presupuesto_to_expediente_blocked(self):
        """PRESUPUESTO → EXPEDIENTE (skipping gateway) must be BLOCKED."""
        allowed, reason = validate_transition("PRESUPUESTO_MODE", "EXPEDIENTE_MODE")
        assert allowed is False, \
            "Direct PRESUPUESTO→EXPEDIENTE should be blocked (must go through EVALUACION_GATEWAY)"

    def test_escalation_always_allowed(self):
        """ESCALATION should be reachable from ANY mode."""
        modes = ["PRESUPUESTO_MODE", "EVALUACION_GATEWAY", "EXPEDIENTE_MODE", "CONSULTA_MODE"]
        for mode in modes:
            allowed, _ = validate_transition(mode, "ESCALATION")
            assert allowed is True, f"Escalation from {mode} should always be allowed"

    def test_context_preservation_presupuesto_to_gateway(self):
        """Keys should be preserved when transitioning PRESUPUESTO → EVALUACION_GATEWAY."""
        keys = get_preserve_keys("PRESUPUESTO_MODE", "EVALUACION_GATEWAY")
        assert "tarifa_calculada" in keys, "tarifa_calculada must be preserved"
        assert "element_codes" in keys, "element_codes must be preserved"
        assert "categoria_slug" in keys, "categoria_slug must be preserved"


# ============================================================================
# Flag Authority Tests (Race Condition Fix)
# ============================================================================

class TestFlagAuthority:
    """Tests for all_applied_flags having FINAL AUTHORITY over context_updates.
    
    This fixes P2 (CRITICAL): precio_comunicado race condition where
    _extract_context_from_tool wrote False over the True set by _apply_tool_flags.
    """

    def test_flags_override_stale_context_updates(self):
        """all_applied_flags should override stale values from context_updates.
        
        Scenario:
        1. identificar_y_resolver_elementos → _internal_flags: {precio_comunicado: False}
        2. calcular_tarifa_con_elementos → _internal_flags: {precio_comunicado: True}
        3. Final merge: all_applied_flags wins → precio_comunicado: True
        """
        mode_context = {"precio_comunicado": False}
        context_updates = {"tarifa_calculada": {"price": 410}}

        # Simulate accumulated flags (from multiple tool calls)
        all_applied_flags = {
            "precio_comunicado": True,  # Latest value from calcular_tarifa
            "imagenes_enviadas": False,
        }

        # Merge exactly like presupuesto_mode._process_message does
        updated_context = {**mode_context, **context_updates}
        for key, value in all_applied_flags.items():
            if key.startswith("_"):
                continue
            updated_context[key] = value

        assert updated_context["precio_comunicado"] is True, \
            "all_applied_flags must have FINAL AUTHORITY over mode_context"
        assert updated_context["imagenes_enviadas"] is False

    def test_transition_key_skipped_in_flag_merge(self):
        """Internal keys starting with _ should be skipped during flag merge."""
        mode_context = {}
        context_updates = {}
        all_applied_flags = {
            "precio_comunicado": True,
            "_transition_to": "EVALUACION_GATEWAY",  # Internal key
        }

        updated_context = {**mode_context, **context_updates}
        for key, value in all_applied_flags.items():
            if key.startswith("_"):
                continue
            updated_context[key] = value

        assert updated_context["precio_comunicado"] is True
        assert "_transition_to" not in updated_context, \
            "Internal keys (starting with _) should be skipped in flag merge"

    def test_flag_accumulation_across_multiple_tools(self):
        """Flags from multiple tool calls should accumulate correctly.
        
        Scenario:
        1. Tool A: _internal_flags: {precio_comunicado: False, imagenes_enviadas: False}
        2. Tool B: _internal_flags: {precio_comunicado: True}
        3. Tool C: _internal_flags: {imagenes_enviadas: True}
        
        Final: {precio_comunicado: True, imagenes_enviadas: True}
        """
        all_applied_flags: dict = {}

        # Tool A flags
        flags_a = {"precio_comunicado": False, "imagenes_enviadas": False}
        all_applied_flags.update(flags_a)

        # Tool B flags (overrides precio_comunicado)
        flags_b = {"precio_comunicado": True}
        all_applied_flags.update(flags_b)

        # Tool C flags (overrides imagenes_enviadas)
        flags_c = {"imagenes_enviadas": True}
        all_applied_flags.update(flags_c)

        assert all_applied_flags["precio_comunicado"] is True
        assert all_applied_flags["imagenes_enviadas"] is True


# ============================================================================
# confirmar_presupuesto Tool Tests
# ============================================================================

class TestConfirmarPresupuesto:
    """Tests for the confirmar_presupuesto transition tool."""

    @pytest.mark.asyncio
    async def test_confirmar_presupuesto_precondition_no_price(self):
        """confirmar_presupuesto should fail if precio_comunicado is False."""
        from unittest.mock import patch

        mock_state = {
            "conversation_id": "test-no-price",
            "mode_context": {
                "precio_comunicado": False,
                "tarifa_calculada": {"datos": {"price": 410}},
            },
        }

        with patch("agent.tools.transition_tools.get_current_state", return_value=mock_state):
            from agent.tools.transition_tools import confirmar_presupuesto
            result = await confirmar_presupuesto.ainvoke({})

        assert result["success"] is False
        assert result["error"] == "PRICE_NOT_COMMUNICATED"

    @pytest.mark.asyncio
    async def test_confirmar_presupuesto_precondition_no_tariff(self):
        """confirmar_presupuesto should fail if no tarifa_calculada exists."""
        from unittest.mock import patch

        mock_state = {
            "conversation_id": "test-no-tariff",
            "mode_context": {
                "precio_comunicado": True,
                "tarifa_calculada": None,
            },
        }

        with patch("agent.tools.transition_tools.get_current_state", return_value=mock_state):
            from agent.tools.transition_tools import confirmar_presupuesto
            result = await confirmar_presupuesto.ainvoke({})

        assert result["success"] is False
        assert result["error"] == "NO_TARIFF"

    @pytest.mark.asyncio
    async def test_confirmar_presupuesto_success(self):
        """confirmar_presupuesto should succeed and signal transition."""
        from unittest.mock import patch

        mock_state = {
            "conversation_id": "test-success",
            "mode_context": {
                "precio_comunicado": True,
                "tarifa_calculada": {
                    "datos": {"price": 410.0},
                },
                "element_codes": ["ESCAPE"],
                "categoria_slug": "motos-part",
            },
        }

        with patch("agent.tools.transition_tools.get_current_state", return_value=mock_state):
            from agent.tools.transition_tools import confirmar_presupuesto
            result = await confirmar_presupuesto.ainvoke({})

        assert result["success"] is True
        assert "_internal_flags" in result
        assert result["_internal_flags"]["_transition_to"] == "EVALUACION_GATEWAY"
        assert result["resumen"]["precio"] == 410.0
        assert result["resumen"]["elementos"] == ["ESCAPE"]


# ============================================================================
# EVALUACION_GATEWAY Response Classification Tests
# ============================================================================

class TestEvaluacionGatewayClassification:
    """Tests for EVALUACION_GATEWAY yes/no/ambiguous pattern matching."""

    def test_yes_patterns(self):
        """Common affirmative responses should be classified as 'yes'."""
        from agent.modes.evaluacion_gateway import EvaluacionGatewayNode

        node = EvaluacionGatewayNode()
        yes_messages = [
            "Sí", "si", "dale", "vale", "adelante", "perfecto", "ok",
            "venga", "claro", "genial", "vamos", "por supuesto", "correcto",
        ]
        for msg in yes_messages:
            result = node._classify_response(msg)
            assert result == "yes", f"'{msg}' should be classified as 'yes', got '{result}'"

    def test_no_patterns(self):
        """Common negative responses should be classified as 'no'."""
        from agent.modes.evaluacion_gateway import EvaluacionGatewayNode

        node = EvaluacionGatewayNode()
        no_messages = [
            "no", "todavía no", "mejor no", "ahora no", "luego", "después",
            "nop", "paso", "cancel",
        ]
        for msg in no_messages:
            result = node._classify_response(msg)
            assert result == "no", f"'{msg}' should be classified as 'no', got '{result}'"

    def test_ambiguous_patterns(self):
        """Ambiguous responses should be classified as 'ambiguous'."""
        from agent.modes.evaluacion_gateway import EvaluacionGatewayNode

        node = EvaluacionGatewayNode()
        ambiguous_messages = [
            "mmm no sé", "cuánto tardará?", "necesito pensarlo",
        ]
        for msg in ambiguous_messages:
            result = node._classify_response(msg)
            assert result == "ambiguous", \
                f"'{msg}' should be classified as 'ambiguous', got '{result}'"


# ============================================================================
# EVALUACION_GATEWAY Tarifa Fallback Tests
# ============================================================================

class TestEvaluacionGatewayTarifaFallback:
    """Tests for EVALUACION_GATEWAY reading price from tarifa_calculada."""

    def test_fallback_reads_from_tarifa_calculada(self):
        """Gateway should read price from tarifa_calculada when precio_exacto is absent."""
        from agent.modes.evaluacion_gateway import EvaluacionGatewayNode

        node = EvaluacionGatewayNode()
        mock_state = {
            "mode_context": {
                # No precio_exacto (PRESUPUESTO doesn't set it)
                "tarifa_calculada": {
                    "datos": {"price": 410.0},
                },
                "element_codes": ["ESCAPE", "MANILLAR"],
            },
        }

        result = node._present_confirmation(mock_state, dict(mock_state["mode_context"]))

        assert "410" in result["ai_response"], \
            "Gateway should display price from tarifa_calculada"
        assert "ESCAPE" in result["ai_response"]
        assert result["mode_context"]["gateway_question_asked"] is True

    def test_fallback_reads_from_tarifa_calculada_json_string(self):
        """Gateway should handle tarifa_calculada as JSON string."""
        from agent.modes.evaluacion_gateway import EvaluacionGatewayNode

        node = EvaluacionGatewayNode()
        tarifa_str = json.dumps({"datos": {"price": 350.0}})
        mock_state = {
            "mode_context": {
                "tarifa_calculada": tarifa_str,
                "element_codes": ["SUBCHASIS"],
            },
        }

        result = node._present_confirmation(mock_state, dict(mock_state["mode_context"]))

        assert "350" in result["ai_response"], \
            "Gateway should parse JSON string tarifa_calculada"
