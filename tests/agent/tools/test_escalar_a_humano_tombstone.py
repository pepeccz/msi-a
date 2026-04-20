"""
T4.3 — escalar_a_humano must tombstone last_cta_emitted in _state_update.

Spec: last_cta_emitted Flag Lifecycle — Scenario: escalar_a_humano transition
  GIVEN the LLM calls escalar_a_humano and escalation succeeds
  WHEN the tool returns its result dict
  THEN result["_state_update"]["last_cta_emitted"] MUST be None (tombstoned per ADR-010)

Design D4: escalar_a_humano adds _state_update = {"last_cta_emitted": None}
  before return result in agent/tools/shared_tools.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def _make_config(conversation_id: str = "test-escalar-001") -> dict:
    """Build a minimal RunnableConfig with conversation state."""
    return {
        "configurable": {
            "state": {
                "conversation_id": conversation_id,
                "user_id": "user-001",
                "user_phone": "+34600000001",
            }
        }
    }


class TestEscalarAHumanoTombstonesLastCtaEmitted:
    """
    T4.3 + T4.4 — escalar_a_humano tombstones last_cta_emitted via _state_update.

    Spec coverage: escalar_a_humano transition — flag tombstoned
    """

    @pytest.mark.asyncio
    async def test_escalar_a_humano_tombstones_last_cta_emitted(self) -> None:
        """
        T4.3 — GREEN assertion:
        escalar_a_humano must return a _state_update dict with last_cta_emitted: None.
        """
        from agent.tools.shared_tools import escalar_a_humano

        # Mock perform_escalation to return a success-like result
        mock_escalation_result = {
            "success": True,
            "message": "Escalación completada.",
            "conversation_id": "test-escalar-001",
        }

        config = _make_config()

        with patch(
            "agent.services.escalation_service.perform_escalation",
            new_callable=AsyncMock,
            return_value=mock_escalation_result,
        ):
            result = await escalar_a_humano.ainvoke(
                {"motivo": "El usuario quiere hablar con una persona"},
                config=config,
            )

        assert isinstance(result, dict), f"Expected dict, got {type(result)!r}"

        state_update = result.get("_state_update")
        assert isinstance(state_update, dict), (
            f"escalar_a_humano must return '_state_update' dict, "
            f"got: {state_update!r}"
        )

        assert "last_cta_emitted" in state_update, (
            "escalar_a_humano._state_update must contain 'last_cta_emitted' tombstone key"
        )
        assert state_update["last_cta_emitted"] is None, (
            f"escalar_a_humano must tombstone last_cta_emitted to None, "
            f"got: {state_update['last_cta_emitted']!r}"
        )

    @pytest.mark.asyncio
    async def test_escalar_a_humano_tombstone_preserved_alongside_existing_flags(
        self,
    ) -> None:
        """
        Triangulation T4.3b:
        The tombstone must coexist with other fields set by perform_escalation
        (escalation_triggered, tool_name).
        """
        from agent.tools.shared_tools import escalar_a_humano

        mock_escalation_result = {
            "success": True,
            "message": "Escalación completada.",
            "conversation_id": "test-escalar-002",
        }

        config = _make_config("test-escalar-002")

        with patch(
            "agent.services.escalation_service.perform_escalation",
            new_callable=AsyncMock,
            return_value=mock_escalation_result,
        ):
            result = await escalar_a_humano.ainvoke(
                {"motivo": "Caso complejo", "es_error_tecnico": True},
                config=config,
            )

        # Pre-existing fields must still be set
        assert result.get("escalation_triggered") is True, (
            "escalation_triggered must still be True"
        )
        assert result.get("tool_name") == "escalar_a_humano", (
            "tool_name must still be 'escalar_a_humano'"
        )

        # Tombstone must also be present
        state_update = result.get("_state_update")
        assert state_update is not None, "Missing _state_update"
        assert state_update.get("last_cta_emitted") is None, (
            f"Tombstone must be None, got: {state_update.get('last_cta_emitted')!r}"
        )
