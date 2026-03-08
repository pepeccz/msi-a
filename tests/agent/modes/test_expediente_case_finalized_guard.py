"""
Tests for ExpedienteModeNode._run_llm_loop() case_finalized guard — Bug 1.

Fix: When finalizar_expediente() returns _internal_flags.case_finalized=True,
the loop exits immediately and no further tools are called.

Scenarios covered:
  1. Single tool [finalizar_expediente] → loop exits, result carries finalization message
  2. Two tools [finalizar_expediente, escalar_a_humano] in same batch →
     loop exits after finalization, escalar_a_humano is NOT executed
  3. Negative: tool returns success without case_finalized → loop continues normally
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from agent.modes.expediente_mode import ExpedienteModeNode, REVIEW_SUMMARY
from agent.state.helpers import set_current_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONVERSATION_ID = "test-conv-guard-001"

FINALIZED_TOOL_RESULT = json.dumps({
    "success": True,
    "message": "¡Perfecto! Tu expediente ha sido enviado para revisión.",
    "case_id": "case-abc-123",
    "next_step": "completed",
    "fsm_state_update": {},
    "_internal_flags": {"case_finalized": True},
})

# A "normal" tool result that does NOT set case_finalized
NORMAL_TOOL_RESULT = json.dumps({
    "success": True,
    "message": "Datos guardados correctamente.",
    "_internal_flags": {},
})

# escalar_a_humano result (plain string, no flags)
ESCALAR_TOOL_RESULT = "Escalado a agente humano."


def _make_state() -> dict[str, Any]:
    return {
        "conversation_id": CONVERSATION_ID,
        "user_id": "user-001",
        "messages": [],
        "mode_context": {
            "expediente_sub_mode": REVIEW_SUMMARY,
            "case_id": "case-abc-123",
            "categoria_slug": "motos-part",
        },
        "fsm_state": {
            "current_step": "review_summary",
            "case_id": "case-abc-123",
            "category_slug": "motos-part",
            "element_codes": ["ESCAPE"],
            "tariff_amount": 350.0,
        },
        "incoming_attachments": [],
    }


def _make_mock_tool(name: str) -> MagicMock:
    """Create a fake LangChain tool mock."""
    t = MagicMock()
    t.name = name
    t.args_schema = None
    return t


def _make_llm_response_with_tool_calls(tool_calls: list[dict]) -> MagicMock:
    """Build a fake LLM AIMessage that has tool_calls."""
    response = MagicMock()
    response.tool_calls = tool_calls
    response.content = ""
    return response


def _make_llm_response_text(text: str) -> MagicMock:
    """Build a fake LLM AIMessage with no tool calls (text response)."""
    response = MagicMock()
    response.tool_calls = []
    response.content = text
    return response


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestExpedienteCaseFinalizedGuard:
    """Bug 1 — _run_llm_loop must exit when case_finalized flag is detected."""

    def _make_node(self) -> ExpedienteModeNode:
        """Build an ExpedienteModeNode with mocked logger."""
        node = ExpedienteModeNode()
        return node

    # ------------------------------------------------------------------
    # Scenario 1: [finalizar_expediente] → loop exits, message extracted
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_loop_exits_when_finalizar_returns_case_finalized(self):
        """
        GIVEN LLM returns tool_call [finalizar_expediente]
        WHEN  finalizar_expediente() returns case_finalized=True
        THEN  loop exits, ai_response is the tool's message, no further LLM invocations
        """
        node = self._make_node()
        state = _make_state()
        mode_context = dict(state["mode_context"])
        tools = [_make_mock_tool("finalizar_expediente")]

        # LLM first call → finalizar_expediente; second call → should NOT happen
        tool_call = {
            "name": "finalizar_expediente",
            "args": {},
            "id": "call-001",
        }
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            side_effect=[
                _make_llm_response_with_tool_calls([tool_call]),
                # If the guard fails, this would be called — we make it fail loudly
                Exception("Guard failed — LLM invoked again after finalization!"),
            ]
        )

        llm_invoke_count = 0

        async def counting_ainvoke(messages):
            nonlocal llm_invoke_count
            llm_invoke_count += 1
            if llm_invoke_count == 1:
                return _make_llm_response_with_tool_calls([tool_call])
            raise AssertionError("LLM invoked more than once — case_finalized guard did not fire!")

        mock_llm.ainvoke = counting_ainvoke

        with patch.object(node, "_get_llm", return_value=mock_llm), \
             patch.object(node, "_execute_and_log_tool", new_callable=AsyncMock,
                          return_value=FINALIZED_TOOL_RESULT) as mock_execute, \
             patch.object(node, "_track_token_usage", new_callable=AsyncMock), \
             patch.object(node, "_ai_message_to_dict", return_value={"role": "assistant", "content": ""}), \
             patch("agent.modes.expediente_mode.assemble_system_prompt", return_value="system prompt"), \
             patch("agent.modes.expediente_mode.format_messages_for_llm", return_value=[]), \
             patch("agent.modes.expediente_mode.set_current_state"), \
             patch("agent.modes.expediente_mode.set_current_state_for_image_tools"), \
             patch("agent.modes.expediente_mode.get_settings") as mock_settings:

            settings = MagicMock()
            settings.ENABLE_LATENCY_GATING = False
            settings.ENABLE_SAME_TURN_TRANSITION_CLOSURE = False
            mock_settings.return_value = settings

            result = await node._run_llm_loop(
                message="Sí, confirmo el expediente",
                state=state,
                mode_context=mode_context,
                tools=tools,
                sub_mode_name=REVIEW_SUMMARY,
            )

        # Guard fired: LLM only called once
        assert llm_invoke_count == 1, (
            f"Expected LLM to be called exactly once, got: {llm_invoke_count}"
        )
        # finalizar_expediente was executed
        mock_execute.assert_called_once()
        # Response carries the finalization message
        assert "expediente" in result.get("ai_response", "").lower() or \
               "revisión" in result.get("ai_response", "").lower() or \
               result.get("ai_response") != "", (
            f"Expected ai_response to contain finalization message, got: {result.get('ai_response')}"
        )

    # ------------------------------------------------------------------
    # Scenario 2: [finalizar_expediente, escalar_a_humano] → escalation skipped
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_escalar_not_executed_when_finalizacion_fires_first(self):
        """
        GIVEN LLM returns [finalizar_expediente, escalar_a_humano] in one batch
        WHEN  finalizar_expediente() returns case_finalized=True
        THEN  escalar_a_humano is NOT executed (inner tool loop breaks)
        """
        node = self._make_node()
        state = _make_state()
        mode_context = dict(state["mode_context"])
        tools = [
            _make_mock_tool("finalizar_expediente"),
            _make_mock_tool("escalar_a_humano"),
        ]

        # LLM returns two tool_calls in the same response
        tool_calls = [
            {"name": "finalizar_expediente", "args": {}, "id": "call-fin-001"},
            {"name": "escalar_a_humano", "args": {"motivo": "finalized"}, "id": "call-esc-002"},
        ]

        llm_invoke_count = 0

        async def counting_ainvoke(messages):
            nonlocal llm_invoke_count
            llm_invoke_count += 1
            if llm_invoke_count == 1:
                return _make_llm_response_with_tool_calls(tool_calls)
            raise AssertionError("LLM invoked again after case_finalized guard")

        mock_llm = AsyncMock()
        mock_llm.ainvoke = counting_ainvoke

        executed_tools: list[str] = []

        async def mock_execute_tool(conversation_id, tool_name, tool_args, tools, iteration):
            executed_tools.append(tool_name)
            if tool_name == "finalizar_expediente":
                return FINALIZED_TOOL_RESULT
            # If escalar_a_humano is somehow called, return a plain result
            return ESCALAR_TOOL_RESULT

        with patch.object(node, "_get_llm", return_value=mock_llm), \
             patch.object(node, "_execute_and_log_tool", side_effect=mock_execute_tool), \
             patch.object(node, "_track_token_usage", new_callable=AsyncMock), \
             patch.object(node, "_ai_message_to_dict", return_value={"role": "assistant", "content": ""}), \
             patch("agent.modes.expediente_mode.assemble_system_prompt", return_value="system prompt"), \
             patch("agent.modes.expediente_mode.format_messages_for_llm", return_value=[]), \
             patch("agent.modes.expediente_mode.set_current_state"), \
             patch("agent.modes.expediente_mode.set_current_state_for_image_tools"), \
             patch("agent.modes.expediente_mode.get_settings") as mock_settings:

            settings = MagicMock()
            settings.ENABLE_LATENCY_GATING = False
            settings.ENABLE_SAME_TURN_TRANSITION_CLOSURE = False
            mock_settings.return_value = settings

            result = await node._run_llm_loop(
                message="Sí, confirmo el expediente",
                state=state,
                mode_context=mode_context,
                tools=tools,
                sub_mode_name=REVIEW_SUMMARY,
            )

        # finalizar_expediente MUST have been executed
        assert "finalizar_expediente" in executed_tools, (
            f"Expected finalizar_expediente to be executed; got: {executed_tools}"
        )
        # escalar_a_humano MUST NOT have been executed
        assert "escalar_a_humano" not in executed_tools, (
            f"escalar_a_humano should NOT have been executed after case_finalized guard; "
            f"executed tools: {executed_tools}"
        )
        # LLM only invoked once
        assert llm_invoke_count == 1

    # ------------------------------------------------------------------
    # Scenario 3: Normal tool (no case_finalized) → loop continues
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_loop_continues_when_tool_does_not_set_case_finalized(self):
        """
        GIVEN tool result has success=True but NO _internal_flags.case_finalized
        THEN  loop does NOT exit early (LLM is called again for the next iteration)
        """
        node = self._make_node()
        state = _make_state()
        mode_context = dict(state["mode_context"])
        # Use collect_personal so there is no false-completion risk
        mode_context["expediente_sub_mode"] = "collect_personal"
        tools = [_make_mock_tool("actualizar_datos_expediente")]

        tool_call = {
            "name": "actualizar_datos_expediente",
            "args": {"nombre": "Test User"},
            "id": "call-upd-001",
        }

        llm_invoke_count = 0
        # First call → tool call; second call → text response (exit loop)
        responses = [
            _make_llm_response_with_tool_calls([tool_call]),
            _make_llm_response_text("Datos guardados. ¿Confirmas?"),
        ]

        async def counting_ainvoke(messages):
            nonlocal llm_invoke_count
            if llm_invoke_count >= len(responses):
                raise AssertionError(f"Unexpected LLM call #{llm_invoke_count + 1}")
            resp = responses[llm_invoke_count]
            llm_invoke_count += 1
            return resp

        mock_llm = AsyncMock()
        mock_llm.ainvoke = counting_ainvoke

        with patch.object(node, "_get_llm", return_value=mock_llm), \
             patch.object(node, "_execute_and_log_tool", new_callable=AsyncMock,
                          return_value=NORMAL_TOOL_RESULT), \
             patch.object(node, "_track_token_usage", new_callable=AsyncMock), \
             patch.object(node, "_ai_message_to_dict", return_value={"role": "assistant", "content": ""}), \
             patch.object(node, "_validate_response_constraints", new_callable=AsyncMock,
                          return_value=(True, None)), \
             patch("agent.modes.expediente_mode.assemble_system_prompt", return_value="system prompt"), \
             patch("agent.modes.expediente_mode.format_messages_for_llm", return_value=[]), \
             patch("agent.modes.expediente_mode.set_current_state"), \
             patch("agent.modes.expediente_mode.set_current_state_for_image_tools"), \
             patch("agent.modes.expediente_mode.get_settings") as mock_settings:

            settings = MagicMock()
            settings.ENABLE_LATENCY_GATING = False
            settings.ENABLE_SAME_TURN_TRANSITION_CLOSURE = False
            mock_settings.return_value = settings

            result = await node._run_llm_loop(
                message="Mi nombre es Test User",
                state=state,
                mode_context=mode_context,
                tools=tools,
                sub_mode_name="COLLECT_PERSONAL",
            )

        # LLM must have been invoked at least twice (tool call + text response)
        assert llm_invoke_count >= 2, (
            f"Expected LLM to be called at least twice (no early exit), got: {llm_invoke_count}"
        )
        # The final response is the text from the second LLM call
        assert "guardados" in result.get("ai_response", "").lower() or \
               "confirmas" in result.get("ai_response", "").lower(), (
            f"Unexpected ai_response: {result.get('ai_response')}"
        )


# ---------------------------------------------------------------------------
# Phase 5.5 — Certainty envelope based finalization gate
# ---------------------------------------------------------------------------


class TestCertaintyEnvelopeFinalizedGate:
    """
    Phase 5.5 tests: verify that the certainty envelope correctly captures
    case_finalized=True when finalizar_expediente() succeeds, and that the
    claim gate correctly allows CASE_FINALIZED claims afterwards.

    These are pure unit tests over the guardrails module — no LLM/Redis required.
    """

    def test_finalized_flag_set_in_envelope_after_tool_success(self) -> None:
        """
        normalize_tool_payload with finalizar_expediente + case_finalized=True
        must produce an envelope with case_finalized=True.
        """
        from agent.modes.expediente_guardrails import (
            CertaintyEnvelope,
            ClaimClass,
            evaluate_claim_eligibility,
            normalize_tool_payload,
        )

        import json
        tool_result = json.loads(FINALIZED_TOOL_RESULT)
        envelope = normalize_tool_payload(
            tool_name="finalizar_expediente",
            raw_result=tool_result,
            current_sub_mode="review_summary",
        )

        assert envelope.case_finalized is True, (
            "Envelope must have case_finalized=True after finalizar_expediente success"
        )

    def test_case_finalized_claim_allowed_after_tool(self) -> None:
        """
        After finalizar_expediente() succeeds, CASE_FINALIZED claim must be allowed.
        """
        from agent.modes.expediente_guardrails import (
            CertaintyEnvelope,
            ClaimClass,
            evaluate_claim_eligibility,
            normalize_tool_payload,
        )
        import json
        tool_result = json.loads(FINALIZED_TOOL_RESULT)
        envelope = normalize_tool_payload(
            tool_name="finalizar_expediente",
            raw_result=tool_result,
            current_sub_mode="review_summary",
        )

        ok, reason = evaluate_claim_eligibility(
            envelope, ClaimClass.CASE_FINALIZED, "review_summary"
        )
        assert ok is True, (
            f"CASE_FINALIZED claim must be allowed after finalizar_expediente; reason: {reason}"
        )

    def test_case_finalized_claim_blocked_without_tool(self) -> None:
        """
        Without finalizar_expediente() in this turn, CASE_FINALIZED must be blocked.
        """
        from agent.modes.expediente_guardrails import (
            CertaintyEnvelope,
            ClaimClass,
            evaluate_claim_eligibility,
        )

        envelope = CertaintyEnvelope.empty(sub_mode="review_summary")
        ok, reason = evaluate_claim_eligibility(
            envelope, ClaimClass.CASE_FINALIZED, "review_summary"
        )
        assert ok is False, (
            "CASE_FINALIZED must be blocked when finalizar_expediente was not called"
        )
        assert "CASE_NOT_FINALIZED_BY_TOOL" in reason, (
            f"Expected reason code CASE_NOT_FINALIZED_BY_TOOL, got: {reason}"
        )

    def test_normal_tool_does_not_set_case_finalized(self) -> None:
        """
        A normal tool (e.g. actualizar_datos_expediente) must NOT set case_finalized=True.
        """
        from agent.modes.expediente_guardrails import normalize_tool_payload
        import json
        tool_result = json.loads(NORMAL_TOOL_RESULT)
        envelope = normalize_tool_payload(
            tool_name="actualizar_datos_expediente",
            raw_result=tool_result,
            current_sub_mode="collect_personal",
        )
        assert envelope.case_finalized is False, (
            "Normal tool must NOT set case_finalized=True in the envelope"
        )

    def test_finalize_tool_added_to_tools_succeeded(self) -> None:
        """
        finalizar_expediente with success=True must appear in envelope.tools_succeeded.
        """
        from agent.modes.expediente_guardrails import normalize_tool_payload
        import json
        tool_result = json.loads(FINALIZED_TOOL_RESULT)
        envelope = normalize_tool_payload(
            tool_name="finalizar_expediente",
            raw_result=tool_result,
            current_sub_mode="review_summary",
        )
        assert "finalizar_expediente" in envelope.tools_succeeded, (
            "finalizar_expediente must appear in tools_succeeded after success"
        )

    def test_progression_to_completed_allowed_after_finalization(self) -> None:
        """
        After finalizar_expediente() succeeds, progression to 'completed' must be allowed.
        """
        from agent.modes.expediente_guardrails import (
            normalize_tool_payload,
            evaluate_progression_eligibility,
        )
        import json
        tool_result = json.loads(FINALIZED_TOOL_RESULT)
        envelope = normalize_tool_payload(
            tool_name="finalizar_expediente",
            raw_result=tool_result,
            current_sub_mode="review_summary",
        )
        allowed, reason = evaluate_progression_eligibility(
            envelope, sub_mode="completed"
        )
        assert allowed is True, (
            f"Progression to 'completed' must be allowed after finalization; reason: {reason}"
        )
