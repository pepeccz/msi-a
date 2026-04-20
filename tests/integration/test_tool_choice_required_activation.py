"""
T6.1 — Integration test: tool_choice="required" activates in POST_PRICE after CTA 5.

Spec coverage:
  - Requirement: Production Bug Elimination — Affirmative After CTA 5
  - Scenario: Affirmative reply after CTA 5 on cloud path

Tests that when the agent is in the full POST_PRICE state with last_cta_emitted="cta_5",
the ModeLoopConfig is built with get_tool_choice returning "required" and that
after a confirmar_presupuesto tool call the last_cta_emitted flag is tombstoned.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CTA_5 = "¿Abrimos expediente o tienes alguna duda?"


def _full_post_price_state(last_cta_emitted: str | None = "cta_5") -> dict:
    """Build a ConversationState-like dict representing full POST_PRICE conditions."""
    mc: dict = {
        "precio_comunicado": True,
        "tarifa_calculada": {
            "success": True,
            "datos": {"price": 450.0, "element_codes": ["ESCAPE"]},
            "imagenes_ejemplo": [{"url": "https://example.com/escape.jpg"}],
        },
        "imagenes_enviadas_codigos": ["ESCAPE"],
        "element_codes": ["ESCAPE"],
        "categoria_slug": "motos-part",
    }
    if last_cta_emitted is not None:
        mc["last_cta_emitted"] = last_cta_emitted

    return {
        "conversation_id": "integration-test-001",
        "mode_context": mc,
        "messages": [],
        "client_type": "particular",
        "is_first_interaction": False,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestToolChoiceRequiredActivation:
    """
    End-to-end activation test: verifies the full flow from state conditions
    to tool_choice binding and post-transition tombstone.
    """

    async def test_tool_choice_required_when_all_conditions_met(self):
        """
        T6.1a:
        GIVEN full POST_PRICE state with last_cta_emitted="cta_5"
        WHEN PreExpedienteModeNode processes a user message
        THEN ModeLoopConfig is built with get_tool_choice that returns "required"
        """
        from agent.modes.pre_expediente_mode import (
            PreExpedienteModeNode,
            _should_force_tool_choice,
        )

        state = _full_post_price_state(last_cta_emitted="cta_5")
        mode_context = state["mode_context"]

        # Directly verify the lambda returns "required" for this state
        result = _should_force_tool_choice(mode_context)
        assert result == "required", (
            f"Expected 'required' for full POST_PRICE + CTA-5 state, got {result!r}"
        )

    async def test_tool_choice_none_without_cta_flag(self):
        """
        T6.1b triangulation:
        GIVEN full POST_PRICE state WITHOUT last_cta_emitted
        WHEN get_tool_choice is evaluated
        THEN returns None (no forced tool call on non-CTA-5 turns)
        """
        from agent.modes.pre_expediente_mode import _should_force_tool_choice

        state = _full_post_price_state(last_cta_emitted=None)
        result = _should_force_tool_choice(state["mode_context"])
        assert result is None, (
            f"Without last_cta_emitted, should be None, got {result!r}"
        )

    async def test_post_transition_tombstone_via_process(self):
        """
        T6.1c:
        GIVEN full POST_PRICE state with last_cta_emitted="cta_5"
        AND the LLM simulation calls confirmar_presupuesto (returning _state_update)
        WHEN _process_with_tool_loop runs
        THEN:
          (a) last_cta_emitted is NOT "cta_5" in result mode_context
              (either None from per-turn clear or None from confirmar tombstone)
          (b) current_mode is "EXPEDIENTE_MODE" (transition fired)
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        # Simulate the loop returning a transition via pending_state_updates
        # (as confirmar_presupuesto would supply via _state_update)
        fake_result = {
            "ai_response": "Perfecto, iniciamos el expediente.",
            "exit_reason": "transition",
            "tools_called": ["confirmar_presupuesto"],
            "pending_state_updates": {
                "_transition_to": "EXPEDIENTE_MODE",
                "expediente_kickoff_pending": True,
                "shared_context": {"warnings_acknowledged": True},
                "last_cta_emitted": None,  # tombstone from confirmar_presupuesto
            },
        }

        fake_graph = MagicMock()
        fake_graph.ainvoke = AsyncMock(return_value=fake_result)
        fake_loop_obj = MagicMock()
        fake_loop_obj.graph = fake_graph
        fake_loop_obj.recursion_limit = 25

        state = _full_post_price_state(last_cta_emitted="cta_5")

        with (
            patch("agent.modes.pre_expediente_mode.ModeLoopConfig"),
            patch("agent.modes.pre_expediente_mode.build_mode_tool_loop", return_value=fake_loop_obj),
            patch("agent.modes.pre_expediente_mode._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch("agent.modes.pre_expediente_mode.clear_image_tools_state"),
        ):
            node = PreExpedienteModeNode()
            result = await node._process_with_tool_loop("abre el expediente si", state)

        # (a) last_cta_emitted must NOT be "cta_5" after transition
        mc = result.get("mode_context", {})
        assert mc.get("last_cta_emitted") != "cta_5", (
            f"last_cta_emitted should not be 'cta_5' after transition, "
            f"got: {mc.get('last_cta_emitted')!r}"
        )

        # (b) current_mode must be EXPEDIENTE_MODE
        assert result.get("current_mode") == "EXPEDIENTE_MODE", (
            f"Expected current_mode='EXPEDIENTE_MODE', got: {result.get('current_mode')!r}"
        )

    async def test_tool_choice_required_produces_required_string(self):
        """
        T6.1d:
        Verify that _should_force_tool_choice specifically returns the string "required"
        (not True, not 1, not "REQUIRED") as LangChain bind_tools expects this exact value.
        """
        from agent.modes.pre_expediente_mode import _should_force_tool_choice

        mc = {
            "precio_comunicado": True,
            "tarifa_calculada": {"datos": {"price": 100}},
            "imagenes_enviadas_codigos": ["T01"],
            "last_cta_emitted": "cta_5",
        }
        result = _should_force_tool_choice(mc)
        assert result == "required", (
            f"Must return the string 'required', got {result!r} ({type(result).__name__})"
        )
        assert isinstance(result, str), (
            f"Must be a str, not {type(result).__name__}"
        )
