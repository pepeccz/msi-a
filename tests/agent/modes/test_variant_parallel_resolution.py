"""
Tests for parallel variant resolution in presupuesto_mode.py on_tool_result.

These tests verify that when the LLM calls seleccionar_variante_por_respuesta
MULTIPLE TIMES in a single iteration (parallel tool calls), the on_tool_result
callback correctly accumulates resolutions across all calls and triggers the
inject_messages/rebind_tools response ONLY after ALL original pending variants
are resolved.

Bug context (fix/variant-parallel-resolution):
  - User: "B y A" → LLM makes 2 parallel calls: call-1 resolves PLACA_SOLAR,
    call-2 resolves TOLDO_LAT.
  - Old code: each call evaluated `all_explicitly_resolved` independently by
    looking at `_internal_flags.pending_variants` from THAT call's result alone.
    Because the ContextVar was not updated between calls, call-2's flags showed
    PLACA_SOLAR as "pending" → all_explicitly_resolved=False → no injection.
  - Fix (Option A): accumulator dict `_resolved_variants_this_turn` in the
    closure scope. When both codes are in the accumulator, injection fires.

Test strategy:
  We intercept the `on_tool_result` callback that presupuesto_mode passes to
  generic_llm_loop, capture it, and invoke it directly multiple times to
  simulate parallel tool calls. This exercises the REAL production closure,
  not a re-implementation.

  The interception uses a patch on `generic_llm_loop` that saves the
  `on_tool_result` kwarg before returning a minimal result.

  RED: Without the fix, tests 1 and 4 fail (parallel calls don't trigger injection).
  GREEN: With the fix, all tests pass.
"""

import json
import sys
import os
from typing import Any
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from agent.modes.presupuesto_mode import PresupuestoModeNode
from agent.modes.generic_loop import GenericLoopResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pending_variant(codigo_base: str) -> dict:
    return {
        "pending_id": f"pv_{codigo_base}",
        "codigo_base": codigo_base,
        "pregunta": f"¿Qué variante de {codigo_base}?",
        "opciones": ["A", "B"],
        "status": "pending",
        "cantidad_total": 1,
        "cantidad_resuelta": 0,
        "cantidad_pendiente": 1,
        "resoluciones": [],
    }


def _make_resolved_flags(
    codigo_base: str, variant_code: str, all_codes: list[str]
) -> dict:
    """
    Build _internal_flags as they appear in real tool results when a single call
    resolves only ITS OWN codigo_base. All other codes remain "pending" — this
    simulates the stale ContextVar snapshot that causes the bug.
    """
    pending_variants = []
    for code in all_codes:
        if code == codigo_base:
            pending_variants.append(
                {
                    "pending_id": f"pv_{code}",
                    "codigo_base": code,
                    "status": "resolved",
                    "cantidad_total": 1,
                    "cantidad_resuelta": 1,
                    "cantidad_pendiente": 0,
                    "resoluciones": [
                        {
                            "variant_code": variant_code,
                            "quantity": 1,
                            "confidence": 0.9,
                            "source": "user_explicit",
                        }
                    ],
                }
            )
        else:
            # STALE: this call didn't know about other codes being resolved
            pending_variants.append(
                {
                    "pending_id": f"pv_{code}",
                    "codigo_base": code,
                    "status": "pending",
                    "cantidad_total": 1,
                    "cantidad_resuelta": 0,
                    "cantidad_pendiente": 1,
                    "resoluciones": [],
                }
            )
    return {"pending_variants": pending_variants}


def _make_tool_result(
    codigo_base: str, variant_code: str, all_codes: list[str]
) -> dict:
    """Full tool result dict for a resolved seleccionar_variante_por_respuesta call."""
    return {
        "selected_variant": variant_code,
        "confidence": 0.9,
        "name": f"Variante {variant_code}",
        "_internal_flags": _make_resolved_flags(codigo_base, variant_code, all_codes),
    }


def _make_clarification_result(codigo_base: str, all_codes: list[str]) -> dict:
    """Tool result where the variant needs clarification."""
    pending_variants = []
    for code in all_codes:
        status = "needs_clarification" if code == codigo_base else "pending"
        pending_variants.append(
            {
                "pending_id": f"pv_{code}",
                "codigo_base": code,
                "status": status,
                "resoluciones": [],
            }
        )
    return {
        "needs_clarification": True,
        "clarification_question": "¿Cuál exactamente?",
        "_internal_flags": {"pending_variants": pending_variants},
    }


def _make_error_result(codigo_base: str, all_codes: list[str]) -> dict:
    """Tool result with error=True."""
    return {
        "error": True,
        "message": "Error: elemento no encontrado",
        "_internal_flags": _make_resolved_flags(codigo_base, "SOME_CODE", all_codes),
    }


async def _capture_on_tool_result(node: PresupuestoModeNode, mode_context: dict) -> Any:
    """
    Run _process_with_generic_loop with a patched generic_llm_loop that
    intercepts the `on_tool_result` callback and saves it for direct testing.

    This exercises the REAL production closure from presupuesto_mode.py —
    not a re-implementation in the test.
    """
    captured = {}

    async def fake_generic_llm_loop(**kwargs):
        captured["on_tool_result"] = kwargs.get("on_tool_result")
        return GenericLoopResult(
            ai_response="ok",
            context_updates={},
            tools_called=set(),
            exit_reason="response",
        )

    # Build minimal ConversationState for _process_with_generic_loop(self, message, state)
    state = {
        "messages": [],
        "mode_context": mode_context,
        "conversation_id": "test-conv",
        "current_mode": "PRESUPUESTO_MODE",
        "retry_count": 0,
        "retry_state": {},
        "pending_images": [],
        "client_type": "particular",
        "is_first_interaction": False,
    }

    with (
        patch(
            "agent.modes.presupuesto_mode.generic_llm_loop",
            side_effect=fake_generic_llm_loop,
        ),
        patch(
            "agent.modes.presupuesto_mode.assemble_system_prompt", return_value="sys"
        ),
        patch("agent.modes.presupuesto_mode.set_current_state"),
        patch("agent.modes.presupuesto_mode.clear_current_state"),
        patch("agent.modes.presupuesto_mode.set_current_state_for_image_tools"),
    ):
        try:
            await node._process_with_generic_loop(message="B y A", state=state)
        except Exception:
            pass  # We only need the callback captured before any error

    return captured.get("on_tool_result")


# ---------------------------------------------------------------------------
# Tests — exercise the REAL production closure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_parallel_calls_both_resolved_triggers_injection():
    """
    SCENARIO (Pepe's bug): User says "B y A" → LLM makes 2 parallel calls.
      - Call 1 result: PLACA_SOLAR:resolved, TOLDO_LAT:pending (stale ContextVar)
      - Call 2 result: TOLDO_LAT:resolved, PLACA_SOLAR:pending (stale ContextVar)

    EXPECTED (with fix):
      - Call 1 → None (accumulator: {PLACA_SOLAR} — only 1 of 2)
      - Call 2 → injection dict (accumulator: {PLACA_SOLAR, TOLDO_LAT} = all)

    RED without fix: Call 2 returns None (all_explicitly_resolved=False because
    PLACA_SOLAR appears "pending" in Call 2's flags → injection never fires).
    """
    node = PresupuestoModeNode()
    pending_codes = ["PLACA_SOLAR", "TOLDO_LAT"]
    mode_context = {
        "element_codes": [],
        "pending_variants": [_make_pending_variant(c) for c in pending_codes],
    }

    on_tool_result = await _capture_on_tool_result(node, mode_context)
    assert on_tool_result is not None, (
        "Failed to capture on_tool_result from production"
    )

    # Call 1: PLACA_SOLAR resolved (TOLDO_LAT still "pending" in flags — stale)
    result1 = await on_tool_result(
        "seleccionar_variante_por_respuesta",
        _make_tool_result("PLACA_SOLAR", "PLACA_SOLAR_SIMPLE", pending_codes),
        {
            "categoria_vehiculo": "motos-part",
            "codigo_elemento_base": "PLACA_SOLAR",
            "respuesta_usuario": "B",
        },
        {},
    )

    # Call 2: TOLDO_LAT resolved (PLACA_SOLAR still "pending" in flags — stale!)
    result2 = await on_tool_result(
        "seleccionar_variante_por_respuesta",
        _make_tool_result("TOLDO_LAT", "TOLDO_LAT_RETRACTIL", pending_codes),
        {
            "categoria_vehiculo": "motos-part",
            "codigo_elemento_base": "TOLDO_LAT",
            "respuesta_usuario": "A",
        },
        {},
    )

    assert result1 is None, (
        f"Call 1 should return None (only 1/2 in accumulator), got: {result1}"
    )
    assert result2 is not None, (
        "Call 2 should trigger injection when both variants are accumulated. "
        "This fails without the fix (old code: all_explicitly_resolved=False for each call)."
    )
    assert "inject_messages" in result2
    assert "rebind_tools" in result2
    assert result2["rebind_tool_choice"] is None

    msg = result2["inject_messages"][0]["content"]
    assert "PLACA_SOLAR_SIMPLE" in msg, f"Missing PLACA_SOLAR_SIMPLE in: {msg}"
    assert "TOLDO_LAT_RETRACTIL" in msg, f"Missing TOLDO_LAT_RETRACTIL in: {msg}"
    assert "calcular_tarifa_con_elementos" in msg


@pytest.mark.asyncio
async def test_first_call_only_no_injection():
    """
    SCENARIO: Only PLACA_SOLAR resolved this turn (no call for TOLDO_LAT yet).
    EXPECTED: on_tool_result returns None (accumulator has only 1 of 2).
    """
    node = PresupuestoModeNode()
    pending_codes = ["PLACA_SOLAR", "TOLDO_LAT"]
    mode_context = {
        "element_codes": [],
        "pending_variants": [_make_pending_variant(c) for c in pending_codes],
    }

    on_tool_result = await _capture_on_tool_result(node, mode_context)
    assert on_tool_result is not None

    result = await on_tool_result(
        "seleccionar_variante_por_respuesta",
        _make_tool_result("PLACA_SOLAR", "PLACA_SOLAR_SIMPLE", pending_codes),
        {
            "categoria_vehiculo": "motos-part",
            "codigo_elemento_base": "PLACA_SOLAR",
            "respuesta_usuario": "B",
        },
        {},
    )

    assert result is None, (
        f"Expected None when only 1 of 2 variants resolved, got: {result}"
    )


@pytest.mark.asyncio
async def test_needs_clarification_does_not_accumulate():
    """
    SCENARIO: Call returns needs_clarification (status != "resolved").
    EXPECTED: Variant NOT added to accumulator; no injection — even with 1 pending.
    """
    node = PresupuestoModeNode()
    pending_codes = ["PLACA_SOLAR"]
    mode_context = {
        "element_codes": [],
        "pending_variants": [_make_pending_variant(c) for c in pending_codes],
    }

    on_tool_result = await _capture_on_tool_result(node, mode_context)
    assert on_tool_result is not None

    result = await on_tool_result(
        "seleccionar_variante_por_respuesta",
        _make_clarification_result("PLACA_SOLAR", pending_codes),
        {
            "categoria_vehiculo": "motos-part",
            "codigo_elemento_base": "PLACA_SOLAR",
            "respuesta_usuario": "no sé",
        },
        {},
    )

    assert result is None, (
        f"needs_clarification should not trigger injection, got: {result}"
    )


@pytest.mark.asyncio
async def test_single_pending_single_call_triggers_injection():
    """
    SCENARIO: One pending variant, one call that resolves it.
    EXPECTED: Injection fires (regression test — happy path preserved after fix).
    """
    node = PresupuestoModeNode()
    pending_codes = ["PLACA_SOLAR"]
    mode_context = {
        "element_codes": [],
        "pending_variants": [_make_pending_variant(c) for c in pending_codes],
    }

    on_tool_result = await _capture_on_tool_result(node, mode_context)
    assert on_tool_result is not None

    result = await on_tool_result(
        "seleccionar_variante_por_respuesta",
        _make_tool_result("PLACA_SOLAR", "PLACA_SOLAR_SIMPLE", pending_codes),
        {
            "categoria_vehiculo": "motos-part",
            "codigo_elemento_base": "PLACA_SOLAR",
            "respuesta_usuario": "la simple",
        },
        {},
    )

    assert result is not None, (
        "Single pending + single resolved call should trigger injection"
    )
    assert "inject_messages" in result
    assert "rebind_tools" in result
    msg = result["inject_messages"][0]["content"]
    assert "PLACA_SOLAR_SIMPLE" in msg
    assert "calcular_tarifa_con_elementos" in msg


@pytest.mark.asyncio
async def test_error_result_does_not_accumulate():
    """
    SCENARIO: Call with error=True — the tool failed.
    EXPECTED: Error result is NOT added to accumulator; no injection.
    The condition `not result_dict.get("error")` must guard the accumulation path.
    """
    node = PresupuestoModeNode()
    pending_codes = ["PLACA_SOLAR"]
    mode_context = {
        "element_codes": [],
        "pending_variants": [_make_pending_variant(c) for c in pending_codes],
    }

    on_tool_result = await _capture_on_tool_result(node, mode_context)
    assert on_tool_result is not None

    result = await on_tool_result(
        "seleccionar_variante_por_respuesta",
        _make_error_result("PLACA_SOLAR", pending_codes),
        {
            "categoria_vehiculo": "motos-part",
            "codigo_elemento_base": "PLACA_SOLAR",
            "respuesta_usuario": "X",
        },
        {},
    )

    assert result is None, f"Error result should not trigger injection, got: {result}"
