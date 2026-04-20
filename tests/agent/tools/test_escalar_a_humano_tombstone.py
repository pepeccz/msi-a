"""
T4.3 — escalar_a_humano must tombstone last_cta_emitted in its return dict.

Spec coverage:
  - Requirement: last_cta_emitted Flag Lifecycle — escalar_a_humano transition
  - GIVEN escalar_a_humano is called (via perform_escalation success path)
  - WHEN the tool returns its result dict
  - THEN result["_state_update"]["last_cta_emitted"] is None (tombstoned per ADR-010)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def _make_escalation_config(conversation_id: str = "test-escalar-001") -> dict:
    """Build a minimal RunnableConfig for escalar_a_humano."""
    return {
        "configurable": {
            "state": {
                "conversation_id": conversation_id,
                "user_id": "user-uuid-001",
                "user_phone": "+34600000001",
            }
        }
    }


def _fake_escalation_result() -> dict:
    """Minimal success result from perform_escalation."""
    return {
        "success": True,
        "message": "Escalación realizada.",
        "escalation_id": "esc-001",
    }


class TestEscalarAHumanoTombstone:
    """
    T4.3 → T4.4 RED/GREEN:
    escalar_a_humano must return _state_update with last_cta_emitted=None.
    """

    @pytest.mark.asyncio
    async def test_escalar_a_humano_tombstones_last_cta_emitted(self):
        """
        GIVEN perform_escalation returns a success dict
        WHEN escalar_a_humano is called
        THEN result["_state_update"]["last_cta_emitted"] is None
        """
        from agent.tools.shared_tools import escalar_a_humano

        config = _make_escalation_config()

        with patch(
            "agent.services.escalation_service.perform_escalation",
            new_callable=AsyncMock,
            return_value=_fake_escalation_result(),
        ):
            result = await escalar_a_humano.ainvoke(
                {"motivo": "El usuario quiere hablar con una persona"},
                config=config,
            )

        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert result.get("escalation_triggered") is True, (
            "escalation_triggered must be True"
        )

        state_update = result.get("_state_update")
        assert isinstance(state_update, dict), (
            f"Expected _state_update dict in result, got: {state_update!r}. "
            "escalar_a_humano must return _state_update with last_cta_emitted=None."
        )

        assert "last_cta_emitted" in state_update, (
            "'last_cta_emitted' key MUST be in _state_update to tombstone it (ADR-010). "
            "Without it, merge_dicts would resurrect the stale 'cta_5' from checkpoint."
        )
        assert state_update["last_cta_emitted"] is None, (
            f"Expected last_cta_emitted=None (tombstone), "
            f"got: {state_update['last_cta_emitted']!r}"
        )

    @pytest.mark.asyncio
    async def test_escalar_a_humano_tombstone_with_technical_error(self):
        """
        Triangulation: tombstone works on error path (es_error_tecnico=True) too.
        """
        from agent.tools.shared_tools import escalar_a_humano

        config = _make_escalation_config("test-escalar-002")

        with patch(
            "agent.services.escalation_service.perform_escalation",
            new_callable=AsyncMock,
            return_value=_fake_escalation_result(),
        ):
            result = await escalar_a_humano.ainvoke(
                {
                    "motivo": "Error técnico recurrente",
                    "es_error_tecnico": True,
                    "contexto": "Falló 3 veces al calcular tarifa",
                },
                config=config,
            )

        state_update = result.get("_state_update", {})
        assert state_update.get("last_cta_emitted") is None, (
            f"Tombstone must work on technical-error path too. "
            f"Got _state_update={state_update!r}"
        )
