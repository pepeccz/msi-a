"""
Unit tests for R3 pre-inject validation — C4 of fix-r3-tool-not-found.

Defense-in-depth: before building the synthetic tariff tool_call, verify that
`_r3_get_tools_for_validation(config, updated_context)` returns a list that
contains `calcular_tarifa_con_elementos`. If missing → abort R3 injection,
emit structured ERROR log. No tail loop is invoked.

Scenarios:
  - P1: tool missing from registry → R3 MUST abort, no tail loop, ERROR logged
        with `tools_in_registry` and `ctx_has_elements` fields.
  - P2: tool present in registry (normal path) → R3 MUST NOT abort, tail loop fires.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

_MODULE = "agent.modes.pre_expediente_mode"

_TEXT_ONLY = "Para homologar subchasis necesitas los siguientes documentos..."
_PRICE_REPLY = "El presupuesto total es 480€ +IVA. ¿Quieres proceder?"


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_tariff_gate_self_heal.py)
# ---------------------------------------------------------------------------


def _make_loop_result(
    *,
    ai_response: str = _TEXT_ONLY,
    tools_called: list[str] | None = None,
    pending_state_updates: dict | None = None,
) -> dict:
    return {
        "ai_response": ai_response,
        "exit_reason": "response",
        "tools_called": tools_called if tools_called is not None else [],
        "pending_state_updates": pending_state_updates or {},
        "messages": [],
    }


def _make_graph_mock(result: dict) -> MagicMock:
    mock = MagicMock()
    mock.graph.ainvoke = AsyncMock(return_value=result)
    mock.recursion_limit = 25
    return mock


def _make_tail_mock(result: dict) -> MagicMock:
    mock = MagicMock()
    mock.graph.ainvoke = AsyncMock(return_value=result)
    mock.recursion_limit = 35
    return mock


def _pricing_state() -> dict:
    """PRE_EXPEDIENTE_PRICING state with element_codes populated."""
    return {
        "conversation_id": "test-r3-pre-inject-conv",
        "mode_context": {
            "element_codes": ["SUBCHASIS"],
            "categoria_slug": "motos-part",
            "tarifa_calculada": None,
            "precio_comunicado": False,
        },
        "messages": [],
        "client_type": "particular",
        "is_first_interaction": False,
    }


# ---------------------------------------------------------------------------
# Fake tool sentinels used as return value from _r3_get_tools_for_validation
# ---------------------------------------------------------------------------


class _FakeCalcularTool:
    """Sentinel that represents calcular_tarifa_con_elementos in the tool list."""
    name = "calcular_tarifa_con_elementos"


class _FakeOtherTool:
    name = "identificar_y_resolver_elementos"


_TOOLS_WITH_CALCULAR = [_FakeCalcularTool(), _FakeOtherTool()]
_TOOLS_WITHOUT_CALCULAR = [_FakeOtherTool()]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestR3PreInjectValidation:
    @pytest.mark.asyncio
    async def test_P1_aborts_when_calcular_missing_from_registry(self):
        """
        P1 (RED scenario): R3 fire conditions are met (text-only after identificar,
        element_codes populated), BUT _r3_get_tools_for_validation returns a list
        that does NOT contain calcular_tarifa_con_elementos.
        THEN: tail loop must NOT be invoked AND logger.error(
        "pre_expediente_r3_abort_tool_missing", tools_in_registry=...,
        ctx_has_elements=...) is emitted.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        first = _make_loop_result(
            ai_response=_TEXT_ONLY,
            tools_called=["identificar_y_resolver_elementos"],
            pending_state_updates={
                "element_codes": ["SUBCHASIS"],
                "categoria_slug": "motos-part",
            },
        )
        second = _make_loop_result(
            ai_response=_PRICE_REPLY,
            tools_called=["calcular_tarifa_con_elementos"],
            pending_state_updates={
                "tarifa_calculada": {"total": 480.0},
                "precio_comunicado": True,
            },
        )

        graph_mock = _make_graph_mock(first)
        tail_mock = _make_tail_mock(second)

        node = PreExpedienteModeNode()
        node._build_client_context = MagicMock(return_value={})

        logged_errors: list[dict] = []

        with (
            patch(f"{_MODULE}._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch(f"{_MODULE}.build_mode_tool_loop", return_value=graph_mock),
            patch(f"{_MODULE}.build_tail_loop", return_value=tail_mock),
            patch(f"{_MODULE}.clear_image_tools_state"),
            patch(f"{_MODULE}.assemble_system_prompt", return_value="prompt"),
            patch("agent.tools.draft_quote_service._deactivate_draft_quote", new_callable=AsyncMock),
            patch(f"{_MODULE}._enforce_cta5_if_needed", side_effect=lambda ai_response, **k: ai_response),
            # Key patch: force the validation seam to return tools WITHOUT calcular
            patch(
                f"{_MODULE}._r3_get_tools_for_validation",
                return_value=_TOOLS_WITHOUT_CALCULAR,
            ),
        ):
            node._logger = MagicMock()
            node._logger.warning = MagicMock()
            node._logger.info = MagicMock()
            node._logger.error = MagicMock(
                side_effect=lambda ev, **kw: logged_errors.append({"event": ev, **kw})
            )

            result = await node._process_with_tool_loop("homologar subchasis", _pricing_state())

        # Tail loop must NOT have been invoked
        assert tail_mock.graph.ainvoke.call_count == 0, (
            f"P1: R3 tail loop MUST NOT fire when calcular_tarifa_con_elementos is "
            f"missing from get_tools registry. "
            f"Got call_count={tail_mock.graph.ainvoke.call_count}"
        )

        # An ERROR must have been logged with the required event name
        error_events = [e["event"] for e in logged_errors]
        assert "pre_expediente_r3_abort_tool_missing" in error_events, (
            f"P1: logger.error('pre_expediente_r3_abort_tool_missing', ...) MUST be "
            f"emitted when tool is missing. Logged error events: {error_events!r}"
        )

        # The error log must carry both required structured fields
        abort_log = next(
            e for e in logged_errors if e["event"] == "pre_expediente_r3_abort_tool_missing"
        )
        assert "tools_in_registry" in abort_log, (
            f"P1: abort log must include 'tools_in_registry' field. Got: {abort_log!r}"
        )
        assert "ctx_has_elements" in abort_log, (
            f"P1: abort log must include 'ctx_has_elements' field. Got: {abort_log!r}"
        )

    @pytest.mark.asyncio
    async def test_P2_proceeds_normally_when_calcular_present(self):
        """
        P2: R3 fire conditions met AND _r3_get_tools_for_validation returns a list
        that DOES contain calcular_tarifa_con_elementos → validation passes,
        tail loop IS invoked exactly once.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        first = _make_loop_result(
            ai_response=_TEXT_ONLY,
            tools_called=["identificar_y_resolver_elementos"],
            pending_state_updates={
                "element_codes": ["SUBCHASIS"],
                "categoria_slug": "motos-part",
            },
        )
        second = _make_loop_result(
            ai_response=_PRICE_REPLY,
            tools_called=["calcular_tarifa_con_elementos"],
            pending_state_updates={
                "tarifa_calculada": {"total": 480.0},
                "precio_comunicado": True,
            },
        )

        graph_mock = _make_graph_mock(first)
        tail_mock = _make_tail_mock(second)

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
            # Key patch: validation seam returns tools WITH calcular → proceed
            patch(
                f"{_MODULE}._r3_get_tools_for_validation",
                return_value=_TOOLS_WITH_CALCULAR,
            ),
        ):
            result = await node._process_with_tool_loop("homologar subchasis", _pricing_state())

        assert tail_mock.graph.ainvoke.call_count == 1, (
            f"P2: tail loop MUST fire when calcular_tarifa_con_elementos IS present. "
            f"Got call_count={tail_mock.graph.ainvoke.call_count}"
        )
