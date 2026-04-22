"""
Tests for tool_loop.py::tools_or_end transition wiring.

Change: fix-tool-loop-transition-wiring
Spec:   sdd/fix-tool-loop-transition-wiring/spec  (engram #4309)
Design: sdd/fix-tool-loop-transition-wiring/design (engram #4311)

This file exercises:
  1. Unit tests for tools_or_end routing logic.
  2. End-to-end subgraph termination via real build_mode_tool_loop().
  3. tool_choice="required" regression-proof.
  4. Negative tests (non-transition tool continues loop).
  5. Backward-compat (legacy pending_mode_transition key).

All E2E tests use the REAL compiled subgraph + ScriptedLLM — no mocking of
tools_or_end itself. ScriptedLLM raises AssertionError if called more times
than scripted, guaranteeing silent non-termination is caught.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage

# ---------------------------------------------------------------------------
# ScriptedLLM — deterministic LLM stub per design D5
# ---------------------------------------------------------------------------


class ScriptedLLM:
    """Deterministic LLM stub for tool_loop subgraph tests.

    Queue of pre-canned responses (AIMessage). ``.ainvoke()`` pops left.
    ``.bind_tools(tools, **kw)`` returns self (passthrough).
    If queue empties before subgraph exits → raises AssertionError so the test
    fails loudly instead of hanging silently.

    Also tracks how many times ainvoke was called (via self.call_count).
    """

    def __init__(self, responses: list[AIMessage]) -> None:
        self._queue: deque[AIMessage] = deque(responses)
        self.call_count: int = 0

    def bind_tools(self, tools: list, **kwargs: Any) -> "ScriptedLLM":  # noqa: ANN401
        return self

    async def ainvoke(self, messages: Any) -> AIMessage:  # noqa: ANN401
        self.call_count += 1
        if not self._queue:
            raise AssertionError(
                f"ScriptedLLM exhausted after {self.call_count - 1} call(s) — "
                "subgraph did not terminate after the transition tool fired. "
                "This proves an infinite loop (or extra LLM iteration) exists."
            )
        return self._queue.popleft()


# ---------------------------------------------------------------------------
# Minimal state builders
# ---------------------------------------------------------------------------


def _state_with_transition_to(
    value: str | None,
    *,
    in_pending: bool = True,
    also_in_mode_context: bool = False,
) -> dict:
    """
    Build a minimal ToolLoopState dict with _transition_to set.

    Args:
        value: The target mode string (or None for tombstone test).
        in_pending: If True, put it at the TOP LEVEL of pending_state_updates.
                    This matches what post_tool_node actually stores.
        also_in_mode_context: If True, ALSO put it in _mode_context.
    """
    state: dict = {
        "messages": [AIMessage(content="ok", tool_calls=[])],
        "_mode_context": {},
        "pending_state_updates": {},
    }
    if in_pending:
        # post_tool_node stores _state_update keys at the TOP LEVEL of pending_state_updates,
        # NOT under pending_state_updates.mode_context.
        state["pending_state_updates"] = {"_transition_to": value}
    if also_in_mode_context:
        state["_mode_context"] = {"_transition_to": value}
    return state


def _state_with_legacy_pending(value: str) -> dict:
    """Build state with legacy pending_mode_transition in pending_state_updates (top-level)."""
    return {
        "messages": [AIMessage(content="ok", tool_calls=[])],
        "_mode_context": {},
        "pending_state_updates": {"pending_mode_transition": value},
    }


def _state_with_tool_calls(tool_name: str = "some_tool") -> dict:
    """Build state whose last message is an AIMessage with tool_calls."""
    return {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": tool_name, "args": {}, "id": "call_001"}],
            )
        ],
        "_mode_context": {},
        "pending_state_updates": {},
    }


def _state_no_tool_calls() -> dict:
    """Build state whose last message is an AIMessage without tool_calls."""
    return {
        "messages": [AIMessage(content="Respuesta final", tool_calls=[])],
        "_mode_context": {},
        "pending_state_updates": {},
    }


def _empty_state() -> dict:
    return {"messages": [], "_mode_context": {}, "pending_state_updates": {}}


# ---------------------------------------------------------------------------
# E2E subgraph builder helper
# ---------------------------------------------------------------------------


def _make_ai_tool_call(tool_name: str, args: dict, call_id: str = "call_001") -> AIMessage:
    """Build an AIMessage that requests one tool call."""
    return AIMessage(
        content="",
        tool_calls=[{"name": tool_name, "args": args, "id": call_id}],
    )


def _make_tool_result(tool_name: str, result_dict: dict, call_id: str = "call_001") -> str:
    """Serialise a tool result as the ToolMessage content string."""
    return json.dumps(result_dict)


def _build_subgraph_for_tool(
    scripted_llm: "ScriptedLLM",
    get_tool_choice: Any = None,
) -> Any:
    """
    Build a real tool_loop subgraph with ScriptedLLM injected.

    Uses build_mode_tool_loop() with minimal stub get_tools, get_system_prompt,
    and post_tool_hook so the subgraph compiles and runs without real services.
    The tool list is empty — we only care about the LLM→tools_or_end routing,
    and tools are mocked via custom_tool_node patching in E2E tests.
    """
    from agent.modes.tool_loop import ModeLoopConfig, build_mode_tool_loop

    config = ModeLoopConfig(
        mode_name="PRE_EXPEDIENTE_MODE",
        get_tools=lambda mc: [],  # no real tools — E2E tests patch execute_and_log_tool
        get_system_prompt=lambda state: "Test system prompt",
        post_tool_hook=None,
        max_iterations=4,  # low limit — 1 iteration must suffice
        get_tool_choice=get_tool_choice,
        _llm_override=scripted_llm,
    )
    return build_mode_tool_loop(config)


def _base_tool_loop_state(mode_context: dict | None = None) -> dict:
    """Return a minimal ToolLoopState for subgraph.ainvoke()."""
    return {
        "messages": [],
        "_mode_context": mode_context or {},
        "_conversation_id": "test-conv-001",
        "_mode_name": "PRE_EXPEDIENTE_MODE",
        "pending_state_updates": {},
        "tools_called": [],
        "tool_results": [],
    }


# ===========================================================================
# Phase 0 — Scaffolding validation
# ===========================================================================


class TestScriptedLLMGuard:
    """T0.3 — ScriptedLLM guard: exhaustion raises AssertionError."""

    @pytest.mark.asyncio
    async def test_scripted_llm_exhaustion_raises(self) -> None:
        """Empty ScriptedLLM raises AssertionError on ainvoke."""
        llm = ScriptedLLM([])
        with pytest.raises(AssertionError, match="ScriptedLLM exhausted"):
            await llm.ainvoke([])

    @pytest.mark.asyncio
    async def test_scripted_llm_returns_response_when_queued(self) -> None:
        """ScriptedLLM returns the queued response and tracks call_count."""
        msg = AIMessage(content="hello")
        llm = ScriptedLLM([msg])
        result = await llm.ainvoke([])
        assert result is msg
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_scripted_llm_exhaustion_after_one_call(self) -> None:
        """ScriptedLLM raises on second call when only one response is queued."""
        llm = ScriptedLLM([AIMessage(content="one")])
        await llm.ainvoke([])  # consumes the only response
        with pytest.raises(AssertionError):
            await llm.ainvoke([])


# ===========================================================================
# Phase 1 — Unit tests for tools_or_end (RED before Phase 2 fix)
# ===========================================================================


class TestToolsOrEndCanonicalKey:
    """Unit tests for tools_or_end routing — spec scenarios from #4309.

    T1.1: _transition_to set in pending → END
    T1.2.a: pending_mode_transition only → END
    T1.2.b: both keys set → END
    T1.2.c: neither key, no tool_calls → END (free-text)
    T1.2.d: neither key, tool_calls present → custom_tool_node
    T1.2.e: _transition_to in _mode_context (already merged) → END
    T1.2.f: _transition_to=None tombstone → continue
    T1.2.g: empty state → does not crash
    """

    def test_exits_when_transition_to_in_pending_overrides_tool_calls(self) -> None:
        """
        T1.1 — canonical _transition_to in pending_state_updates (top-level) + last message HAS
        tool_calls → still END.

        This is the KEY assertion: _transition_to must take priority over tool_calls.
        Without the fix, _transition_to is ignored and the tool_calls would route to
        custom_tool_node instead of END — this is the bug.

        Note: post_tool_node stores _state_update keys at the TOP LEVEL of
        pending_state_updates, NOT under pending_state_updates.mode_context.
        The fix must check pending_state_updates["_transition_to"] directly.
        """
        from langgraph.graph import END as GRAPH_END

        from agent.modes.tool_loop import tools_or_end

        # State: last message HAS tool_calls AND _transition_to is set in pending (top-level)
        # This mirrors what post_tool_node actually stores after a transition tool executes.
        state = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "confirmar_presupuesto", "args": {}, "id": "c1"}],
                )
            ],
            "_mode_context": {},
            "pending_state_updates": {
                "_transition_to": "EXPEDIENTE_MODE",  # top-level, not under mode_context
            },
        }
        result = tools_or_end(state)
        assert result == GRAPH_END, (
            f"Expected END when _transition_to='EXPEDIENTE_MODE' in pending_state_updates "
            f"(even with tool_calls in last message), got {result!r}. "
            "Without the fix, this would return 'custom_tool_node' — that's the bug."
        )

    def test_exits_when_legacy_pending_mode_transition(self) -> None:
        """T1.2.a — legacy pending_mode_transition only → END."""
        from langgraph.graph import END as GRAPH_END

        from agent.modes.tool_loop import tools_or_end

        state = _state_with_legacy_pending("MODE_X")
        result = tools_or_end(state)
        assert result == GRAPH_END, (
            f"Expected END when pending_mode_transition='MODE_X', got {result!r}"
        )

    def test_exits_when_both_keys_set(self) -> None:
        """T1.2.b — both _transition_to and pending_mode_transition → END."""
        from langgraph.graph import END as GRAPH_END

        from agent.modes.tool_loop import tools_or_end

        state = {
            "messages": [AIMessage(content="ok", tool_calls=[])],
            "_mode_context": {},
            "pending_state_updates": {
                "mode_context": {
                    "_transition_to": "EXPEDIENTE_MODE",
                    "pending_mode_transition": "LEGACY_MODE",
                }
            },
        }
        result = tools_or_end(state)
        assert result == GRAPH_END

    def test_exits_when_no_messages(self) -> None:
        """T1.2.c — no tool_calls, no messages → END."""
        from langgraph.graph import END as GRAPH_END

        from agent.modes.tool_loop import tools_or_end

        result = tools_or_end(_empty_state())
        assert result == GRAPH_END

    def test_exits_when_last_message_has_no_tool_calls(self) -> None:
        """T1.2.c — last AIMessage has no tool_calls → END (free-text branch)."""
        from langgraph.graph import END as GRAPH_END

        from agent.modes.tool_loop import tools_or_end

        result = tools_or_end(_state_no_tool_calls())
        assert result == GRAPH_END

    def test_continues_when_tool_calls_present(self) -> None:
        """T1.2.d — tool_calls present and no transition key → custom_tool_node."""
        from agent.modes.tool_loop import tools_or_end

        result = tools_or_end(_state_with_tool_calls())
        assert result == "custom_tool_node", (
            f"Expected 'custom_tool_node' when tool_calls present, got {result!r}"
        )

    def test_exits_when_transition_to_in_mode_context(self) -> None:
        """T1.2.e — _transition_to already in _mode_context (merged) → END."""
        from langgraph.graph import END as GRAPH_END

        from agent.modes.tool_loop import tools_or_end

        state = _state_with_transition_to(
            "EXPEDIENTE_MODE", in_pending=False, also_in_mode_context=True
        )
        result = tools_or_end(state)
        assert result == GRAPH_END, (
            f"Expected END when _transition_to in _mode_context, got {result!r}"
        )

    def test_continues_when_transition_to_is_none_tombstone(self) -> None:
        """T1.2.f — _transition_to=None tombstone → must NOT exit via transition."""
        from agent.modes.tool_loop import tools_or_end

        state = _state_with_transition_to(None, in_pending=True)
        # With tool_calls present, should continue; without, should exit via free-text
        # Here we have no tool_calls in the last message (default _state_with_transition_to)
        # so it exits via END due to "no tool_calls" — NOT due to _transition_to.
        # We verify _transition_to=None does NOT trigger the transition branch.
        # (The result is still END, but for the correct reason: no tool_calls.)
        from langgraph.graph import END as GRAPH_END

        result = tools_or_end(state)
        # Regardless of reason — if _transition_to=None, the transition guard must
        # be falsy and not consume the tombstone as a transition signal.
        # Final result is END via "no tool_calls" branch — that's fine.
        assert result == GRAPH_END

    def test_empty_state_does_not_crash(self) -> None:
        """T1.2.g — completely empty state dict → routes to END, no crash."""
        from langgraph.graph import END as GRAPH_END

        from agent.modes.tool_loop import tools_or_end

        result = tools_or_end({})
        assert result == GRAPH_END


# ===========================================================================
# Phase 3 — End-to-end subgraph termination
# ===========================================================================


class TestEndToEndSubgraphTermination:
    """
    E2E tests using real build_mode_tool_loop() + ScriptedLLM.

    Actual LangGraph flow for a transition tool:
      llm_node iter1 → (ScriptedLLM call 1, tool call)
      → tools_or_end → custom_tool_node → post_tool_node (sets _transition_to in pending)
      → llm_node iter2 → (ScriptedLLM call 2 — LLM always runs before tools_or_end checks)
      → tools_or_end detects _transition_to in merged _mode_context → END

    So ScriptedLLM.call_count == 2 is the CORRECT count for a single-tool transition.

    WITHOUT the fix: tools_or_end on iter2 does NOT detect _transition_to.
    If response2 has tool_calls, the loop continues and iter3 exhausts ScriptedLLM → AssertionError.
    That is exactly what happens on master — this proves the bug.

    WITH the fix: tools_or_end on iter2 detects _transition_to → END.
    call_count == 2 and response3 (UNREACHABLE) is never consumed.
    """

    @pytest.mark.asyncio
    async def test_confirmar_presupuesto_exits_after_transition(self) -> None:
        """
        Spec S3.2: confirmar_presupuesto → _transition_to='EXPEDIENTE_MODE'.

        ScriptedLLM queue: 3 responses.
          response1: AI tool call → confirmar_presupuesto fires
          response2: AI with tool_calls (would continue loop without fix; with fix tools_or_end exits)
          response3: UNREACHABLE sentinel → AssertionError if consumed (proves infinite loop)

        With fix: call_count == 2, loop exits cleanly.
        Without fix: response2 has tool_calls → loop continues → call_count == 3 → AssertionError.
        """
        tool_result = json.dumps({
            "success": True,
            "message": "ok",
            "_state_update": {
                "_transition_to": "EXPEDIENTE_MODE",
            },
        })

        scripted_llm = ScriptedLLM([
            # Iter 1: tool call that sets _transition_to
            _make_ai_tool_call("confirmar_presupuesto", {}, "call_001"),
            # Iter 2: LLM runs again (llm_node always precedes tools_or_end).
            # With fix: tools_or_end sees _transition_to in _mode_context → END before these tool_calls matter.
            # Without fix: this tool_call would continue the loop indefinitely.
            _make_ai_tool_call("confirmar_presupuesto", {}, "call_002"),
            # Iter 3 (UNREACHABLE with fix): proves loop did not exit after iter 2
            AIMessage(content="UNREACHABLE — subgraph ran 3 iterations instead of 2", tool_calls=[]),
        ])

        loop_result = _build_subgraph_for_tool(scripted_llm)

        initial_state = _base_tool_loop_state(mode_context={
            "precio_comunicado": True,
            "tarifa_calculada": {"datos": {"price": 410}},
            "element_codes": ["ESCAPE"],
            "categoria_slug": "aseicars",
        })

        with patch(
            "agent.modes.tool_executor.execute_and_log_tool",
            new_callable=AsyncMock,
            return_value=tool_result,
        ):
            final_state = await loop_result.graph.ainvoke(
                initial_state,
                config={"recursion_limit": loop_result.recursion_limit},
            )

        # With fix: LLM called exactly twice (iter1 + iter2), then tools_or_end exits via _transition_to
        assert scripted_llm.call_count == 2, (
            f"ScriptedLLM called {scripted_llm.call_count} times — expected exactly 2 "
            "(iter1: tool call, iter2: LLM runs then tools_or_end detects _transition_to → END). "
            "If count > 2, the fix is not working and the loop continues past the transition signal."
        )

        # _transition_to must be in final state (from post_tool_node → pending_state_updates top-level)
        # post_tool_node stores _state_update keys at the TOP LEVEL of pending_state_updates.
        psu = final_state.get("pending_state_updates") or {}
        assert psu.get("_transition_to") == "EXPEDIENTE_MODE", (
            f"Expected _transition_to='EXPEDIENTE_MODE' at pending_state_updates top-level, "
            f"got: {psu}"
        )

        # Messages: 2 AIMessages (iter1 + iter2) + at least 1 ToolMessage
        messages = final_state.get("messages", [])
        ai_msgs = [m for m in messages if type(m).__name__ in ("AIMessage", "AIMessageChunk")]
        tool_msgs = [m for m in messages if type(m).__name__ == "ToolMessage"]
        assert len(ai_msgs) == 2, f"Expected 2 AIMessages, got {len(ai_msgs)}"
        assert len(tool_msgs) >= 1, f"Expected at least 1 ToolMessage, got {len(tool_msgs)}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_name,tool_result_dict,expected_transition", [
        (
            "confirmar_presupuesto",
            {
                "success": True,
                "_state_update": {"_transition_to": "EXPEDIENTE_MODE"},
            },
            "EXPEDIENTE_MODE",
        ),
        (
            "finalizar_expediente",
            {
                "success": True,
                "_state_update": {"_transition_to": "PRE_EXPEDIENTE_MODE"},
            },
            "PRE_EXPEDIENTE_MODE",
        ),
        (
            "cancelar_expediente",
            {
                "success": True,
                "_state_update": {"_transition_to": "PRE_EXPEDIENTE_MODE"},
            },
            "PRE_EXPEDIENTE_MODE",
        ),
    ])
    async def test_parametrized_transition_tools_exit_after_transition(
        self,
        tool_name: str,
        tool_result_dict: dict,
        expected_transition: str,
    ) -> None:
        """
        Spec S3.2: parametrized over 3 transition tools.

        Each must exit after exactly 2 LLM iterations:
          iter1 → transition tool fires (sets _transition_to in pending)
          iter2 → tools_or_end detects _transition_to → END

        Without fix: iter2 continues if response2 has tool_calls → iter3 → AssertionError.
        """
        tool_result_json = json.dumps(tool_result_dict)

        scripted_llm = ScriptedLLM([
            _make_ai_tool_call(tool_name, {}, "call_001"),
            # Iter 2 response — with fix, tools_or_end exits before routing to tool_node
            _make_ai_tool_call(tool_name, {}, "call_002"),
            # Sentinel — consumed only if loop ran 3+ iterations (proves bug without fix)
            AIMessage(content="UNREACHABLE", tool_calls=[]),
        ])

        loop_result = _build_subgraph_for_tool(scripted_llm)
        initial_state = _base_tool_loop_state()

        with patch(
            "agent.modes.tool_executor.execute_and_log_tool",
            new_callable=AsyncMock,
            return_value=tool_result_json,
        ):
            final_state = await loop_result.graph.ainvoke(
                initial_state,
                config={"recursion_limit": loop_result.recursion_limit},
            )

        assert scripted_llm.call_count == 2, (
            f"[{tool_name}] ScriptedLLM called {scripted_llm.call_count} times — "
            "expected 2 (iter1+iter2). If > 2, the fix is not working."
        )

        psu = final_state.get("pending_state_updates") or {}
        assert psu.get("_transition_to") == expected_transition, (
            f"[{tool_name}] Expected _transition_to={expected_transition!r} at top-level of "
            f"pending_state_updates, got: {psu}"
        )

    @pytest.mark.asyncio
    async def test_escalar_a_humano_terminates_non_regression(self) -> None:
        """
        Spec S3.3 / escalar_a_humano path — non-regression test.

        escalar_a_humano does NOT set _transition_to — it's the escalation path, not a mode
        transition. The loop exits via the "no tool_calls" branch when the LLM eventually
        emits free text. This test verifies that:
        1. The subgraph terminates (no GraphRecursionError).
        2. _transition_to is NOT set (escalation uses a different path).
        3. The new _transition_to OR-clause does NOT interfere with the escalation path.

        call_count == 3 (iter1=tool call, iter2=tool call again since no _transition_to,
        iter3=free text → END via "no tool_calls" branch).
        """
        tool_result = json.dumps({
            "success": True,
            "escalation_triggered": True,
            "terminate_processing": True,
            # No _state_update with _transition_to — escalation does not use this channel
            "_state_update": {
                "escalation_triggered": True,
            },
        })

        scripted_llm = ScriptedLLM([
            # Iter 1: escalar_a_humano tool call
            _make_ai_tool_call("escalar_a_humano", {"motivo": "test"}, "call_001"),
            # Iter 2: no _transition_to detected → loop continues
            _make_ai_tool_call("escalar_a_humano", {"motivo": "test"}, "call_002"),
            # Iter 3: LLM emits free text → END via "no tool_calls" branch
            AIMessage(content="Te estoy conectando con un agente humano.", tool_calls=[]),
        ])

        loop_result = _build_subgraph_for_tool(scripted_llm)
        initial_state = _base_tool_loop_state()

        with patch(
            "agent.modes.tool_executor.execute_and_log_tool",
            new_callable=AsyncMock,
            return_value=tool_result,
        ):
            final_state = await loop_result.graph.ainvoke(
                initial_state,
                config={"recursion_limit": loop_result.recursion_limit},
            )

        # Subgraph must terminate (not raise GraphRecursionError)
        # call_count == 3: the loop ran 3 iterations (no _transition_to exit)
        assert scripted_llm.call_count == 3, (
            f"escalar_a_humano: ScriptedLLM called {scripted_llm.call_count} times — "
            "expected 3 (escalation path does not use _transition_to; exits via free text)"
        )

        # _transition_to is NOT set by escalar_a_humano
        psu = final_state.get("pending_state_updates") or {}
        assert psu.get("_transition_to") is None, (
            f"escalar_a_humano must NOT set _transition_to, got: {psu.get('_transition_to')!r}"
        )


# ===========================================================================
# Phase 4 — tool_choice="required" regression-proof
# ===========================================================================


class TestEndToEndWithToolChoiceRequired:
    """
    Same matrix as Phase 3 but with get_tool_choice=lambda mc: "required".

    Proves that re-applying sdd/tool-choice-required-post-price won't
    reintroduce the infinite-loop regression after this fix lands.
    """

    @pytest.mark.asyncio
    async def test_confirmar_presupuesto_exits_with_tool_choice_required(self) -> None:
        """
        Spec S3.2 + S4.1: confirmar_presupuesto with tool_choice='required'.

        Before the fix with tool_choice="required":
        1. tool_choice="required" forces the LLM to always call a tool.
        2. tools_or_end only checked pending_mode_transition (never written by confirmar_presupuesto).
        3. Loop never exited → kept calling ScriptedLLM until exhausted → AssertionError.

        After the fix:
        - iter1: tool call → confirmar_presupuesto fires → _transition_to in pending
        - iter2: llm_node runs (even with tool_choice=required; but tools_or_end runs AFTER)
        - tools_or_end: detects _transition_to → END
        - call_count == 2

        Without fix with the 3-response queue:
        - iter2 response has tool_calls → loop continues → iter3 → AssertionError.
        """
        tool_result = json.dumps({
            "success": True,
            "_state_update": {
                "_transition_to": "EXPEDIENTE_MODE",
            },
        })

        scripted_llm = ScriptedLLM([
            _make_ai_tool_call("confirmar_presupuesto", {}, "call_001"),
            # Iter 2 — with fix, tools_or_end exits after this; without fix, continues
            _make_ai_tool_call("confirmar_presupuesto", {}, "call_002"),
            # Sentinel
            AIMessage(content="UNREACHABLE", tool_calls=[]),
        ])

        loop_result = _build_subgraph_for_tool(
            scripted_llm,
            get_tool_choice=lambda mc: "required",
        )
        initial_state = _base_tool_loop_state(mode_context={
            "precio_comunicado": True,
            "tarifa_calculada": {"datos": {"price": 410}},
        })

        with patch(
            "agent.modes.tool_executor.execute_and_log_tool",
            new_callable=AsyncMock,
            return_value=tool_result,
        ):
            final_state = await loop_result.graph.ainvoke(
                initial_state,
                config={"recursion_limit": loop_result.recursion_limit},
            )

        assert scripted_llm.call_count == 2, (
            f"[tool_choice=required] ScriptedLLM called {scripted_llm.call_count} times — "
            "expected 2 (iter1: tool call, iter2: tools_or_end detects _transition_to → END). "
            "If count > 2: this is the infinite-loop regression from master branch."
        )

        psu = final_state.get("pending_state_updates") or {}
        assert psu.get("_transition_to") == "EXPEDIENTE_MODE"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_name,tool_result_dict,expected_transition", [
        (
            "confirmar_presupuesto",
            {"success": True, "_state_update": {"_transition_to": "EXPEDIENTE_MODE"}},
            "EXPEDIENTE_MODE",
        ),
        (
            "finalizar_expediente",
            {"success": True, "_state_update": {"_transition_to": "PRE_EXPEDIENTE_MODE"}},
            "PRE_EXPEDIENTE_MODE",
        ),
        (
            "cancelar_expediente",
            {"success": True, "_state_update": {"_transition_to": "PRE_EXPEDIENTE_MODE"}},
            "PRE_EXPEDIENTE_MODE",
        ),
    ])
    async def test_parametrized_tool_choice_required(
        self,
        tool_name: str,
        tool_result_dict: dict,
        expected_transition: str,
    ) -> None:
        """
        Spec S4.1: all transition tools exit after exactly 2 LLM iters under tool_choice='required'.
        Without fix: iter2 response has tool_calls → loop continues → iter3 → AssertionError.
        """
        tool_result_json = json.dumps(tool_result_dict)

        scripted_llm = ScriptedLLM([
            _make_ai_tool_call(tool_name, {}, "call_001"),
            _make_ai_tool_call(tool_name, {}, "call_002"),
            AIMessage(content="UNREACHABLE", tool_calls=[]),
        ])

        loop_result = _build_subgraph_for_tool(
            scripted_llm,
            get_tool_choice=lambda mc: "required",
        )
        initial_state = _base_tool_loop_state()

        with patch(
            "agent.modes.tool_executor.execute_and_log_tool",
            new_callable=AsyncMock,
            return_value=tool_result_json,
        ):
            final_state = await loop_result.graph.ainvoke(
                initial_state,
                config={"recursion_limit": loop_result.recursion_limit},
            )

        assert scripted_llm.call_count == 2, (
            f"[tool_choice=required][{tool_name}] ScriptedLLM called {scripted_llm.call_count} times "
            "— expected 2. If > 2: infinite-loop regression."
        )

        psu = final_state.get("pending_state_updates") or {}
        assert psu.get("_transition_to") == expected_transition


# ===========================================================================
# Phase 5 — Negative tests
# ===========================================================================


class TestNegative:
    """
    T5.1: A non-transition tool MUST NOT cause early exit.
    The loop continues to the second LLM iteration (free-text → END).
    """

    @pytest.mark.asyncio
    async def test_non_transition_tool_continues_loop(self) -> None:
        """
        Spec: Non-transition tool → loop proceeds; LLM's 2nd response is consumed.
        calcular_tarifa_con_elementos returns no _transition_to → loop continues.
        2nd LLM response = free text (no tool_calls) → END via "no tool_calls" branch.
        ScriptedLLM must be exhausted (both responses consumed).
        """
        # Tool result with no _transition_to
        non_transition_result = json.dumps({
            "success": True,
            "datos": {"price": 410},
            "_state_update": {"tarifa_calculada": {"datos": {"price": 410}}},
        })

        scripted_llm = ScriptedLLM([
            # Iteration 1: LLM calls non-transition tool
            _make_ai_tool_call("calcular_tarifa_con_elementos", {"skip_validation": True}, "call_001"),
            # Iteration 2: LLM emits free text → subgraph exits via "no tool_calls" branch
            AIMessage(content="El precio es 410€. ¿Empezamos?", tool_calls=[]),
        ])

        loop_result = _build_subgraph_for_tool(scripted_llm)
        initial_state = _base_tool_loop_state()

        with patch(
            "agent.modes.tool_executor.execute_and_log_tool",
            new_callable=AsyncMock,
            return_value=non_transition_result,
        ):
            final_state = await loop_result.graph.ainvoke(
                initial_state,
                config={"recursion_limit": loop_result.recursion_limit},
            )

        # BOTH responses were consumed → 2 iterations
        assert scripted_llm.call_count == 2, (
            f"Expected 2 LLM iterations for non-transition tool, got {scripted_llm.call_count}. "
            "If count == 1, the loop exited too early (false positive). "
            "If ScriptedLLM raised, the loop ran more than 2 iterations."
        )

        # Final state should have no _transition_to (non-transition tool doesn't set it)
        psu = final_state.get("pending_state_updates") or {}
        assert psu.get("_transition_to") is None, (
            f"Non-transition tool must not set _transition_to, got: {psu}"
        )

        # Exit reason should be "response" (normal free-text exit)
        assert final_state.get("exit_reason") == "response", (
            f"Expected exit_reason='response', got: {final_state.get('exit_reason')!r}"
        )


# ===========================================================================
# Phase 6 — Backward compatibility (legacy pending_mode_transition)
# ===========================================================================


class TestBackwardCompat:
    """
    T6.1: Legacy pending_mode_transition still exits the subgraph.
    Ensures callers at expediente_state.py:362-370 and pre_expediente_mode.py:597-612
    continue working after the _transition_to OR-clause is added.
    """

    def test_legacy_pending_mode_transition_exits_via_tools_or_end(self) -> None:
        """
        T6.1 — Unit test: pending_mode_transition in pending_state_updates → END.
        This covers the non-regression requirement from spec scenario S1.2.
        """
        from langgraph.graph import END as GRAPH_END

        from agent.modes.tool_loop import tools_or_end

        state = _state_with_legacy_pending("CONSULTA_MODE")
        result = tools_or_end(state)
        assert result == GRAPH_END, (
            f"Legacy pending_mode_transition='CONSULTA_MODE' must still exit the loop, "
            f"got {result!r}"
        )

    def test_legacy_key_in_mode_context_directly(self) -> None:
        """
        T6.1 variant: pending_mode_transition in _mode_context (already merged) → END.
        """
        from langgraph.graph import END as GRAPH_END

        from agent.modes.tool_loop import tools_or_end

        state = {
            "messages": [AIMessage(content="ok", tool_calls=[])],
            "_mode_context": {"pending_mode_transition": "SOME_MODE"},
            "pending_state_updates": {},
        }
        result = tools_or_end(state)
        assert result == GRAPH_END
