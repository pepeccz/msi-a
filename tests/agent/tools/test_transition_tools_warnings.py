"""
T1 — Concern A: warnings_acknowledged setter on confirmar_presupuesto.

Spec: ConfirmarPresupuestoSetsWarningsAcknowledged
  - GIVEN precio_comunicado=True and tarifa_calculada present in mode_context
  - WHEN confirmar_presupuesto is invoked
  - THEN result["_state_update"]["shared_context"]["warnings_acknowledged"] == True
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(mode_context: dict) -> dict:
    """Build a minimal RunnableConfig with the given mode_context."""
    return {
        "configurable": {
            "state": {
                "conversation_id": "test-conv-001",
                "mode_context": mode_context,
            }
        }
    }


def _mode_context_confirmed() -> dict:
    """Mode context that passes all confirmar_presupuesto preconditions."""
    return {
        "precio_comunicado": True,
        "tarifa_calculada": {
            "datos": {"price": 450.0},
        },
        "element_codes": ["ESCAPE", "SUSPENSION"],
        "categoria_slug": "motos-part",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestConfirmarPresupuestoWarningsAcknowledged:
    """
    Spec coverage: ConfirmarPresupuestoSetsWarningsAcknowledged — scenario
    'success — flag present in state update'.
    """

    @pytest.mark.asyncio
    async def test_state_update_contains_warnings_acknowledged_true(self):
        """
        T1 — GREEN assertion:
        confirmar_presupuesto must set _state_update.shared_context.warnings_acknowledged == True.
        """
        from agent.tools.transition_tools import confirmar_presupuesto

        config = _make_config(_mode_context_confirmed())

        result = await confirmar_presupuesto.ainvoke({}, config=config)

        assert isinstance(result, dict), "Expected dict result"
        assert result.get("success") is True, f"Expected success=True, got: {result}"

        state_update = result.get("_state_update")
        assert isinstance(state_update, dict), (
            f"Expected _state_update to be a dict, got: {state_update!r}"
        )

        shared_context = state_update.get("shared_context")
        assert isinstance(shared_context, dict), (
            f"Expected _state_update.shared_context to be a dict, got: {shared_context!r}"
        )

        assert shared_context.get("warnings_acknowledged") is True, (
            f"Expected warnings_acknowledged=True, got: {shared_context!r}"
        )

    @pytest.mark.asyncio
    async def test_existing_transition_fields_preserved(self):
        """
        Regression: existing _state_update fields (_transition_to)
        must not be removed when adding shared_context.warnings_acknowledged.
        """
        from agent.tools.transition_tools import confirmar_presupuesto

        config = _make_config(_mode_context_confirmed())

        result = await confirmar_presupuesto.ainvoke({}, config=config)

        assert result.get("success") is True
        state_update = result["_state_update"]
        assert state_update.get("_transition_to") == "EXPEDIENTE_MODE", (
            "_transition_to must still be EXPEDIENTE_MODE"
        )


class TestConfirmarPresupuestoTombstonesLastCtaEmitted:
    """
    T4.1 — confirmar_presupuesto must tombstone last_cta_emitted in _state_update.

    Spec: last_cta_emitted Flag Lifecycle — Scenario: confirmar_presupuesto transition
      GIVEN the LLM calls confirmar_presupuesto
      WHEN the tool's _state_update triggers EXPEDIENTE_MODE transition
      THEN mode_context["last_cta_emitted"] MUST be set to None (tombstoned per ADR-010)
    """

    @pytest.mark.asyncio
    async def test_confirmar_presupuesto_tombstones_last_cta_emitted(self):
        """
        T4.1 — GREEN assertion:
        confirmar_presupuesto._state_update must contain last_cta_emitted: None.
        """
        from agent.tools.transition_tools import confirmar_presupuesto

        config = _make_config(_mode_context_confirmed())

        result = await confirmar_presupuesto.ainvoke({}, config=config)

        assert result.get("success") is True, f"Expected success=True, got: {result}"

        state_update = result.get("_state_update")
        assert isinstance(state_update, dict), (
            f"Expected _state_update dict, got: {state_update!r}"
        )

        assert "last_cta_emitted" in state_update, (
            "confirmar_presupuesto._state_update must contain 'last_cta_emitted' tombstone key"
        )
        assert state_update["last_cta_emitted"] is None, (
            f"confirmar_presupuesto must tombstone last_cta_emitted to None, "
            f"got: {state_update['last_cta_emitted']!r}"
        )
