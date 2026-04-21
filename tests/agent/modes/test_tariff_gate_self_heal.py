"""
Unit tests for the tariff-gate red-net self-heal in PRE_EXPEDIENTE_MODE.

Spec reference: S1–S5, AD-3, AD-4, AD-5, AD-6
  - S1: identificar succeeds → LLM text-only → self-heal fires → user gets price
  - S2: identificar + calcular already called → detector is no-op
  - S3: off-topic turn (no identificar this turn) → detector does not fire
  - S4: precio_comunicado already True → detector does not fire
  - S5: missing categoria_slug or element_codes → degraded fallback + WARNING

Strategy: patch _process_with_tool_loop infrastructure so it reaches the new
tariff-gate block without real DB/Redis/LLM. Spy on graph.ainvoke call count,
the messages passed to the second ainvoke, and structlog output.

All tests are pure unit/integration mock tests — no DB, no Redis, no LLM.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

_MODULE = "agent.modes.pre_expediente_mode"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TARIFA_CALCULADA = {
    "total": 480.0,
    "elementos": [{"codigo": "SUBCHASIS", "precio": 480.0}],
    "imagenes_ejemplo": {},
}

_TEXT_ONLY_RESPONSE = (
    "Para la homologación de subchasis en motos necesitas los siguientes documentos..."
)

_PRICE_RESPONSE = (
    "El presupuesto total para el subchasis es de 480€ +IVA. ¿Quieres proceder?"
)


def _make_loop_result(
    *,
    ai_response: str = _TEXT_ONLY_RESPONSE,
    tools_called: list[str] | None = None,
    pending_state_updates: dict | None = None,
) -> dict:
    """
    Build a minimal loop_result dict as returned by build_mode_tool_loop graph.

    Mirrors the structure that _process_with_tool_loop expects from the tool loop.
    """
    if pending_state_updates is None:
        pending_state_updates = {}

    return {
        "ai_response": ai_response,
        "exit_reason": "response",
        "tools_called": tools_called if tools_called is not None else [],
        "pending_state_updates": pending_state_updates,
        "messages": [],
    }


def _make_graph_mock_seq(results: list[dict]) -> MagicMock:
    """
    Build a mock build_mode_tool_loop return value whose graph.ainvoke
    cycles through `results` in order (side_effect list).
    """
    graph_mock = MagicMock()
    graph_mock.graph.ainvoke = AsyncMock(side_effect=results)
    graph_mock.recursion_limit = 25
    return graph_mock


def _make_tail_loop_mock(result: dict) -> MagicMock:
    """Build a mock for the build_tail_loop return value."""
    tail_mock = MagicMock()
    tail_mock.graph.ainvoke = AsyncMock(return_value=result)
    tail_mock.recursion_limit = 35
    return tail_mock


def _minimal_pricing_state(
    *,
    element_codes: list[str] | None = None,
    categoria_slug: str = "motos-part",
    tarifa_calculada: dict | None = None,
    precio_comunicado: bool = False,
) -> dict:
    """
    Minimal ConversationState-compatible dict for _process_with_tool_loop,
    representing PRE_EXPEDIENTE_PRICING phase.

    - element_codes present → phase is PRICING (not DISCOVERY)
    - tarifa_calculada empty (default) → price not yet calculated
    - precio_comunicado=False → price not yet communicated
    """
    return {
        "conversation_id": "test-tariff-gate-conv-001",
        "mode_context": {
            "element_codes": element_codes if element_codes is not None else ["SUBCHASIS"],
            "categoria_slug": categoria_slug,
            "tarifa_calculada": tarifa_calculada,
            "precio_comunicado": precio_comunicado,
        },
        "messages": [],
        "client_type": "particular",
        "is_first_interaction": False,
    }


# ---------------------------------------------------------------------------
# T-2: S1 — text-only after identificar triggers self-heal
# ---------------------------------------------------------------------------


class TestTariffGateSelfHeal:
    """
    Core tariff-gate red-net detector tests.
    S1: LLM text-only after identificar → self-heal fires, second loop result returned.
    """

    @pytest.mark.asyncio
    async def test_S1_text_only_after_identify_triggers_self_heal(self):
        """
        S1: GIVEN PRE_EXPEDIENTE_PRICING (element_codes set, tarifa_calculada empty,
        precio_comunicado=False) AND identificar_y_resolver_elementos in tools_called
        AND LLM returned text-only (no calcular_tarifa_con_elementos in tools_called),
        THEN graph.ainvoke is called TWICE, the second call's messages contain a
        synthetic AIMessage with calcular_tarifa_con_elementos tool_call, and the
        final ai_response is the SECOND loop's response.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        # First loop: identificar called, text-only response (the bug scenario)
        first_loop = _make_loop_result(
            ai_response=_TEXT_ONLY_RESPONSE,
            tools_called=["identificar_y_resolver_elementos"],
            pending_state_updates={
                "element_codes": ["SUBCHASIS"],
                "categoria_slug": "motos-part",
            },
        )

        # Second loop (tail): calcular_tarifa called, price response
        second_loop = _make_loop_result(
            ai_response=_PRICE_RESPONSE,
            tools_called=["calcular_tarifa_con_elementos"],
            pending_state_updates={
                "tarifa_calculada": _TARIFA_CALCULADA,
                "precio_comunicado": True,
            },
        )

        tail_mock = _make_tail_loop_mock(second_loop)
        graph_mock = _make_graph_mock_seq([first_loop])
        node = PreExpedienteModeNode()
        node._build_client_context = MagicMock(return_value={})

        with (
            patch(f"{_MODULE}._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch(f"{_MODULE}.build_mode_tool_loop", return_value=graph_mock),
            patch(f"{_MODULE}.build_tail_loop", return_value=tail_mock),
            patch(f"{_MODULE}.clear_image_tools_state"),
            patch(f"{_MODULE}.assemble_system_prompt", return_value="prompt"),
            patch("agent.tools.draft_quote_service._deactivate_draft_quote", new_callable=AsyncMock),
            patch(f"{_MODULE}._enforce_cta5_if_needed", side_effect=lambda ai_response, **k: ai_response),
        ):
            result = await node._process_with_tool_loop(
                "¿Qué necesito?", _minimal_pricing_state()
            )

        # First loop must have been called exactly once
        assert graph_mock.graph.ainvoke.call_count == 1, (
            f"S1: build_mode_tool_loop graph.ainvoke must be called exactly ONCE "
            f"(the main loop). Got: {graph_mock.graph.ainvoke.call_count}"
        )

        # Tail loop must have been called exactly once (the self-heal retry)
        assert tail_mock.graph.ainvoke.call_count == 1, (
            f"S1: build_tail_loop graph.ainvoke must be called exactly ONCE "
            f"(the self-heal retry). Got: {tail_mock.graph.ainvoke.call_count}"
        )

        # The tail loop's ainvoke must have received a state with the synthetic AIMessage
        tail_call_args = tail_mock.graph.ainvoke.call_args
        retry_state = tail_call_args[0][0]  # positional first arg
        retry_messages = retry_state.get("messages", [])
        assert len(retry_messages) > 0, (
            f"S1: retry_state passed to tail loop must have at least one message "
            f"(the synthetic AIMessage). Got messages: {retry_messages!r}"
        )

        # Find the synthetic AIMessage
        from langchain_core.messages import AIMessage
        synthetic_msgs = [
            m for m in retry_messages
            if isinstance(m, AIMessage) and m.tool_calls
        ]
        assert len(synthetic_msgs) >= 1, (
            f"S1: retry_state messages must contain at least one AIMessage with "
            f"tool_calls (the synthetic calcular_tarifa_con_elementos call). "
            f"Got messages: {retry_messages!r}"
        )

        synthetic = synthetic_msgs[-1]
        assert synthetic.tool_calls[0]["name"] == "calcular_tarifa_con_elementos", (
            f"S1: synthetic AIMessage tool_calls[0]['name'] must be "
            f"'calcular_tarifa_con_elementos'. Got: {synthetic.tool_calls[0]!r}"
        )

        # Final ai_response must be from the SECOND (tail) loop, not the discarded first
        final_response = result.get("ai_response")
        assert final_response == _PRICE_RESPONSE, (
            f"S1: final ai_response must be the tail loop's response ('{_PRICE_RESPONSE[:40]}...'). "
            f"Got: {final_response!r}"
        )

    # -------------------------------------------------------------------------
    # T-7: S2 — calcular already called → no self-heal
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_S2_no_self_heal_when_tariff_already_called(self):
        """
        S2: GIVEN identificar AND calcular_tarifa both in tools_called,
        THEN graph.ainvoke is called ONCE (the detector is a no-op).
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        first_loop = _make_loop_result(
            ai_response=_PRICE_RESPONSE,
            tools_called=[
                "identificar_y_resolver_elementos",
                "calcular_tarifa_con_elementos",
            ],
            pending_state_updates={
                "element_codes": ["SUBCHASIS"],
                "categoria_slug": "motos-part",
                "tarifa_calculada": _TARIFA_CALCULADA,
            },
        )

        tail_mock = _make_tail_loop_mock(_make_loop_result())
        graph_mock = _make_graph_mock_seq([first_loop])
        node = PreExpedienteModeNode()
        node._build_client_context = MagicMock(return_value={})

        with (
            patch(f"{_MODULE}._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch(f"{_MODULE}.build_mode_tool_loop", return_value=graph_mock),
            patch(f"{_MODULE}.build_tail_loop", return_value=tail_mock),
            patch(f"{_MODULE}.clear_image_tools_state"),
            patch(f"{_MODULE}.assemble_system_prompt", return_value="prompt"),
            patch("agent.tools.draft_quote_service._deactivate_draft_quote", new_callable=AsyncMock),
            patch(f"{_MODULE}._enforce_cta5_if_needed", side_effect=lambda ai_response, **k: ai_response),
        ):
            await node._process_with_tool_loop("¿Qué precio?", _minimal_pricing_state())

        # Main loop called once
        assert graph_mock.graph.ainvoke.call_count == 1, (
            f"S2: main loop must be called exactly ONCE. Got: {graph_mock.graph.ainvoke.call_count}"
        )
        # Tail loop must NOT have been called
        assert tail_mock.graph.ainvoke.call_count == 0, (
            f"S2: tail loop must NOT be called when calcular was already in tools_called. "
            f"Got: {tail_mock.graph.ainvoke.call_count}"
        )

    # -------------------------------------------------------------------------
    # T-8: S3 — off-topic turn → no self-heal
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_S3_no_self_heal_off_topic_turn(self):
        """
        S3: GIVEN identificar NOT in tools_called (off-topic turn) but element_codes
        present in state from a prior turn, THEN graph.ainvoke is called ONCE
        and no self-heal warning is logged.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        # Off-topic turn: no tools called at all
        first_loop = _make_loop_result(
            ai_response="Para ese trámite necesitas ir al ministerio.",
            tools_called=[],
            pending_state_updates={},
        )

        tail_mock = _make_tail_loop_mock(_make_loop_result())
        graph_mock = _make_graph_mock_seq([first_loop])
        node = PreExpedienteModeNode()
        node._build_client_context = MagicMock(return_value={})

        # element_codes present in state from a prior turn
        state = _minimal_pricing_state(element_codes=["SUBCHASIS"], categoria_slug="motos-part")
        mock_logger = MagicMock()

        with (
            patch(f"{_MODULE}._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch(f"{_MODULE}.build_mode_tool_loop", return_value=graph_mock),
            patch(f"{_MODULE}.build_tail_loop", return_value=tail_mock),
            patch(f"{_MODULE}.clear_image_tools_state"),
            patch(f"{_MODULE}.assemble_system_prompt", return_value="prompt"),
            patch("agent.tools.draft_quote_service._deactivate_draft_quote", new_callable=AsyncMock),
            patch(f"{_MODULE}._enforce_cta5_if_needed", side_effect=lambda ai_response, **k: ai_response),
            patch(f"{_MODULE}.logger", mock_logger),
        ):
            await node._process_with_tool_loop("¿Qué más necesito?", state)

        # Main loop called once
        assert graph_mock.graph.ainvoke.call_count == 1, (
            f"S3: main loop must be called exactly ONCE. Got: {graph_mock.graph.ainvoke.call_count}"
        )
        # Tail loop must NOT have been called
        assert tail_mock.graph.ainvoke.call_count == 0, (
            f"S3: tail loop must NOT be called for off-topic turn. "
            f"Got: {tail_mock.graph.ainvoke.call_count}"
        )
        # No self-heal warning logged
        self_heal_warning_calls = [
            c for c in mock_logger.warning.call_args_list
            if c.args and "self_heal" in str(c.args[0])
        ]
        assert len(self_heal_warning_calls) == 0, (
            f"S3: no self-heal WARNING must be emitted for off-topic turn. "
            f"Got: {self_heal_warning_calls!r}"
        )

    # -------------------------------------------------------------------------
    # T-9: S4 — precio_comunicado already True → no self-heal
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_S4_no_self_heal_when_precio_already_communicated(self):
        """
        S4: GIVEN mc.precio_comunicado=True AND identificar in tools_called
        AND tarifa_calculada empty, THEN graph.ainvoke is called ONCE.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        first_loop = _make_loop_result(
            ai_response="Como ya te comenté, el precio es 480€.",
            tools_called=["identificar_y_resolver_elementos"],
            pending_state_updates={
                "element_codes": ["SUBCHASIS"],
                "categoria_slug": "motos-part",
            },
        )

        tail_mock = _make_tail_loop_mock(_make_loop_result())
        graph_mock = _make_graph_mock_seq([first_loop])
        node = PreExpedienteModeNode()
        node._build_client_context = MagicMock(return_value={})

        # precio_comunicado=True → guard must block self-heal
        state = _minimal_pricing_state(
            element_codes=["SUBCHASIS"],
            categoria_slug="motos-part",
            precio_comunicado=True,
        )

        with (
            patch(f"{_MODULE}._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch(f"{_MODULE}.build_mode_tool_loop", return_value=graph_mock),
            patch(f"{_MODULE}.build_tail_loop", return_value=tail_mock),
            patch(f"{_MODULE}.clear_image_tools_state"),
            patch(f"{_MODULE}.assemble_system_prompt", return_value="prompt"),
            patch("agent.tools.draft_quote_service._deactivate_draft_quote", new_callable=AsyncMock),
            patch(f"{_MODULE}._enforce_cta5_if_needed", side_effect=lambda ai_response, **k: ai_response),
        ):
            await node._process_with_tool_loop("¿Cuánto era?", state)

        assert graph_mock.graph.ainvoke.call_count == 1, (
            f"S4: main loop must be called exactly ONCE. Got: {graph_mock.graph.ainvoke.call_count}"
        )
        assert tail_mock.graph.ainvoke.call_count == 0, (
            f"S4: tail loop must NOT be called when precio_comunicado=True. "
            f"Got: {tail_mock.graph.ainvoke.call_count}"
        )

    # -------------------------------------------------------------------------
    # T-10: S5 — missing categoria_slug → degraded fallback + WARNING
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_S5_no_self_heal_when_categoria_slug_missing(self):
        """
        S5: GIVEN element_codes present but categoria_slug missing,
        AND identificar in tools_called AND text-only response,
        THEN graph.ainvoke is called ONCE AND WARNING log
        'tariff_gate_self_heal_skipped_missing_categoria' is emitted.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        first_loop = _make_loop_result(
            ai_response=_TEXT_ONLY_RESPONSE,
            tools_called=["identificar_y_resolver_elementos"],
            pending_state_updates={
                "element_codes": ["SUBCHASIS"],
                # categoria_slug intentionally absent from pending updates
            },
        )

        tail_mock = _make_tail_loop_mock(_make_loop_result())
        graph_mock = _make_graph_mock_seq([first_loop])
        node = PreExpedienteModeNode()
        node._build_client_context = MagicMock(return_value={})

        # Build state WITHOUT categoria_slug in mode_context
        state = _minimal_pricing_state(
            element_codes=["SUBCHASIS"],
            categoria_slug="",  # empty → falsy → S5 guard fires
        )
        mock_logger = MagicMock()

        with (
            patch(f"{_MODULE}._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch(f"{_MODULE}.build_mode_tool_loop", return_value=graph_mock),
            patch(f"{_MODULE}.build_tail_loop", return_value=tail_mock),
            patch(f"{_MODULE}.clear_image_tools_state"),
            patch(f"{_MODULE}.assemble_system_prompt", return_value="prompt"),
            patch("agent.tools.draft_quote_service._deactivate_draft_quote", new_callable=AsyncMock),
            patch(f"{_MODULE}._enforce_cta5_if_needed", side_effect=lambda ai_response, **k: ai_response),
            patch(f"{_MODULE}.logger", mock_logger),
        ):
            await node._process_with_tool_loop("¿Qué necesito?", state)

        # Main loop called once (no retry)
        assert graph_mock.graph.ainvoke.call_count == 1, (
            f"S5: main loop must be called exactly ONCE. Got: {graph_mock.graph.ainvoke.call_count}"
        )
        assert tail_mock.graph.ainvoke.call_count == 0, (
            f"S5: tail loop must NOT be called when categoria_slug is missing. "
            f"Got: {tail_mock.graph.ainvoke.call_count}"
        )
        # S5 WARNING must be emitted with the specific event name
        s5_warning_calls = [
            c for c in mock_logger.warning.call_args_list
            if c.args and c.args[0] == "tariff_gate_self_heal_skipped_missing_categoria"
        ]
        assert len(s5_warning_calls) >= 1, (
            f"S5: WARNING 'tariff_gate_self_heal_skipped_missing_categoria' must be logged. "
            f"Got warning calls: {mock_logger.warning.call_args_list!r}"
        )

    # -------------------------------------------------------------------------
    # T-11: Idempotency — tail loop failure passes through (no third call)
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_idempotency_second_failure_passes_through(self):
        """
        AD-5 / Spec S6: GIVEN self-heal fires (S1 conditions met) AND the tail loop
        also returns text-only (no calcular_tarifa in its tools_called),
        THEN main graph is called exactly ONCE and tail loop is called exactly ONCE —
        no infinite retry. The final ai_response is the tail loop's degraded text.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        # First loop: S1 conditions — identificar called, text-only response
        first_loop = _make_loop_result(
            ai_response=_TEXT_ONLY_RESPONSE,
            tools_called=["identificar_y_resolver_elementos"],
            pending_state_updates={
                "element_codes": ["SUBCHASIS"],
                "categoria_slug": "motos-part",
            },
        )

        # Tail loop also fails: text-only, no calcular_tarifa (degraded scenario)
        _DEGRADED_RESPONSE = "Disculpa, vuelve a intentarlo en un momento."
        tail_degraded = _make_loop_result(
            ai_response=_DEGRADED_RESPONSE,
            tools_called=[],  # No calcular called — degraded fallback
            pending_state_updates={},
        )

        tail_mock = _make_tail_loop_mock(tail_degraded)
        graph_mock = _make_graph_mock_seq([first_loop])
        node = PreExpedienteModeNode()
        node._build_client_context = MagicMock(return_value={})

        with (
            patch(f"{_MODULE}._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch(f"{_MODULE}.build_mode_tool_loop", return_value=graph_mock),
            patch(f"{_MODULE}.build_tail_loop", return_value=tail_mock),
            patch(f"{_MODULE}.clear_image_tools_state"),
            patch(f"{_MODULE}.assemble_system_prompt", return_value="prompt"),
            patch("agent.tools.draft_quote_service._deactivate_draft_quote", new_callable=AsyncMock),
            patch(f"{_MODULE}._enforce_cta5_if_needed", side_effect=lambda ai_response, **k: ai_response),
        ):
            result = await node._process_with_tool_loop(
                "¿Qué necesito?", _minimal_pricing_state()
            )

        # Main graph called exactly ONCE (no re-call of main loop)
        assert graph_mock.graph.ainvoke.call_count == 1, (
            f"Idempotency: main loop must be called ONCE even if tail loop also fails. "
            f"Got: {graph_mock.graph.ainvoke.call_count}"
        )
        # Tail loop called exactly ONCE (flag prevents second tail retry)
        assert tail_mock.graph.ainvoke.call_count == 1, (
            f"Idempotency: tail loop must be called ONCE only. "
            f"Got: {tail_mock.graph.ainvoke.call_count}"
        )
        # Final response is the tail loop's degraded text (not the first loop's text)
        final_response = result.get("ai_response")
        assert final_response == _DEGRADED_RESPONSE, (
            f"Idempotency: final ai_response must be the tail loop's response "
            f"(degraded fallback). Got: {final_response!r}"
        )

    # -------------------------------------------------------------------------
    # T-12: Telemetry — WARNING log fields validated
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_telemetry_log_fields(self):
        """
        AD-4: GIVEN S1 conditions trigger the self-heal,
        THEN WARNING 'pre_expediente_tariff_gate_self_heal_fired' is emitted
        with all required telemetry fields: conversation_id, element_codes,
        categoria_slug, discarded_text_preview, discarded_text_length,
        tools_called_first_loop, synthetic_call_id.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        first_loop = _make_loop_result(
            ai_response=_TEXT_ONLY_RESPONSE,
            tools_called=["identificar_y_resolver_elementos"],
            pending_state_updates={
                "element_codes": ["SUBCHASIS"],
                "categoria_slug": "motos-part",
            },
        )
        second_loop = _make_loop_result(
            ai_response=_PRICE_RESPONSE,
            tools_called=["calcular_tarifa_con_elementos"],
            pending_state_updates={"tarifa_calculada": _TARIFA_CALCULADA},
        )

        tail_mock = _make_tail_loop_mock(second_loop)
        graph_mock = _make_graph_mock_seq([first_loop])
        node = PreExpedienteModeNode()
        node._build_client_context = MagicMock(return_value={})

        # Capture WARNING from self._logger (BaseModeNode instance logger)
        mock_instance_logger = MagicMock()
        node._logger = mock_instance_logger

        with (
            patch(f"{_MODULE}._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch(f"{_MODULE}.build_mode_tool_loop", return_value=graph_mock),
            patch(f"{_MODULE}.build_tail_loop", return_value=tail_mock),
            patch(f"{_MODULE}.clear_image_tools_state"),
            patch(f"{_MODULE}.assemble_system_prompt", return_value="prompt"),
            patch("agent.tools.draft_quote_service._deactivate_draft_quote", new_callable=AsyncMock),
            patch(f"{_MODULE}._enforce_cta5_if_needed", side_effect=lambda ai_response, **k: ai_response),
        ):
            await node._process_with_tool_loop(
                "¿Qué necesito?", _minimal_pricing_state()
            )

        # Find the self-heal WARNING call on the instance logger
        fired_calls = [
            c for c in mock_instance_logger.warning.call_args_list
            if c.args and c.args[0] == "pre_expediente_tariff_gate_self_heal_fired"
        ]
        assert len(fired_calls) == 1, (
            f"T-12: exactly one 'pre_expediente_tariff_gate_self_heal_fired' WARNING expected. "
            f"Got: {mock_instance_logger.warning.call_args_list!r}"
        )

        # Inspect keyword args of that call
        kwargs = fired_calls[0].kwargs

        required_fields = [
            "conversation_id",
            "element_codes",
            "categoria_slug",
            "discarded_text_preview",
            "discarded_text_length",
            "tools_called_first_loop",
            "synthetic_call_id",
        ]
        for field in required_fields:
            assert field in kwargs, (
                f"T-12: WARNING must include field '{field}'. "
                f"Got kwargs keys: {list(kwargs.keys())!r}"
            )

        # Spot-check values
        assert kwargs["conversation_id"] == "test-tariff-gate-conv-001"
        assert "SUBCHASIS" in kwargs["element_codes"]
        assert kwargs["categoria_slug"] == "motos-part"
        assert kwargs["discarded_text_preview"] == _TEXT_ONLY_RESPONSE[:1000]
        assert kwargs["discarded_text_length"] == len(_TEXT_ONLY_RESPONSE)
        assert kwargs["tools_called_first_loop"] == ["identificar_y_resolver_elementos"]
        assert kwargs["synthetic_call_id"].startswith("call_self_heal_tariff_")

    # -------------------------------------------------------------------------
    # T-13: Synthetic tool call args shape
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_synthetic_tool_call_args_shape(self):
        """
        AD-3: GIVEN S1 conditions with categoria_slug='motos-part' and
        element_codes=['A', 'B'], WHEN self-heal fires, THEN the retry_state
        passed to the tail loop contains a synthetic AIMessage whose
        tool_calls[0] has the exact required shape.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode
        from langchain_core.messages import AIMessage

        first_loop = _make_loop_result(
            ai_response=_TEXT_ONLY_RESPONSE,
            tools_called=["identificar_y_resolver_elementos"],
            pending_state_updates={
                "element_codes": ["A", "B"],
                "categoria_slug": "motos-part",
            },
        )
        second_loop = _make_loop_result(
            ai_response=_PRICE_RESPONSE,
            tools_called=["calcular_tarifa_con_elementos"],
            pending_state_updates={"tarifa_calculada": _TARIFA_CALCULADA},
        )

        tail_mock = _make_tail_loop_mock(second_loop)
        graph_mock = _make_graph_mock_seq([first_loop])
        node = PreExpedienteModeNode()
        node._build_client_context = MagicMock(return_value={})

        # Use state with element_codes=["A","B"] and categoria_slug="motos-part"
        state = _minimal_pricing_state(
            element_codes=["A", "B"],
            categoria_slug="motos-part",
        )

        with (
            patch(f"{_MODULE}._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch(f"{_MODULE}.build_mode_tool_loop", return_value=graph_mock),
            patch(f"{_MODULE}.build_tail_loop", return_value=tail_mock),
            patch(f"{_MODULE}.clear_image_tools_state"),
            patch(f"{_MODULE}.assemble_system_prompt", return_value="prompt"),
            patch("agent.tools.draft_quote_service._deactivate_draft_quote", new_callable=AsyncMock),
            patch(f"{_MODULE}._enforce_cta5_if_needed", side_effect=lambda ai_response, **k: ai_response),
        ):
            await node._process_with_tool_loop("¿Qué precio?", state)

        # Get the args passed to tail_mock.graph.ainvoke
        tail_call_args = tail_mock.graph.ainvoke.call_args
        assert tail_call_args is not None, "T-13: tail loop must have been called"

        retry_state = tail_call_args[0][0]
        retry_messages = retry_state.get("messages", [])

        # Find the synthetic AIMessage
        synthetic_msgs = [
            m for m in retry_messages
            if isinstance(m, AIMessage) and m.tool_calls
        ]
        assert len(synthetic_msgs) >= 1, (
            f"T-13: retry_state must contain an AIMessage with tool_calls. "
            f"Got messages: {retry_messages!r}"
        )

        tc = synthetic_msgs[-1].tool_calls[0]

        assert tc["name"] == "calcular_tarifa_con_elementos", (
            f"T-13: tool_calls[0]['name'] must be 'calcular_tarifa_con_elementos'. Got: {tc['name']!r}"
        )
        assert tc["args"] == {
            "categoria_vehiculo": "motos-part",
            "codigos_elementos": ["A", "B"],
            "skip_validation": True,
        }, (
            f"T-13: tool_calls[0]['args'] must match spec (AD-3). Got: {tc['args']!r}"
        )
        assert tc["id"].startswith("call_self_heal_tariff_"), (
            f"T-13: tool_calls[0]['id'] must start with 'call_self_heal_tariff_'. Got: {tc['id']!r}"
        )
        assert tc["type"] == "tool_call", (
            f"T-13: tool_calls[0]['type'] must be 'tool_call'. Got: {tc['type']!r}"
        )
