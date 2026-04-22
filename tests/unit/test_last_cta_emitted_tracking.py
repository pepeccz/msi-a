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
    """Build minimal ConversationState dict for _process_with_tool_loop calls."""
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
        "client_type": "particular",
        "is_first_interaction": False,
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


def _patch_process_with_tool_loop_deps():
    """Return context manager that patches all external deps of _process_with_tool_loop."""
    from unittest.mock import AsyncMock, patch
    from contextlib import AsyncExitStack, contextmanager

    @contextmanager
    def _patches(loop_result_obj):
        with patch(
            "agent.modes.pre_expediente_mode._load_active_draft_quote_into_context",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "agent.modes.pre_expediente_mode.build_mode_tool_loop",
            return_value=loop_result_obj,
        ), patch(
            "agent.modes.pre_expediente_mode.clear_image_tools_state",
        ):
            yield

    return _patches


class TestCta5GateFiresFlag:
    """T3.1 — When CTA 5 is appended, last_cta_emitted must become 'cta_5'."""

    @pytest.mark.asyncio
    async def test_cta5_gate_fires_sets_flag(self) -> None:
        """
        T3.1 — GREEN assertion:
        When the tool loop returns an ai_response that does NOT end with CTA 5
        AND the preconditions (precio_comunicado+imagenes) are met,
        _enforce_cta5_if_needed appends CTA 5 and the result mode_context
        must have last_cta_emitted == "cta_5".
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        # AI response that does NOT end with CTA 5 → enforce will append it
        raw_ai_response = "Aquí tienes el resumen del presupuesto."

        loop_result = _make_loop_result(raw_ai_response)

        node = PreExpedienteModeNode()
        state = _base_state()
        patches = _patch_process_with_tool_loop_deps()

        with patches(loop_result):
            result = await node._process_with_tool_loop("dale", state)

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
        patches = _patch_process_with_tool_loop_deps()

        with patches(loop_result):
            result = await node._process_with_tool_loop("dale", state)

        assert result["mode_context"].get("last_cta_emitted") == "cta_5", (
            f"Even with passthrough, last_cta_emitted must be 'cta_5' when response ends in CTA 5, "
            f"got: {result['mode_context'].get('last_cta_emitted')!r}"
        )


# ---------------------------------------------------------------------------
# T3.3 — No-CTA-5 turn → F6: flag updated to "cta_4" or "none" per extended domain
# ---------------------------------------------------------------------------


class TestNonCta5TurnClearsFlag:
    """T3.3 (updated for F6) — last_cta_emitted is always written with extended domain values."""

    @pytest.mark.asyncio
    async def test_non_cta5_turn_enforces_cta4(self) -> None:
        """
        F1+F6 update: When imagenes_enviadas_codigos is empty AND precio_comunicado=True,
        _enforce_phase_cta fires CTA 4 (not CTA 5). last_cta_emitted must be "cta_4".
        (Previously: was a no-op and flag was None; F1 re-introduces branching.)
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        raw_ai_response = "Claro, calculo el presupuesto ahora."

        loop_result = _make_loop_result(raw_ai_response)

        node = PreExpedienteModeNode()
        # imagenes empty + precio_comunicado True → CTA 4 enforced by F1
        state = _base_state(extra_context={
            "imagenes_enviadas_codigos": [],  # EMPTY → CTA 4 branch
            "precio_comunicado": True,
            "last_cta_emitted": "cta_5",    # Stale value from prior turn
        })
        patches = _patch_process_with_tool_loop_deps()

        with patches(loop_result):
            result = await node._process_with_tool_loop("dale", state)

        assert result["mode_context"].get("last_cta_emitted") == "cta_4", (
            f"F1+F6: imagenes=[], precio=True → CTA 4 enforced, last_cta_emitted must be 'cta_4', "
            f"got: {result['mode_context'].get('last_cta_emitted')!r}"
        )

    @pytest.mark.asyncio
    async def test_non_cta5_turn_precio_not_comunicado(self) -> None:
        """
        F6 update: When precio_comunicado=False, enforcer is no-op.
        last_cta_emitted is set to "none" (the extended domain value, not Python None).
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        raw_ai_response = "Aquí tienes los detalles."

        loop_result = _make_loop_result(raw_ai_response)

        node = PreExpedienteModeNode()
        state = _base_state(extra_context={
            "precio_comunicado": False,      # Not communicated yet
            "last_cta_emitted": "cta_5",    # Stale from prior turn
        })
        patches = _patch_process_with_tool_loop_deps()

        with patches(loop_result):
            result = await node._process_with_tool_loop("dale", state)

        assert result["mode_context"].get("last_cta_emitted") == "none", (
            f"F6: precio=False, enforcer no-op → last_cta_emitted must be 'none', "
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
        T5.1 — updated for F1+F6:
        Turn T (images sent) → sets flag to "cta_5".
        Turn T+1 (images empty, precio=True) → F1 enforces CTA 4, sets flag to "cta_4".
        The stale "cta_5" is overwritten — D4 design confirmed, but with extended domain.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        node = PreExpedienteModeNode()
        patches = _patch_process_with_tool_loop_deps()

        # --- TURN T: CTA 5 fires (images sent via _base_state default) ---
        turn_t_response = "Aquí está el presupuesto."
        loop_result_t = _make_loop_result(turn_t_response)

        state_t = _base_state(extra_context={"last_cta_emitted": None})

        with patches(loop_result_t):
            result_t = await node._process_with_tool_loop("dale", state_t)

        # Turn T must set the flag to "cta_5" (images sent → CTA 5 branch)
        assert result_t["mode_context"].get("last_cta_emitted") == "cta_5", (
            f"Turn T must set last_cta_emitted='cta_5', "
            f"got: {result_t['mode_context'].get('last_cta_emitted')!r}"
        )

        # --- TURN T+1: imagenes empty → F1 enforces CTA 4, flag → "cta_4" ---
        turn_t1_response = "Claro, ¿tienes alguna otra pregunta?"
        loop_result_t1 = _make_loop_result(turn_t1_response)

        state_t1 = _base_state(extra_context={
            "imagenes_enviadas_codigos": [],  # empty → CTA 4 branch (F1)
            "precio_comunicado": True,
            "last_cta_emitted": result_t["mode_context"].get("last_cta_emitted"),  # "cta_5"
        })

        with patches(loop_result_t1):
            result_t1 = await node._process_with_tool_loop("dale", state_t1)

        # Turn T+1 must OVERWRITE stale "cta_5" → "cta_4" (F1+F6 update)
        assert result_t1["mode_context"].get("last_cta_emitted") == "cta_4", (
            f"Turn T+1 must overwrite stale 'cta_5' to 'cta_4' (F1: imagenes=[], precio=True), "
            f"got: {result_t1['mode_context'].get('last_cta_emitted')!r}. "
            "F6: last_cta_emitted always written with extended domain values."
        )
