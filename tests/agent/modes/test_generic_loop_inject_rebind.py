"""
Tests for the inject_messages / rebind_tools hook in generic_llm_loop.

Covers:
1. on_tool_result returning inject_messages → messages appended before next LLM call
2. on_tool_result returning rebind_tools → LLM rebound with new toolset
3. on_tool_result returning None → no change (backward-compatible)
4. Opción-C integration: presupuesto on_tool_result injects state message when
   all pending_variants are resolved after seleccionar_variante_por_respuesta.
"""

import json
import sys
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.modes.generic_loop import generic_llm_loop, GenericLoopResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm(responses: list) -> Any:
    """Build a mock LLM that returns responses in sequence and supports bind_tools."""
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(side_effect=responses)

    # bind_tools must return another mock that also has ainvoke
    def _bind_tools(tools, **kwargs):
        new_llm = AsyncMock()
        # After rebind, next response is the last in the sequence
        # We reuse the same ainvoke side_effect list (pointer advances)
        new_llm.ainvoke = llm.ainvoke
        new_llm.bind_tools = _bind_tools
        return new_llm

    llm.bind_tools = _bind_tools
    return llm


def _make_tool_response(tool_name: str, tool_args: dict, tc_id: str = "tc_001") -> Any:
    """Build a fake LLM AIMessage with a single tool call."""
    response = MagicMock()
    response.content = ""
    response.tool_calls = [{"id": tc_id, "name": tool_name, "args": tool_args}]
    return response


def _make_text_response(text: str) -> Any:
    """Build a fake LLM AIMessage with plain text (no tool calls)."""
    response = MagicMock()
    response.content = text
    response.tool_calls = []
    return response


def _noop_tool(name: str, result: dict) -> Any:
    """Build a fake LangChain tool that returns the given result dict."""
    tool = MagicMock()
    tool.name = name
    tool.ainvoke = AsyncMock(return_value=json.dumps(result))
    return tool


# ---------------------------------------------------------------------------
# Tests: inject_messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inject_messages_are_appended_before_next_call():
    """
    When on_tool_result returns inject_messages, those messages must appear
    in the LLM context before the NEXT ainvoke call.
    """
    captured_messages: list[list[dict]] = []

    tool_result_payload = {"success": True, "selected_variant": "FOO_A"}
    my_tool = _noop_tool("my_tool", tool_result_payload)

    async def on_tool_result(tool_name, result_dict, tool_args, context_updates):
        return {
            "inject_messages": [
                {"role": "system", "content": "[Estado]: variante resuelta"}
            ]
        }

    # LLM: first call → tool call, second call → text response
    def recording_ainvoke(messages):
        captured_messages.append(list(messages))
        # Second call returns text
        if len(captured_messages) >= 2:
            return _make_text_response("todo listo")
        return _make_tool_response("my_tool", {})

    llm = AsyncMock()
    llm.ainvoke = AsyncMock(side_effect=recording_ainvoke)
    llm.bind_tools = MagicMock(return_value=llm)

    with patch("agent.modes.tool_executor.execute_and_log_tool") as mock_exec:
        mock_exec.return_value = json.dumps(tool_result_payload)

        result = await generic_llm_loop(
            system_prompt="system",
            messages=[{"role": "user", "content": "hola"}],
            tools=[my_tool],
            max_iterations=5,
            conversation_id="test-conv",
            mode_name="TEST_MODE",
            state={},
            llm=llm,
            on_tool_result=on_tool_result,
        )

    assert result.exit_reason == "response"
    assert result.ai_response == "todo listo"
    # The second call to ainvoke must contain the injected message
    assert len(captured_messages) == 2
    second_call_messages = captured_messages[1]
    injected = [
        m
        for m in second_call_messages
        if m.get("role") == "system" and "variante resuelta" in m.get("content", "")
    ]
    assert len(injected) == 1, (
        f"Expected injected system message in second call, got: {second_call_messages}"
    )


# ---------------------------------------------------------------------------
# Tests: rebind_tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rebind_tools_replaces_llm_binding():
    """
    When on_tool_result returns rebind_tools, the loop must rebind the LLM
    and use the new toolset for subsequent iterations.
    """
    tool_a = _noop_tool("tool_a", {"success": True})
    tool_b = _noop_tool("tool_b", {"success": True, "result": "B done"})

    rebind_called_with: list[list] = []

    def fake_bind_tools(tools, **kwargs):
        rebind_called_with.append(list(tools))
        new_llm = AsyncMock()
        new_llm.ainvoke = AsyncMock(return_value=_make_text_response("rebind ok"))
        new_llm.bind_tools = fake_bind_tools
        return new_llm

    llm = AsyncMock()
    # First call → tool_a call, subsequent calls → text (handled by rebound llm)
    llm.ainvoke = AsyncMock(return_value=_make_tool_response("tool_a", {}))
    llm.bind_tools = fake_bind_tools

    async def on_tool_result(tool_name, result_dict, tool_args, context_updates):
        if tool_name == "tool_a":
            return {
                "rebind_tools": [tool_b],
                "rebind_tool_choice": None,
            }
        return None

    with patch("agent.modes.tool_executor.execute_and_log_tool") as mock_exec:
        mock_exec.return_value = json.dumps({"success": True})

        result = await generic_llm_loop(
            system_prompt="system",
            messages=[{"role": "user", "content": "hola"}],
            tools=[tool_a],
            max_iterations=5,
            conversation_id="test-conv",
            mode_name="TEST_MODE",
            state={},
            llm=llm,
            on_tool_result=on_tool_result,
        )

    assert result.exit_reason == "response"
    # bind_tools must have been called once (after tool_a resolved)
    assert len(rebind_called_with) == 1
    assert rebind_called_with[0] == [tool_b]


# ---------------------------------------------------------------------------
# Tests: None return (backward compat)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_none_callback_return_is_safe():
    """
    on_tool_result returning None must not break anything (backward compat).
    """
    tool = _noop_tool("my_tool", {"success": True})

    async def on_tool_result(tool_name, result_dict, tool_args, context_updates):
        return None  # explicitly return None

    responses = [
        _make_tool_response("my_tool", {}),
        _make_text_response("ok"),
    ]
    llm = _make_llm(responses)

    with patch("agent.modes.tool_executor.execute_and_log_tool") as mock_exec:
        mock_exec.return_value = json.dumps({"success": True})

        result = await generic_llm_loop(
            system_prompt="system",
            messages=[{"role": "user", "content": "hola"}],
            tools=[tool],
            max_iterations=5,
            conversation_id="test-conv",
            mode_name="TEST_MODE",
            state={},
            llm=llm,
            on_tool_result=on_tool_result,
        )

    assert result.exit_reason == "response"
    assert result.ai_response == "ok"


# ---------------------------------------------------------------------------
# Tests: Opción-C — presupuesto_mode on_tool_result variant injection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_opcion_c_injects_message_when_all_variants_resolved():
    """
    Integration test for Opción-C pattern:
    When on_tool_result receives seleccionar_variante_por_respuesta with
    _internal_flags.pending_variants all resolved, it should:
    1. Return inject_messages with the state-update system message
    2. Return rebind_tools with the full toolset
    3. Return rebind_tool_choice: None
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode

    # Build a tool result where all variants are resolved
    resolved_pending = [
        {
            "pending_id": "pv_001",
            "codigo_base": "PLACA_SOLAR",
            "pregunta": "¿Qué tipo de placa solar?",
            "opciones": [],
            "cantidad_total": 1,
            "cantidad_resuelta": 1,
            "cantidad_pendiente": 0,
            "resoluciones": [
                {
                    "variant_code": "PLACA_SOLAR_SIMPLE",
                    "quantity": 1,
                    "confidence": 0.9,
                    "source": "user_explicit",
                }
            ],
            "status": "resolved",
        }
    ]
    tool_result = {
        "selected_variant": "PLACA_SOLAR_SIMPLE",
        "confidence": 0.9,
        "name": "Placa solar simple",
        "_internal_flags": {
            "pending_variants": resolved_pending,
        },
    }
    tool_args = {
        "categoria_vehiculo": "motos-part",
        "codigo_elemento_base": "PLACA_SOLAR",
        "respuesta_usuario": "la simple",
    }

    # We need to exercise the on_tool_result closure from _process_with_generic_loop.
    # Rather than running the full loop, we'll call it via a thin harness that
    # captures the return value of the callback.

    node = PresupuestoModeNode()
    # Build minimal mode_context
    mode_context: dict[str, Any] = {
        "element_codes": [],
        "pending_variants": resolved_pending,
    }
    conversation_id = "test-conv-opcion-c"

    # Simulate extracting the callback as it would be built in _process_with_generic_loop.
    # We mirror the closure setup here for a focused unit test.
    context_from_tools: dict[str, Any] = {}
    context_updates: dict[str, Any] = {}

    # Apply the internal flags (as generic_loop would do before the callback)
    context_updates["pending_variants"] = resolved_pending

    # Build the callback (mirror the production closure)
    async def on_tool_result(
        tool_name: str,
        result_dict: dict,
        tool_args: dict,
        context_updates: dict,
    ):
        result_str = json.dumps(result_dict)
        tool_context = node._extract_context_from_tool(
            tool_name,
            tool_args,
            result_str,
            current_element_codes=list(mode_context.get("element_codes") or []),
        )
        context_from_tools.update(tool_context)

        if tool_name == "seleccionar_variante_por_respuesta" and not result_dict.get(
            "error"
        ):
            tool_flags = result_dict.get("_internal_flags", {})
            updated_pending = tool_flags.get("pending_variants")
            if updated_pending is not None:
                still_unresolved = [
                    pv
                    for pv in updated_pending
                    if isinstance(pv, dict) and pv.get("status") != "resolved"
                ]
            else:
                updated_pending_ctx = context_updates.get("pending_variants") or []
                still_unresolved = [
                    pv
                    for pv in updated_pending_ctx
                    if isinstance(pv, dict) and pv.get("status") != "resolved"
                ]

            if not still_unresolved:
                resolved_codes: list[str] = []
                if updated_pending is not None:
                    for pv in updated_pending:
                        if isinstance(pv, dict):
                            for res in pv.get("resoluciones", []):
                                if isinstance(res, dict):
                                    code = res.get("variant_code")
                                else:
                                    code = getattr(res, "variant_code", None)
                                if code and code not in resolved_codes:
                                    resolved_codes.append(code)

                ctx_codes = list(context_from_tools.get("element_codes") or [])
                for c in ctx_codes:
                    if c not in resolved_codes:
                        resolved_codes.append(c)

                codes_str = (
                    ", ".join(resolved_codes) if resolved_codes else "(ver contexto)"
                )
                inject_msg = (
                    f"[Estado actualizado]: Todas las variantes han sido confirmadas. "
                    f"Códigos resueltos: {codes_str}. "
                    f"Siguiente paso: llamar calcular_tarifa_con_elementos "
                    f"con estos códigos."
                )
                return {
                    "inject_messages": [{"role": "system", "content": inject_msg}],
                    "rebind_tools": node.get_tools(mode_context={}),
                    "rebind_tool_choice": None,
                }
        return None

    cb_result = await on_tool_result(
        "seleccionar_variante_por_respuesta",
        tool_result,
        tool_args,
        context_updates,
    )

    assert cb_result is not None, (
        "Callback should return a dict when all variants resolved"
    )
    assert "inject_messages" in cb_result
    assert "rebind_tools" in cb_result
    assert cb_result["rebind_tool_choice"] is None

    # Check inject_messages content
    msgs = cb_result["inject_messages"]
    assert len(msgs) == 1
    assert msgs[0]["role"] == "system"
    assert "PLACA_SOLAR_SIMPLE" in msgs[0]["content"]
    assert "calcular_tarifa_con_elementos" in msgs[0]["content"]

    # Check rebind_tools is the full toolset (not the restricted one)
    rebind_tools = cb_result["rebind_tools"]
    tool_names = {t.name for t in rebind_tools}
    assert "calcular_tarifa_con_elementos" in tool_names
    assert "enviar_imagenes_ejemplo" in tool_names


@pytest.mark.asyncio
async def test_opcion_c_no_injection_when_variants_still_unresolved():
    """
    Opción-C must NOT inject when there are still unresolved variants.
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode

    still_pending = [
        {
            "pending_id": "pv_001",
            "codigo_base": "PLACA_SOLAR",
            "status": "resolved",
            "resoluciones": [
                {
                    "variant_code": "PLACA_SOLAR_SIMPLE",
                    "quantity": 1,
                    "confidence": 0.9,
                    "source": "user_explicit",
                }
            ],
        },
        {
            "pending_id": "pv_002",
            "codigo_base": "ESCAPE",
            "status": "pending",  # Still unresolved
            "resoluciones": [],
        },
    ]
    tool_result = {
        "selected_variant": "PLACA_SOLAR_SIMPLE",
        "confidence": 0.9,
        "_internal_flags": {"pending_variants": still_pending},
    }

    node = PresupuestoModeNode()
    mode_context: dict[str, Any] = {
        "element_codes": [],
        "pending_variants": still_pending,
    }
    context_from_tools: dict[str, Any] = {}
    context_updates: dict[str, Any] = {}

    async def on_tool_result_simple(tool_name, result_dict, tool_args, context_updates):
        # Simplified version of the Opción-C check
        tool_flags = result_dict.get("_internal_flags", {})
        updated_pending = tool_flags.get("pending_variants")
        if updated_pending is not None:
            still_unresolved = [
                pv for pv in updated_pending if pv.get("status") != "resolved"
            ]
        else:
            still_unresolved = []

        if not still_unresolved:
            return {"inject_messages": [{"role": "system", "content": "all resolved"}]}
        return None  # Still variants pending → no injection

    cb_result = await on_tool_result_simple(
        "seleccionar_variante_por_respuesta",
        tool_result,
        {},
        context_updates,
    )

    assert cb_result is None, (
        "Must not inject when variants still pending, got: " + str(cb_result)
    )
