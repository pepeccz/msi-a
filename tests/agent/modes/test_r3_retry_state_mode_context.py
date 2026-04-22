"""
Unit test for R3 tariff-gate self-heal retry_state mode_context propagation.

Regression: the self-heal used to build _retry_state with {**initial_state, ...},
carrying the TURN-START _mode_context (pre-identificar, element_codes=[]). When the
tail loop's tool_node re-evaluates get_tools(mode_context), GATE 4 in
pre_expediente_mode.py:1581 removes calcular_tarifa_con_elementos because
has_elements is False. Result: synthetic tool_call hits tool_executor lookup →
tool_not_found silent failure → LLM turn 3 regurgitates narration without €.

This test asserts that _retry_state passed to build_tail_loop.graph.ainvoke
carries the UPDATED mode_context (post-identificar, element_codes populated).
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

_MODULE = "agent.modes.pre_expediente_mode"

_TEXT_ONLY = "Para homologar subchasis necesitas los siguientes documentos..."
_PRICE_REPLY = "El presupuesto total es 480€ +IVA. ¿Quieres proceder?"


def _loop_result(*, ai_response: str, tools_called: list[str], psu: dict | None = None) -> dict:
    return {
        "ai_response": ai_response,
        "exit_reason": "response",
        "tools_called": tools_called,
        "pending_state_updates": psu or {},
        "messages": [],
    }


def _state_discovery() -> dict:
    """Turn-start state: DISCOVERY phase (no element_codes yet)."""
    return {
        "conversation_id": "test-r3-retry-conv",
        "mode_context": {
            "element_codes": [],
            "categoria_slug": "",
            "tarifa_calculada": None,
            "precio_comunicado": False,
        },
        "messages": [],
        "client_type": "particular",
        "is_first_interaction": False,
    }


class TestR3RetryStateModeContext:
    @pytest.mark.asyncio
    async def test_retry_state_carries_post_identificar_mode_context(self):
        """
        GIVEN turn-start mode_context with element_codes=[] (DISCOVERY),
        WHEN the main tool loop returns with tools_called=[identificar] and
          pending_state_updates.element_codes=[SUBCHASIS, ASIDEROS] AND ai_response
          is text-only (triggers R3 self-heal),
        THEN the _retry_state passed to build_tail_loop.graph.ainvoke MUST have
          _mode_context with element_codes=[SUBCHASIS, ASIDEROS] (NOT the empty
          turn-start snapshot). This ensures the tail loop's tool_node
          get_tools(_mode_context) sees has_elements=True and GATE 4 keeps
          calcular_tarifa_con_elementos in the registry.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        first = _loop_result(
            ai_response=_TEXT_ONLY,
            tools_called=["identificar_y_resolver_elementos"],
            psu={
                "element_codes": ["SUBCHASIS", "ASIDEROS"],
                "categoria_slug": "motos-part",
            },
        )
        second = _loop_result(
            ai_response=_PRICE_REPLY,
            tools_called=["calcular_tarifa_con_elementos"],
            psu={
                "tarifa_calculada": {"total": 480.0},
                "precio_comunicado": True,
            },
        )

        graph_mock = MagicMock()
        graph_mock.graph.ainvoke = AsyncMock(return_value=first)
        graph_mock.recursion_limit = 25

        tail_mock = MagicMock()
        tail_mock.graph.ainvoke = AsyncMock(return_value=second)
        tail_mock.recursion_limit = 35

        node = PreExpedienteModeNode()
        node._build_client_context = MagicMock(return_value={})

        with (
            patch(f"{_MODULE}._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch(f"{_MODULE}.build_mode_tool_loop", return_value=graph_mock),
            patch(f"{_MODULE}.build_tail_loop", return_value=tail_mock),
            patch(f"{_MODULE}.clear_image_tools_state"),
            patch(f"{_MODULE}.assemble_system_prompt", return_value="prompt"),
            patch(
                "agent.tools.draft_quote_service._deactivate_draft_quote",
                new_callable=AsyncMock,
            ),
            patch(
                f"{_MODULE}._enforce_cta5_if_needed",
                side_effect=lambda ai_response, **k: ai_response,
            ),
        ):
            await node._process_with_tool_loop("homologar subchasis y agarraderas", _state_discovery())

        assert tail_mock.graph.ainvoke.call_count == 1, (
            "R3 tail loop must fire exactly once"
        )

        retry_state = tail_mock.graph.ainvoke.call_args[0][0]
        retry_mc = retry_state.get("_mode_context") or {}
        retry_elements = retry_mc.get("element_codes") or []

        assert retry_elements == ["SUBCHASIS", "ASIDEROS"], (
            f"R3 BUG: _retry_state._mode_context.element_codes must be "
            f"['SUBCHASIS', 'ASIDEROS'] (post-identificar merged). "
            f"Got: {retry_elements!r}. "
            f"Turn-start empty mode_context leaks into tail loop → "
            f"GATE 4 removes calcular_tarifa_con_elementos → tool_not_found."
        )
        assert retry_mc.get("categoria_slug") == "motos-part", (
            f"R3 BUG: _retry_state._mode_context.categoria_slug must be 'motos-part'. "
            f"Got: {retry_mc.get('categoria_slug')!r}"
        )
