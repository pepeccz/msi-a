"""
Unit tests for standalone review_summary_node with deterministic pre-call.

fix-pre-to-expediente-state-propagation — Bug 2:
Verifies that review_summary_node calls obtener_estado_expediente before the
LLM loop and injects the result as a synthetic ToolMessage.

Spec scenarios:
- Happy path: pre-call result injected as ToolMessage before LLM.
- Fabrication guard: fixture result verbatim in LLM input.
- Fallback guard (first failure): returns blocking message, increments counter.
- Fallback guard (second failure): escalates.
"""

from __future__ import annotations

import json
import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Pre-patch structlog and langgraph.checkpoint.redis before agent imports
# ---------------------------------------------------------------------------

if "structlog" not in sys.modules:
    _structlog = types.ModuleType("structlog")
    _structlog.get_logger = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    sys.modules["structlog"] = _structlog

for _redis_mod in ("langgraph.checkpoint.redis", "langgraph.checkpoint.redis.aio"):
    if _redis_mod not in sys.modules:
        _stub = types.ModuleType(_redis_mod)
        _stub.AsyncRedisSaver = MagicMock()  # type: ignore[attr-defined]
        sys.modules[_redis_mod] = _stub

import pytest
from langchain_core.messages import ToolMessage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FIXTURE_RESULT = {
    "has_active_case": True,
    "estado": "COMPLETO",
    "precio_total": 350.0,
    "data_source": "db",
}

_FALLBACK_RESULT = {
    "data_source": "fallback",
    "has_active_case": False,
}


def _make_state(**extra: Any) -> dict:
    return {
        "conversation_id": "conv-test",
        "user_message": "Sí, confirmo",
        "expediente_sub_mode": "review_summary",
        "messages": [],
        "_review_fallback_count": 0,
        "case_id": "case-xyz",
        **extra,
    }


def _make_fake_tool(return_value: dict) -> MagicMock:
    """Return a mock that behaves like a LangChain StructuredTool (has .ainvoke)."""
    mock_tool = MagicMock()
    mock_tool.ainvoke = AsyncMock(return_value=return_value)
    return mock_tool


def _make_loop_result(ai_response: str = "Resumen listo.") -> MagicMock:
    obj = MagicMock()
    obj.recursion_limit = 10
    obj.graph.ainvoke = AsyncMock(
        return_value={
            "ai_response": ai_response,
            "exit_reason": "response",
            "pending_state_updates": {},
        }
    )
    return obj


# ---------------------------------------------------------------------------
# B1: obtener_estado_expediente called exactly once
# ---------------------------------------------------------------------------


class TestObtenerEstadoExpedienteCalledOnce:
    """review_summary_node must call obtener_estado_expediente exactly once."""

    @pytest.mark.asyncio
    async def test_obtener_estado_expediente_called_once(self):
        """
        B1 — GIVEN review_summary_node is invoked
        WHEN the node executes
        THEN obtener_estado_expediente.ainvoke is called exactly once with {}
        """
        fake_tool = _make_fake_tool(_FIXTURE_RESULT)

        with (
            patch("agent.modes.expediente_nodes.obtener_estado_expediente", fake_tool),
            patch(
                "agent.modes.expediente_nodes.build_mode_tool_loop",
                return_value=_make_loop_result(),
            ),
        ):
            from agent.modes.expediente_nodes import review_summary_node

            state = _make_state()
            await review_summary_node(state)

        fake_tool.ainvoke.assert_awaited_once_with({})


# ---------------------------------------------------------------------------
# B2: ToolMessage injected in LLM input
# ---------------------------------------------------------------------------


class TestToolMessageInjectedInLlmInput:
    """review_summary_node must inject a ToolMessage with the pre-call result."""

    @pytest.mark.asyncio
    async def test_tool_message_injected_in_llm_input(self):
        """
        B2 — GIVEN obtener_estado_expediente returns _FIXTURE_RESULT
        WHEN review_summary_node executes
        THEN the messages passed to build_mode_tool_loop contain a ToolMessage
             with name="obtener_estado_expediente" and content=json.dumps(fixture)
        """
        mock_ainvoke = AsyncMock(
            return_value={"ai_response": "ok", "exit_reason": "response", "pending_state_updates": {}}
        )

        loop_obj = MagicMock()
        loop_obj.recursion_limit = 10
        loop_obj.graph.ainvoke = mock_ainvoke

        fake_tool = _make_fake_tool(_FIXTURE_RESULT)

        with (
            patch("agent.modes.expediente_nodes.obtener_estado_expediente", fake_tool),
            patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=loop_obj),
        ):
            from agent.modes.expediente_nodes import review_summary_node

            state = _make_state()
            await review_summary_node(state)

        mock_ainvoke.assert_awaited_once()
        call_args = mock_ainvoke.call_args
        initial_state_passed = call_args[0][0]  # first positional arg

        messages = initial_state_passed.get("messages", [])

        # Find ToolMessage by checking both type name and attributes
        # (isinstance may differ across import paths in some test runners)
        review_tool_msg = next(
            (
                m
                for m in messages
                if type(m).__name__ == "ToolMessage"
                and getattr(m, "name", None) == "obtener_estado_expediente"
            ),
            None,
        )
        assert review_tool_msg is not None, (
            f"No ToolMessage(name='obtener_estado_expediente') found in LLM input. "
            f"messages={[type(m).__name__ for m in messages]}"
        )
        assert review_tool_msg.content == json.dumps(_FIXTURE_RESULT, ensure_ascii=False)


# ---------------------------------------------------------------------------
# B3: Fabrication guard — fixture content verbatim in LLM input
# ---------------------------------------------------------------------------


class TestFabricationGuard:
    """
    review_summary_node must pass the fixture result verbatim so the LLM
    cannot fabricate data not present in the tool result.
    """

    @pytest.mark.asyncio
    async def test_fabrication_guard_fixture_verbatim(self):
        """
        B3 — GIVEN fixture has estado="COMPLETO" and precio_total=350.0
        WHEN review_summary_node executes
        THEN the ToolMessage content has those exact values verbatim
        """
        mock_ainvoke = AsyncMock(
            return_value={"ai_response": "ok", "exit_reason": "response", "pending_state_updates": {}}
        )

        loop_obj = MagicMock()
        loop_obj.recursion_limit = 10
        loop_obj.graph.ainvoke = mock_ainvoke

        fake_tool = _make_fake_tool(_FIXTURE_RESULT)

        with (
            patch("agent.modes.expediente_nodes.obtener_estado_expediente", fake_tool),
            patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=loop_obj),
        ):
            from agent.modes.expediente_nodes import review_summary_node

            state = _make_state()
            await review_summary_node(state)

        mock_ainvoke.assert_awaited_once()
        initial_state_passed = mock_ainvoke.call_args[0][0]
        messages = initial_state_passed.get("messages", [])

        review_msg = next(
            (
                m
                for m in messages
                if type(m).__name__ == "ToolMessage"
                and getattr(m, "name", None) == "obtener_estado_expediente"
            ),
            None,
        )
        assert review_msg is not None, (
            f"ToolMessage for obtener_estado_expediente not found. "
            f"messages={[type(m).__name__ for m in messages]}"
        )
        content = json.loads(review_msg.content)
        assert content["estado"] == "COMPLETO"
        assert content["precio_total"] == 350.0

        # Triangulation: non-ToolMessage content must not contain contradictory estado
        non_tool_contents = [
            str(getattr(m, "content", ""))
            for m in messages
            if type(m).__name__ != "ToolMessage"
        ]
        for msg_content in non_tool_contents:
            assert "INCOMPLETO" not in msg_content, (
                f"Fabricated estado found in LLM input: {msg_content!r}"
            )


# ---------------------------------------------------------------------------
# B4: Fallback guard — blocks on first fallback, escalates on second
# ---------------------------------------------------------------------------


class TestFallbackGuard:
    """review_summary_node must block on data_source=fallback and escalate on 2nd."""

    @pytest.mark.asyncio
    async def test_fallback_guard_blocks_on_first_fallback(self):
        """
        B4a — GIVEN data_source="fallback" AND _review_fallback_count=0
        WHEN review_summary_node executes
        THEN returns Command with blocking ai_response
        AND _review_fallback_count incremented to 1
        AND build_mode_tool_loop is NOT called
        """
        fake_tool = _make_fake_tool(_FALLBACK_RESULT)
        mock_build_loop = MagicMock()

        with (
            patch("agent.modes.expediente_nodes.obtener_estado_expediente", fake_tool),
            patch("agent.modes.expediente_nodes.build_mode_tool_loop", mock_build_loop),
        ):
            from agent.modes.expediente_nodes import review_summary_node

            state = _make_state(_review_fallback_count=0)
            result = await review_summary_node(state)

        mock_build_loop.assert_not_called()

        assert result is not None
        update = result.update
        assert update is not None
        ai_response = update.get("ai_response", "")
        assert len(ai_response) > 0, "Expected a non-empty blocking ai_response"
        assert update.get("_review_fallback_count") == 1

    @pytest.mark.asyncio
    async def test_fallback_guard_escalates_on_second_fallback(self):
        """
        B4b — GIVEN data_source="fallback" AND _review_fallback_count=1
        WHEN review_summary_node executes
        THEN escalates: ai_response is non-empty, _review_fallback_count is None (tombstone)
        AND build_mode_tool_loop is NOT called
        """
        fake_tool = _make_fake_tool(_FALLBACK_RESULT)
        fake_escalar = MagicMock()
        fake_escalar.ainvoke = AsyncMock(return_value={"success": True})
        mock_build_loop = MagicMock()

        with (
            patch("agent.modes.expediente_nodes.obtener_estado_expediente", fake_tool),
            patch("agent.modes.expediente_nodes.build_mode_tool_loop", mock_build_loop),
            patch("agent.tools.shared_tools.escalar_a_humano", fake_escalar),
        ):
            from agent.modes.expediente_nodes import review_summary_node

            state = _make_state(_review_fallback_count=1)
            result = await review_summary_node(state)

        mock_build_loop.assert_not_called()

        assert result is not None
        update = result.update
        assert update is not None
        ai_response = update.get("ai_response", "")
        assert len(ai_response) > 0
        assert update.get("_review_fallback_count") is None


# ---------------------------------------------------------------------------
# B7: _auto_emit_review_summary path unchanged (regression)
# ---------------------------------------------------------------------------


class TestAutoEmitReviewSummaryPathUnchanged:
    """
    B7 — _auto_emit_review_summary still calls review_summary_node by symbol name.
    """

    @pytest.mark.asyncio
    async def test_auto_emit_path_invokes_review_summary_node(self):
        """
        GIVEN _auto_emit_review_summary calls review_summary_node
        WHEN review_summary_node is patched with a fake
        THEN the fake is invoked — symbol reference is stable after refactor.
        """
        from agent.modes.expediente_nodes import _auto_emit_review_summary
        from agent.utils.expediente_types import CollectionStep

        review_text = "Resumen completo del expediente."
        fake_cmd = MagicMock()
        fake_cmd.update = {
            "ai_response": review_text,
            "expediente_sub_mode": CollectionStep.REVIEW_SUMMARY.value,
        }
        fake_node = AsyncMock(return_value=fake_cmd)

        state = {
            "case_id": "c-123",
            "conversation_id": "cv-123",
            "expediente_sub_mode": CollectionStep.COLLECT_WORKSHOP.value,
            "user_message": "listo",
            "messages": [],
            "personal_collected": True,
            "vehicle_collected": True,
            "workshop_collected": False,
            "taller_propio": None,
            "ai_response": "",
            "pending_images": None,
            "element_phase": None,
            "element_data_status": {},
            "current_element_code": None,
        }
        update = {
            "workshop_collected": True,
            "expediente_sub_mode": CollectionStep.REVIEW_SUMMARY.value,
            "ai_response": "promesa...",
        }

        with patch("agent.modes.expediente_nodes.review_summary_node", fake_node):
            result = await _auto_emit_review_summary(
                update=update,
                state=state,
                mode_name="EXPEDIENTE_COLLECT_WORKSHOP",
                conversation_id="cv-123",
            )

        fake_node.assert_awaited_once()
        assert result["ai_response"] == review_text
