"""
T6.1 — End-to-end integration test: tool_choice="required" activation on POST_PRICE + CTA 5.

Change: tool-choice-required-post-price
Spec:   sdd/tool-choice-required-post-price/spec  (engram #4296)
Design: sdd/tool-choice-required-post-price/design (engram #4297)

This test uses the REAL build_mode_tool_loop() factory (not mocked) + ScriptedLLM.
It proves:
  (a) bind_tools() is called with tool_choice="required" when POST_PRICE+CTA5 conditions hold.
  (b) confirmar_presupuesto tool fires and the loop exits in exactly 2 LLM iterations.
  (c) After the transition, last_cta_emitted is tombstoned to None in pending_state_updates.
  (d) Without the lambda (tool_choice=None), bind_tools() does NOT receive tool_choice="required".

Closes prior W1 gap: integration test now uses the actual build_mode_tool_loop() factory,
injects ScriptedLLM with exhaustion sentinel, and asserts both iteration count
and that bind_tools was called with tool_choice="required".

RE-APPLY after revert 4ccf29a + wiring fix a92652a.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage


# ---------------------------------------------------------------------------
# ScriptedLLM — borrowed from test_tool_loop_transitions.py pattern
# ---------------------------------------------------------------------------


class ScriptedLLMWithBindCapture:
    """Deterministic LLM stub that also captures bind_tools() kwargs.

    Queue of pre-canned AIMessage responses. ``.ainvoke()`` pops left.
    ``.bind_tools(tools, **kw)`` returns self AND records the kwargs so tests
    can assert that ``tool_choice="required"`` was (or was not) passed.

    If queue empties before subgraph exits → raises AssertionError so the test
    fails loudly instead of hanging silently (sentinel pattern).
    """

    def __init__(self, responses: list[AIMessage]) -> None:
        self._queue: deque[AIMessage] = deque(responses)
        self.call_count: int = 0
        self.bind_calls: list[dict[str, Any]] = []  # captured bind_tools() kwargs per call

    def bind_tools(self, tools: list, **kwargs: Any) -> "ScriptedLLMWithBindCapture":
        """Capture kwargs and return self (passthrough)."""
        self.bind_calls.append(dict(kwargs))
        return self

    async def ainvoke(self, messages: Any) -> AIMessage:
        self.call_count += 1
        if not self._queue:
            raise AssertionError(
                f"ScriptedLLMWithBindCapture exhausted after {self.call_count - 1} call(s) — "
                "subgraph did not terminate. Possible infinite loop."
            )
        return self._queue.popleft()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ai_tool_call(tool_name: str, args: dict, call_id: str = "call_001") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": tool_name, "args": args, "id": call_id}],
    )


def _base_tool_loop_state(mode_context: dict | None = None) -> dict:
    """Minimal ToolLoopState for subgraph.ainvoke()."""
    return {
        "messages": [],
        "_mode_context": mode_context or {},
        "_conversation_id": "test-integ-tc-001",
        "_mode_name": "PRE_EXPEDIENTE_MODE",
        "pending_state_updates": {},
        "tools_called": [],
        "tool_results": [],
    }


def _post_price_cta5_context() -> dict:
    """Full POST_PRICE + CTA 5 preconditions all satisfied."""
    return {
        "precio_comunicado": True,
        "tarifa_calculada": {"datos": {"price": 450.0}},
        "imagenes_enviadas_codigos": ["T01"],
        "last_cta_emitted": "cta_5",
        "element_codes": ["ESCAPE"],
        "categoria_slug": "aseicars",
    }


def _post_price_no_cta5_context() -> dict:
    """POST_PRICE conditions met but last_cta_emitted is absent."""
    return {
        "precio_comunicado": True,
        "tarifa_calculada": {"datos": {"price": 450.0}},
        "imagenes_enviadas_codigos": ["T01"],
        "last_cta_emitted": None,
        "element_codes": ["ESCAPE"],
        "categoria_slug": "aseicars",
    }


def _make_fake_tool() -> Any:
    """Build a minimal fake tool that satisfies LangChain's tool contract.

    We need at least 1 tool so that tool_loop._get_llm() calls llm.bind_tools()
    (it skips bind_tools when the list is empty). ScriptedLLMWithBindCapture.bind_tools
    returns self, so the fake tool is never actually called.
    """
    from langchain_core.tools import tool as _tool

    @_tool
    def _fake_tool_for_test(x: str = "") -> str:
        """Fake tool used only to trigger bind_tools() in integration tests."""
        return "fake"

    return _fake_tool_for_test


def _build_subgraph(scripted_llm: ScriptedLLMWithBindCapture, tool_choice_lambda: Any = None) -> Any:
    """Build a real tool_loop subgraph with the given LLM stub injected.

    Provides one fake tool so bind_tools() is always called (needed to assert
    tool_choice="required" was passed). Real tools are patched via execute_and_log_tool.
    """
    from agent.modes.tool_loop import ModeLoopConfig, build_mode_tool_loop

    fake_tool = _make_fake_tool()

    config = ModeLoopConfig(
        mode_name="PRE_EXPEDIENTE_MODE",
        get_tools=lambda mc: [fake_tool],  # one fake tool so bind_tools is called
        get_system_prompt=lambda state: "Integration test system prompt",
        post_tool_hook=None,
        max_iterations=4,
        get_tool_choice=tool_choice_lambda,
        _llm_override=scripted_llm,
    )
    return build_mode_tool_loop(config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestToolChoiceRequiredActivation:
    """
    T6.1 — End-to-end: tool_choice="required" is passed to bind_tools when
    POST_PRICE + CTA 5 conditions hold.
    """

    @pytest.mark.asyncio
    async def test_bind_tools_receives_required_on_post_price_cta5(self) -> None:
        """
        Spec S1.1 — Full POST_PRICE + CTA 5 conditions met → bind_tools called
        with tool_choice="required".

        Uses REAL build_mode_tool_loop() + ScriptedLLM with bind capture.
        Asserts:
          (a) bind_tools was called with tool_choice="required"
          (b) Loop exits in exactly 2 iterations (confirmar_presupuesto fires → _transition_to)
          (c) _transition_to in final pending_state_updates
        """
        from agent.modes.pre_expediente_mode import _should_force_tool_choice

        tool_result = json.dumps({
            "success": True,
            "message": "ok",
            "_state_update": {
                "_transition_to": "EXPEDIENTE_MODE",
                "expediente_kickoff_pending": True,
                "last_cta_emitted": None,
            },
        })

        scripted_llm = ScriptedLLMWithBindCapture([
            # Iter 1: confirmar_presupuesto fires
            _make_ai_tool_call("confirmar_presupuesto", {}, "call_001"),
            # Iter 2: LLM runs again; tools_or_end detects _transition_to → END
            _make_ai_tool_call("confirmar_presupuesto", {}, "call_002"),
            # Iter 3 sentinel: AssertionError if consumed (proves fix works)
            AIMessage(content="UNREACHABLE — loop ran 3+ iterations", tool_calls=[]),
        ])

        mode_context = _post_price_cta5_context()
        loop_result = _build_subgraph(
            scripted_llm,
            tool_choice_lambda=lambda mc: _should_force_tool_choice(mc),
        )

        initial_state = _base_tool_loop_state(mode_context=mode_context)

        with patch(
            "agent.modes.tool_executor.execute_and_log_tool",
            new_callable=AsyncMock,
            return_value=tool_result,
        ):
            final_state = await loop_result.graph.ainvoke(
                initial_state,
                config={"recursion_limit": loop_result.recursion_limit},
            )

        # (a) bind_tools was called with tool_choice="required"
        assert scripted_llm.bind_calls, (
            "bind_tools() was never called — LLM did not bind any tools"
        )
        required_calls = [c for c in scripted_llm.bind_calls if c.get("tool_choice") == "required"]
        assert required_calls, (
            f"bind_tools() was called but never with tool_choice='required'. "
            f"Actual bind calls: {scripted_llm.bind_calls!r}. "
            "This means the get_tool_choice lambda is not being evaluated or wired."
        )

        # (b) Loop exited in exactly 2 iterations
        assert scripted_llm.call_count == 2, (
            f"ScriptedLLM called {scripted_llm.call_count} times — expected exactly 2 "
            "(iter1: tool call, iter2: LLM runs then tools_or_end detects _transition_to → END). "
            "If count > 2, the loop did not exit after the transition signal."
        )

        # (c) _transition_to is set in final state
        psu = final_state.get("pending_state_updates") or {}
        assert psu.get("_transition_to") == "EXPEDIENTE_MODE", (
            f"Expected _transition_to='EXPEDIENTE_MODE' in pending_state_updates, got: {psu!r}"
        )

    @pytest.mark.asyncio
    async def test_bind_tools_no_required_when_last_cta_emitted_absent(self) -> None:
        """
        Spec S1.2 — POST_PRICE conditions met but last_cta_emitted=None →
        bind_tools NOT called with tool_choice="required".

        Proves the lambda guards correctly: tool_choice="required" is NOT forced
        when CTA 5 was not the last emission.
        """
        from agent.modes.pre_expediente_mode import _should_force_tool_choice

        scripted_llm = ScriptedLLMWithBindCapture([
            # Free-text response (no tool call)
            AIMessage(content="Aquí tienes el resumen.", tool_calls=[]),
        ])

        mode_context = _post_price_no_cta5_context()
        loop_result = _build_subgraph(
            scripted_llm,
            tool_choice_lambda=lambda mc: _should_force_tool_choice(mc),
        )

        initial_state = _base_tool_loop_state(mode_context=mode_context)

        final_state = await loop_result.graph.ainvoke(
            initial_state,
            config={"recursion_limit": loop_result.recursion_limit},
        )

        # bind_tools must NOT have been called with tool_choice="required"
        required_calls = [c for c in scripted_llm.bind_calls if c.get("tool_choice") == "required"]
        assert not required_calls, (
            f"bind_tools() must NOT be called with tool_choice='required' when "
            f"last_cta_emitted=None. Actual bind calls: {scripted_llm.bind_calls!r}"
        )

    @pytest.mark.asyncio
    async def test_tombstone_clears_last_cta_emitted_after_transition(self) -> None:
        """
        Spec S1.3 — After confirmar_presupuesto fires, last_cta_emitted must be
        tombstoned to None in pending_state_updates.
        """
        from agent.modes.pre_expediente_mode import _should_force_tool_choice

        tool_result = json.dumps({
            "success": True,
            "message": "ok",
            "_state_update": {
                "_transition_to": "EXPEDIENTE_MODE",
                "expediente_kickoff_pending": True,
                "last_cta_emitted": None,  # tombstone from T4.2
            },
        })

        scripted_llm = ScriptedLLMWithBindCapture([
            _make_ai_tool_call("confirmar_presupuesto", {}, "call_001"),
            _make_ai_tool_call("confirmar_presupuesto", {}, "call_002"),
            AIMessage(content="UNREACHABLE", tool_calls=[]),
        ])

        mode_context = _post_price_cta5_context()
        loop_result = _build_subgraph(
            scripted_llm,
            tool_choice_lambda=lambda mc: _should_force_tool_choice(mc),
        )

        initial_state = _base_tool_loop_state(mode_context=mode_context)

        with patch(
            "agent.modes.tool_executor.execute_and_log_tool",
            new_callable=AsyncMock,
            return_value=tool_result,
        ):
            final_state = await loop_result.graph.ainvoke(
                initial_state,
                config={"recursion_limit": loop_result.recursion_limit},
            )

        psu = final_state.get("pending_state_updates") or {}
        # The tombstone from confirmar_presupuesto._state_update propagates here
        assert psu.get("last_cta_emitted") is None, (
            f"last_cta_emitted must be tombstoned (None) in pending_state_updates "
            f"after confirmar_presupuesto fires. Got: {psu.get('last_cta_emitted')!r}"
        )

    @pytest.mark.asyncio
    async def test_no_infinite_loop_with_tool_choice_required(self) -> None:
        """
        Regression proof (closes prior W1 gap): with tool_choice="required" active
        AND the wiring fix from fix-tool-loop-transition-wiring (a92652a) in place,
        the subgraph MUST exit in exactly 2 iterations — no infinite loop.

        This test would have FAILED with the old pre-fix code:
          - tool_choice="required" forces LLM to always call a tool
          - old tools_or_end only checked pending_mode_transition (never written by confirmar)
          - loop ran forever → ScriptedLLM exhausted → AssertionError

        With the wiring fix AND this SDD:
          - tools_or_end checks _transition_to (canonical key) BEFORE tool_calls
          - Loop exits after iter2 → call_count == 2
        """
        from agent.modes.pre_expediente_mode import _should_force_tool_choice

        tool_result = json.dumps({
            "success": True,
            "message": "ok",
            "_state_update": {
                "_transition_to": "EXPEDIENTE_MODE",
                "expediente_kickoff_pending": True,
                "last_cta_emitted": None,
            },
        })

        scripted_llm = ScriptedLLMWithBindCapture([
            _make_ai_tool_call("confirmar_presupuesto", {}, "call_001"),
            # Iter 2 — with wiring fix: tools_or_end detects _transition_to → END
            # Without wiring fix: this tool_call would loop forever
            _make_ai_tool_call("confirmar_presupuesto", {}, "call_002"),
            # Sentinel: AssertionError if consumed
            AIMessage(
                content="UNREACHABLE — infinite loop regression detected",
                tool_calls=[],
            ),
        ])

        mode_context = _post_price_cta5_context()
        loop_result = _build_subgraph(
            scripted_llm,
            tool_choice_lambda=lambda mc: _should_force_tool_choice(mc),
        )

        initial_state = _base_tool_loop_state(mode_context=mode_context)

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
            f"INFINITE LOOP REGRESSION: ScriptedLLM called {scripted_llm.call_count} times "
            "with tool_choice='required'. Expected exactly 2 iterations. "
            "Wiring fix (a92652a) + tool-choice-required SDD must cooperate: "
            "tools_or_end must detect _transition_to before tool_calls route to another loop."
        )
