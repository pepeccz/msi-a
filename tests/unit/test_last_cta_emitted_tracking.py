"""
T3.1, T3.3, T5.1 — last_cta_emitted flag lifecycle tests.

Spec coverage:
  - Requirement: last_cta_emitted Flag Lifecycle
  - Scenario: CTA 5 appended → flag set to "cta_5"
  - Scenario: Non-CTA-5 turn → flag None
  - Scenario: Stale flag overwritten next turn
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CTA_5 = "¿Abrimos expediente o tienes alguna duda?"


def _make_state(mode_context: dict) -> dict:
    return {
        "conversation_id": "test-cta-track-001",
        "mode_context": mode_context,
        "messages": [],
        "client_type": "particular",
        "is_first_interaction": False,
    }


def _make_fake_loop_obj(ai_response: str, tools_called: list | None = None):
    """Return a fake loop result + object for patching build_mode_tool_loop."""
    fake_result = {
        "ai_response": ai_response,
        "exit_reason": "response",
        "tools_called": tools_called or [],
        "pending_state_updates": {},
    }
    fake_graph = MagicMock()
    fake_graph.ainvoke = AsyncMock(return_value=fake_result)
    fake_loop_obj = MagicMock()
    fake_loop_obj.graph = fake_graph
    fake_loop_obj.recursion_limit = 25
    return fake_loop_obj


# ---------------------------------------------------------------------------
# T3.1 — CTA 5 gate fires → last_cta_emitted = "cta_5"
# ---------------------------------------------------------------------------

class TestCTA5GateSetsFlag:
    """When the CTA 5 gate appends CTA 5 to the response, last_cta_emitted must be 'cta_5'."""

    async def test_cta5_gate_fires_sets_flag(self):
        """
        T3.1 RED:
        GIVEN ai_response ends with canonical CTA 5 AND preconditions met
        WHEN _process_with_tool_loop runs
        THEN result_dict["mode_context"]["last_cta_emitted"] == "cta_5"
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        # Simulate LLM returning just the CTA 5 (e.g. after an image send turn)
        loop_obj = _make_fake_loop_obj(
            ai_response=f"Aquí tienes las fotos.\n\n{_CTA_5}",
        )

        state = _make_state({
            "precio_comunicado": True,
            "tarifa_calculada": {"datos": {"price": 100}},
            "imagenes_enviadas_codigos": ["T01"],  # non-empty → gate fires
        })

        with (
            patch("agent.modes.pre_expediente_mode.ModeLoopConfig"),
            patch("agent.modes.pre_expediente_mode.build_mode_tool_loop", return_value=loop_obj),
            patch("agent.modes.pre_expediente_mode._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch("agent.modes.pre_expediente_mode.clear_image_tools_state"),
        ):
            node = PreExpedienteModeNode()
            result = await node._process_with_tool_loop("¿puedo ver fotos?", state)

        mc = result.get("mode_context", {})
        assert mc.get("last_cta_emitted") == "cta_5", (
            f"Expected last_cta_emitted='cta_5', got {mc.get('last_cta_emitted')!r}. "
            "Ensure the per-turn default-clear + conditional-set is implemented in "
            "_process_with_tool_loop."
        )

    async def test_cta5_gate_fires_via_append(self):
        """
        Triangulation: even when LLM response doesn't end with CTA 5 but preconditions
        are met, _enforce_cta5_if_needed appends it → flag must still be set.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        # LLM returns text WITHOUT CTA 5 — the gate will append it
        loop_obj = _make_fake_loop_obj(
            ai_response="Las fotos de ejemplo están disponibles.",
        )

        state = _make_state({
            "precio_comunicado": True,
            "tarifa_calculada": {"datos": {"price": 100}},
            "imagenes_enviadas_codigos": ["T01"],
        })

        with (
            patch("agent.modes.pre_expediente_mode.ModeLoopConfig"),
            patch("agent.modes.pre_expediente_mode.build_mode_tool_loop", return_value=loop_obj),
            patch("agent.modes.pre_expediente_mode._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch("agent.modes.pre_expediente_mode.clear_image_tools_state"),
        ):
            node = PreExpedienteModeNode()
            result = await node._process_with_tool_loop("muéstrame", state)

        mc = result.get("mode_context", {})
        assert mc.get("last_cta_emitted") == "cta_5", (
            f"Expected last_cta_emitted='cta_5' when gate appends CTA 5, "
            f"got {mc.get('last_cta_emitted')!r}"
        )
        # Also verify CTA 5 was actually appended to the response
        assert result.get("ai_response", "").endswith(_CTA_5), (
            "CTA 5 was not appended to ai_response even though preconditions were met."
        )


# ---------------------------------------------------------------------------
# T3.3 — Non-CTA-5 turn → flag None (default clear works)
# ---------------------------------------------------------------------------

class TestNonCTA5TurnClearsFlag:
    """When preconditions are NOT met, last_cta_emitted must remain None."""

    async def test_non_cta5_turn_clears_flag(self):
        """
        T3.3:
        GIVEN prior state has last_cta_emitted="cta_5"
        AND this turn does NOT meet CTA 5 preconditions (no images)
        WHEN _process_with_tool_loop runs
        THEN result_dict["mode_context"]["last_cta_emitted"] is None
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        # LLM returns a DISCOVERY-phase response (no images sent yet)
        loop_obj = _make_fake_loop_obj(
            ai_response="El precio de homologación es 450€.",
        )

        # Prior state has stale "cta_5" but imagenes_enviadas_codigos is empty
        state = _make_state({
            "precio_comunicado": False,       # gate won't fire
            "imagenes_enviadas_codigos": [],   # empty → gate won't fire
            "last_cta_emitted": "cta_5",       # stale from prior turn
        })

        with (
            patch("agent.modes.pre_expediente_mode.ModeLoopConfig"),
            patch("agent.modes.pre_expediente_mode.build_mode_tool_loop", return_value=loop_obj),
            patch("agent.modes.pre_expediente_mode._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch("agent.modes.pre_expediente_mode.clear_image_tools_state"),
        ):
            node = PreExpedienteModeNode()
            result = await node._process_with_tool_loop("¿cuánto cuesta?", state)

        mc = result.get("mode_context", {})
        assert mc.get("last_cta_emitted") is None, (
            f"Expected last_cta_emitted=None on non-CTA-5 turn, "
            f"got {mc.get('last_cta_emitted')!r}. "
            "The per-turn default-clear must reset stale flag values."
        )


# ---------------------------------------------------------------------------
# T5.1 — Multi-turn stale flag overwrite
# ---------------------------------------------------------------------------

class TestStaleFlagOverwrittenNextTurn:
    """
    T5.1 — Multi-turn: flag set in turn T must be cleared in turn T+1 if CTA 5
    is not re-emitted.
    """

    async def test_stale_flag_overwritten_next_turn(self):
        """
        Simulates two consecutive turns:
          Turn T:   images sent + CTA 5 appended → last_cta_emitted="cta_5"
          Turn T+1: user asks Q&A (no images, no CTA 5 preconditions) → None

        This confirms D4 default-clear in T3.2 is correct and per-turn.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        # ---- Turn T: CTA 5 fired ----
        loop_obj_t = _make_fake_loop_obj(
            ai_response=f"Aquí tienes.\n\n{_CTA_5}",
        )
        state_t = _make_state({
            "precio_comunicado": True,
            "tarifa_calculada": {"datos": {"price": 100}},
            "imagenes_enviadas_codigos": ["T01"],
        })

        with (
            patch("agent.modes.pre_expediente_mode.ModeLoopConfig"),
            patch("agent.modes.pre_expediente_mode.build_mode_tool_loop", return_value=loop_obj_t),
            patch("agent.modes.pre_expediente_mode._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch("agent.modes.pre_expediente_mode.clear_image_tools_state"),
        ):
            node = PreExpedienteModeNode()
            result_t = await node._process_with_tool_loop("muéstrame fotos", state_t)

        assert result_t["mode_context"].get("last_cta_emitted") == "cta_5", (
            "Turn T should have set last_cta_emitted='cta_5'"
        )

        # ---- Turn T+1: user asks Q&A, no new images this turn ----
        # Simulate checkpoint state carrying the flag from turn T
        state_t1 = _make_state({
            **result_t["mode_context"],
            # Simulate user got the images but now asks a clarification question
            # preconditions still partially met but imagenes_enviadas_codigos is now []
            "precio_comunicado": True,
            "tarifa_calculada": {"datos": {"price": 100}},
            "imagenes_enviadas_codigos": [],  # no images this turn path
        })

        loop_obj_t1 = _make_fake_loop_obj(
            ai_response="La homologación tarda aproximadamente 2 meses.",
        )

        with (
            patch("agent.modes.pre_expediente_mode.ModeLoopConfig"),
            patch("agent.modes.pre_expediente_mode.build_mode_tool_loop", return_value=loop_obj_t1),
            patch("agent.modes.pre_expediente_mode._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch("agent.modes.pre_expediente_mode.clear_image_tools_state"),
        ):
            result_t1 = await node._process_with_tool_loop("¿cuánto tarda?", state_t1)

        mc_t1 = result_t1["mode_context"]
        assert mc_t1.get("last_cta_emitted") is None, (
            f"Turn T+1 should have cleared last_cta_emitted (stale flag from T). "
            f"Got: {mc_t1.get('last_cta_emitted')!r}"
        )
