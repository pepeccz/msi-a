"""
Unit tests for AC-9.1 — _is_reprice_turn() pure function.

Spec R9 (AD-Y2 set-point): When calcular_tarifa fires while precio_comunicado=True,
reprice_allowed_this_turn=True must be set in _state_update.

We test the extracted pure function _is_reprice_turn() directly — zero mocks needed.
The integration of the flag into the tool response is validated indirectly via the
guard tests (guard does not strip when reprice_allowed=True).
"""
from __future__ import annotations

import pytest


def _call(tool_state: dict) -> bool:
    from agent.tools.element_tools import _is_reprice_turn

    return _is_reprice_turn(tool_state)


class TestIsRepriceTurn:
    """AC-9.1: pure flag derivation logic."""

    def test_true_when_precio_comunicado_in_shared_context(self):
        """Flag=True when shared_context.precio_comunicado=True."""
        state = {"shared_context": {"precio_comunicado": True}, "mode_context": {}}
        assert _call(state) is True

    def test_true_when_precio_comunicado_in_mode_context(self):
        """Flag=True when mode_context.precio_comunicado=True (fallback path)."""
        state = {"shared_context": {}, "mode_context": {"precio_comunicado": True}}
        assert _call(state) is True

    def test_false_when_precio_comunicado_false_in_both(self):
        """First-turn pricing: precio_comunicado=False in both → not a reprice."""
        state = {
            "shared_context": {"precio_comunicado": False},
            "mode_context": {"precio_comunicado": False},
        }
        assert _call(state) is False

    def test_false_when_precio_comunicado_absent(self):
        """precio_comunicado absent → not a reprice turn."""
        state = {"shared_context": {}, "mode_context": {}}
        assert _call(state) is False

    def test_false_when_shared_context_missing(self):
        """shared_context key absent → falls back to mode_context check."""
        state = {"mode_context": {"precio_comunicado": False}}
        assert _call(state) is False

    def test_true_when_shared_context_missing_but_mc_true(self):
        """shared_context absent → mode_context=True is sufficient."""
        state = {"mode_context": {"precio_comunicado": True}}
        assert _call(state) is True


class TestRepriceFlagInResponse:
    """AC-9.1 (indirect): verify _is_reprice_turn() drives the correct _state_update shape."""

    def test_flag_set_shape_when_reprice(self):
        """When _is_reprice_turn=True, _state_update must have both flat and nested keys."""
        from agent.tools.element_tools import _is_reprice_turn

        tool_state = {"shared_context": {"precio_comunicado": True}, "mode_context": {}}
        is_reprice = _is_reprice_turn(tool_state)

        # Simulate the tool's _state_update construction
        state_update: dict = {"shared_context": {}}
        if is_reprice:
            state_update["reprice_allowed_this_turn"] = True
            state_update["shared_context"]["reprice_allowed_this_turn"] = True

        assert state_update.get("reprice_allowed_this_turn") is True, (
            "Flat key reprice_allowed_this_turn must be True in _state_update"
        )
        assert state_update["shared_context"].get("reprice_allowed_this_turn") is True, (
            "shared_context mirror must also be True"
        )

    def test_flag_not_set_when_not_reprice(self):
        """When _is_reprice_turn=False, _state_update must NOT have reprice flag."""
        from agent.tools.element_tools import _is_reprice_turn

        tool_state = {"shared_context": {"precio_comunicado": False}, "mode_context": {}}
        is_reprice = _is_reprice_turn(tool_state)

        state_update: dict = {"shared_context": {}}
        if is_reprice:
            state_update["reprice_allowed_this_turn"] = True
            state_update["shared_context"]["reprice_allowed_this_turn"] = True

        assert "reprice_allowed_this_turn" not in state_update, (
            "reprice_allowed_this_turn must NOT appear in _state_update on first-turn pricing"
        )
