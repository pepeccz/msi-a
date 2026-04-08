"""
Integration tests for CONSULTA_MODE using build_mode_tool_loop() (T-13).

Strict TDD — these tests are written BEFORE the consulta_mode.py rewrite (T-14).
They verify:
1. The subgraph compiles and runs a full CONSULTA turn with mocked LLM + tools.
2. AIMessage → ToolMessage pairing is maintained (no protocol corruption).
3. No generic_llm_loop reference remains in consulta_mode.py after migration.
4. Feature flag guard correctly routes to new engine when CONSULTA is enabled.
5. Fallback path still works when CONSULTA is NOT in TOOLNODE_ENABLED_MODES.

Design references:
- AD-1: Custom tool_node subgraph pattern
- AD-7: Feature flag (TOOLNODE_ENABLED_MODES)
- Domain 5: CONSULTA mode migration scenario
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, AsyncMock
import pytest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_llm(responses: list[AIMessage]) -> MagicMock:
    """Create a mock LLM that returns responses in sequence."""
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


# ---------------------------------------------------------------------------
# T-13: Integration tests for CONSULTA full loop
# ---------------------------------------------------------------------------


class TestConsultaToolLoopIntegration:
    """Full subgraph integration: compile → invoke → verify output."""

    @pytest.mark.asyncio
    async def test_consulta_loop_no_tools_returns_ai_response(self):
        """
        GIVEN a CONSULTA turn where LLM decides no tool is needed,
        WHEN the subgraph is invoked,
        THEN it returns ai_response immediately without entering custom_tool_node.
        """
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        final_response = AIMessage(
            content="La homologación de un escape cuesta 410€ +IVA."
        )
        mock_llm = _make_mock_llm([final_response])

        config = ModeLoopConfig(
            mode_name="CONSULTA_MODE",
            get_tools=lambda ctx: [],
            get_system_prompt=lambda state: "Eres un asistente especializado.",
            post_tool_hook=None,
            max_iterations=5,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="¿Cuánto cuesta el escape?")],
                "_mode_context": {"categoria_slug": "motos-part"},
                "_conversation_id": "int-test-01",
            }
        )

        assert result["ai_response"] == "La homologación de un escape cuesta 410€ +IVA."
        assert result["exit_reason"] == "response"

    @pytest.mark.asyncio
    async def test_consulta_loop_with_tool_call_maintains_message_pairing(self):
        """
        GIVEN a CONSULTA turn where LLM calls a tool and then responds,
        WHEN the subgraph runs,
        THEN messages contain: HumanMessage → AIMessage(tool_call) → ToolMessage → AIMessage(final)
        AND every ToolMessage has a preceding AIMessage with matching tool_call_id.
        """
        from langchain_core.tools import tool as lc_tool
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        @lc_tool
        async def listar_categorias_test() -> dict:
            """Listar categorías disponibles."""
            return {"success": True, "categorias": ["motos-part", "coches-prot"]}

        tool_call_ai = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_int_001",
                    "name": "listar_categorias_test",
                    "args": {},
                    "type": "tool_call",
                }
            ],
        )
        final_ai = AIMessage(
            content="Las categorías disponibles son: motos-part, coches-prot."
        )
        mock_llm = _make_mock_llm([tool_call_ai, final_ai])

        config = ModeLoopConfig(
            mode_name="CONSULTA_MODE",
            get_tools=lambda ctx: [listar_categorias_test],
            get_system_prompt=lambda state: "Eres un asistente de homologación.",
            post_tool_hook=None,
            max_iterations=5,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        initial_user_msg = HumanMessage(content="¿Qué categorías hay?")
        result = await graph.ainvoke(
            {
                "messages": [initial_user_msg],
                "_mode_context": {},
                "_conversation_id": "int-test-02",
            }
        )

        # Final response is correct
        assert "categorías" in result["ai_response"]

        # Verify message protocol — find all ToolMessages and check pairing
        # Use duck-typing (check class name) to avoid isinstance issues when
        # langchain_core.messages is reloaded between test files.
        all_messages = result.get("messages", [])
        tool_messages = [m for m in all_messages if type(m).__name__ == "ToolMessage"]
        assert len(tool_messages) >= 1, (
            f"No ToolMessages found in messages: {[type(m).__name__ for m in all_messages]}"
        )

        # Each ToolMessage must have a preceding AIMessage with matching tool_call_id
        for tm in tool_messages:
            # Find the AIMessage that has this tool_call_id
            matching_ai = None
            for msg in all_messages:
                if type(msg).__name__ in ("AIMessage", "AIMessageChunk"):
                    for tc in getattr(msg, "tool_calls", None) or []:
                        if tc.get("id") == getattr(tm, "tool_call_id", None):
                            matching_ai = msg
                            break
            assert matching_ai is not None, (
                f"ToolMessage with tool_call_id={getattr(tm, 'tool_call_id', '?')} has no matching AIMessage"
            )

    @pytest.mark.asyncio
    async def test_consulta_loop_multi_tool_turn(self):
        """
        GIVEN a CONSULTA turn with 2 tool calls in one LLM response,
        WHEN the subgraph runs,
        THEN both tools execute and both ToolMessages appear in final state.
        """
        from langchain_core.tools import tool as lc_tool
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        tool_a_called = {"n": 0}
        tool_b_called = {"n": 0}

        @lc_tool
        async def tool_a_test(query: str) -> dict:
            """Tool A."""
            tool_a_called["n"] += 1
            return {"success": True, "result": f"A: {query}"}

        @lc_tool
        async def tool_b_test(query: str) -> dict:
            """Tool B."""
            tool_b_called["n"] += 1
            return {"success": True, "result": f"B: {query}"}

        two_tool_ai = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_a",
                    "name": "tool_a_test",
                    "args": {"query": "escape"},
                    "type": "tool_call",
                },
                {
                    "id": "call_b",
                    "name": "tool_b_test",
                    "args": {"query": "manillar"},
                    "type": "tool_call",
                },
            ],
        )
        final_ai = AIMessage(content="Encontré información sobre escape y manillar.")
        mock_llm = _make_mock_llm([two_tool_ai, final_ai])

        config = ModeLoopConfig(
            mode_name="CONSULTA_MODE",
            get_tools=lambda ctx: [tool_a_test, tool_b_test],
            get_system_prompt=lambda state: "Prompt.",
            post_tool_hook=None,
            max_iterations=5,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Busca escape y manillar.")],
                "_mode_context": {},
                "_conversation_id": "int-test-multi",
            }
        )

        assert tool_a_called["n"] == 1
        assert tool_b_called["n"] == 1
        assert "ai_response" in result

    @pytest.mark.asyncio
    async def test_consulta_loop_state_update_reaches_pending_state_updates(self):
        """
        GIVEN a tool that returns _state_update,
        WHEN the loop completes,
        THEN pending_state_updates contains the merged updates from all tools.
        """
        from langchain_core.tools import tool as lc_tool
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        @lc_tool
        async def catalog_tool(categoria: str) -> dict:
            """Tool returning _state_update."""
            return {
                "success": True,
                "categorias": [categoria],
                "_state_update": {
                    "last_category_viewed": categoria,
                    "mode_context": {"categoria_slug": categoria},
                },
            }

        tool_call_ai = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_cat",
                    "name": "catalog_tool",
                    "args": {"categoria": "motos-part"},
                    "type": "tool_call",
                }
            ],
        )
        final_ai = AIMessage(content="He buscado motos-part para ti.")
        mock_llm = _make_mock_llm([tool_call_ai, final_ai])

        config = ModeLoopConfig(
            mode_name="CONSULTA_MODE",
            get_tools=lambda ctx: [catalog_tool],
            get_system_prompt=lambda state: "Prompt.",
            post_tool_hook=None,
            max_iterations=5,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Dame info de motos-part.")],
                "_mode_context": {},
                "_conversation_id": "int-test-state",
            }
        )

        pending = result.get("pending_state_updates", {})
        assert pending.get("last_category_viewed") == "motos-part"


# ---------------------------------------------------------------------------
# T-13 continued: Verify no generic_llm_loop in consulta_mode.py (post T-14)
# ---------------------------------------------------------------------------


class TestConsultaModeCodeQuality:
    """Code quality checks that verify T-14 acceptance criteria."""

    def test_no_generic_llm_loop_at_module_level_in_consulta_mode(self):
        """
        AC for T-14: consulta_mode.py MUST NOT have generic_llm_loop as a
        module-level import. The fallback path may use a lazy local import.

        The new engine code path (feature-flag=ON) must be free of generic_loop
        references at the module level — ensuring clean separation.
        """
        import pathlib

        consulta_path = pathlib.Path("agent/modes/consulta_mode.py")
        source = consulta_path.read_text(encoding="utf-8")

        # Must NOT be a top-level (module-level) import from generic_loop
        lines = source.split("\n")
        top_level_generic_imports = [
            line
            for line in lines
            if ("generic_llm_loop" in line or "GenericLoopResult" in line)
            and line.startswith("from ")
            or line.startswith("import ")
            and "generic_loop" in line
        ]
        # The fallback path may have lazy imports inside functions — that's OK.
        # What's NOT OK is module-level imports.
        module_level_bad = [
            line
            for line in lines[:50]  # check first 50 lines (module level)
            if "from agent.modes.generic_loop" in line
            and not line.strip().startswith("#")
        ]
        assert not module_level_bad, (
            f"consulta_mode.py has module-level generic_loop import: {module_level_bad}"
        )

    def test_no_generic_loop_top_level_import_in_consulta_mode(self):
        """consulta_mode.py must not have top-level generic_loop import after T-14."""
        import pathlib

        consulta_path = pathlib.Path("agent/modes/consulta_mode.py")
        source = consulta_path.read_text(encoding="utf-8")

        lines = source.split("\n")
        # Check only the top-level imports (before any class/def/if)
        top_level_generic = [
            line
            for line in lines[:50]
            if "from agent.modes.generic_loop" in line
            and not line.strip().startswith("#")
        ]
        assert not top_level_generic, (
            f"consulta_mode.py has top-level import from generic_loop: {top_level_generic}"
        )

    def test_consulta_mode_imports_build_mode_tool_loop(self):
        """
        After T-14, consulta_mode.py MUST import build_mode_tool_loop
        from agent.modes.tool_loop.
        """
        import pathlib

        consulta_path = pathlib.Path("agent/modes/consulta_mode.py")
        source = consulta_path.read_text(encoding="utf-8")

        assert "build_mode_tool_loop" in source, (
            "consulta_mode.py does not reference build_mode_tool_loop — T-14 not done"
        )

    def test_feature_flag_guard_in_consulta_mode(self):
        """
        After T-14, consulta_mode.py MUST check TOOLNODE_ENABLED_MODES
        to decide which engine to use.
        """
        import pathlib

        consulta_path = pathlib.Path("agent/modes/consulta_mode.py")
        source = consulta_path.read_text(encoding="utf-8")

        assert "TOOLNODE_ENABLED_MODES" in source, (
            "consulta_mode.py does not check TOOLNODE_ENABLED_MODES feature flag"
        )


# ---------------------------------------------------------------------------
# T-13 continued: Feature flag integration
# ---------------------------------------------------------------------------


class TestConsultaFeatureFlag:
    """Feature flag routing tests for CONSULTA_MODE."""

    @pytest.mark.asyncio
    async def test_consulta_mode_uses_new_engine_when_flag_set(self):
        """
        GIVEN TOOLNODE_ENABLED_MODES includes "CONSULTA_MODE",
        WHEN ConsultaModeNode._process_message is called,
        THEN it must use build_mode_tool_loop (not generic_llm_loop).

        This test will be RED until T-14 is complete.
        """
        from unittest.mock import patch, AsyncMock, MagicMock
        from langchain_core.messages import HumanMessage, AIMessage
        from agent.modes.consulta_mode import ConsultaModeNode

        # Patch settings so CONSULTA is in TOOLNODE_ENABLED_MODES
        mock_settings = MagicMock()
        mock_settings.TOOLNODE_ENABLED_MODES = "CONSULTA_MODE"

        # Track which engine is called
        tool_loop_called = {"n": 0}
        generic_loop_called = {"n": 0}

        final_ai = AIMessage(content="Respuesta de prueba.")
        mock_subgraph = AsyncMock()
        mock_subgraph.ainvoke = AsyncMock(
            return_value={
                "ai_response": "Respuesta de prueba.",
                "exit_reason": "response",
                "pending_state_updates": {},
                "messages": [final_ai],
            }
        )

        def mock_build(config):
            tool_loop_called["n"] += 1
            return mock_subgraph

        mock_state = {
            "conversation_id": "flag-test-conv",
            "messages": [],
            "mode_context": {},
            "current_mode": "CONSULTA_MODE",
            "client_type": "particular",
            "is_first_interaction": False,
        }

        node = ConsultaModeNode()

        with patch(
            "agent.modes.consulta_mode.get_settings", return_value=mock_settings
        ):
            with patch(
                "agent.modes.consulta_mode.build_mode_tool_loop", side_effect=mock_build
            ):
                result = await node._process_message("¿Cuánto cuesta?", mock_state)

        assert tool_loop_called["n"] == 1, (
            "build_mode_tool_loop was not called — feature flag not checked"
        )

    @pytest.mark.asyncio
    async def test_consulta_mode_always_uses_tool_loop_after_t25(self):
        """
        T-25 (loop-to-toolnode-migration): generic_loop.py deleted.
        CONSULTA_MODE always uses _process_with_tool_loop regardless of TOOLNODE_ENABLED_MODES.

        Updated from test_consulta_mode_uses_generic_loop_when_flag_not_set:
        the old fallback to generic_llm_loop is removed in T-25. Now CONSULTA
        always calls build_mode_tool_loop, even when TOOLNODE_ENABLED_MODES == "".
        """
        from unittest.mock import patch, AsyncMock, MagicMock
        from agent.modes.consulta_mode import ConsultaModeNode

        mock_settings = MagicMock()
        mock_settings.TOOLNODE_ENABLED_MODES = (
            ""  # Flag not set — but consulta still uses tool_loop
        )

        tool_loop_called = {"n": 0}

        original_process_tool_loop = None

        mock_state = {
            "conversation_id": "fallback-conv",
            "messages": [],
            "mode_context": {},
            "current_mode": "CONSULTA_MODE",
            "client_type": "particular",
            "is_first_interaction": False,
        }

        node = ConsultaModeNode()

        async def mock_process_with_tool_loop(message, state):
            tool_loop_called["n"] += 1
            return {"ai_response": "Respuesta via tool loop.", "mode_context": {}}

        with patch.object(
            node, "_process_with_tool_loop", side_effect=mock_process_with_tool_loop
        ):
            result = await node._process_message("¿Cuánto cuesta?", mock_state)

        assert tool_loop_called["n"] == 1, (
            "_process_with_tool_loop not called — CONSULTA should always use tool_loop after T-25"
        )
        assert result["ai_response"] == "Respuesta via tool loop."
