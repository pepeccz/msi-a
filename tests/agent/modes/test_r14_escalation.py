"""
Unit tests for R-14 guard — C5 of fix-r3-tool-not-found.

R-14 escalates to ESCALATION mode when the R3 self-heal tail loop hits an
unrecoverable tool_not_found failure, or when C4 already aborted R3 due to
the tool missing from the registry.

Scenarios:
  - Q1: After tail loop, last ToolMessage has tool_call_id starting with
        "call_self_heal_tariff_" AND contains error_type=tool_not_found →
        R-14 MUST fire: result_dict["current_mode"] = "ESCALATION" and
        emit structured log "pre_expediente_r14_fired" with 8 R-12 fields.
  - Q2: Non-self-heal tool_not_found (call_id NOT prefixed "call_self_heal_tariff_")
        → R-14 MUST NOT fire.
  - Q3: C4 abort path (_r3_aborted_tool_missing=True) MUST also trigger R-14
        (reason="r3_abort_tool_missing").
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

_MODULE = "agent.modes.pre_expediente_mode"

_TEXT_ONLY = "Para homologar subchasis necesitas los siguientes documentos..."
_PRICE_REPLY = "El presupuesto total es 480€ +IVA. ¿Quieres proceder?"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_message(*, tool_call_id: str, content: str | dict) -> object:
    """Build a ToolMessage-like object for injection into loop messages."""
    from langchain_core.messages import ToolMessage

    if isinstance(content, dict):
        content = json.dumps(content)
    return ToolMessage(content=content, tool_call_id=tool_call_id)


def _tool_not_found_content(tool_name: str = "calcular_tarifa_con_elementos") -> dict:
    return {"error": f"Tool '{tool_name}' not found", "error_type": "tool_not_found"}


def _make_loop_result(
    *,
    ai_response: str = _TEXT_ONLY,
    tools_called: list[str] | None = None,
    pending_state_updates: dict | None = None,
    messages: list | None = None,
) -> dict:
    return {
        "ai_response": ai_response,
        "exit_reason": "response",
        "tools_called": tools_called if tools_called is not None else [],
        "pending_state_updates": pending_state_updates or {},
        "messages": messages if messages is not None else [],
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
        "conversation_id": "test-r14-conv",
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


class _FakeCalcularTool:
    name = "calcular_tarifa_con_elementos"


class _FakeOtherTool:
    name = "identificar_y_resolver_elementos"


_TOOLS_WITH_CALCULAR = [_FakeCalcularTool(), _FakeOtherTool()]
_TOOLS_WITHOUT_CALCULAR = [_FakeOtherTool()]

_R14_FIELDS = {
    "guard_id",
    "conversation_id",
    "mode",
    "categoria_slug",
    "element_codes",
    "synthetic_call_id",
    "tool_name",
    "reason",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestR14EscalationGuard:
    @pytest.mark.asyncio
    async def test_Q1_r14_fires_on_self_heal_tool_not_found(self):
        """
        Q1: After R3 tail loop, last ToolMessage has tool_call_id prefixed
        "call_self_heal_tariff_" and error_type=tool_not_found.
        R-14 MUST:
          - set result_dict["current_mode"] = "ESCALATION"
          - emit log "pre_expediente_r14_fired" with all 8 R-12 fields.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        synthetic_call_id = "call_self_heal_tariff_abcdef123456"
        tool_msg = _make_tool_message(
            tool_call_id=synthetic_call_id,
            content=_tool_not_found_content(),
        )

        first = _make_loop_result(
            ai_response=_TEXT_ONLY,
            tools_called=["identificar_y_resolver_elementos"],
            pending_state_updates={
                "element_codes": ["SUBCHASIS"],
                "categoria_slug": "motos-part",
            },
        )
        # Tail loop result contains the tool_not_found ToolMessage
        tail_result = _make_loop_result(
            ai_response="Lo siento, ha ocurrido un error.",
            tools_called=[],
            messages=[tool_msg],
        )

        graph_mock = _make_graph_mock(first)
        tail_mock = _make_tail_mock(tail_result)

        node = PreExpedienteModeNode()
        node._build_client_context = MagicMock(return_value={})

        logged_warnings: list[dict] = []

        with (
            patch(f"{_MODULE}._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch(f"{_MODULE}.build_mode_tool_loop", return_value=graph_mock),
            patch(f"{_MODULE}.build_tail_loop", return_value=tail_mock),
            patch(f"{_MODULE}.clear_image_tools_state"),
            patch(f"{_MODULE}.assemble_system_prompt", return_value="prompt"),
            patch("agent.tools.draft_quote_service._deactivate_draft_quote", new_callable=AsyncMock),
            patch(f"{_MODULE}._enforce_cta5_if_needed", side_effect=lambda ai_response, **k: ai_response),
            patch(f"{_MODULE}._r3_get_tools_for_validation", return_value=_TOOLS_WITH_CALCULAR),
        ):
            node._logger = MagicMock()
            node._logger.warning = MagicMock(
                side_effect=lambda ev, **kw: logged_warnings.append({"event": ev, **kw})
            )
            node._logger.info = MagicMock()
            node._logger.error = MagicMock()

            result = await node._process_with_tool_loop("homologar subchasis", _pricing_state())

        # R-14 MUST escalate
        assert result.get("current_mode") == "ESCALATION", (
            f"Q1: R-14 MUST set current_mode='ESCALATION' when self-heal tail loop "
            f"hits tool_not_found. Got current_mode={result.get('current_mode')!r}"
        )

        # "pre_expediente_r14_fired" MUST be logged
        r14_logs = [e for e in logged_warnings if e["event"] == "pre_expediente_r14_fired"]
        assert r14_logs, (
            f"Q1: logger.warning('pre_expediente_r14_fired', ...) MUST be emitted. "
            f"Logged warning events: {[e['event'] for e in logged_warnings]!r}"
        )

        r14_log = r14_logs[0]
        missing_fields = _R14_FIELDS - set(r14_log.keys())
        assert not missing_fields, (
            f"Q1: R-14 log missing required R-12 fields: {missing_fields!r}. "
            f"Got fields: {set(r14_log.keys())!r}"
        )

    @pytest.mark.asyncio
    async def test_Q2_r14_does_not_fire_for_non_self_heal_tool_not_found(self):
        """
        Q2: A ToolMessage whose tool_call_id does NOT start with
        "call_self_heal_tariff_" and has error_type=tool_not_found.
        R-14 MUST NOT fire — no ESCALATION, no "pre_expediente_r14_fired" log.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        # Generic tool_call_id (not self-heal prefixed)
        tool_msg = _make_tool_message(
            tool_call_id="call_some_other_tool_xyz123",
            content=_tool_not_found_content("some_other_tool"),
        )

        first = _make_loop_result(
            ai_response=_TEXT_ONLY,
            tools_called=["identificar_y_resolver_elementos"],
            pending_state_updates={
                "element_codes": ["SUBCHASIS"],
                "categoria_slug": "motos-part",
            },
        )
        tail_result = _make_loop_result(
            ai_response="Lo siento, ha ocurrido un error.",
            tools_called=[],
            messages=[tool_msg],
        )

        graph_mock = _make_graph_mock(first)
        tail_mock = _make_tail_mock(tail_result)

        node = PreExpedienteModeNode()
        node._build_client_context = MagicMock(return_value={})

        logged_warnings: list[dict] = []

        with (
            patch(f"{_MODULE}._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch(f"{_MODULE}.build_mode_tool_loop", return_value=graph_mock),
            patch(f"{_MODULE}.build_tail_loop", return_value=tail_mock),
            patch(f"{_MODULE}.clear_image_tools_state"),
            patch(f"{_MODULE}.assemble_system_prompt", return_value="prompt"),
            patch("agent.tools.draft_quote_service._deactivate_draft_quote", new_callable=AsyncMock),
            patch(f"{_MODULE}._enforce_cta5_if_needed", side_effect=lambda ai_response, **k: ai_response),
            patch(f"{_MODULE}._r3_get_tools_for_validation", return_value=_TOOLS_WITH_CALCULAR),
        ):
            node._logger = MagicMock()
            node._logger.warning = MagicMock(
                side_effect=lambda ev, **kw: logged_warnings.append({"event": ev, **kw})
            )
            node._logger.info = MagicMock()
            node._logger.error = MagicMock()

            result = await node._process_with_tool_loop("homologar subchasis", _pricing_state())

        assert result.get("current_mode") != "ESCALATION", (
            f"Q2: R-14 MUST NOT fire for non-self-heal tool_not_found. "
            f"Got current_mode={result.get('current_mode')!r}"
        )

        r14_logs = [e for e in logged_warnings if e["event"] == "pre_expediente_r14_fired"]
        assert not r14_logs, (
            f"Q2: 'pre_expediente_r14_fired' MUST NOT be logged for non-self-heal "
            f"tool_not_found. Got: {r14_logs!r}"
        )

    @pytest.mark.asyncio
    async def test_Q3_r14_fires_on_c4_abort_path(self):
        """
        Q3: C4 aborted R3 because calcular_tarifa_con_elementos was missing from
        the tools registry (_r3_aborted_tool_missing=True).
        R-14 MUST also fire on this path with reason="r3_abort_tool_missing".
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

        graph_mock = _make_graph_mock(first)
        tail_mock = _make_tail_mock({})  # tail loop must NOT be called

        node = PreExpedienteModeNode()
        node._build_client_context = MagicMock(return_value={})

        logged_warnings: list[dict] = []

        with (
            patch(f"{_MODULE}._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch(f"{_MODULE}.build_mode_tool_loop", return_value=graph_mock),
            patch(f"{_MODULE}.build_tail_loop", return_value=tail_mock),
            patch(f"{_MODULE}.clear_image_tools_state"),
            patch(f"{_MODULE}.assemble_system_prompt", return_value="prompt"),
            patch("agent.tools.draft_quote_service._deactivate_draft_quote", new_callable=AsyncMock),
            patch(f"{_MODULE}._enforce_cta5_if_needed", side_effect=lambda ai_response, **k: ai_response),
            # C4 abort: validation seam returns tools WITHOUT calcular
            patch(f"{_MODULE}._r3_get_tools_for_validation", return_value=_TOOLS_WITHOUT_CALCULAR),
        ):
            node._logger = MagicMock()
            node._logger.warning = MagicMock(
                side_effect=lambda ev, **kw: logged_warnings.append({"event": ev, **kw})
            )
            node._logger.info = MagicMock()
            node._logger.error = MagicMock()

            result = await node._process_with_tool_loop("homologar subchasis", _pricing_state())

        # R-14 MUST escalate even on C4 abort path
        assert result.get("current_mode") == "ESCALATION", (
            f"Q3: R-14 MUST set current_mode='ESCALATION' on C4 abort path. "
            f"Got current_mode={result.get('current_mode')!r}"
        )

        # "pre_expediente_r14_fired" must be logged with reason="r3_abort_tool_missing"
        r14_logs = [e for e in logged_warnings if e["event"] == "pre_expediente_r14_fired"]
        assert r14_logs, (
            f"Q3: logger.warning('pre_expediente_r14_fired', ...) MUST be emitted on "
            f"C4 abort path. Logged warning events: {[e['event'] for e in logged_warnings]!r}"
        )

        r14_log = r14_logs[0]
        assert r14_log.get("reason") == "r3_abort_tool_missing", (
            f"Q3: R-14 log 'reason' MUST be 'r3_abort_tool_missing' on C4 abort path. "
            f"Got reason={r14_log.get('reason')!r}"
        )

        missing_fields = _R14_FIELDS - set(r14_log.keys())
        assert not missing_fields, (
            f"Q3: R-14 log missing required R-12 fields: {missing_fields!r}. "
            f"Got fields: {set(r14_log.keys())!r}"
        )
