"""
Tests for the identificar_y_resolver_elementos variant discovery injection in
presupuesto_mode.py on_tool_result.

When identificar_y_resolver_elementos returns preguntas_variantes (non-empty),
on_tool_result MUST inject a role:system message that includes:
  (a) the original user message verbatim
  (b) the list of pending variants with available options
  (c) instruction to call seleccionar_variante_por_respuesta before asking user

This injection fires at the moment variants are discovered (first turn), before
the LLM has a chance to write text directly — nudging it to execute Paso 5.5.

TDD Cycle:
  RED:   Create this file — test_on_tool_result_identificar_with_variants_injects_system_message fails
  GREEN: Add block in on_tool_result for identificar_y_resolver_elementos with preguntas_variantes
  VERIFY: This test passes; suite has no regressions
"""

import sys
import os
from typing import Any
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from agent.modes.presupuesto_mode import PresupuestoModeNode
from agent.modes.generic_loop import GenericLoopResult


# ---------------------------------------------------------------------------
# Helpers (reuse pattern from test_variant_parallel_resolution.py)
# ---------------------------------------------------------------------------


async def _capture_on_tool_result(
    node: PresupuestoModeNode,
    mode_context: dict,
    user_message: str = "quiero homologar mi placa solar y el toldo, regulador oculto en el armario",
) -> Any:
    """
    Run _process_with_generic_loop with a patched generic_llm_loop that
    intercepts the `on_tool_result` callback and saves it for direct testing.
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

    state = {
        "messages": [
            {"role": "human", "content": user_message},
        ],
        "mode_context": mode_context,
        "conversation_id": "test-conv-injection",
        "current_mode": "PRESUPUESTO_MODE",
        "retry_count": 0,
        "retry_state": {},
        "pending_images": [],
        "client_type": "particular",
        "is_first_interaction": True,
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
            await node._process_with_generic_loop(message=user_message, state=state)
        except Exception:
            pass  # We only need the callback captured

    return captured.get("on_tool_result")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_tool_result_identificar_with_variants_injects_system_message():
    """
    SCENARIO (Pepe's case):
      User: "quiero homologar mi placa solar y el toldo, regulador oculto en el armario"
      identificar_y_resolver_elementos returns preguntas_variantes = [PLACA_SOLAR, TOLDO_LAT]

    EXPECTED:
      on_tool_result returns a dict with inject_messages containing:
        - role: "system"
        - content that includes:
            (a) the original user message
            (b) the variant list (PLACA_SOLAR, TOLDO_LAT)
            (c) instruction to call seleccionar_variante_por_respuesta

    RED: This test FAILS before the implementation block is added to on_tool_result.
    GREEN: Passes after the block is implemented.
    """
    user_message = (
        "quiero homologar mi placa solar y el toldo, regulador oculto en el armario"
    )

    node = PresupuestoModeNode()
    # Empty mode_context — first turn, no pending_variants yet
    mode_context = {
        "element_codes": [],
    }

    on_tool_result = await _capture_on_tool_result(node, mode_context, user_message)
    assert on_tool_result is not None, (
        "Failed to capture on_tool_result from production"
    )

    # Build result_dict matching what identificar_y_resolver_elementos returns
    result_dict = {
        "success": True,
        "elementos_listos": [],
        "elementos_con_variantes": [
            {
                "codigo_base": "PLACA_SOLAR",
                "variantes": [
                    {"nombre": "Placa solar simple", "codigo": "PLACA_SOLAR_SIMPLE"},
                    {
                        "nombre": "Con regulador interior",
                        "codigo": "PLACA_SOLAR_REG_INT",
                    },
                    {
                        "nombre": "Con regulador exterior",
                        "codigo": "PLACA_SOLAR_REG_EXT",
                    },
                ],
                "pregunta": "¿El regulador está en el interior o maletero?",
            },
            {
                "codigo_base": "TOLDO_LAT",
                "variantes": [
                    {"nombre": "Sin galibo", "codigo": "TOLDO_SIMPLE"},
                    {"nombre": "Con galibo", "codigo": "TOLDO_GALIBO"},
                ],
                "pregunta": "¿El toldo afecta al gálibo?",
            },
        ],
        "preguntas_variantes": [
            {
                "pending_id": "pv_PLACA_SOLAR",
                "codigo_base": "PLACA_SOLAR",
                "pregunta": "¿El regulador está en el interior o maletero?",
                "opciones": [
                    "A - Placa solar simple",
                    "B - Con regulador interior",
                    "C - Con regulador exterior",
                ],
            },
            {
                "pending_id": "pv_TOLDO_LAT",
                "codigo_base": "TOLDO_LAT",
                "pregunta": "¿El toldo afecta al gálibo?",
                "opciones": ["A - Sin galibo", "B - Con galibo"],
            },
        ],
    }

    result = await on_tool_result(
        "identificar_y_resolver_elementos",
        result_dict,
        {
            "categoria_vehiculo": "aseicars-part",
            "descripcion": "placa solar y toldo",
        },
        {},
    )

    # --- Core assertions ---
    assert result is not None, (
        "on_tool_result should return inject_messages dict when "
        "identificar_y_resolver_elementos returns preguntas_variantes. "
        "This fails (RED) before the implementation block is added."
    )
    assert "inject_messages" in result, (
        f"Result should contain 'inject_messages' key, got: {result}"
    )
    msgs = result["inject_messages"]
    assert len(msgs) >= 1, "Should inject at least one message"

    # Must be a system message
    system_msgs = [m for m in msgs if m.get("role") == "system"]
    assert len(system_msgs) >= 1, (
        f"At least one injected message must have role=system, got roles: "
        f"{[m.get('role') for m in msgs]}"
    )

    content = system_msgs[0]["content"]

    # (a) Original user message included
    assert "regulador oculto en el armario" in content, (
        f"Injected system message must include the original user message text. "
        f"Content: {content[:200]}"
    )

    # (b) Variant elements listed
    assert "PLACA_SOLAR" in content, (
        f"Injected message must list PLACA_SOLAR variant. Content: {content[:300]}"
    )
    assert "TOLDO_LAT" in content, (
        f"Injected message must list TOLDO_LAT variant. Content: {content[:300]}"
    )

    # (c) Instruction to call seleccionar_variante_por_respuesta
    assert "seleccionar_variante_por_respuesta" in content, (
        f"Injected message must instruct calling seleccionar_variante_por_respuesta. "
        f"Content: {content[:300]}"
    )


@pytest.mark.asyncio
async def test_on_tool_result_identificar_empty_variants_no_injection():
    """
    SCENARIO: identificar_y_resolver_elementos returns empty preguntas_variantes
    (all elements resolved immediately, no variants needed).

    EXPECTED: on_tool_result returns None — no injection.
    """
    user_message = "quiero homologar el escape de mi moto"
    node = PresupuestoModeNode()
    mode_context = {"element_codes": []}

    on_tool_result = await _capture_on_tool_result(node, mode_context, user_message)
    assert on_tool_result is not None

    result_dict = {
        "success": True,
        "elementos_listos": [
            {"codigo": "ESCAPE", "nombre": "Escape"},
        ],
        "elementos_con_variantes": [],
        "preguntas_variantes": [],
    }

    result = await on_tool_result(
        "identificar_y_resolver_elementos",
        result_dict,
        {"categoria_vehiculo": "motos-part", "descripcion": "escape"},
        {},
    )

    assert result is None, (
        f"Should return None when preguntas_variantes is empty, got: {result}"
    )


@pytest.mark.asyncio
async def test_on_tool_result_identificar_missing_preguntas_no_injection():
    """
    SCENARIO: identificar_y_resolver_elementos result has no preguntas_variantes key at all.
    EXPECTED: on_tool_result returns None.
    """
    user_message = "homologar escape"
    node = PresupuestoModeNode()
    mode_context = {"element_codes": []}

    on_tool_result = await _capture_on_tool_result(node, mode_context, user_message)
    assert on_tool_result is not None

    result_dict = {
        "success": True,
        "elementos_listos": [{"codigo": "ESCAPE", "nombre": "Escape"}],
    }

    result = await on_tool_result(
        "identificar_y_resolver_elementos",
        result_dict,
        {"categoria_vehiculo": "motos-part", "descripcion": "escape"},
        {},
    )

    assert result is None, (
        f"Should return None when preguntas_variantes key is absent, got: {result}"
    )


@pytest.mark.asyncio
async def test_other_tool_names_not_affected():
    """
    SCENARIO: on_tool_result is called for a DIFFERENT tool name (not identificar).
    EXPECTED: The new block does NOT fire; function continues to existing logic.
    """
    user_message = "quiero ver las fotos"
    node = PresupuestoModeNode()
    mode_context = {"element_codes": ["ESCAPE"]}

    on_tool_result = await _capture_on_tool_result(node, mode_context, user_message)
    assert on_tool_result is not None

    result_dict = {
        "success": True,
        "message": "Imágenes enviadas",
    }

    result = await on_tool_result(
        "enviar_imagenes_ejemplo",
        result_dict,
        {"tipo": "presupuesto"},
        {},
    )

    # enviar_imagenes_ejemplo doesn't set _pending_images in this case
    # so result should still be None (no injection from variant-discovery block)
    assert result is None, (
        f"enviar_imagenes_ejemplo without images should not trigger variant injection, got: {result}"
    )
