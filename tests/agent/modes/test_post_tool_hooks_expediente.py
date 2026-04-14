"""
Unit tests for expediente_post_tool_hook — fix-expediente-mode-not-reset.

Tests that finalizar_expediente sets _transition_to to a valid graph mode.

The hook returns updates inside mode_context (three-layer merge pattern):
  updates["mode_context"]["_transition_to"]
"""

import pytest

from agent.modes.post_tool_hooks import expediente_post_tool_hook


class TestFinalizarExpedienteHookTransition:
    """expediente_post_tool_hook must set valid _transition_to for finalizar."""

    @pytest.mark.asyncio
    async def test_finalizar_success_sets_presupuesto_mode(self):
        """
        Spec: finalizar_expediente succeeds → _transition_to MUST be CONSULTA_MODE.
        (Previously was "COMPLETED" which is not a valid mode.)
        """
        result_dict = {
            "success": True,
            "message": "Expediente enviado.",
            "case_id": "some-uuid",
            "_state_update": {
                "case_finalized": True,
                "expediente_sub_mode": "completed",
                "expediente_completed": True,
            },
        }
        state = {
            "_mode_context": {"case_id": "some-uuid"},
            "pending_state_updates": {},
        }

        updates = await expediente_post_tool_hook(
            "finalizar_expediente", result_dict, state
        )

        mc = updates.get("mode_context", {})
        assert mc.get("_transition_to") == "CONSULTA_MODE"
        assert mc.get("expediente_completed") is True

    @pytest.mark.asyncio
    async def test_finalizar_failure_no_transition(self):
        """Finalizar fails → no _transition_to set."""
        result_dict = {"success": False, "error": "DB error"}
        state = {
            "_mode_context": {"case_id": "some-uuid"},
            "pending_state_updates": {},
        }

        updates = await expediente_post_tool_hook(
            "finalizar_expediente", result_dict, state
        )

        mc = updates.get("mode_context", {})
        assert "_transition_to" not in mc

    @pytest.mark.asyncio
    async def test_cancelar_sets_presupuesto_mode(self):
        """cancelar_expediente → _transition_to MUST be CONSULTA_MODE."""
        result_dict = {"success": True, "message": "Cancelado."}
        state = {
            "_mode_context": {"case_id": "some-uuid"},
            "pending_state_updates": {},
        }

        updates = await expediente_post_tool_hook(
            "cancelar_expediente", result_dict, state
        )

        mc = updates.get("mode_context", {})
        assert mc.get("_transition_to") == "CONSULTA_MODE"
        assert mc.get("expediente_cancelled") is True
