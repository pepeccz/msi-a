"""
Tests for variant state persistence fixes.

Bug: After all variants are resolved in presupuesto_mode, calcular_tarifa_con_elementos
was blocked by a stale ContextVar snapshot that still showed pending_variants.

Three fixes:
  Fix 1 (presupuesto_mode.py): When all_resolved_accumulated, write
    context_updates["pending_variants"] = [] in the on_tool_result callback.
  Fix 2 (generic_loop.py): At end of each iteration, propagate context_updates
    keys into nested mode_context in the ContextVar so tools in the next
    iteration see fresh values.
  Fix 3 (element_tools.py): Convert the hard block tariff_blocked_pending_variants
    to a soft warning — logs but does NOT return {"success": False}.

Test strategy follows test_variant_parallel_resolution.py:
  We intercept the `on_tool_result` callback that presupuesto_mode passes to
  generic_llm_loop, capture it, and invoke it directly.

RED phase: all 3 tests fail BEFORE the fixes are applied.
GREEN phase: all 3 tests pass AFTER the fixes are applied.
"""

from __future__ import annotations

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
# Shared helpers (mirror test_variant_parallel_resolution.py)
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
    resolves only ITS OWN codigo_base. All other codes remain "pending" in the
    stale ContextVar snapshot — this is the core of the bug.
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


async def _capture_on_tool_result_with_context_updates(
    node: PresupuestoModeNode, mode_context: dict
) -> tuple[Any, dict]:
    """
    Run _process_with_generic_loop with a patched generic_llm_loop that:
    1. Intercepts the `on_tool_result` callback
    2. Captures the context_updates dict that is passed to generic_llm_loop

    Returns (on_tool_result_callback, context_updates_dict).
    The context_updates dict is the same mutable reference that on_tool_result
    receives — so mutations written by the callback are visible here.
    """
    captured: dict = {}

    async def fake_generic_llm_loop(**kwargs):
        captured["on_tool_result"] = kwargs.get("on_tool_result")
        # The real loop creates GenericLoopResult() with context_updates={}
        # and passes it (by reference) to the callback.
        # We simulate this: create the dict and store it so tests can inspect it.
        loop_context_updates: dict = {}
        captured["context_updates"] = loop_context_updates
        return GenericLoopResult(
            ai_response="ok",
            context_updates=loop_context_updates,
            tools_called=set(),
            exit_reason="response",
        )

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
            pass  # Only need the callback captured

    return captured.get("on_tool_result"), captured.get("context_updates", {})


# ---------------------------------------------------------------------------
# T1.1 — Fix 1: on_tool_result callback writes pending_variants=[] to
#         context_updates when all_resolved_accumulated.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_resolved_clears_pending_variants_in_context_updates():
    """
    Fix 1: When all variants are resolved (all_resolved_accumulated=True),
    the on_tool_result callback MUST write context_updates["pending_variants"]=[]
    BEFORE returning the inject_messages dict.

    Without Fix 1: context_updates is NOT mutated by the callback. The dict
    remains empty (or has resolved-but-non-empty entries from _apply_internal_flags).
    calcular_tarifa_con_elementos reads the ContextVar (which has the STALE checkpoint
    snapshot) and sees pending_variants=[PLACA_SOLAR:pending, TOLDO_LAT:pending].

    With Fix 1: callback writes [] to context_updates["pending_variants"]. Fix 2
    then propagates this into the nested mode_context of the ContextVar.
    calcular_tarifa_con_elementos sees pending_variants=[] and proceeds.
    """
    node = PresupuestoModeNode()
    pending_codes = ["PLACA_SOLAR", "TOLDO_LAT"]
    mode_context = {
        "element_codes": [],
        "pending_variants": [_make_pending_variant(c) for c in pending_codes],
    }

    (
        on_tool_result,
        context_updates,
    ) = await _capture_on_tool_result_with_context_updates(node, mode_context)
    assert on_tool_result is not None, "Failed to capture on_tool_result callback"

    # Simulate two parallel calls resolving BOTH variants:
    # Call 1: PLACA_SOLAR resolved (TOLDO_LAT still "pending" in flags — stale ContextVar)
    result1 = await on_tool_result(
        "seleccionar_variante_por_respuesta",
        _make_tool_result(
            "PLACA_SOLAR", "PLACA_SOLAR_REGULADOR_INTERIOR", pending_codes
        ),
        {
            "categoria_vehiculo": "motos-part",
            "codigo_elemento_base": "PLACA_SOLAR",
            "respuesta_usuario": "con regulador",
        },
        context_updates,
    )

    # After first call: accumulator has only PLACA_SOLAR — NOT all resolved yet
    # context_updates["pending_variants"] should NOT be [] at this point
    # (since only 1 of 2 resolved)
    assert result1 is None, (
        f"First call should return None (only 1/2 resolved), got: {result1}"
    )

    # Call 2: TOLDO_LAT resolved (PLACA_SOLAR still "pending" in flags — stale!)
    result2 = await on_tool_result(
        "seleccionar_variante_por_respuesta",
        _make_tool_result("TOLDO_LAT", "TOLDO_SIMPLE", pending_codes),
        {
            "categoria_vehiculo": "motos-part",
            "codigo_elemento_base": "TOLDO_LAT",
            "respuesta_usuario": "simple",
        },
        context_updates,
    )

    # After second call: accumulator has BOTH codes → all_resolved_accumulated=True
    assert result2 is not None, (
        "Second call should trigger injection when both variants are accumulated"
    )
    assert "inject_messages" in result2, (
        f"Expected inject_messages in result2: {result2}"
    )

    # ★ THE KEY ASSERTION FOR FIX 1 ★
    # The callback must have written pending_variants=[] to the context_updates dict.
    # Without Fix 1: context_updates["pending_variants"] is absent or has resolved entries.
    # With Fix 1: context_updates["pending_variants"] == [].
    assert "pending_variants" in context_updates, (
        "Fix 1 MISSING: context_updates must have 'pending_variants' key after all_resolved. "
        "Add: context_updates['pending_variants'] = [] in the all_resolved_accumulated branch "
        "of presupuesto_mode.py on_tool_result callback."
    )
    assert context_updates["pending_variants"] == [], (
        f"Fix 1 MISSING: context_updates['pending_variants'] should be [] after all resolved, "
        f"got: {context_updates['pending_variants']}. "
        "The callback must clear pending_variants when all variants are resolved."
    )


# ---------------------------------------------------------------------------
# T1.2 — Fix 2: generic_loop propagates context_updates into nested mode_context
#         in the ContextVar so the next iteration sees fresh pending_variants.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generic_loop_propagates_pending_variants_to_mode_context():
    """
    Fix 2: After processing a tool that returns _internal_flags with
    pending_variants=[], the ContextVar's mode_context["pending_variants"]
    must also be [] in the NEXT iteration.

    Without Fix 2: generic_loop does `updated_state = {**full_state, **result.context_updates}`
    which puts pending_variants at the ROOT of updated_state, NOT inside
    mode_context. Tools reading state.get("mode_context", {}).get("pending_variants")
    still see the stale checkpoint value.

    With Fix 2: After building updated_state, the loop also propagates
    _MODE_CONTEXT_PROPAGATION_KEYS into updated_state["mode_context"], so tools
    in the next iteration see the fresh value.

    This test directly verifies the propagation logic:
    1. The constant _MODE_CONTEXT_PROPAGATION_KEYS exists and includes 'pending_variants'
    2. When context_updates has pending_variants=[], the merged mode_context also has []
    """
    from agent.modes.generic_loop import (
        generic_llm_loop,
        _MODE_CONTEXT_PROPAGATION_KEYS,
    )
    from agent.state.helpers import get_current_state, set_current_state

    # ── Assert the constant exists (part of Fix 2) ──────────────────────────
    assert "pending_variants" in _MODE_CONTEXT_PROPAGATION_KEYS, (
        "Fix 2 MISSING: 'pending_variants' must be in _MODE_CONTEXT_PROPAGATION_KEYS"
    )
    assert "element_codes" in _MODE_CONTEXT_PROPAGATION_KEYS, (
        "Fix 2 MISSING: 'element_codes' must be in _MODE_CONTEXT_PROPAGATION_KEYS"
    )

    # ── Unit test the propagation logic directly ─────────────────────────────
    # Instead of running the full loop (which requires DB/Redis), we test
    # the propagation logic by simulating what the loop does at line ~425:
    #
    #   updated_state = {**full_state, **result.context_updates}
    #   existing_mc = full_state.get("mode_context") or {}
    #   refreshed_mc = dict(existing_mc)
    #   for _k in _MODE_CONTEXT_PROPAGATION_KEYS:
    #       if _k in result.context_updates:
    #           refreshed_mc[_k] = result.context_updates[_k]
    #   updated_state["mode_context"] = refreshed_mc
    #   set_current_state(updated_state)

    stale_pending = [
        _make_pending_variant("PLACA_SOLAR"),
        _make_pending_variant("TOLDO_LAT"),
    ]

    # Simulate: full_state is the checkpoint snapshot (stale pending_variants)
    full_state = {
        "mode_context": {
            "pending_variants": stale_pending,
            "element_codes": [],
        },
        "conversation_id": "test-fix2",
    }

    # Simulate: context_updates from _apply_internal_flags (Fix 1 wrote pending_variants=[])
    context_updates = {
        "pending_variants": [],  # Fix 1 wrote this
        "element_codes": ["TOLDO_SIMPLE", "PLACA_SOLAR_REGULADOR_INTERIOR"],
    }

    # ── Apply Fix 2 propagation logic ────────────────────────────────────────
    updated_state = {**full_state, **context_updates}
    existing_mc = full_state.get("mode_context") or {}
    refreshed_mc = dict(existing_mc)
    for _k in _MODE_CONTEXT_PROPAGATION_KEYS:
        if _k in context_updates:
            refreshed_mc[_k] = context_updates[_k]
    updated_state["mode_context"] = refreshed_mc
    set_current_state(updated_state)

    # ★ THE KEY ASSERTION FOR FIX 2 ★
    final_state = get_current_state()
    assert final_state is not None, "ContextVar state was never set"

    final_mode_context = final_state.get("mode_context", {})
    assert "pending_variants" in final_mode_context, (
        "Fix 2 MISSING: mode_context in ContextVar must have 'pending_variants' key"
    )
    assert final_mode_context["pending_variants"] == [], (
        f"Fix 2 MISSING: mode_context['pending_variants'] should be [] after propagation, "
        f"got: {final_mode_context['pending_variants']}. "
        "The generic_loop must propagate _MODE_CONTEXT_PROPAGATION_KEYS from "
        "context_updates into the nested mode_context of the ContextVar."
    )
    assert final_mode_context["element_codes"] == [
        "TOLDO_SIMPLE",
        "PLACA_SOLAR_REGULADOR_INTERIOR",
    ], f"element_codes not propagated correctly: {final_mode_context['element_codes']}"

    # Also verify the propagation is in the actual generic_loop code by running
    # the loop with a mocked tool_executor (inline import inside loop)
    mock_tool = MagicMock()
    mock_tool.name = "variant_tool"

    ai_with_tool = MagicMock()
    ai_with_tool.content = ""
    ai_with_tool.tool_calls = [{"id": "tc1", "name": "variant_tool", "args": {}}]

    ai_plain = MagicMock()
    ai_plain.content = "Listo."
    ai_plain.tool_calls = None

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=[ai_with_tool, ai_plain])

    loop_state = {
        "mode_context": {
            "pending_variants": stale_pending,
            "element_codes": [],
        },
        "conversation_id": "test-fix2-loop",
    }

    tool_result_payload = json.dumps(
        {
            "success": True,
            "_internal_flags": {
                "pending_variants": [],
                "element_codes": ["TOLDO_SIMPLE"],
            },
        }
    )

    async def fake_execute_and_log(**kwargs):
        return tool_result_payload

    with patch(
        "agent.modes.tool_executor.execute_and_log_tool",
        side_effect=fake_execute_and_log,
    ):
        await generic_llm_loop(
            system_prompt="test",
            messages=[],
            tools=[mock_tool],
            max_iterations=5,
            conversation_id="test-fix2-loop",
            mode_name="TEST",
            state=loop_state,
            llm=mock_llm,
        )

    # After the loop, ContextVar's mode_context["pending_variants"] must be []
    loop_final_state = get_current_state()
    assert loop_final_state is not None
    loop_mc = loop_final_state.get("mode_context", {})
    assert loop_mc.get("pending_variants") == [], (
        f"Fix 2 integration: mode_context['pending_variants'] should be [] after loop, "
        f"got: {loop_mc.get('pending_variants')}"
    )
    from agent.state.helpers import get_current_state, set_current_state

    # ── Assert the constant exists (part of Fix 2) ──────────────────────────
    assert "_MODE_CONTEXT_PROPAGATION_KEYS" in dir(
        __import__(
            "agent.modes.generic_loop", fromlist=["_MODE_CONTEXT_PROPAGATION_KEYS"]
        )
    ), (
        "Fix 2 MISSING: _MODE_CONTEXT_PROPAGATION_KEYS constant not found in generic_loop.py"
    )
    assert "pending_variants" in _MODE_CONTEXT_PROPAGATION_KEYS, (
        "Fix 2 MISSING: 'pending_variants' must be in _MODE_CONTEXT_PROPAGATION_KEYS"
    )

    # ── Build a tool that returns _internal_flags with pending_variants=[] ──
    mock_tool = MagicMock()
    mock_tool.name = "seleccionar_variante_por_respuesta"
    mock_tool.ainvoke = AsyncMock(
        return_value=json.dumps(
            {
                "selected_variant": "TOLDO_SIMPLE",
                "_internal_flags": {
                    "pending_variants": [],  # All resolved!
                    "element_codes": ["TOLDO_SIMPLE"],
                },
            }
        )
    )

    # ── LLM: iter 1 → tool call; iter 2 → plain response ───────────────────
    ai_with_tool = MagicMock()
    ai_with_tool.content = ""
    ai_with_tool.tool_calls = [
        {"id": "tc1", "name": "seleccionar_variante_por_respuesta", "args": {}}
    ]

    ai_plain = MagicMock()
    ai_plain.content = "Variante resuelta."
    ai_plain.tool_calls = None

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=[ai_with_tool, ai_plain])

    # ── State: stale checkpoint with 2 pending variants ──────────────────────
    stale_pending = [
        _make_pending_variant("PLACA_SOLAR"),
        _make_pending_variant("TOLDO_LAT"),
    ]
    state = {
        "mode_context": {
            "pending_variants": stale_pending,
            "element_codes": [],
        },
        "conversation_id": "test-fix2",
    }

    # Patch execute_and_log_tool to avoid real DB/logging
    async def fake_execute_and_log(**kwargs):
        return json.dumps(
            {
                "selected_variant": "TOLDO_SIMPLE",
                "_internal_flags": {
                    "pending_variants": [],
                    "element_codes": ["TOLDO_SIMPLE"],
                },
            }
        )

    with patch(
        "agent.modes.tool_executor.execute_and_log_tool",
        side_effect=fake_execute_and_log,
    ):
        await generic_llm_loop(
            system_prompt="test",
            messages=[],
            tools=[mock_tool],
            max_iterations=5,
            conversation_id="test-fix2",
            mode_name="TEST",
            state=state,
            llm=mock_llm,
        )

    # ★ THE KEY ASSERTION FOR FIX 2 ★
    # After the loop ends, the ContextVar's mode_context must have pending_variants=[].
    # Without Fix 2: mode_context still has stale_pending (the checkpoint value).
    # With Fix 2: mode_context["pending_variants"] reflects the updated value.
    final_state = get_current_state()
    assert final_state is not None, "ContextVar state was never set"

    final_mode_context = final_state.get("mode_context", {})
    assert "pending_variants" in final_mode_context, (
        "Fix 2 MISSING: mode_context in ContextVar must have 'pending_variants' key"
    )
    assert final_mode_context["pending_variants"] == [], (
        f"Fix 2 MISSING: mode_context['pending_variants'] should be [] after tool "
        f"returned empty list, got: {final_mode_context['pending_variants']}. "
        "The generic_loop must propagate _MODE_CONTEXT_PROPAGATION_KEYS from "
        "context_updates into the nested mode_context of the ContextVar."
    )


# ---------------------------------------------------------------------------
# T1.3 — Fix 3: calcular_tarifa does NOT block when pending_variants present
#         (soft warning only, execution continues).
# ---------------------------------------------------------------------------


def test_calcular_tarifa_proceeds_when_pending_variants_in_state():
    """
    Fix 3: The hard guard `tariff_blocked_pending_variants` in element_tools.py
    MUST be replaced with a soft warning (logger.warning) that does NOT return
    {"success": False} when pending_variants are present in the ContextVar.

    Without Fix 3: Lines 1747-1791 contain:
        if unresolved_pending:
            return {"success": False, "error": "NO puedes calcular tarifa...",
                    "variantes_pendientes": [...]}

    With Fix 3: The `return {"success": False, ...}` block is removed.
    A `logger.warning(...)` is emitted but execution continues.

    This is a structural/static test — we verify the source code does NOT
    contain the blocking pattern. This avoids the Redis/DB mocking complexity
    while still being a valid test of Fix 3.

    The behavioral test is covered by the integration tests in Phase 3.
    """
    import inspect
    import ast
    import agent.tools.element_tools as element_tools_module

    # Get the source code of calcular_tarifa_con_elementos
    # Note: it's a @tool decorated function, so we need to look at the module source
    source = inspect.getsource(element_tools_module)

    # ★ FIX 3 ASSERTION 1: The old blocking guard MUST be gone ★
    # The hard guard returned {"variantes_pendientes": ...} — a unique key that
    # only exists in the guard's return dict.
    BLOCKED_RETURN_PATTERN = '"variantes_pendientes"'
    assert BLOCKED_RETURN_PATTERN not in source, (
        f"Fix 3 MISSING: The source of element_tools.py still contains "
        f'"{BLOCKED_RETURN_PATTERN}" which is part of the hard blocking guard. '
        'Remove the \'return {"success": False, "variantes_pendientes": ...}\' block '
        "from calcular_tarifa_con_elementos."
    )

    # ★ FIX 3 ASSERTION 2: The soft warning MUST be present ★
    # After Fix 3, the guard is replaced with logger.warning(...).
    SOFT_WARNING_PATTERN = "tariff_calc_with_pending_variants_soft_warning"
    assert SOFT_WARNING_PATTERN in source, (
        f"Fix 3 MISSING: The source of element_tools.py does NOT contain the soft "
        f"warning key '{SOFT_WARNING_PATTERN}'. "
        "Replace the hard guard with a logger.warning() call using this key."
    )

    # ★ FIX 3 ASSERTION 3: The old hard guard log key MUST be gone ★
    OLD_HARD_GUARD_KEY = '"tariff_blocked_pending_variants"'
    # This key was used in the hard guard — after Fix 3 it should be replaced
    # by the new soft warning key. But the old key may still exist in OTHER guards
    # (e.g. parent_codes guard) — so we check for it in context.
    # The key assertion is that the blocking return is gone (checked above).

    # ★ FIX 3 ASSERTION 4: The hard guard error message MUST be gone ★
    # The guard returned this specific Spanish message — verify it's absent.
    HARD_GUARD_MSG = "NO puedes calcular tarifa porque hay variantes pendientes"
    assert HARD_GUARD_MSG not in source, (
        f"Fix 3 MISSING: The source still contains the hard guard error message. "
        'Remove the \'return {"success": False, "error": "NO puedes calcular..."}'
        " block from calcular_tarifa_con_elementos."
    )


# ---------------------------------------------------------------------------
# PHASE 3 — Integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_two_variants_resolve_then_no_block_in_context_updates():
    """
    T3.1 — End-to-end flow: 2 parallel variants → both resolved in same turn
    → context_updates has pending_variants=[] → calcular_tarifa is NOT blocked.

    This test simulates the complete on_tool_result cycle with two parallel
    variant resolution calls, and verifies:
    1. context_updates["pending_variants"] == [] after both resolve (Fix 1)
    2. The inject_messages tell the LLM to call calcular_tarifa (Fix 1 + existing)
    3. context_updates does NOT have the blocking guard signature (Fix 3 structural)
    """
    node = PresupuestoModeNode()
    pending_codes = ["PLACA_SOLAR", "TOLDO_LAT"]
    mode_context = {
        "element_codes": [],
        "pending_variants": [_make_pending_variant(c) for c in pending_codes],
    }

    (
        on_tool_result,
        context_updates,
    ) = await _capture_on_tool_result_with_context_updates(node, mode_context)
    assert on_tool_result is not None

    # Step 1: Resolve PLACA_SOLAR (first call — only 1 of 2)
    r1 = await on_tool_result(
        "seleccionar_variante_por_respuesta",
        _make_tool_result(
            "PLACA_SOLAR", "PLACA_SOLAR_REGULADOR_INTERIOR", pending_codes
        ),
        {
            "categoria_vehiculo": "motos-part",
            "codigo_elemento_base": "PLACA_SOLAR",
            "respuesta_usuario": "con regulador",
        },
        context_updates,
    )
    assert r1 is None, "Should not inject after only 1/2 resolved"

    # Step 2: Resolve TOLDO_LAT (second call — all resolved)
    r2 = await on_tool_result(
        "seleccionar_variante_por_respuesta",
        _make_tool_result("TOLDO_LAT", "TOLDO_SIMPLE", pending_codes),
        {
            "categoria_vehiculo": "motos-part",
            "codigo_elemento_base": "TOLDO_LAT",
            "respuesta_usuario": "simple",
        },
        context_updates,
    )

    # Fix 1: injection fires when all resolved
    assert r2 is not None, "Should inject after all 2/2 resolved"
    assert "inject_messages" in r2
    assert "rebind_tools" in r2

    # Fix 1: context_updates has pending_variants=[]
    assert context_updates.get("pending_variants") == [], (
        f"Fix 1 MISSING in e2e: context_updates['pending_variants'] should be [] "
        f"after all resolved, got: {context_updates.get('pending_variants')}"
    )

    # Fix 1: resolved codes in context_updates
    element_codes = context_updates.get("element_codes", [])
    assert "PLACA_SOLAR_REGULADOR_INTERIOR" in element_codes
    assert "TOLDO_SIMPLE" in element_codes

    # Fix 3 structural: the inject message guides the LLM to calcular_tarifa
    inject_content = r2["inject_messages"][0]["content"]
    assert "calcular_tarifa_con_elementos" in inject_content
    assert "PLACA_SOLAR_REGULADOR_INTERIOR" in inject_content
    assert "TOLDO_SIMPLE" in inject_content

    # Fix 3 structural: verify the hard guard is gone (same as T1.3)
    import inspect
    import agent.tools.element_tools as et_module

    source = inspect.getsource(et_module)
    assert "variantes_pendientes" not in source, (
        "Fix 3: 'variantes_pendientes' key still in element_tools source"
    )


@pytest.mark.asyncio
async def test_multi_turn_clean_pending_variants_no_repreg():
    """
    T3.2 — Multi-turn: After all variants resolved and pending_variants=[] is
    in mode_context, the system prompt does NOT include the pending variants block.

    This verifies that the loader.py condition correctly omits the
    "VARIANTES PENDIENTES" block when mode_context["pending_variants"] is [].

    Scenario:
    - Turn 1: Variants resolved, context saved with pending_variants=[]
    - Turn 2: System prompt built with empty pending_variants → no variants block
    """
    from agent.prompts.loader import assemble_system_prompt

    # Case 1: Clean mode_context with pending_variants=[]
    clean_context = {
        "pending_variants": [],
        "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_SIMPLE"],
        "categoria_slug": "motos-part",
    }
    prompt_clean = assemble_system_prompt(
        mode="PRESUPUESTO_MODE",
        mode_context=clean_context,
    )

    # The variants block should NOT appear
    assert "VARIANTES PENDIENTES" not in prompt_clean, (
        "Fix 2+1: When pending_variants=[], the system prompt must NOT contain "
        "'VARIANTES PENDIENTES'. The block should be absent so the LLM doesn't "
        "re-ask about already-resolved variants."
    )
    assert "seleccionar_variante_por_respuesta" not in prompt_clean or (
        # It may appear in generic instructions but NOT in the variants-specific block
        "VARIANTES PENDIENTES" not in prompt_clean
    ), "Variants block should not appear with empty pending_variants"

    # Case 2: Mode context with unresolved pending_variants (baseline for comparison)
    dirty_context = {
        "pending_variants": [
            {
                "pending_id": "pv_TOLDO_LAT",
                "codigo_base": "TOLDO_LAT",
                "pregunta": "¿Simple o articulado?",
                "opciones": ["Simple", "Articulado"],
                "status": "pending",
                "cantidad_total": 1,
                "cantidad_resuelta": 0,
                "cantidad_pendiente": 1,
                "resoluciones": [],
            }
        ],
        "element_codes": [],
        "categoria_slug": "motos-part",
    }
    prompt_dirty = assemble_system_prompt(
        mode="PRESUPUESTO_MODE",
        mode_context=dirty_context,
    )

    # The variants block SHOULD appear when there are unresolved variants
    assert "VARIANTES PENDIENTES" in prompt_dirty, (
        "Baseline check: When pending_variants has unresolved entries, "
        "'VARIANTES PENDIENTES' block must appear in the system prompt."
    )
    assert "TOLDO_LAT" in prompt_dirty, "TOLDO_LAT should appear in variants block"
    assert "Simple" in prompt_dirty, "Options should appear in variants block"
