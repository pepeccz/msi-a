"""
Integration tests for EXPEDIENTE_MODE using build_mode_tool_loop().

These tests verify:
1. Tool selection varies per sub-mode (DATOS_PERSONALES vs COLLECT_ELEMENT_DATA, etc.)
2. Sub-mode transition via post_tool_node (completar_elemento_actual → collect_base_docs)
3. _build_generic_loop_fn adapter is NOT referenced (legacy path removed).

Design references:
- AD-1: ModeLoopConfig with per-sub-mode get_tools callback
- expediente_mode.py: _HANDLERS dispatch table
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
    """Serialize a tool result dict to JSON."""
    return json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------------------
# T-21 Scenario 1: COLLECT_PERSONAL sub-mode uses DATOS_PERSONALES_TOOLS
# ---------------------------------------------------------------------------


class TestExpedienteSubModeToolSelection:
    """
    GIVEN collect_personal state → tools must come from _get_personal_tools().
    GIVEN collect_element_data state → tools must come from _get_element_data_tools().
    GIVEN collect_base_docs state → tools must come from _get_base_docs_tools().
    """

    def test_personal_tools_returns_actualizar_datos_expediente(self):
        """
        _get_personal_tools() must include actualizar_datos_expediente
        (the primary data-collection tool for COLLECT_PERSONAL).
        """
        from agent.modes.submodos._shared import _get_personal_tools

        tools = _get_personal_tools()
        tool_names = {t.name for t in tools}
        assert "actualizar_datos_expediente" in tool_names, (
            f"actualizar_datos_expediente missing from PERSONAL tools. Got: {tool_names}"
        )

    def test_personal_tools_does_not_include_element_data_tools(self):
        """
        _get_personal_tools() must NOT include element-data-collection tools
        like confirmar_fotos_elemento or completar_elemento_actual.
        """
        from agent.modes.submodos._shared import _get_personal_tools

        tools = _get_personal_tools()
        tool_names = {t.name for t in tools}
        for element_only_tool in (
            "confirmar_fotos_elemento",
            "completar_elemento_actual",
        ):
            assert element_only_tool not in tool_names, (
                f"{element_only_tool} should NOT be in PERSONAL tools. Got: {tool_names}"
            )

    def test_element_data_tools_includes_completar_elemento_actual(self):
        """
        _get_element_data_tools() must include completar_elemento_actual
        (triggers sub-mode transition to collect_base_docs).
        """
        from agent.modes.submodos._shared import _get_element_data_tools

        tools = _get_element_data_tools()
        tool_names = {t.name for t in tools}
        assert "completar_elemento_actual" in tool_names, (
            f"completar_elemento_actual missing from ELEMENT_DATA tools. Got: {tool_names}"
        )

    def test_base_docs_tools_includes_confirmar_documentacion_base(self):
        """
        _get_base_docs_tools() must include confirmar_documentacion_base
        (the trigger for advancing to COLLECT_PERSONAL).
        """
        from agent.modes.submodos._shared import _get_base_docs_tools

        tools = _get_base_docs_tools()
        tool_names = {t.name for t in tools}
        assert "confirmar_documentacion_base" in tool_names, (
            f"confirmar_documentacion_base missing from BASE_DOCS tools. Got: {tool_names}"
        )

    def test_tool_sets_are_disjoint_between_personal_and_element_data(self):
        """
        PERSONAL and ELEMENT_DATA tool sets share only universal tools
        (escalar_a_humano, consulta_durante_expediente, etc.).
        They must NOT share domain-specific tools.
        """
        from agent.modes.submodos._shared import (
            _get_personal_tools,
            _get_element_data_tools,
        )

        personal_names = {t.name for t in _get_personal_tools()}
        element_names = {t.name for t in _get_element_data_tools()}

        # Domain-specific tools must not overlap
        personal_only = {"actualizar_datos_expediente"}
        element_only = {
            "completar_elemento_actual",
            "confirmar_fotos_elemento",
            "guardar_datos_elemento",
        }

        for name in personal_only:
            assert name not in element_names, (
                f"{name} is PERSONAL-only but found in ELEMENT_DATA tools"
            )
        for name in element_only:
            assert name not in personal_names, (
                f"{name} is ELEMENT_DATA-only but found in PERSONAL tools"
            )


# ---------------------------------------------------------------------------
# T-21 Scenario 2: Sub-mode transition via post_tool_node
# ---------------------------------------------------------------------------


class TestExpedienteSubModeTransition:
    """
    GIVEN completar_elemento_actual returns all_elements_complete=True,
    WHEN the tool loop processes this via post_tool_node,
    THEN pending_state_updates["expediente_sub_mode"] == "collect_base_docs".
    """

    @pytest.mark.asyncio
    async def test_completar_elemento_returns_transition_signal(self):
        """
        completar_elemento_actual returning all_elements_complete=True
        must produce a result dict with expediente_sub_mode = collect_base_docs.
        This is the signal that expediente_mode picks up to advance sub-modes.
        """
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        # Build a fake completar_elemento_actual tool that returns transition signal
        from langchain_core.tools import tool as lc_tool

        @lc_tool
        def fake_completar_elemento_actual() -> dict:
            """Fake tool: marks all elements complete → transition to collect_base_docs."""
            return {
                "success": True,
                "all_elements_complete": True,
                "expediente_sub_mode": "collect_base_docs",
                "_state_update": {
                    "expediente_sub_mode": "collect_base_docs",
                },
            }

        # LLM: one tool call then final response
        ai_with_tool = AIMessage(
            content="",
            tool_calls=[_tool_call("fake_completar_elemento_actual", {}, "call-001")],
        )
        ai_final = AIMessage(content="Pasamos a documentación base.")
        mock_llm = _make_mock_llm([ai_with_tool, ai_final])

        config = ModeLoopConfig(
            mode_name="EXPEDIENTE_MODE",
            get_tools=lambda ctx: [fake_completar_elemento_actual],
            get_system_prompt=lambda state: "Eres el asistente de expediente.",
            post_tool_hook=None,
            max_iterations=5,
            _llm_override=mock_llm,
        )

        with patch(
            "agent.modes.tool_executor.execute_and_log_tool",
            new_callable=AsyncMock,
        ) as mock_exec:
            mock_exec.return_value = _tool_result(
                {
                    "success": True,
                    "all_elements_complete": True,
                    "expediente_sub_mode": "collect_base_docs",
                    "_state_update": {
                        "expediente_sub_mode": "collect_base_docs",
                    },
                }
            )

            loop_result_obj = build_mode_tool_loop(config)
            graph = loop_result_obj.graph
            result = await graph.ainvoke(
                {
                    "messages": [HumanMessage(content="Ya envié todas las fotos.")],
                    "_mode_context": {
                        "expediente_sub_mode": "collect_element_data",
                        "case_id": "test-case-01",
                    },
                    "_conversation_id": "exp-test-01",
                }
            )

        # After the loop, pending_state_updates should contain the sub-mode transition
        pending = result.get("pending_state_updates", {})
        assert pending.get("expediente_sub_mode") == "collect_base_docs", (
            f"Expected pending_state_updates['expediente_sub_mode'] == 'collect_base_docs', "
            f"got: {pending}"
        )

    @pytest.mark.asyncio
    async def test_post_tool_node_accumulates_state_updates_from_multiple_tools(self):
        """
        When two tools are called in the same LLM turn,
        their _state_update dicts are MERGED in pending_state_updates.
        """
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig
        from langchain_core.tools import tool as lc_tool

        @lc_tool
        def tool_a() -> dict:
            """Tool A: sets field_a."""
            return {"_state_update": {"field_a": "value_a"}}

        @lc_tool
        def tool_b() -> dict:
            """Tool B: sets field_b."""
            return {"_state_update": {"field_b": "value_b"}}

        ai_with_two_tools = AIMessage(
            content="",
            tool_calls=[
                _tool_call("tool_a", {}, "call-a"),
                _tool_call("tool_b", {}, "call-b"),
            ],
        )
        ai_final = AIMessage(content="Hecho.")
        mock_llm = _make_mock_llm([ai_with_two_tools, ai_final])

        call_counter = {"n": 0}

        async def mock_exec(**kwargs):
            n = call_counter["n"]
            call_counter["n"] += 1
            if n == 0:
                return _tool_result({"_state_update": {"field_a": "value_a"}})
            return _tool_result({"_state_update": {"field_b": "value_b"}})

        config = ModeLoopConfig(
            mode_name="EXPEDIENTE_MODE",
            get_tools=lambda ctx: [tool_a, tool_b],
            get_system_prompt=lambda state: "Prompt.",
            post_tool_hook=None,
            max_iterations=5,
            _llm_override=mock_llm,
        )

        with patch(
            "agent.modes.tool_executor.execute_and_log_tool",
            side_effect=mock_exec,
        ):
            loop_result_obj = build_mode_tool_loop(config)
            graph = loop_result_obj.graph
            result = await graph.ainvoke(
                {
                    "messages": [HumanMessage(content="Datos del expediente.")],
                    "_mode_context": {"case_id": "test-002"},
                    "_conversation_id": "exp-test-02",
                }
            )

        pending = result.get("pending_state_updates", {})
        assert "field_a" in pending, (
            f"field_a missing from pending_state_updates: {pending}"
        )
        assert "field_b" in pending, (
            f"field_b missing from pending_state_updates: {pending}"
        )
        assert pending["field_a"] == "value_a"
        assert pending["field_b"] == "value_b"


# ---------------------------------------------------------------------------
# T-21 Scenario 3: No _build_generic_loop_fn after migration
# ---------------------------------------------------------------------------


class TestExpedienteModeNoGenericLoopFn:
    """
    After T-22 migration, expediente_mode.py must NOT define
    or reference _build_generic_loop_fn.

    This test is RED now (before T-22) and GREEN after the migration.
    """

    def test_expediente_mode_does_not_define_build_generic_loop_fn(self):
        """
        After T-22, _build_generic_loop_fn must not exist in ExpedienteModeNode.
        Currently FAILS (RED) — will pass after T-22 removes the adapter.
        """
        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()
        assert not hasattr(node, "_build_generic_loop_fn"), (
            "_build_generic_loop_fn still exists on ExpedienteModeNode — T-22 not yet applied"
        )

    def test_expediente_mode_no_top_level_generic_loop_import(self):
        """
        After T-22, expediente_mode.py must not have a top-level (module-level) import
        of generic_loop. Lazy imports inside function bodies are allowed for the fallback path.
        Currently passes after T-22 (generic_loop is only lazy-imported inside _run_with_generic_loop).
        """
        import ast
        import pathlib

        src = pathlib.Path("agent/modes/expediente_mode.py").read_text()
        tree = ast.parse(src)

        # Only check top-level statements (tree.body), not nested function bodies
        top_level_generic_loop_imports = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                if node.module and "generic_loop" in node.module:
                    top_level_generic_loop_imports.append(
                        f"line {node.lineno}: from {node.module} import ..."
                    )

        assert top_level_generic_loop_imports == [], (
            f"Top-level generic_loop imports still present in expediente_mode.py: "
            f"{top_level_generic_loop_imports}"
        )

    def test_expediente_mode_no_set_current_state_top_level_call(self):
        """
        After T-22, expediente_mode.py must not call set_current_state() at
        the module level (it may remain in _build_generic_loop_fn fallback path
        if lazy-imported, but the adapter itself must be removed).
        After T-22 is complete, _build_generic_loop_fn should not exist.
        """
        from agent.modes.expediente_mode import ExpedienteModeNode

        # The method _build_generic_loop_fn should not exist after T-22
        # This is the same as test_expediente_mode_does_not_define_build_generic_loop_fn
        # Kept as a distinct test for clarity on the migration goal.
        assert not hasattr(ExpedienteModeNode, "_build_generic_loop_fn"), (
            "_build_generic_loop_fn class method still present — legacy loop must stay removed"
        )
