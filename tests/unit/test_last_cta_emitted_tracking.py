"""
T3 + T5 — last_cta_emitted flag lifecycle in _process_with_tool_loop.

Spec: last_cta_emitted Flag Lifecycle
  T3.1: CTA 5 gate fires → flag="cta_5" in result mode_context
  T3.3: No-CTA-5 turn → flag=None (default clear)
  T5.1: Stale flag from prior turn → overwritten to None next turn

Design D3 + D4:
  In _process_with_tool_loop (~line 703 in pre_expediente_mode.py):
    BEFORE CTA 5 gate: updated_context["last_cta_emitted"] = None   (default clear)
    AFTER gate, if response ends with _CTA_5: updated_context["last_cta_emitted"] = "cta_5"
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CTA_5 = "¿Abrimos expediente o tienes alguna duda?"


def _base_state(extra_context: dict | None = None) -> dict:
    """Build minimal ConversationState dict for _process_message calls."""
    mc = {
        "precio_comunicado": True,
        "tarifa_calculada": {"datos": {"price": 450.0}},
        "imagenes_enviadas_codigos": ["T01"],
        "element_codes": ["ESCAPE"],
        "categoria_slug": "motos-part",
        "last_cta_emitted": None,
    }
    if extra_context:
        mc.update(extra_context)
    return {
        "conversation_id": "test-cta-flag-01",
        "user_phone": "+34600000099",
        "messages": [],
        "mode_context": mc,
        "current_mode": "PRE_EXPEDIENTE_MODE",
        "user_message": "dale",
    }


def _make_loop_result(ai_response: str) -> MagicMock:
    """Build a fake loop_result_obj whose graph.ainvoke returns the given ai_response."""
    loop_result = MagicMock()
    loop_result.graph = MagicMock()
    loop_result.graph.ainvoke = AsyncMock(return_value={
        "ai_response": ai_response,
        "exit_reason": "response",
        "tools_called": [],
        "pending_state_updates": {},
    })
    loop_result.recursion_limit = 25
    return loop_result


# ---------------------------------------------------------------------------
# T3.1 — CTA 5 gate fires → flag="cta_5"
# ---------------------------------------------------------------------------


class TestCta5GateFiresFlag:
    """T3.1 — When CTA 5 is appended, last_cta_emitted must become 'cta_5'."""

    @pytest.mark.asyncio
    async def test_cta5_gate_fires_sets_flag(self) -> None:
        """
        T3.1 — GREEN assertion:
        When the tool loop returns an ai_response that ends with canonical CTA 5
        AND the preconditions (precio_comunicado+imagenes) are met,
        _enforce_cta5_if_needed appends/keeps CTA 5 and the result mode_context
        must have last_cta_emitted == "cta_5".
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        # AI response that does NOT end with CTA 5 → enforce will append it
        raw_ai_response = "Aquí tienes el resumen del presupuesto."

        loop_result = _make_loop_result(raw_ai_response)

        node = PreExpedienteModeNode()
        state = _base_state()

        with patch(
            "agent.modes.pre_expediente_mode.build_mode_tool_loop",
            return_value=loop_result,
        ):
            result = await node._process_message(state)

        # After _enforce_cta5_if_needed, the response must end with CTA 5
        assert result["ai_response"].endswith(_CTA_5), (
            f"Expected ai_response ending with CTA 5, got: {result['ai_response']!r}"
        )
        # And the flag must be set
        assert result["mode_context"].get("last_cta_emitted") == "cta_5", (
            f"Expected last_cta_emitted='cta_5', got: "
            f"{result['mode_context'].get('last_cta_emitted')!r}"
        )

    @pytest.mark.asyncio
    async def test_cta5_gate_fires_when_response_already_ends_with_cta5(self) -> None:
        """
        Triangulation T3.1b: LLM already ends with canonical CTA 5 →
        _enforce passthrough; flag still set to "cta_5".
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        raw_ai_response = f"Aquí tienes el presupuesto.\n\n{_CTA_5}"

        loop_result = _make_loop_result(raw_ai_response)

        node = PreExpedienteModeNode()
        state = _base_state()

        with patch(
            "agent.modes.pre_expediente_mode.build_mode_tool_loop",
            return_value=loop_result,
        ):
            result = await node._process_message(state)

        assert result["mode_context"].get("last_cta_emitted") == "cta_5", (
            f"Even with passthrough, last_cta_emitted must be 'cta_5' when response ends in CTA 5, "
            f"got: {result['mode_context'].get('last_cta_emitted')!r}"
        )


# ---------------------------------------------------------------------------
# T3.3 — No-CTA-5 turn → flag cleared to None
# ---------------------------------------------------------------------------


class TestNonCta5TurnClearsFlag:
    """T3.3 — When CTA 5 preconditions are NOT met, flag must be None."""

    @pytest.mark.asyncio
    async def test_non_cta5_turn_clears_flag(self) -> None:
        """
        T3.3 — GREEN assertion:
        When imagenes_enviadas_codigos is empty (preconditions not met),
        _enforce_cta5_if_needed is a no-op and last_cta_emitted must be None.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        raw_ai_response = "Claro, calculo el presupuesto ahora."

        loop_result = _make_loop_result(raw_ai_response)

        node = PreExpedienteModeNode()
        # Mode context WITHOUT imagenes → CTA 5 gate won't fire
        state = _base_state(extra_context={
            "imagenes_enviadas_codigos": [],  # EMPTY — CTA 5 gate won't activate
            "last_cta_emitted": "cta_5",    # Stale value from prior turn
        })

        with patch(
            "agent.modes.pre_expediente_mode.build_mode_tool_loop",
            return_value=loop_result,
        ):
            result = await node._process_message(state)

        assert result["mode_context"].get("last_cta_emitted") is None, (
            f"Non-CTA-5 turn must clear last_cta_emitted to None, "
            f"got: {result['mode_context'].get('last_cta_emitted')!r}"
        )

    @pytest.mark.asyncio
    async def test_non_cta5_turn_precio_not_comunicado(self) -> None:
        """
        Triangulation T3.3b: When precio_comunicado=False, CTA 5 gate won't fire.
        Flag must be None even if prior state had "cta_5".
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        raw_ai_response = "Aquí tienes los detalles."

        loop_result = _make_loop_result(raw_ai_response)

        node = PreExpedienteModeNode()
        state = _base_state(extra_context={
            "precio_comunicado": False,      # Not communicated yet
            "last_cta_emitted": "cta_5",    # Stale from prior turn
        })

        with patch(
            "agent.modes.pre_expediente_mode.build_mode_tool_loop",
            return_value=loop_result,
        ):
            result = await node._process_message(state)

        assert result["mode_context"].get("last_cta_emitted") is None, (
            f"When precio_comunicado=False, last_cta_emitted must be None, "
            f"got: {result['mode_context'].get('last_cta_emitted')!r}"
        )


# ---------------------------------------------------------------------------
# T5.1 — Stale flag overwritten next turn (multi-turn isolation)
# ---------------------------------------------------------------------------


class TestStaleFlagOverwrittenNextTurn:
    """T5.1 — Stale last_cta_emitted from turn T is overwritten in turn T+1."""

    @pytest.mark.asyncio
    async def test_stale_flag_overwritten_next_turn(self) -> None:
        """
        T5.1 — GREEN assertion:
        Turn T sets flag to "cta_5". Turn T+1 does NOT meet CTA 5 conditions.
        After turn T+1, last_cta_emitted must be None (not "cta_5").

        This confirms D4 design: default-clear to None at start of each turn,
        overwrite only when the gate fires.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        node = PreExpedienteModeNode()

        # --- TURN T: CTA 5 fires ---
        turn_t_response = "Aquí está el presupuesto."
        loop_result_t = _make_loop_result(turn_t_response)

        state_t = _base_state(extra_context={"last_cta_emitted": None})

        with patch(
            "agent.modes.pre_expediente_mode.build_mode_tool_loop",
            return_value=loop_result_t,
        ):
            result_t = await node._process_message(state_t)

        # Turn T must set the flag
        assert result_t["mode_context"].get("last_cta_emitted") == "cta_5", (
            f"Turn T must set last_cta_emitted='cta_5', "
            f"got: {result_t['mode_context'].get('last_cta_emitted')!r}"
        )

        # --- TURN T+1: Conditions not met (imagenes empty) ---
        turn_t1_response = "Claro, ¿tienes alguna otra pregunta?"
        loop_result_t1 = _make_loop_result(turn_t1_response)

        # State T+1 inherits last_cta_emitted="cta_5" from the prior turn
        state_t1 = _base_state(extra_context={
            "imagenes_enviadas_codigos": [],  # CTA 5 gate won't fire
            "last_cta_emitted": result_t["mode_context"].get("last_cta_emitted"),  # "cta_5"
        })

        with patch(
            "agent.modes.pre_expediente_mode.build_mode_tool_loop",
            return_value=loop_result_t1,
        ):
            result_t1 = await node._process_message(state_t1)

        # Turn T+1 must CLEAR the stale flag
        assert result_t1["mode_context"].get("last_cta_emitted") is None, (
            f"Turn T+1 must clear stale last_cta_emitted to None, "
            f"got: {result_t1['mode_context'].get('last_cta_emitted')!r}. "
            "D4: default-clear at turn start prevents stale-flag persistence."
        )
