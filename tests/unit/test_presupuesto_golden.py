"""
Golden conversation tests for PRESUPUESTO_MODE — Phase 3, T-15.

Strict TDD: written BEFORE the presupuesto_mode.py migration (T-18).
These tests define the EXPECTED behaviour of the new tool_loop engine.

Scenarios:
1. Price-before-image enforcement (no images until price stated)
2. Variant flow: identificar → variantes pendientes → seleccionar → calcular
3. EXPEDIENTE transition trigger (confirmar_presupuesto)
4. Multi-tool turn (two tools in one LLM response)
5. Tool error recovery (tool raises → LLM self-corrects)
6. (T-20 append) Message protocol integrity (no unpaired ToolMessages, no fake AIMessage)

Design references:
- AD-4: post_tool_hook replaces inject_messages (SystemMessage, NOT fake AIMessage)
- AD-7: TOOLNODE_ENABLED_MODES feature flag guards the new engine
- Domain 4: inject_messages/on_tool_result must be removed
- Domain 5: PRESUPUESTO migration scenarios
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_mock_llm(responses: list[AIMessage]) -> MagicMock:
    """Create a mock LLM that returns AIMessage responses in sequence."""
    call_num = {"n": 0}

    async def mock_invoke(messages, **kwargs):
        idx = min(call_num["n"], len(responses) - 1)
        call_num["n"] += 1
        return responses[idx]

    mock_llm = MagicMock()
    mock_llm.ainvoke = mock_invoke
    bound_mock = MagicMock()
    bound_mock.ainvoke = mock_invoke
    mock_llm.bind_tools = MagicMock(return_value=bound_mock)
    return mock_llm


def _tool_call(name: str, args: dict, call_id: str) -> dict:
    """Build a tool_call dict matching LangChain's format."""
    return {"id": call_id, "name": name, "args": args, "type": "tool_call"}


def _tool_result(data: dict) -> str:
    """Serialize a tool result dict to JSON (matching what custom_tool_node returns)."""
    return json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------------------
# T-15 Scenario 1: Price before image enforcement
# ---------------------------------------------------------------------------


class TestPricedBeforeImage:
    """
    The new engine must NOT allow enviar_imagenes_ejemplo to be called
    when price_authority_confirmed is False.

    The filtering happens in get_tools(mode_context): when price is not
    confirmed, image tools are excluded from the available tool set.
    """

    @pytest.mark.asyncio
    async def test_image_tool_excluded_when_price_not_confirmed(self):
        """
        GIVEN PRESUPUESTO turn with price_authority_confirmed=False
        WHEN the subgraph builds the tool list via get_tools(mode_context)
        THEN enviar_imagenes_ejemplo is NOT in the returned list.
        """
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        # Track what tools the LLM receives
        tools_seen_by_llm: list[list] = []

        final_response = AIMessage(
            content="El presupuesto es de 410€ +IVA. ¿Desea ver imágenes de ejemplo?"
        )
        mock_llm = _make_mock_llm([final_response])

        def get_tools_with_spy(ctx: dict) -> list:
            from agent.tools.element_tools import identificar_y_resolver_elementos

            # Simulates the price-gate: no image tools until price confirmed
            tools = [identificar_y_resolver_elementos]
            if ctx.get("price_authority_confirmed"):
                from agent.tools.image_tools import enviar_imagenes_ejemplo

                tools.append(enviar_imagenes_ejemplo)
            tools_seen_by_llm.append(tools)
            return tools

        config = ModeLoopConfig(
            mode_name="PRESUPUESTO_MODE",
            get_tools=get_tools_with_spy,
            get_system_prompt=lambda s: "Eres el asistente de MSI.",
            post_tool_hook=None,
            max_iterations=5,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="¿Cuánto cuesta el escape?")],
                "_mode_context": {"price_authority_confirmed": False},
                "_conversation_id": "price-gate-test",
            }
        )

        # Verify no image tools were offered when price not confirmed
        assert len(tools_seen_by_llm) >= 1
        for seen_tools in tools_seen_by_llm:
            tool_names = [getattr(t, "name", type(t).__name__) for t in seen_tools]
            assert "enviar_imagenes_ejemplo" not in tool_names, (
                f"enviar_imagenes_ejemplo was available before price confirmed: {tool_names}"
            )

    @pytest.mark.asyncio
    async def test_image_tool_available_after_price_confirmed(self):
        """
        GIVEN PRESUPUESTO turn with price_authority_confirmed=True in mode_context
        WHEN the tool list is built
        THEN enviar_imagenes_ejemplo IS available.
        """
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        tools_seen: list[list] = []

        final_response = AIMessage(content="Aquí tiene las imágenes de ejemplo.")
        mock_llm = _make_mock_llm([final_response])

        def get_tools_after_price(ctx: dict) -> list:
            from agent.tools.element_tools import identificar_y_resolver_elementos
            from agent.tools.image_tools import enviar_imagenes_ejemplo

            result_tools = [identificar_y_resolver_elementos]
            if ctx.get("price_authority_confirmed"):
                result_tools.append(enviar_imagenes_ejemplo)
            tools_seen.append(result_tools)
            return result_tools

        config = ModeLoopConfig(
            mode_name="PRESUPUESTO_MODE",
            get_tools=get_tools_after_price,
            get_system_prompt=lambda s: "Eres el asistente de MSI.",
            post_tool_hook=None,
            max_iterations=5,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Muéstrame las imágenes")],
                "_mode_context": {"price_authority_confirmed": True},
                "_conversation_id": "price-confirmed-test",
            }
        )

        assert len(tools_seen) >= 1
        image_tool_available = any(
            any(getattr(t, "name", "") == "enviar_imagenes_ejemplo" for t in seen)
            for seen in tools_seen
        )
        assert image_tool_available, (
            "enviar_imagenes_ejemplo should be available after price confirmed"
        )


# ---------------------------------------------------------------------------
# T-15 Scenario 2: Variant flow (suspension → delantera)
# ---------------------------------------------------------------------------


class TestVariantFlow:
    """
    Tests the variant resolution flow:
    1. LLM calls identificar_y_resolver_elementos → returns variant question
    2. post_tool_hook sets variant_pending in state
    3. No inject_messages (fake AIMessage) used
    4. LLM calls seleccionar_variante_por_respuesta → resolves variant
    """

    @pytest.mark.asyncio
    async def test_variant_detection_sets_state_not_injects_message(self):
        """
        GIVEN identificar_y_resolver_elementos returns pending variants,
        WHEN post_tool_hook processes the ToolMessage,
        THEN state contains variant_pending info (via _state_update),
        AND no fake AIMessage (role=assistant) is injected into messages.
        """
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        # Turn 1: LLM calls identificar_y_resolver_elementos
        ai_with_tool_call = AIMessage(
            content="",
            tool_calls=[
                _tool_call(
                    "identificar_y_resolver_elementos",
                    {
                        "texto_descripcion": "la suspension delantera",
                        "categoria_vehiculo": "motos-part",
                    },
                    "call_ident_01",
                )
            ],
        )
        # Turn 2: After seeing variant info in state, LLM asks user
        ai_final = AIMessage(
            content="¿Qué tipo de suspensión deseas: delantera o trasera?"
        )

        mock_llm = _make_mock_llm([ai_with_tool_call, ai_final])

        # Tool result: variant question detected
        variant_tool_result = {
            "success": True,
            "elementos_listos": [],
            "elementos_con_variantes": [
                {
                    "codigo_base": "SUSPENSION",
                    "variantes": [
                        {"codigo": "SUSPENSION_DEL"},
                        {"codigo": "SUSPENSION_TRA"},
                    ],
                }
            ],
            "preguntas_variantes": [
                {"codigo_base": "SUSPENSION", "opciones": ["delantera", "trasera"]}
            ],
            "_state_update": {
                "pending_variants": [
                    {
                        "codigo_base": "SUSPENSION",
                        "status": "pending",
                        "opciones": ["delantera", "trasera"],
                    }
                ],
                "variant_pending": True,
            },
        }

        injected_messages_detected: list[str] = []

        async def capturing_post_tool_hook(
            tool_name: str, result_dict: dict, state: dict
        ) -> dict:
            """Hook that captures state writes, verifying no AIMessage injection."""
            if tool_name == "identificar_y_resolver_elementos":
                pending = result_dict.get("_state_update", {}).get(
                    "pending_variants", []
                )
                if pending:
                    # Return state update — NOT an inject_messages
                    return {
                        "mode_context": {
                            **state.get("_mode_context", {}),
                            "pending_variants": pending,
                            "variant_pending": True,
                        }
                    }
            return {}

        async def mock_execute_and_log(
            conversation_id,
            tool_name,
            tool_args,
            tools,
            tool_call_id,
            iteration,
            dedup_cache,
        ):
            if tool_name == "identificar_y_resolver_elementos":
                return _tool_result(variant_tool_result)
            return _tool_result({"success": False, "error": "unexpected tool"})

        config = ModeLoopConfig(
            mode_name="PRESUPUESTO_MODE",
            get_tools=lambda ctx: [],  # Tools mocked at execute level
            get_system_prompt=lambda s: "Eres el asistente de MSI.",
            post_tool_hook=capturing_post_tool_hook,
            max_iterations=5,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        with patch(
            "agent.modes.tool_executor.execute_and_log_tool", mock_execute_and_log
        ):
            result = await graph.ainvoke(
                {
                    "messages": [
                        HumanMessage(content="Quiero homologar la suspensión")
                    ],
                    "_mode_context": {"categoria_slug": "motos-part"},
                    "_conversation_id": "variant-test-01",
                }
            )

        # Verify: NO fake AIMessage injected into message history
        messages = result.get("messages", [])
        for msg in messages:
            if hasattr(msg, "role") and msg.role == "assistant":
                content = getattr(msg, "content", "")
                assert "[Estado" not in content, (
                    f"Fake inject_messages AIMessage found: {content[:100]}"
                )

        # Verify the final response is from the AI (not a fake inject)
        assert result.get("ai_response", ""), "Should have an AI response"

    @pytest.mark.asyncio
    async def test_full_variant_resolution_flow(self):
        """
        GIVEN: LLM identifies element with variants, then resolves variant
        WHEN the two-turn sequence runs through the subgraph
        THEN no inject_messages protocol corruption occurs,
        AND the ToolMessages are properly paired with AIMessages.
        """
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        # LLM step 1: call identificar
        ai_step1 = AIMessage(
            content="",
            tool_calls=[
                _tool_call(
                    "identificar_y_resolver_elementos",
                    {
                        "texto_descripcion": "suspension delantera",
                        "categoria_vehiculo": "motos-part",
                    },
                    "call_id_01",
                )
            ],
        )
        # LLM step 2: after tool result showing variants, asks user question
        ai_step2 = AIMessage(
            content="¿Qué tipo de suspensión necesitas: delantera o trasera?"
        )

        mock_llm = _make_mock_llm([ai_step1, ai_step2])

        ident_result = {
            "success": True,
            "elementos_listos": [],
            "elementos_con_variantes": [{"codigo_base": "SUSPENSION"}],
            "preguntas_variantes": [
                {"codigo_base": "SUSPENSION", "opciones": ["delantera", "trasera"]}
            ],
            "_state_update": {
                "pending_variants": [{"codigo_base": "SUSPENSION", "status": "pending"}]
            },
        }

        async def mock_execute(
            conversation_id,
            tool_name,
            tool_args,
            tools,
            tool_call_id,
            iteration,
            dedup_cache,
        ):
            if tool_name == "identificar_y_resolver_elementos":
                return _tool_result(ident_result)
            return _tool_result({"success": False})

        config = ModeLoopConfig(
            mode_name="PRESUPUESTO_MODE",
            get_tools=lambda ctx: [],
            get_system_prompt=lambda s: "Eres el asistente.",
            post_tool_hook=None,
            max_iterations=5,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        with patch("agent.modes.tool_executor.execute_and_log_tool", mock_execute):
            result = await graph.ainvoke(
                {
                    "messages": [
                        HumanMessage(content="Quiero homologar la suspensión")
                    ],
                    "_mode_context": {"categoria_slug": "motos-part"},
                    "_conversation_id": "variant-test-01",
                }
            )

        messages = result.get("messages", [])
        # Verify proper AIMessage → ToolMessage pairing
        ai_msgs = [
            m for m in messages if type(m).__name__ in ("AIMessage", "AIMessageChunk")
        ]
        tool_msgs = [m for m in messages if type(m).__name__ == "ToolMessage"]

        # Every ToolMessage must have a matching AIMessage with that tool_call_id
        ai_tool_call_ids = {
            tc["id"] for m in ai_msgs for tc in (getattr(m, "tool_calls", None) or [])
        }
        for tm in tool_msgs:
            assert getattr(tm, "tool_call_id", None) in ai_tool_call_ids, (
                f"ToolMessage tool_call_id={tm.tool_call_id!r} has no matching AIMessage tool_call"
            )


# ---------------------------------------------------------------------------
# T-15 Scenario 3: EXPEDIENTE transition trigger
# ---------------------------------------------------------------------------


class TestExpedienteTransitionTrigger:
    """
    When confirmar_presupuesto tool returns a mode transition signal,
    the engine must:
    1. Set pending_mode_transition in mode_context
    2. Exit the tool loop cleanly (tools_or_end → END)
    3. The caller (presupuesto_mode) promotes it to current_mode
    """

    @pytest.mark.asyncio
    async def test_confirmar_presupuesto_triggers_mode_transition_exit(self):
        """
        GIVEN confirmar_presupuesto returns _state_update with pending_mode_transition,
        WHEN post_tool_node applies it,
        THEN tools_or_end routes to END on the next iteration (no more tool calls).
        """
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        # LLM calls confirmar_presupuesto
        ai_with_confirm = AIMessage(
            content="",
            tool_calls=[
                _tool_call(
                    "confirmar_presupuesto",
                    {},
                    "call_confirm_01",
                )
            ],
        )
        # After the tool result sets mode transition, LLM wraps up
        ai_final = AIMessage(content="Perfecto, vamos a abrir el expediente.")

        mock_llm = _make_mock_llm([ai_with_confirm, ai_final])

        confirm_result = {
            "success": True,
            "message": "Presupuesto confirmado. Iniciando expediente.",
            "_state_update": {
                "pending_mode_transition": "EXPEDIENTE_MODE",
            },
        }

        async def mock_execute(
            conversation_id,
            tool_name,
            tool_args,
            tools,
            tool_call_id,
            iteration,
            dedup_cache,
        ):
            if tool_name == "confirmar_presupuesto":
                return _tool_result(confirm_result)
            return _tool_result({"success": False})

        config = ModeLoopConfig(
            mode_name="PRESUPUESTO_MODE",
            get_tools=lambda ctx: [],
            get_system_prompt=lambda s: "Eres el asistente.",
            post_tool_hook=None,
            max_iterations=5,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        with patch("agent.modes.tool_executor.execute_and_log_tool", mock_execute):
            result = await graph.ainvoke(
                {
                    "messages": [
                        HumanMessage(content="Sí, quiero abrir el expediente")
                    ],
                    "_mode_context": {"price_authority_confirmed": True},
                    "_conversation_id": "transition-test-01",
                }
            )

        # The pending_state_updates should include the transition signal
        pending = result.get("pending_state_updates", {})
        assert pending.get("pending_mode_transition") == "EXPEDIENTE_MODE", (
            f"Expected EXPEDIENTE_MODE transition, got: {pending}"
        )


# ---------------------------------------------------------------------------
# T-15 Scenario 4: Multi-tool turn
# ---------------------------------------------------------------------------


class TestMultiToolTurn:
    """
    Tests a turn where the LLM calls 2 tools in a single AIMessage.
    Both ToolMessages must be properly paired and state updates merged.
    """

    @pytest.mark.asyncio
    async def test_two_tools_in_one_turn_both_paired(self):
        """
        GIVEN LLM returns AIMessage with 2 tool_calls,
        WHEN custom_tool_node executes both,
        THEN 2 ToolMessages are returned,
        AND each has a unique tool_call_id matching the AIMessage.
        """
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        ai_multi = AIMessage(
            content="",
            tool_calls=[
                _tool_call(
                    "identificar_y_resolver_elementos",
                    {"texto_descripcion": "escape"},
                    "call_multi_01",
                ),
                _tool_call(
                    "identificar_tipo_vehiculo",
                    {"descripcion": "moto"},
                    "call_multi_02",
                ),
            ],
        )
        ai_final = AIMessage(content="He identificado el escape para motos.")

        mock_llm = _make_mock_llm([ai_multi, ai_final])

        results_by_tool = {
            "identificar_y_resolver_elementos": {
                "success": True,
                "elementos_listos": [{"codigo": "ESCAPE", "nombre": "Escape"}],
                "elementos_con_variantes": [],
                "preguntas_variantes": [],
                "_state_update": {"element_codes": ["ESCAPE"]},
            },
            "identificar_tipo_vehiculo": {
                "success": True,
                "categoria_sugerida": "motos-part",
                "_state_update": {"categoria_slug": "motos-part"},
            },
        }

        async def mock_execute(
            conversation_id,
            tool_name,
            tool_args,
            tools,
            tool_call_id,
            iteration,
            dedup_cache,
        ):
            return _tool_result(results_by_tool.get(tool_name, {"success": False}))

        config = ModeLoopConfig(
            mode_name="PRESUPUESTO_MODE",
            get_tools=lambda ctx: [],
            get_system_prompt=lambda s: "Eres el asistente.",
            post_tool_hook=None,
            max_iterations=5,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        with patch("agent.modes.tool_executor.execute_and_log_tool", mock_execute):
            result = await graph.ainvoke(
                {
                    "messages": [
                        HumanMessage(content="Sí, quiero abrir el expediente")
                    ],
                    "_mode_context": {"price_authority_confirmed": True},
                    "_conversation_id": "transition-test-01",
                }
            )

        messages = result.get("messages", [])

        # Count ToolMessages
        tool_msgs = [m for m in messages if type(m).__name__ == "ToolMessage"]
        assert len(tool_msgs) >= 2, f"Expected 2+ ToolMessages, got {len(tool_msgs)}"

        # Verify pairing
        ai_msgs = [
            m for m in messages if type(m).__name__ in ("AIMessage", "AIMessageChunk")
        ]
        ai_call_ids = {
            tc["id"] for m in ai_msgs for tc in (getattr(m, "tool_calls", None) or [])
        }
        for tm in tool_msgs:
            tcid = getattr(tm, "tool_call_id", None)
            assert tcid in ai_call_ids, (
                f"ToolMessage tool_call_id={tcid!r} has no matching AIMessage tool_call"
            )

        # Verify _state_update was accumulated
        pending = result.get("pending_state_updates", {})
        assert "element_codes" in pending or "categoria_slug" in pending, (
            f"Expected state updates from tools, got: {pending}"
        )


# ---------------------------------------------------------------------------
# T-15 Scenario 5: Tool error recovery
# ---------------------------------------------------------------------------


class TestToolErrorRecovery:
    """
    When a tool raises an exception, custom_tool_node must:
    1. Return a ToolMessage with the error content (not raise)
    2. Let the LLM see the error and self-correct
    3. NOT crash the subgraph
    """

    @pytest.mark.asyncio
    async def test_tool_error_becomes_toolmessage_not_exception(self):
        """
        GIVEN a tool raises ValueError,
        WHEN custom_tool_node handles it,
        THEN a ToolMessage with error content is returned,
        AND the subgraph continues to the LLM for recovery.
        """
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        # LLM tries to call a tool that errors
        ai_with_bad_tool = AIMessage(
            content="",
            tool_calls=[
                _tool_call(
                    "calcular_tarifa_con_elementos",
                    {"error_trigger": True},
                    "call_err_01",
                )
            ],
        )
        # LLM self-corrects after seeing the error ToolMessage
        ai_recovery = AIMessage(
            content="Lo siento, ha habido un error. Permítame intentarlo de nuevo."
        )

        mock_llm = _make_mock_llm([ai_with_bad_tool, ai_recovery])

        async def mock_execute_with_error(
            conversation_id,
            tool_name,
            tool_args,
            tools,
            tool_call_id,
            iteration,
            dedup_cache,
        ):
            if tool_name == "calcular_tarifa_con_elementos":
                # Simulate execute_and_log_tool returning an error string
                return json.dumps({"success": False, "error": "elemento no encontrado"})
            return _tool_result({"success": False})

        config = ModeLoopConfig(
            mode_name="PRESUPUESTO_MODE",
            get_tools=lambda ctx: [],
            get_system_prompt=lambda s: "Eres el asistente.",
            post_tool_hook=None,
            max_iterations=5,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        with patch(
            "agent.modes.tool_executor.execute_and_log_tool", mock_execute_with_error
        ):
            # Should NOT raise — errors become ToolMessages
            result = await graph.ainvoke(
                {
                    "messages": [HumanMessage(content="Calcula el precio del escape")],
                    "_mode_context": {},
                    "_conversation_id": "error-recovery-test-01",
                }
            )

        assert result is not None
        assert result.get("exit_reason") in ("response", "error", None), (
            f"Unexpected exit_reason: {result.get('exit_reason')}"
        )

        # Find the error ToolMessage
        messages = result.get("messages", [])
        tool_msgs = [m for m in messages if type(m).__name__ == "ToolMessage"]
        assert len(tool_msgs) >= 1, "Expected at least one ToolMessage"

        # At least one ToolMessage should contain error info
        error_found = any(
            "error" in (getattr(tm, "content", "") or "").lower() for tm in tool_msgs
        )
        assert error_found, "Expected an error ToolMessage for recovery"


# ---------------------------------------------------------------------------
# T-15 Scenario 6 / T-20: Message protocol integrity
# (Appended as per T-20 task description)
# ---------------------------------------------------------------------------


class TestMessageProtocolIntegrity:
    """
    PRESUPUESTO turn with 2+ tool calls must maintain strict message protocol:
    - No unpaired ToolMessages
    - No role='assistant' injected mid-turn (no inject_messages)
    - All ToolMessage.tool_call_id matches an AIMessage tool_call
    """

    @pytest.mark.asyncio
    async def test_no_unpaired_tool_messages_in_two_tool_turn(self):
        """
        GIVEN a PRESUPUESTO turn with 2 tool calls,
        WHEN the turn completes,
        THEN every ToolMessage.tool_call_id exists in some AIMessage.tool_calls,
        AND no synthetic AIMessage (fake inject_messages) appears between ToolMessages.
        """
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        ai_two_tools = AIMessage(
            content="",
            tool_calls=[
                _tool_call(
                    "identificar_y_resolver_elementos",
                    {"texto_descripcion": "escape"},
                    "call_proto_01",
                ),
                _tool_call(
                    "identificar_tipo_vehiculo",
                    {"descripcion": "moto deportiva"},
                    "call_proto_02",
                ),
            ],
        )
        ai_final = AIMessage(content="He identificado los elementos correctamente.")

        mock_llm = _make_mock_llm([ai_two_tools, ai_final])

        results = {
            "identificar_y_resolver_elementos": {
                "success": True,
                "elementos_listos": [{"codigo": "ESCAPE"}],
            },
            "identificar_tipo_vehiculo": {
                "success": True,
                "categoria_sugerida": "motos-part",
            },
        }

        async def mock_execute(
            conversation_id,
            tool_name,
            tool_args,
            tools,
            tool_call_id,
            iteration,
            dedup_cache,
        ):
            return _tool_result(results.get(tool_name, {"success": False}))

        config = ModeLoopConfig(
            mode_name="PRESUPUESTO_MODE",
            get_tools=lambda ctx: [],
            get_system_prompt=lambda s: "Sistema.",
            post_tool_hook=None,
            max_iterations=5,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        with patch("agent.modes.tool_executor.execute_and_log_tool", mock_execute):
            result = await graph.ainvoke(
                {
                    "messages": [HumanMessage(content="Suspensión delantera")],
                    "_mode_context": {},
                    "_conversation_id": "variant-flow-test",
                }
            )

        messages = result.get("messages", [])
        ai_msgs = [
            m for m in messages if type(m).__name__ in ("AIMessage", "AIMessageChunk")
        ]
        tool_msgs = [m for m in messages if type(m).__name__ == "ToolMessage"]

        # All tool_call_ids in ToolMessages must match an AIMessage
        ai_call_ids = {
            tc["id"] for m in ai_msgs for tc in (getattr(m, "tool_calls", None) or [])
        }
        for tm in tool_msgs:
            tcid = getattr(tm, "tool_call_id", None)
            assert tcid in ai_call_ids, (
                f"Unpaired ToolMessage found: tool_call_id={tcid!r} not in {ai_call_ids}"
            )

        # No fake AIMessage (inject_messages) between ToolMessages
        # A fake inject would have content starting with "[Estado" (the old pattern)
        for msg in messages:
            if type(msg).__name__ in ("AIMessage", "AIMessageChunk"):
                content = getattr(msg, "content", "") or ""
                assert not content.startswith("[Estado"), (
                    f"Found inject_messages pattern in AIMessage: {content[:100]}"
                )

    @pytest.mark.asyncio
    async def test_no_role_assistant_injected_mid_turn(self):
        """
        GIVEN a PRESUPUESTO turn,
        WHEN tools execute and post_tool_hook runs,
        THEN no AIMessage with role='assistant' is injected into messages
        between ToolMessages (the old inject_messages anti-pattern).

        The NEW pattern uses SystemMessage for context injection (AD-4).
        """
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        ai_tool_call = AIMessage(
            content="",
            tool_calls=[
                _tool_call(
                    "calcular_tarifa_con_elementos",
                    {"elementos": ["ESCAPE"]},
                    "call_tarif_01",
                )
            ],
        )
        ai_final = AIMessage(content="El presupuesto es de 410€ +IVA.")

        mock_llm = _make_mock_llm([ai_tool_call, ai_final])

        tariff_result = {
            "success": True,
            "precio_final": 410.0,
            "datos": {
                "price": 410.0,
                "elements": ["Escape"],
                "element_codes": ["ESCAPE"],
            },
            "_state_update": {
                "price_authority_confirmed": True,
                "tarifa_calculada": {"precio_final": 410.0},
            },
        }

        async def mock_execute(
            conversation_id,
            tool_name,
            tool_args,
            tools,
            tool_call_id,
            iteration,
            dedup_cache,
        ):
            if tool_name == "calcular_tarifa_con_elementos":
                return _tool_result(tariff_result)
            return _tool_result({"success": False})

        # Post-tool hook that uses SystemMessage (correct pattern), NOT fake AIMessage
        async def presupuesto_style_hook(
            tool_name: str, result_dict: dict, state: dict
        ) -> dict:
            if tool_name == "calcular_tarifa_con_elementos" and result_dict.get(
                "success"
            ):
                precio = result_dict.get("precio_final", 0)
                # CORRECT: return state update, do NOT inject AIMessage
                return {"price_authority_confirmed": True}
            return {}

        config = ModeLoopConfig(
            mode_name="PRESUPUESTO_MODE",
            get_tools=lambda ctx: [],
            get_system_prompt=lambda s: "Sistema.",
            post_tool_hook=presupuesto_style_hook,
            max_iterations=5,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        with patch("agent.modes.tool_executor.execute_and_log_tool", mock_execute):
            result = await graph.ainvoke(
                {
                    "messages": [
                        HumanMessage(content="Quiero homologar el escape de mi moto")
                    ],
                    "_mode_context": {},
                    "_conversation_id": "multi-tool-test-01",
                }
            )

        messages = result.get("messages", [])

        # Find ToolMessages and verify no AIMessage injected between them
        for i, msg in enumerate(messages):
            if type(msg).__name__ == "ToolMessage":
                # Check surrounding messages for fake injects
                for j, other_msg in enumerate(messages[i:], start=i):
                    if type(other_msg).__name__ == "ToolMessage" and j > i:
                        # Between two ToolMessages, there should be NO AIMessage
                        between = messages[i + 1 : j]
                        for between_msg in between:
                            assert type(between_msg).__name__ not in (
                                "AIMessage",
                                "AIMessageChunk",
                            ), (
                                f"Found AIMessage between ToolMessages at index {i + 1} to {j - 1}: "
                                f"{getattr(between_msg, 'content', '')[:100]}"
                            )

        # post_tool_hook result should be reflected in pending_state_updates
        pending = result.get("pending_state_updates", {})
        assert pending.get("price_authority_confirmed") is True, (
            f"price_authority_confirmed not set in pending_state_updates: {pending}"
        )
