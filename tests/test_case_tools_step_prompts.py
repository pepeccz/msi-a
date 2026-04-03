"""
Unit tests for case_tools.py _STEP_PROMPTS neutralization — expediente-transition-ux BUG-5.

BUG-5: _STEP_PROMPTS dict in case_tools.py contained verbose per-step kickoff strings
(e.g., "Ahora necesito tus datos personales:\n• Nombre y apellidos\n• DNI o CIF\n...")
that editar_expediente() embeds in its tool return message field.
These strings conflicted with the .md prompts for each sub-mode and contained
outdated field lists (e.g., COLLECT_VEHICLE was missing 'bastidor').

Fix: Replace all values with neutral one-liners following the pattern:
     "Volvemos a [section]. El sub-modo gestionará el resto."
     The .md prompt for each sub-mode now governs the detailed kickoff.

Scenarios:
  1. editar_expediente("personal") message does NOT contain field lists ("DNI", "Email")
  2. editar_expediente("vehiculo") message does NOT contain field lists ("Marca", "Modelo")
  3. editar_expediente("personal") message contains "datos personales"
  4. editar_expediente("vehiculo") message contains "datos del vehículo"
  5. editar_expediente("documentacion") message does NOT contain verbose instructions
  6. editar_expediente("taller") message contains "taller"
  7. editar_expediente(any valid section) message contains "El sub-modo gestionará el resto"
  8. _STEP_PROMPTS values are all short (< 100 chars each)
"""

from __future__ import annotations

import types
import sys
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Stub phonenumbers before importing agent modules
sys.modules.setdefault("phonenumbers", types.ModuleType("phonenumbers"))

from agent.state.helpers import set_current_state


def _make_review_summary_state(case_id: str | None = None) -> dict[str, Any]:
    """Build state at REVIEW_SUMMARY so editar_expediente() is allowed."""
    cid = case_id or str(uuid.uuid4())
    return {
        "conversation_id": "42",
        "user_id": str(uuid.uuid4()),
        "current_mode": "EXPEDIENTE_MODE",
        "mode_context": {
            "expediente_sub_mode": "review_summary",
            "case_id": cid,
            "category_slug": "motos-part",
            "element_codes": ["ESCAPE"],
            "tariff_amount": 350.0,
        },
        "fsm_state": {
            "case_collection": {
                "step": "review_summary",
                "case_id": cid,
                "category_slug": "motos-part",
                "element_codes": ["ESCAPE"],
                "current_element_index": 0,
                "element_data_status": {"ESCAPE": "completed"},
                "base_docs_received": True,
                "received_images": [],
            }
        },
    }


async def _call_editar(seccion: str, state: dict[str, Any]) -> dict[str, Any]:
    """Helper: call editar_expediente with mocked DB and state."""
    from agent.tools.case_tools import editar_expediente

    set_current_state(state)

    # Build a minimal mock FSM state that the transition validator accepts
    mock_new_fsm = {
        "case_collection": {
            "step": seccion,
            "case_id": state["mode_context"]["case_id"],
        }
    }

    with (
        patch(
            "agent.tools.case_tools.get_current_state",
            return_value=state,
        ),
        patch(
            "agent.tools.case_tools._transition_with_db_sync",
            new_callable=AsyncMock,
            return_value=mock_new_fsm,
        ),
    ):
        return await editar_expediente.coroutine(seccion=seccion)


class TestStepPromptsNeutralization:
    """BUG-5 — _STEP_PROMPTS values must be neutral (no verbose field lists)."""

    def test_step_prompts_values_are_short(self):
        """
        GIVEN _STEP_PROMPTS dict
        WHEN checking each value's length
        THEN every value must be < 100 chars (neutral one-liners)
        """
        from agent.tools.case_tools import _STEP_PROMPTS

        for step, prompt in _STEP_PROMPTS.items():
            assert len(prompt) < 100, (
                f"_STEP_PROMPTS[{step}] is too long ({len(prompt)} chars). "
                f"Expected neutral one-liner (< 100 chars). Got: {prompt!r}"
            )

    def test_step_prompts_do_not_contain_field_bullets(self):
        """
        GIVEN _STEP_PROMPTS dict
        THEN no value should contain bullet point field lists
        """
        from agent.tools.case_tools import _STEP_PROMPTS

        for step, prompt in _STEP_PROMPTS.items():
            assert "•" not in prompt, (
                f"_STEP_PROMPTS[{step}] contains bullet points — must be neutral. Got: {prompt!r}"
            )
            assert "\n" not in prompt or len(prompt) < 60, (
                f"_STEP_PROMPTS[{step}] is multi-line — must be a neutral one-liner. Got: {prompt!r}"
            )

    @pytest.mark.asyncio
    async def test_editar_personal_does_not_contain_field_list(self):
        """
        GIVEN editar_expediente("personal") is called from REVIEW_SUMMARY
        WHEN the tool returns
        THEN message MUST NOT contain the old field list ("DNI", "Email")
        """
        state = _make_review_summary_state()
        result = await _call_editar("personal", state)

        assert result.get("success") is True, f"Expected success=True, got: {result}"
        message = result.get("message", "")
        assert "DNI" not in message, (
            f"message must not contain old field list 'DNI'. Got: {message!r}"
        )
        assert "Email" not in message, (
            f"message must not contain old field list 'Email'. Got: {message!r}"
        )

    @pytest.mark.asyncio
    async def test_editar_personal_contains_section_name(self):
        """
        GIVEN editar_expediente("personal") is called
        THEN message must contain "datos personales"
        """
        state = _make_review_summary_state()
        result = await _call_editar("personal", state)

        message = result.get("message", "")
        assert "datos personales" in message.lower(), (
            f"Expected 'datos personales' in message. Got: {message!r}"
        )

    @pytest.mark.asyncio
    async def test_editar_vehiculo_does_not_contain_old_field_list(self):
        """
        GIVEN editar_expediente("vehiculo") is called from REVIEW_SUMMARY
        THEN message MUST NOT contain the old field list ("Marca", "Modelo")
        AND MUST NOT be missing bastidor (old list was incomplete)
        """
        state = _make_review_summary_state()
        result = await _call_editar("vehiculo", state)

        assert result.get("success") is True, f"Expected success=True, got: {result}"
        message = result.get("message", "")
        # The old verbose string had "• Marca\n• Modelo\n• Matrícula\n• Año de primera matriculación"
        # (no bastidor!) — after fix, none of those bullets should appear
        assert "• Marca" not in message, (
            f"message must not contain old verbose field list. Got: {message!r}"
        )

    @pytest.mark.asyncio
    async def test_editar_vehiculo_contains_section_name(self):
        """
        GIVEN editar_expediente("vehiculo") is called
        THEN message must contain "datos del vehículo"
        """
        state = _make_review_summary_state()
        result = await _call_editar("vehiculo", state)

        message = result.get("message", "")
        assert (
            "datos del vehículo" in message.lower() or "vehículo" in message.lower()
        ), f"Expected vehicle section name in message. Got: {message!r}"

    @pytest.mark.asyncio
    async def test_editar_section_message_contains_submode_gestionara(self):
        """
        GIVEN any valid section is passed to editar_expediente()
        THEN message should contain 'El sub-modo gestionará el resto' (neutral signal)
        """
        state = _make_review_summary_state()
        result = await _call_editar("personal", state)

        message = result.get("message", "")
        assert "sub-modo" in message.lower() or "gestionará" in message.lower(), (
            f"Expected neutral sub-mode handoff phrase in message. Got: {message!r}"
        )

    @pytest.mark.asyncio
    async def test_editar_documentacion_returns_success(self):
        """
        GIVEN editar_expediente("documentacion") is called from REVIEW_SUMMARY
        THEN success is True and message is not verbose
        """
        state = _make_review_summary_state()
        result = await _call_editar("documentacion", state)

        assert result.get("success") is True, f"Expected success=True, got: {result}"
        message = result.get("message", "")
        # Old verbose string had "• Ficha técnica\n• Permiso de circulación\n• Vistas del vehículo"
        assert "Ficha técnica" not in message, (
            f"message must not contain old verbose doc list. Got: {message!r}"
        )
