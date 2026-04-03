"""
Unit tests for transition_tools.py — expediente-transition-ux BUG-1.

BUG-1: confirmar_presupuesto() was returning a user-facing orientation string
("¡Perfecto! Vamos a iniciar el expediente. Te iré pidiendo la información paso a paso.")
which the LLM echoed verbatim — user received minimal orientation instead of the
full expediente onboarding overview.

Fix: message field is now a neutral internal signal; the LLM generates orientation
from the .md prompt and case_instructions context.

Scenarios:
  1. Returns success=True with neutral message on valid state (precio_comunicado=True)
  2. message does NOT contain "paso a paso" (old string guard)
  3. message equals the exact neutral internal signal
  4. _internal_flags._transition_to == "EXPEDIENTE_MODE"
  5. Returns success=False if precio_comunicado is missing
  6. Returns success=False if no tarifa_calculada
"""

from __future__ import annotations

import types
import sys
from typing import Any
from unittest.mock import patch

import pytest

# Stub phonenumbers to avoid import errors in agent module tree
sys.modules.setdefault("phonenumbers", types.ModuleType("phonenumbers"))

from agent.state.helpers import set_current_state
from agent.tools.transition_tools import confirmar_presupuesto


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_valid_state() -> dict[str, Any]:
    """Build a state with precio_comunicado=True and a tarifa_calculada dict."""
    return {
        "conversation_id": "101",
        "user_id": "user-abc",
        "current_mode": "PRESUPUESTO_MODE",
        "mode_context": {
            "precio_comunicado": True,
            "tarifa_calculada": {
                "datos": {
                    "price": 350.0,
                    "elementos": ["ESCAPE"],
                    "categoria": "motos-part",
                }
            },
            "element_codes": ["ESCAPE"],
            "categoria_slug": "motos-part",
        },
    }


def _make_state_no_price() -> dict[str, Any]:
    """State where price has NOT been communicated yet."""
    state = _make_valid_state()
    state["mode_context"]["precio_comunicado"] = False
    return state


def _make_state_no_tariff() -> dict[str, Any]:
    """State where price is communicated but tarifa_calculada is missing."""
    state = _make_valid_state()
    del state["mode_context"]["tarifa_calculada"]
    return state


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestConfirmarPresupuestoBUG1:
    """BUG-1 — confirmar_presupuesto() must return a neutral internal signal."""

    @pytest.mark.asyncio
    async def test_returns_success_true_on_valid_state(self):
        """
        GIVEN a valid state with precio_comunicado=True and tarifa_calculada
        WHEN confirmar_presupuesto() is called
        THEN result.success is True
        """
        state = _make_valid_state()
        set_current_state(state)

        with patch(
            "agent.tools.transition_tools.get_current_state", return_value=state
        ):
            result = await confirmar_presupuesto.coroutine()

        assert result.get("success") is True, f"Expected success=True, got: {result}"

    @pytest.mark.asyncio
    async def test_message_does_not_contain_paso_a_paso(self):
        """
        GIVEN a valid state
        WHEN confirmar_presupuesto() is called
        THEN result.message does NOT contain the old 'paso a paso' string
        """
        state = _make_valid_state()
        set_current_state(state)

        with patch(
            "agent.tools.transition_tools.get_current_state", return_value=state
        ):
            result = await confirmar_presupuesto.coroutine()

        message = result.get("message", "")
        assert "paso a paso" not in message, (
            f"message must not contain 'paso a paso' (old user-facing string), got: {message!r}"
        )

    @pytest.mark.asyncio
    async def test_message_is_neutral_internal_signal(self):
        """
        GIVEN a valid state
        WHEN confirmar_presupuesto() is called
        THEN result.message equals the exact neutral internal signal
        """
        expected = "El usuario ha confirmado el presupuesto. Expediente en preparación."
        state = _make_valid_state()
        set_current_state(state)

        with patch(
            "agent.tools.transition_tools.get_current_state", return_value=state
        ):
            result = await confirmar_presupuesto.coroutine()

        assert result.get("message") == expected, (
            f"Expected neutral internal message, got: {result.get('message')!r}"
        )

    @pytest.mark.asyncio
    async def test_internal_flags_transition_to_expediente_mode(self):
        """
        GIVEN a valid state
        WHEN confirmar_presupuesto() is called
        THEN _internal_flags._transition_to == "EXPEDIENTE_MODE"
        AND  _internal_flags._chain_next_mode is True
        """
        state = _make_valid_state()
        set_current_state(state)

        with patch(
            "agent.tools.transition_tools.get_current_state", return_value=state
        ):
            result = await confirmar_presupuesto.coroutine()

        flags = result.get("_internal_flags", {})
        assert flags.get("_transition_to") == "EXPEDIENTE_MODE", (
            f"Expected _transition_to=EXPEDIENTE_MODE, got: {flags}"
        )
        assert flags.get("_chain_next_mode") is True, (
            f"Expected _chain_next_mode=True, got: {flags}"
        )

    @pytest.mark.asyncio
    async def test_returns_failure_when_price_not_communicated(self):
        """
        GIVEN a state where precio_comunicado=False
        WHEN confirmar_presupuesto() is called
        THEN result.success is False
        AND result.error == "PRICE_NOT_COMMUNICATED"
        """
        state = _make_state_no_price()
        set_current_state(state)

        with patch(
            "agent.tools.transition_tools.get_current_state", return_value=state
        ):
            result = await confirmar_presupuesto.coroutine()

        assert result.get("success") is False
        assert result.get("error") == "PRICE_NOT_COMMUNICATED"

    @pytest.mark.asyncio
    async def test_returns_failure_when_no_tariff(self):
        """
        GIVEN a state with precio_comunicado=True but no tarifa_calculada
        WHEN confirmar_presupuesto() is called
        THEN result.success is False
        """
        state = _make_state_no_tariff()
        set_current_state(state)

        with patch(
            "agent.tools.transition_tools.get_current_state", return_value=state
        ):
            result = await confirmar_presupuesto.coroutine()

        assert result.get("success") is False
