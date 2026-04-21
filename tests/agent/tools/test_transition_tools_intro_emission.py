"""
B1-T1 [RED] — confirmar_presupuesto emits expediente_intro_message in _state_update.

Spec: expediente-intro-emission — Requirement: Intro Message Population at Transition Boundary

  GIVEN precio_comunicado=True and tarifa_calculada present in mode_context
  WHEN confirmar_presupuesto is invoked
  THEN result["_state_update"]["expediente_intro_message"] is a non-empty str
       starting with "He abierto"
  AND  result["_state_update"]["expediente_intro_sent"] is False

These tests FAIL before B1-T3 (GREEN implementation) and PASS after.
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
                "conversation_id": "test-conv-intro-001",
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
        "element_codes": ["SUBCHASIS"],
        "categoria_slug": "furgonetas-part",
    }


# ---------------------------------------------------------------------------
# B1-T1: confirmar_presupuesto._state_update contains intro emission fields
# ---------------------------------------------------------------------------


class TestConfirmarPresupuestoIntroEmission:
    """
    B1-T1 [RED]: confirmar_presupuesto must populate expediente_intro_message
    and expediente_intro_sent=False in its _state_update.

    Fails before B1-T3 (tool not yet calling build_expediente_opening_overview).
    Passes after B1-T3 GREEN.
    """

    @pytest.mark.asyncio
    async def test_expediente_intro_message_present_and_non_empty(self):
        """
        B1-T1a: _state_update must contain key 'expediente_intro_message'
        as a non-empty string.
        """
        from agent.tools.transition_tools import confirmar_presupuesto

        config = _make_config(_mode_context_confirmed())
        result = await confirmar_presupuesto.ainvoke({}, config=config)

        assert result.get("success") is True, f"Expected success=True, got: {result}"

        state_update = result.get("_state_update")
        assert isinstance(state_update, dict), (
            f"Expected _state_update dict, got: {state_update!r}"
        )

        intro_msg = state_update.get("expediente_intro_message")
        assert isinstance(intro_msg, str) and intro_msg, (
            "confirmar_presupuesto._state_update must contain 'expediente_intro_message' "
            f"as a non-empty string. Got: {intro_msg!r}"
        )

    @pytest.mark.asyncio
    async def test_expediente_intro_message_starts_with_canonical_prefix(self):
        """
        B1-T1b: expediente_intro_message must start with "He abierto" (canonical prefix
        from build_expediente_opening_overview).
        """
        from agent.tools.transition_tools import confirmar_presupuesto

        config = _make_config(_mode_context_confirmed())
        result = await confirmar_presupuesto.ainvoke({}, config=config)

        state_update = result["_state_update"]
        intro_msg = state_update.get("expediente_intro_message", "")

        assert intro_msg.startswith("He abierto"), (
            "expediente_intro_message must start with 'He abierto' "
            "(canonical prefix from build_expediente_opening_overview). "
            f"Got: {intro_msg!r}"
        )

    @pytest.mark.asyncio
    async def test_expediente_intro_sent_is_false(self):
        """
        B1-T1c: _state_update must contain 'expediente_intro_sent' == False.
        Defensive reset — clears stale True from prior expediente on same conversation.
        """
        from agent.tools.transition_tools import confirmar_presupuesto

        config = _make_config(_mode_context_confirmed())
        result = await confirmar_presupuesto.ainvoke({}, config=config)

        state_update = result["_state_update"]
        intro_sent = state_update.get("expediente_intro_sent")

        assert intro_sent is False, (
            "confirmar_presupuesto._state_update must set 'expediente_intro_sent' = False "
            "(explicit defensive reset). "
            f"Got: {intro_sent!r}"
        )

    @pytest.mark.asyncio
    async def test_existing_transition_fields_still_present(self):
        """
        B1-T1 triangulation / regression guard: adding intro fields must not
        remove existing _state_update keys (_transition_to, expediente_kickoff_pending,
        last_cta_emitted, shared_context).
        """
        from agent.tools.transition_tools import confirmar_presupuesto

        config = _make_config(_mode_context_confirmed())
        result = await confirmar_presupuesto.ainvoke({}, config=config)

        state_update = result["_state_update"]

        assert state_update.get("_transition_to") == "EXPEDIENTE_MODE", (
            "_transition_to must still be EXPEDIENTE_MODE after adding intro fields"
        )
        assert state_update.get("expediente_kickoff_pending") is True, (
            "expediente_kickoff_pending must still be True"
        )
        assert "last_cta_emitted" in state_update and state_update["last_cta_emitted"] is None, (
            "last_cta_emitted tombstone must still be present"
        )
        assert isinstance(state_update.get("shared_context"), dict), (
            "shared_context must still be a dict"
        )
