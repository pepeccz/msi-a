"""Integration-style tests for expediente-v2 key flows (TASK-15).

These tests exercise multi-step behavior in ``ExpedienteModeNode`` and
``agent.main.process_message`` while mocking external dependencies.
"""

from __future__ import annotations

import json
import importlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.modes.expediente_mode import ExpedienteModeNode


def _state(mode_context: dict | None = None) -> dict:
    return {
        "conversation_id": "12345",
        "user_id": "user-1",
        "user_name": "Usuario Test",
        "client_type": "particular",
        "messages": [],
        "mode_context": mode_context or {},
        "retry_state": {},
        "incoming_attachments": [],
    }


def _tool(name: str) -> MagicMock:
    t = MagicMock()
    t.name = name
    t.args_schema = None
    return t


def _llm_tool_call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id}


def _llm_response(*, tool_calls: list[dict] | None = None, content: str = "") -> SimpleNamespace:
    return SimpleNamespace(tool_calls=tool_calls or [], content=content)


def _settings(**overrides) -> SimpleNamespace:
    base = {
        "EXPEDIENTE_V2_ENABLED": True,
        "ENABLE_LATENCY_GATING": False,
        "ENABLE_SAME_TURN_TRANSITION_CLOSURE": True,
        "MAX_TOOL_ITERATIONS_EXPEDIENTE": 6,
        "AGENT_GRAPH_TIMEOUT_SECONDS": 10,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_photos_listo_confirm_data_complete_next_element_flow():
    """1) Photos -> listo -> confirm -> data -> complete -> next element."""
    node = ExpedienteModeNode()
    mode_context = {
        "expediente_sub_mode": "collect_element_data",
        "element_codes": ["ESCAPE", "SUSPENSION"],
        "current_element_index": 0,
        "current_element_code": "ESCAPE",
        "element_phase": "photos",
        "case_id": "case-1",
    }
    state = _state(mode_context)
    tools = [_tool("guardar_datos_elemento"), _tool("completar_elemento_actual")]

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        side_effect=[
            _llm_response(
                tool_calls=[
                    _llm_tool_call("guardar_datos_elemento", {"campo": "valor"}, "tc-1"),
                    _llm_tool_call("completar_elemento_actual", {}, "tc-2"),
                ]
            ),
            _llm_response(content="Perfecto, pasamos al siguiente elemento."),
        ]
    )

    async def execute_tool(*_, **kwargs):
        tool_name = kwargs["tool_name"]
        if tool_name == "guardar_datos_elemento":
            return json.dumps(
                {
                    "success": True,
                    "all_required_collected": True,
                    "action": "ELEMENT_DATA_COMPLETE",
                    "element_code": "ESCAPE",
                    "current_element_index": 0,
                    "element_phase": "data",
                }
            )
        return json.dumps(
            {
                "success": True,
                "all_elements_complete": False,
                "current_element_index": 1,
                "current_element_code": "SUSPENSION",
                "element_phase": "photos",
            }
        )

    confirm_tool = MagicMock()
    confirm_tool.ainvoke = AsyncMock(
        return_value=json.dumps(
            {
                "success": True,
                "photos_count": 3,
                "element_phase": "data",
                "current_element_index": 0,
                "all_elements_complete": False,
            }
        )
    )

    with (
        patch.object(node, "_get_llm", return_value=mock_llm),
        patch.object(node, "_execute_and_log_tool", side_effect=execute_tool),
        patch.object(node, "_track_token_usage", new_callable=AsyncMock),
        patch.object(node, "_validate_response_constraints", new_callable=AsyncMock, return_value=(True, None)),
        patch("agent.modes.expediente_mode._get_element_data_tools", return_value=tools),
        patch("agent.tools.element_data_tools.confirmar_fotos_elemento", confirm_tool),
        patch("agent.modes.expediente_mode.assemble_system_prompt", return_value="system"),
        patch("agent.modes.expediente_mode.format_messages_for_llm", return_value=[]),
        patch("agent.modes.expediente_mode.set_current_state"),
        patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
        patch("agent.modes.expediente_mode.get_settings", return_value=_settings()),
    ):
        result = await node._handle_element_data("listo", state, mode_context)

    assert result["mode_context"]["current_element_index"] == 1
    assert result["mode_context"]["element_phase"] == "photos"
    assert result["mode_context"]["element_states"]["ESCAPE"]["state"] == "element_complete"
    assert result["ai_response"].startswith("📍 Paso 1/6")


@pytest.mark.asyncio
async def test_race_listo_before_persisted_retry_then_success():
    """2) Race: listo before image persistence -> retry state -> success."""
    node = ExpedienteModeNode()
    mode_context = {
        "element_codes": ["ESCAPE"],
        "current_element_index": 0,
        "current_element_code": "ESCAPE",
        "element_phase": "photos",
        "case_id": "case-race",
    }
    state = _state(mode_context)

    confirm_tool = MagicMock()
    confirm_tool.ainvoke = AsyncMock(
        side_effect=[
            json.dumps({"success": False, "photos_count": 0, "message": "No veo fotos aún"}),
            json.dumps({"success": True, "photos_count": 2, "element_phase": "data"}),
        ]
    )

    with (
        patch("agent.tools.element_data_tools.confirmar_fotos_elemento", confirm_tool),
        patch("agent.modes.expediente_mode.set_current_state"),
        patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
        patch("agent.modes.expediente_mode.get_settings", return_value=_settings()),
    ):
        fired_first = await node._guard_photo_completion_intent("listo", mode_context, state, "12345")
        fired_second = await node._guard_photo_completion_intent("listo", mode_context, state, "12345")

    assert fired_first is True
    assert mode_context["element_states"]["ESCAPE"]["state"] in {"retry_photos", "photos_confirmed"}
    assert fired_second is True
    assert mode_context["element_phase"] == "data"
    assert mode_context["element_states"]["ESCAPE"]["state"] == "photos_confirmed"


@pytest.mark.asyncio
async def test_multi_element_two_steps_state_and_prefix_correctness():
    """3) Multi-element flow preserves state and correct step prefixes."""
    node = ExpedienteModeNode()
    mode_context = {
        "expediente_sub_mode": "collect_element_data",
        "element_codes": ["ESCAPE", "SUSPENSION"],
        "current_element_index": 1,
        "current_element_code": "SUSPENSION",
        "element_phase": "data",
        "element_states": {
            "ESCAPE": {"state": "element_complete", "photos_count": 2, "data_complete": True},
            "SUSPENSION": {"state": "data_collection", "photos_count": 2, "data_complete": False},
        },
    }
    state = _state(mode_context)
    tools = [_tool("completar_elemento_actual")]

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=_llm_response(
            tool_calls=[_llm_tool_call("completar_elemento_actual", {}, "tc-last")]
        )
    )

    with (
        patch.object(node, "_get_llm", return_value=mock_llm),
        patch.object(
            node,
            "_execute_and_log_tool",
            new_callable=AsyncMock,
            return_value=json.dumps({"success": True, "all_elements_complete": True, "message": "Elemento final completado"}),
        ),
        patch.object(node, "_track_token_usage", new_callable=AsyncMock),
        patch("agent.modes.expediente_mode.assemble_system_prompt", return_value="system"),
        patch("agent.modes.expediente_mode.format_messages_for_llm", return_value=[]),
        patch("agent.modes.expediente_mode.set_current_state"),
        patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
        patch("agent.modes.expediente_mode.get_settings", return_value=_settings()),
    ):
        result = await node._run_llm_loop("ok", state, mode_context, tools, "COLLECT_ELEMENT_DATA")

    assert result["mode_context"]["expediente_sub_mode"] == "collect_base_docs"
    assert result["mode_context"]["element_states"]["ESCAPE"]["state"] == "element_complete"
    assert result["mode_context"]["element_states"]["SUSPENSION"]["state"] == "element_complete"
    assert "📍 Paso 2/6" in result["ai_response"]


@pytest.mark.asyncio
async def test_submode_transition_chain_to_personal_with_anti_anticipation():
    """4) collect_element_data -> collect_base_docs -> collect_personal anti-anticipation."""
    node = ExpedienteModeNode()

    # First hop: element_data -> base_docs
    mode_context_a = {
        "expediente_sub_mode": "collect_element_data",
        "element_codes": ["ESCAPE"],
        "current_element_index": 0,
        "element_phase": "data",
    }
    state_a = _state(mode_context_a)
    llm_a = MagicMock()
    llm_a.ainvoke = AsyncMock(return_value=_llm_response(tool_calls=[_llm_tool_call("completar_elemento_actual", {}, "tc-a")]))

    # Second hop: base_docs -> personal
    mode_context_b = {"expediente_sub_mode": "collect_base_docs"}
    state_b = _state(mode_context_b)
    llm_b = MagicMock()
    llm_b.ainvoke = AsyncMock(return_value=_llm_response(tool_calls=[_llm_tool_call("confirmar_documentacion_base", {}, "tc-b")]))

    with (
        patch("agent.modes.expediente_mode.assemble_system_prompt", return_value="system"),
        patch("agent.modes.expediente_mode.format_messages_for_llm", return_value=[]),
        patch("agent.modes.expediente_mode.set_current_state"),
        patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
        patch("agent.modes.expediente_mode.get_settings", return_value=_settings()),
        patch.object(node, "_track_token_usage", new_callable=AsyncMock),
    ):
        with (
            patch.object(node, "_get_llm", return_value=llm_a),
            patch.object(
                node,
                "_execute_and_log_tool",
                new_callable=AsyncMock,
                return_value=json.dumps({"success": True, "all_elements_complete": True}),
            ),
        ):
            result_a = await node._run_llm_loop("ok", state_a, mode_context_a, [_tool("completar_elemento_actual")], "COLLECT_ELEMENT_DATA")

        with (
            patch.object(node, "_get_llm", return_value=llm_b),
            patch.object(
                node,
                "_execute_and_log_tool",
                new_callable=AsyncMock,
                return_value=json.dumps({"success": True, "next_step": "collect_personal"}),
            ),
        ):
            result_b = await node._run_llm_loop("ok", state_b, mode_context_b, [_tool("confirmar_documentacion_base")], "COLLECT_BASE_DOCS")

    assert result_a["mode_context"]["expediente_sub_mode"] == "collect_base_docs"
    assert "Pasamos al paso 2" in result_a["ai_response"]
    assert "ficha" not in result_a["ai_response"].lower()

    assert result_b["mode_context"]["expediente_sub_mode"] == "collect_personal"
    assert "Pasamos al paso 3" in result_b["ai_response"]
    assert "dni" not in result_b["ai_response"].lower()


@pytest.mark.asyncio
async def test_tool_matrix_blocks_guardar_in_photos_then_recovers():
    """5) Tool matrix blocks guardar_datos in photos phase, then recovers."""
    node = ExpedienteModeNode()
    mode_context = {
        "expediente_sub_mode": "collect_element_data",
        "element_codes": ["ESCAPE"],
        "current_element_index": 0,
        "current_element_code": "ESCAPE",
        "element_phase": "photos",
    }
    state = _state(mode_context)
    tools = [_tool("guardar_datos_elemento"), _tool("confirmar_fotos_elemento")]

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        side_effect=[
            _llm_response(tool_calls=[_llm_tool_call("guardar_datos_elemento", {"x": 1}, "tc-blocked")]),
            _llm_response(tool_calls=[_llm_tool_call("confirmar_fotos_elemento", {"usuario_confirma": True}, "tc-ok")]),
            _llm_response(content="Perfecto, ahora pasamos a los datos tecnicos."),
        ]
    )

    execute_mock = AsyncMock(
        return_value=json.dumps({"success": True, "element_phase": "data", "photos_count": 2})
    )

    with (
        patch.object(node, "_get_llm", return_value=mock_llm),
        patch.object(node, "_execute_and_log_tool", execute_mock),
        patch.object(node, "_track_token_usage", new_callable=AsyncMock),
        patch.object(node, "_validate_response_constraints", new_callable=AsyncMock, return_value=(True, None)),
        patch("agent.modes.expediente_mode.assemble_system_prompt", return_value="system"),
        patch("agent.modes.expediente_mode.format_messages_for_llm", return_value=[]),
        patch("agent.modes.expediente_mode.set_current_state"),
        patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
        patch("agent.modes.expediente_mode.get_settings", return_value=_settings()),
    ):
        result = await node._run_llm_loop("te paso datos", state, mode_context, tools, "COLLECT_ELEMENT_DATA")

    called_tools = [call.kwargs["tool_name"] for call in execute_mock.await_args_list]
    assert "guardar_datos_elemento" not in called_tools
    assert called_tools == ["confirmar_fotos_elemento"]
    assert result["mode_context"]["element_phase"] == "data"
    assert "datos" in result["ai_response"].lower()


@pytest.mark.asyncio
async def test_invalid_audio_video_attachment_rejected_and_flow_continues():
    """6) Audio/video attachment is rejected and graph flow still continues."""
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value={"ai_response": "Seguimos con el expediente."})

    chatwoot = AsyncMock()
    redis_client = AsyncMock()

    user = SimpleNamespace(id="user-1", first_name="Ada", last_name="Lovelace", client_type="particular")
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: user))
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False

    message_data = {
        "conversation_id": "12345",
        "customer_phone": "+34600111222",
        "message_text": "hola",
        "attachments": [{"file_type": "audio", "data_url": "https://x/audio.ogg"}],
    }

    sys.modules.setdefault("phonenumbers", MagicMock())
    agent_main = importlib.import_module("agent.main")
    process_message = agent_main.process_message

    with (
        patch.object(agent_main, "get_async_session", return_value=session),
        patch.object(agent_main, "save_user_message", new_callable=AsyncMock),
        patch.object(agent_main, "save_assistant_message", new_callable=AsyncMock),
        patch.object(agent_main, "get_settings", return_value=_settings()),
        patch.object(agent_main, "is_rejected_attachment", return_value=True),
        patch.object(agent_main, "is_accepted_attachment", return_value=False),
        patch.object(agent_main, "is_image_attachment", return_value=False),
    ):
        await process_message(graph, chatwoot, redis_client, message_data)

    assert chatwoot.send_message.await_count >= 2
    first_msg = chatwoot.send_message.await_args_list[0].kwargs["message"]
    assert "Solo puedo aceptar imágenes" in first_msg
    assert graph.ainvoke.await_count == 1


@pytest.mark.asyncio
async def test_anti_repetition_reformulates_repeated_message():
    """7) Repeated assistant response is reformulated with anti-repetition guard."""
    node = ExpedienteModeNode()
    mode_context = {"expediente_sub_mode": "collect_personal"}

    async def run_turn(ctx: dict, text: str) -> dict:
        state = _state(ctx)
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=_llm_response(content=text))
        with (
            patch.object(node, "_get_llm", return_value=llm),
            patch.object(node, "_track_token_usage", new_callable=AsyncMock),
            patch.object(node, "_validate_response_constraints", new_callable=AsyncMock, return_value=(True, None)),
            patch("agent.modes.expediente_mode.assemble_system_prompt", return_value="system"),
            patch("agent.modes.expediente_mode.format_messages_for_llm", return_value=[]),
            patch("agent.modes.expediente_mode.set_current_state"),
            patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
            patch("agent.modes.expediente_mode.get_settings", return_value=_settings()),
        ):
            return await node._run_llm_loop("ok", state, ctx, [], "COLLECT_PERSONAL")

    first = await run_turn(dict(mode_context), "Necesito tu nombre completo.")
    second = await run_turn(dict(first["mode_context"]), first["ai_response"])

    assert "📍 Paso 3/6" in first["ai_response"]
    assert "📍 Paso 3/6" in second["ai_response"]
    assert "Para recordarte:" in second["ai_response"]
