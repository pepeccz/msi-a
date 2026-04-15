"""
Unit tests for PRE_EXPEDIENTE_MODE routing and compat shim.

Covers:
1. route_to_mode() compat shim — legacy CONSULTA_MODE / PRESUPUESTO_MODE
2. route_to_mode() normal routing — PRE_EXPEDIENTE_MODE
3. _resolve_target_mode() intent routing
   - CONFIRMACION with prev=PRE_EXPEDIENTE_MODE → EXPEDIENTE_MODE
   - CONFIRMACION with prev=PRESUPUESTO_MODE (compat) → EXPEDIENTE_MODE
   - RECHAZO → PRE_EXPEDIENTE_MODE
4. INTENT_TO_MODE mapping verification for CONSULTA_GENERAL

All tests are pure unit tests — no DB, no Redis, no LLM.
"""

import pytest
from unittest.mock import MagicMock

from agent.graph.conversation_graph import (
    route_to_mode,
    NODE_PRE_EXPEDIENTE,
    NODE_EXPEDIENTE,
    NODE_ESCALATION,
    _resolve_target_mode,
)
from agent.router.intent_router import (
    INTENT_TO_MODE,
    UserIntent,
    IntentResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_intent_result(intent: UserIntent, suggested_mode: str = "", confidence: float = 0.9) -> IntentResult:
    return IntentResult(
        intent=intent,
        confidence=confidence,
        suggested_mode=suggested_mode,
    )


def _make_state(current_mode: str, previous_mode: str | None = None) -> dict:
    state: dict = {"current_mode": current_mode}
    if previous_mode is not None:
        state["previous_mode"] = previous_mode
    return state


# ---------------------------------------------------------------------------
# route_to_mode — compat shim
# ---------------------------------------------------------------------------


class TestCompatShim:
    """Legacy mode strings must map transparently to PRE_EXPEDIENTE node."""

    def test_compat_shim_consulta(self):
        state = _make_state("CONSULTA_MODE")
        result = route_to_mode(state)
        assert result == NODE_PRE_EXPEDIENTE

    def test_compat_shim_presupuesto(self):
        state = _make_state("PRESUPUESTO_MODE")
        result = route_to_mode(state)
        assert result == NODE_PRE_EXPEDIENTE


# ---------------------------------------------------------------------------
# route_to_mode — normal routing
# ---------------------------------------------------------------------------


class TestNormalRouting:
    """Standard mode strings should route correctly without compat shim."""

    def test_normal_routing_pre_expediente(self):
        state = _make_state("PRE_EXPEDIENTE_MODE")
        result = route_to_mode(state)
        assert result == NODE_PRE_EXPEDIENTE

    def test_normal_routing_expediente(self):
        state = _make_state("EXPEDIENTE_MODE")
        result = route_to_mode(state)
        assert result == NODE_EXPEDIENTE

    def test_normal_routing_escalation(self):
        state = _make_state("ESCALATION")
        result = route_to_mode(state)
        assert result == NODE_ESCALATION

    def test_default_mode_routes_to_pre_expediente(self):
        # Empty state — defaults to PRE_EXPEDIENTE_MODE
        result = route_to_mode({})
        assert result == NODE_PRE_EXPEDIENTE

    def test_unknown_mode_routes_to_pre_expediente(self):
        state = _make_state("NONEXISTENT_MODE_XYZ")
        result = route_to_mode(state)
        assert result == NODE_PRE_EXPEDIENTE


# ---------------------------------------------------------------------------
# _resolve_target_mode — CONFIRMACION intent
# ---------------------------------------------------------------------------


class TestConfirmacionRouting:
    """CONFIRMACION depends on previous mode."""

    def test_confirmacion_from_pre_expediente(self):
        intent = _make_intent_result(UserIntent.CONFIRMACION, suggested_mode="")
        state = _make_state("PRE_EXPEDIENTE_MODE", previous_mode="PRE_EXPEDIENTE_MODE")
        result = _resolve_target_mode(intent, state)
        assert result == "EXPEDIENTE_MODE"

    def test_confirmacion_from_legacy_presupuesto(self):
        """Compat: PRESUPUESTO_MODE in previous_mode should still route to EXPEDIENTE."""
        intent = _make_intent_result(UserIntent.CONFIRMACION, suggested_mode="")
        state = _make_state("PRE_EXPEDIENTE_MODE", previous_mode="PRESUPUESTO_MODE")
        result = _resolve_target_mode(intent, state)
        assert result == "EXPEDIENTE_MODE"

    def test_confirmacion_no_previous_mode(self):
        """No previous_mode → generic query, goes to PRE_EXPEDIENTE_MODE."""
        intent = _make_intent_result(UserIntent.CONFIRMACION, suggested_mode="")
        state = _make_state("PRE_EXPEDIENTE_MODE")
        result = _resolve_target_mode(intent, state)
        assert result == "PRE_EXPEDIENTE_MODE"

    def test_confirmacion_from_expediente(self):
        """Previous mode = EXPEDIENTE → doesn't match compat check, falls through to PRE_EXPEDIENTE."""
        intent = _make_intent_result(UserIntent.CONFIRMACION, suggested_mode="")
        state = _make_state("EXPEDIENTE_MODE", previous_mode="EXPEDIENTE_MODE")
        result = _resolve_target_mode(intent, state)
        assert result == "PRE_EXPEDIENTE_MODE"


# ---------------------------------------------------------------------------
# _resolve_target_mode — RECHAZO intent
# ---------------------------------------------------------------------------


class TestRechazoRouting:
    def test_rechazo_routes_to_pre_expediente(self):
        intent = _make_intent_result(UserIntent.RECHAZO, suggested_mode="")
        state = _make_state("PRE_EXPEDIENTE_MODE")
        result = _resolve_target_mode(intent, state)
        assert result == "PRE_EXPEDIENTE_MODE"


# ---------------------------------------------------------------------------
# INTENT_TO_MODE mapping
# ---------------------------------------------------------------------------


class TestIntentToModeMapping:
    def test_consulta_general_maps_to_pre_expediente(self):
        assert INTENT_TO_MODE[UserIntent.CONSULTA_GENERAL] == "PRE_EXPEDIENTE_MODE"

    def test_presupuesto_directo_maps_to_pre_expediente(self):
        assert INTENT_TO_MODE[UserIntent.PRESUPUESTO_DIRECTO] == "PRE_EXPEDIENTE_MODE"

    def test_escalar_maps_to_escalation(self):
        assert INTENT_TO_MODE[UserIntent.ESCALAR] == "ESCALATION"

    def test_iniciar_expediente_maps_to_expediente(self):
        assert INTENT_TO_MODE[UserIntent.INICIAR_EXPEDIENTE] == "EXPEDIENTE_MODE"
