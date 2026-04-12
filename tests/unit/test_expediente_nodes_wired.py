"""
Tests for wired expediente sub-mode nodes (Phase 2, T-11 through T-20).

Strict TDD — written BEFORE the nodes are wired to build_mode_tool_loop.

Coverage:
  T-11 — each of the 6 nodes returns Command with non-empty update (not bare END)
  T-12 — collect_element_data_node tool set and transition
  T-13 — remaining 5 nodes tool set and transition propagation
  T-16 — config forwarding and error handling (max_iterations, GraphRecursionError)
  T-20 — entry_router re-dispatches correctly after sub_mode write
"""

from __future__ import annotations

import json
import sys
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from agent.modes.tool_loop import ToolLoopResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_expediente_state(
    expediente_sub_mode: str = "collect_element_data",
    conversation_id: str = "test-exp-nodes-001",
    extra: dict | None = None,
) -> dict:
    """Build a minimal ExpedienteState-shaped dict."""
    state: dict[str, Any] = {
        "conversation_id": conversation_id,
        "user_id": None,
        "user_phone": "+34600000001",
        "user_name": "Test User",
        "client_type": "particular",
        "expediente_sub_mode": expediente_sub_mode,
        "user_message": "Hola, ¿cómo va?",
        "incoming_attachments": [],
        "messages": [],
        "case_id": "case-uuid-test-001",
        "element_codes": ["MOTOS-PART-SUSPENSION"],
        "element_display_names": {"MOTOS-PART-SUSPENSION": "Suspensión"},
    }
    if extra:
        state.update(extra)
    return state


def _make_mock_llm(ai_response: str = "Respuesta de prueba") -> MagicMock:
    """Create a mock LLM that returns a plain AIMessage (no tool calls)."""

    async def mock_ainvoke(messages, **kwargs):
        return AIMessage(content=ai_response)

    mock_llm = MagicMock()
    mock_llm.ainvoke = mock_ainvoke
    bound_mock = MagicMock()
    bound_mock.ainvoke = mock_ainvoke
    mock_llm.bind_tools = MagicMock(return_value=bound_mock)
    return mock_llm


def _make_mock_llm_with_tool_call(tool_name: str, args: dict, call_id: str = "tc_001") -> MagicMock:
    """Create a mock LLM that first calls a tool, then returns a plain response."""
    call_count = {"n": 0}

    async def mock_ainvoke(messages, **kwargs):
        if call_count["n"] == 0:
            call_count["n"] += 1
            return AIMessage(
                content="",
                tool_calls=[{"id": call_id, "name": tool_name, "args": args, "type": "tool_call"}],
            )
        return AIMessage(content="Respuesta tras herramienta")

    mock_llm = MagicMock()
    mock_llm.ainvoke = mock_ainvoke
    bound_mock = MagicMock()
    bound_mock.ainvoke = mock_ainvoke
    mock_llm.bind_tools = MagicMock(return_value=bound_mock)
    return mock_llm


# ---------------------------------------------------------------------------
# T-11: Each node returns Command with non-empty update (not bare END)
# ---------------------------------------------------------------------------


NODE_NAMES = [
    "collect_element_data_node",
    "collect_base_docs_node",
    "collect_personal_node",
    "collect_vehicle_node",
    "collect_workshop_node",
    "review_summary_node",
]

SUB_MODES = [
    "collect_element_data",
    "collect_base_docs",
    "collect_personal",
    "collect_vehicle",
    "collect_workshop",
    "review_summary",
]


class TestNodesReturnNonBareEnd:
    """T-11: wired nodes must NOT return bare Command(goto=END) — they must carry updates."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("node_name,sub_mode", list(zip(NODE_NAMES, SUB_MODES)))
    async def test_no_stub_returns_bare_end(self, node_name: str, sub_mode: str) -> None:
        """Each node returns a Command with non-None update (not just Command(goto=END))."""
        import agent.modes.expediente_nodes as mod

        node_fn = getattr(mod, node_name)
        state = _make_expediente_state(expediente_sub_mode=sub_mode)

        # Provide a mock subgraph so the node can execute without real LLM
        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(return_value={
            "ai_response": "ok",
            "exit_reason": "response",
            "tools_called": [],
            "pending_state_updates": {},
        })

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=ToolLoopResult(graph=mock_compiled, recursion_limit=35)):
            result = await node_fn(state)

        from langgraph.types import Command

        assert isinstance(result, Command), f"{node_name} must return Command, got {type(result)}"
        # Wired nodes must carry an update dict — not bare Command(goto=END) with update=None
        assert result.update is not None, (
            f"{node_name} returned bare Command(goto=END) with no update — "
            "still a stub. Wire to build_mode_tool_loop."
        )
        # The update must be a dict (not empty)
        assert isinstance(result.update, dict), (
            f"{node_name}.update must be a dict, got {type(result.update)}"
        )
        assert len(result.update) > 0, f"{node_name}.update is empty — expected at least ai_response"


class TestPostToolHookAlwaysSet:
    """T-11: Each node must use expediente_post_tool_hook (not None)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("node_name,sub_mode", list(zip(NODE_NAMES, SUB_MODES)))
    async def test_post_tool_hook_always_set(self, node_name: str, sub_mode: str) -> None:
        """
        expediente_post_tool_hook must be passed to ModeLoopConfig for all 6 nodes.

        We verify by patching build_mode_tool_loop and capturing the config argument.
        """
        import agent.modes.expediente_nodes as mod
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        node_fn = getattr(mod, node_name)
        state = _make_expediente_state(expediente_sub_mode=sub_mode)

        captured_configs = []

        async def fake_subgraph(initial_state, **kw):
            return {
                "ai_response": "ok",
                "exit_reason": "response",
                "tools_called": [],
                "pending_state_updates": {},
            }

        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(side_effect=fake_subgraph)

        def capture_and_build(config):
            captured_configs.append(config)
            return ToolLoopResult(graph=mock_compiled, recursion_limit=35)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", side_effect=capture_and_build):
            await node_fn(state)

        assert len(captured_configs) == 1, f"{node_name} did not call build_mode_tool_loop"
        cfg = captured_configs[0]
        assert cfg.post_tool_hook is expediente_post_tool_hook, (
            f"{node_name} uses post_tool_hook={cfg.post_tool_hook!r}, "
            "expected expediente_post_tool_hook"
        )


class TestModeContextPassedToLoop:
    """T-11: initial ToolLoopState has _mode_context derived from state."""

    @pytest.mark.asyncio
    async def test_mode_context_passed_to_loop(self) -> None:
        """collect_element_data_node passes element_codes in _mode_context."""
        import agent.modes.expediente_nodes as mod

        state = _make_expediente_state(
            expediente_sub_mode="collect_element_data",
            extra={"element_codes": ["MOTOS-PART-SUSPENSION", "MOTOS-PART-FRENOS"]},
        )

        captured_initial_states = []

        async def fake_invoke(initial_state, **kw):
            captured_initial_states.append(initial_state)
            return {
                "ai_response": "ok",
                "exit_reason": "response",
                "tools_called": [],
                "pending_state_updates": {},
            }

        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(side_effect=fake_invoke)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=ToolLoopResult(graph=mock_compiled, recursion_limit=35)):
            await mod.collect_element_data_node(state)

        assert len(captured_initial_states) == 1
        initial = captured_initial_states[0]
        mc = initial.get("_mode_context", {})
        assert "element_codes" in mc, "_mode_context must carry element_codes"
        assert mc["element_codes"] == ["MOTOS-PART-SUSPENSION", "MOTOS-PART-FRENOS"]


class TestMessagesSurviveRoundTrip:
    """T-11: messages from state appear in loop input."""

    @pytest.mark.asyncio
    async def test_messages_survive_round_trip(self) -> None:
        """User message from state is forwarded to the tool loop initial state."""
        import agent.modes.expediente_nodes as mod

        state = _make_expediente_state(
            expediente_sub_mode="collect_element_data",
            extra={"user_message": "Necesito homologar una suspensión"},
        )

        captured_initial_states = []

        async def fake_invoke(initial_state, **kw):
            captured_initial_states.append(initial_state)
            return {
                "ai_response": "ok",
                "exit_reason": "response",
                "tools_called": [],
                "pending_state_updates": {},
            }

        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(side_effect=fake_invoke)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=ToolLoopResult(graph=mock_compiled, recursion_limit=35)):
            await mod.collect_element_data_node(state)

        assert len(captured_initial_states) == 1
        initial = captured_initial_states[0]
        messages = initial.get("messages", [])
        assert len(messages) > 0, "Initial ToolLoopState must have messages"
        # Last message should contain the user message
        last_msg = messages[-1]
        content = last_msg.content if hasattr(last_msg, "content") else last_msg.get("content", "")
        assert "suspensión" in content or "homologar" in content, (
            f"User message not found in loop input. Last message content: {content!r}"
        )


# ---------------------------------------------------------------------------
# T-12: collect_element_data_node tool set and transition
# ---------------------------------------------------------------------------


class TestCollectElementDataToolSet:
    """T-12: collect_element_data_node uses correct tools and handles transitions."""

    def test_element_data_tools_includes_confirmar_fotos(self) -> None:
        """_get_element_data_tools() includes confirmar_fotos_elemento."""
        from agent.modes.submodos._shared import _get_element_data_tools

        tools = _get_element_data_tools()
        names = {t.name for t in tools}
        assert "confirmar_fotos_elemento" in names

    def test_element_data_tools_includes_guardar_datos(self) -> None:
        """_get_element_data_tools() includes guardar_datos_elemento."""
        from agent.modes.submodos._shared import _get_element_data_tools

        tools = _get_element_data_tools()
        names = {t.name for t in tools}
        assert "guardar_datos_elemento" in names

    def test_element_data_tools_includes_completar_elemento(self) -> None:
        """_get_element_data_tools() includes completar_elemento_actual."""
        from agent.modes.submodos._shared import _get_element_data_tools

        tools = _get_element_data_tools()
        names = {t.name for t in tools}
        assert "completar_elemento_actual" in names

    def test_element_data_tools_includes_obtener_campos(self) -> None:
        """_get_element_data_tools() includes obtener_campos_elemento."""
        from agent.modes.submodos._shared import _get_element_data_tools

        tools = _get_element_data_tools()
        names = {t.name for t in tools}
        assert "obtener_campos_elemento" in names

    def test_element_data_tools_includes_obtener_progreso(self) -> None:
        """_get_element_data_tools() includes obtener_progreso_elementos."""
        from agent.modes.submodos._shared import _get_element_data_tools

        tools = _get_element_data_tools()
        names = {t.name for t in tools}
        assert "obtener_progreso_elementos" in names

    def test_element_data_tools_includes_reenviar_imagenes(self) -> None:
        """_get_element_data_tools() includes reenviar_imagenes_elemento."""
        from agent.modes.submodos._shared import _get_element_data_tools

        tools = _get_element_data_tools()
        names = {t.name for t in tools}
        assert "reenviar_imagenes_elemento" in names

    def test_element_data_tools_includes_enviar_imagenes_ejemplo(self) -> None:
        """_get_element_data_tools() includes enviar_imagenes_ejemplo."""
        from agent.modes.submodos._shared import _get_element_data_tools

        tools = _get_element_data_tools()
        names = {t.name for t in tools}
        assert "enviar_imagenes_ejemplo" in names

    def test_element_data_tools_includes_escalar_a_humano(self) -> None:
        """_get_element_data_tools() includes escalar_a_humano."""
        from agent.modes.submodos._shared import _get_element_data_tools

        tools = _get_element_data_tools()
        names = {t.name for t in tools}
        assert "escalar_a_humano" in names

    def test_element_data_tools_does_NOT_include_confirmar_documentacion_base(self) -> None:
        """_get_element_data_tools() does NOT include confirmar_documentacion_base."""
        from agent.modes.submodos._shared import _get_element_data_tools

        tools = _get_element_data_tools()
        names = {t.name for t in tools}
        assert "confirmar_documentacion_base" not in names, (
            "confirmar_documentacion_base belongs to COLLECT_BASE_DOCS, not COLLECT_ELEMENT_DATA"
        )

    def test_element_data_tools_does_NOT_include_finalizar_expediente(self) -> None:
        """_get_element_data_tools() does NOT include finalizar_expediente."""
        from agent.modes.submodos._shared import _get_element_data_tools

        tools = _get_element_data_tools()
        names = {t.name for t in tools}
        assert "finalizar_expediente" not in names, (
            "finalizar_expediente belongs to REVIEW_SUMMARY, not COLLECT_ELEMENT_DATA"
        )

    @pytest.mark.asyncio
    async def test_all_elements_complete_changes_expediente_sub_mode(self) -> None:
        """
        When pending_state_updates contains expediente_sub_mode transition,
        the node includes that update in its Command.
        """
        import agent.modes.expediente_nodes as mod

        state = _make_expediente_state(expediente_sub_mode="collect_element_data")

        async def fake_invoke(initial_state, **kw):
            return {
                "ai_response": "Elementos completados",
                "exit_reason": "response",
                "tools_called": ["completar_elemento_actual"],
                "pending_state_updates": {
                    "mode_context": {
                        "expediente_sub_mode": "collect_base_docs",
                        "just_transitioned_from": "collect_element_data",
                    }
                },
            }

        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(side_effect=fake_invoke)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=ToolLoopResult(graph=mock_compiled, recursion_limit=35)):
            result = await mod.collect_element_data_node(state)

        from langgraph.types import Command

        assert isinstance(result, Command)
        assert result.update is not None
        # The new sub_mode should appear in the update (at the ExpedienteState level)
        update = result.update
        # expediente_sub_mode may appear directly or via mode_context merge
        new_sub_mode = update.get("expediente_sub_mode") or (
            update.get("mode_context", {}).get("expediente_sub_mode")
        )
        assert new_sub_mode == "collect_base_docs", (
            f"Expected expediente_sub_mode='collect_base_docs' in update, got {update!r}"
        )


# ---------------------------------------------------------------------------
# T-13: Remaining 5 nodes tool set correctness and transition propagation
# ---------------------------------------------------------------------------


class TestCollectBaseDocsToolSet:
    """T-13: collect_base_docs_node uses _get_base_docs_tools."""

    def test_base_docs_tools_includes_confirmar_documentacion_base(self) -> None:
        from agent.modes.submodos._shared import _get_base_docs_tools

        names = {t.name for t in _get_base_docs_tools()}
        assert "confirmar_documentacion_base" in names

    def test_base_docs_tools_includes_escalar_a_humano(self) -> None:
        from agent.modes.submodos._shared import _get_base_docs_tools

        names = {t.name for t in _get_base_docs_tools()}
        assert "escalar_a_humano" in names

    def test_base_docs_tools_does_NOT_include_guardar_datos_elemento(self) -> None:
        from agent.modes.submodos._shared import _get_base_docs_tools

        names = {t.name for t in _get_base_docs_tools()}
        assert "guardar_datos_elemento" not in names

    @pytest.mark.asyncio
    async def test_collect_base_docs_node_propagates_transition(self) -> None:
        """collect_base_docs_node propagates sub_mode transition in its Command update."""
        import agent.modes.expediente_nodes as mod

        state = _make_expediente_state(expediente_sub_mode="collect_base_docs")

        async def fake_invoke(initial_state, **kw):
            return {
                "ai_response": "Documentos confirmados",
                "exit_reason": "response",
                "tools_called": ["confirmar_documentacion_base"],
                "pending_state_updates": {
                    "mode_context": {"expediente_sub_mode": "collect_personal"}
                },
            }

        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(side_effect=fake_invoke)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=ToolLoopResult(graph=mock_compiled, recursion_limit=35)):
            result = await mod.collect_base_docs_node(state)

        from langgraph.types import Command

        assert isinstance(result, Command)
        update = result.update or {}
        new_sub_mode = update.get("expediente_sub_mode") or (
            update.get("mode_context", {}).get("expediente_sub_mode")
        )
        assert new_sub_mode == "collect_personal", (
            f"Expected expediente_sub_mode='collect_personal', got {update!r}"
        )


class TestCollectPersonalToolSet:
    """T-13: collect_personal_node uses _get_personal_tools."""

    def test_personal_tools_includes_actualizar_datos_expediente(self) -> None:
        from agent.modes.submodos._shared import _get_personal_tools

        names = {t.name for t in _get_personal_tools()}
        assert "actualizar_datos_expediente" in names

    def test_personal_tools_does_NOT_include_finalizar_expediente(self) -> None:
        from agent.modes.submodos._shared import _get_personal_tools

        names = {t.name for t in _get_personal_tools()}
        assert "finalizar_expediente" not in names

    @pytest.mark.asyncio
    async def test_collect_personal_node_propagates_transition(self) -> None:
        import agent.modes.expediente_nodes as mod

        state = _make_expediente_state(expediente_sub_mode="collect_personal")

        async def fake_invoke(initial_state, **kw):
            return {
                "ai_response": "Datos personales guardados",
                "exit_reason": "response",
                "tools_called": ["actualizar_datos_expediente"],
                "pending_state_updates": {
                    "mode_context": {"expediente_sub_mode": "collect_vehicle"}
                },
            }

        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(side_effect=fake_invoke)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=ToolLoopResult(graph=mock_compiled, recursion_limit=35)):
            result = await mod.collect_personal_node(state)

        from langgraph.types import Command

        assert isinstance(result, Command)
        update = result.update or {}
        new_sub_mode = update.get("expediente_sub_mode") or (
            update.get("mode_context", {}).get("expediente_sub_mode")
        )
        assert new_sub_mode == "collect_vehicle"


class TestCollectVehicleToolSet:
    """T-13: collect_vehicle_node uses _get_vehicle_tools."""

    def test_vehicle_tools_includes_actualizar_datos_expediente(self) -> None:
        from agent.modes.submodos._shared import _get_vehicle_tools

        names = {t.name for t in _get_vehicle_tools()}
        assert "actualizar_datos_expediente" in names

    def test_vehicle_tools_does_NOT_include_confirmar_fotos_elemento(self) -> None:
        from agent.modes.submodos._shared import _get_vehicle_tools

        names = {t.name for t in _get_vehicle_tools()}
        assert "confirmar_fotos_elemento" not in names

    @pytest.mark.asyncio
    async def test_collect_vehicle_node_propagates_transition(self) -> None:
        import agent.modes.expediente_nodes as mod

        state = _make_expediente_state(expediente_sub_mode="collect_vehicle")

        async def fake_invoke(initial_state, **kw):
            return {
                "ai_response": "Datos vehículo guardados",
                "exit_reason": "response",
                "tools_called": ["actualizar_datos_expediente"],
                "pending_state_updates": {
                    "mode_context": {"expediente_sub_mode": "collect_workshop"}
                },
            }

        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(side_effect=fake_invoke)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=ToolLoopResult(graph=mock_compiled, recursion_limit=35)):
            result = await mod.collect_vehicle_node(state)

        from langgraph.types import Command

        assert isinstance(result, Command)
        update = result.update or {}
        new_sub_mode = update.get("expediente_sub_mode") or (
            update.get("mode_context", {}).get("expediente_sub_mode")
        )
        assert new_sub_mode == "collect_workshop"


class TestCollectWorkshopToolSet:
    """T-13: collect_workshop_node uses _get_workshop_tools."""

    def test_workshop_tools_includes_actualizar_datos_taller(self) -> None:
        from agent.modes.submodos._shared import _get_workshop_tools

        names = {t.name for t in _get_workshop_tools()}
        assert "actualizar_datos_taller" in names

    def test_workshop_tools_does_NOT_include_finalizar_expediente(self) -> None:
        from agent.modes.submodos._shared import _get_workshop_tools

        names = {t.name for t in _get_workshop_tools()}
        assert "finalizar_expediente" not in names

    @pytest.mark.asyncio
    async def test_collect_workshop_node_propagates_transition(self) -> None:
        import agent.modes.expediente_nodes as mod

        state = _make_expediente_state(expediente_sub_mode="collect_workshop")

        async def fake_invoke(initial_state, **kw):
            return {
                "ai_response": "Datos taller guardados",
                "exit_reason": "response",
                "tools_called": ["actualizar_datos_taller"],
                "pending_state_updates": {
                    "mode_context": {"expediente_sub_mode": "review_summary"}
                },
            }

        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(side_effect=fake_invoke)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=ToolLoopResult(graph=mock_compiled, recursion_limit=35)):
            result = await mod.collect_workshop_node(state)

        from langgraph.types import Command

        assert isinstance(result, Command)
        update = result.update or {}
        new_sub_mode = update.get("expediente_sub_mode") or (
            update.get("mode_context", {}).get("expediente_sub_mode")
        )
        assert new_sub_mode == "review_summary"


class TestReviewSummaryToolSet:
    """T-13: review_summary_node uses _get_review_tools."""

    def test_review_tools_includes_finalizar_expediente(self) -> None:
        from agent.modes.submodos._shared import _get_review_tools

        names = {t.name for t in _get_review_tools()}
        assert "finalizar_expediente" in names

    def test_review_tools_includes_editar_expediente(self) -> None:
        from agent.modes.submodos._shared import _get_review_tools

        names = {t.name for t in _get_review_tools()}
        assert "editar_expediente" in names

    def test_review_tools_does_NOT_include_guardar_datos_elemento(self) -> None:
        from agent.modes.submodos._shared import _get_review_tools

        names = {t.name for t in _get_review_tools()}
        assert "guardar_datos_elemento" not in names

    @pytest.mark.asyncio
    async def test_review_summary_node_returns_update_with_ai_response(self) -> None:
        import agent.modes.expediente_nodes as mod

        state = _make_expediente_state(expediente_sub_mode="review_summary")

        async def fake_invoke(initial_state, **kw):
            return {
                "ai_response": "Resumen del expediente",
                "exit_reason": "response",
                "tools_called": [],
                "pending_state_updates": {},
            }

        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(side_effect=fake_invoke)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=ToolLoopResult(graph=mock_compiled, recursion_limit=35)):
            result = await mod.review_summary_node(state)

        from langgraph.types import Command

        assert isinstance(result, Command)
        update = result.update or {}
        assert update.get("ai_response") == "Resumen del expediente"


# ---------------------------------------------------------------------------
# T-16: Config forwarding and error handling
# ---------------------------------------------------------------------------


class TestConfigForwarding:
    """T-16: RunnableConfig forwarded to subgraph.ainvoke, max_iterations = 10."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("node_name,sub_mode", list(zip(NODE_NAMES, SUB_MODES)))
    async def test_max_iterations_is_10(self, node_name: str, sub_mode: str) -> None:
        """ModeLoopConfig.max_iterations must be 10 for all expediente nodes."""
        import agent.modes.expediente_nodes as mod

        node_fn = getattr(mod, node_name)
        state = _make_expediente_state(expediente_sub_mode=sub_mode)

        captured_configs = []

        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(return_value={
            "ai_response": "ok",
            "exit_reason": "response",
            "tools_called": [],
            "pending_state_updates": {},
        })

        def capture_and_return(config):
            captured_configs.append(config)
            return ToolLoopResult(graph=mock_compiled, recursion_limit=35)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", side_effect=capture_and_return):
            await node_fn(state)

        assert len(captured_configs) == 1
        assert captured_configs[0].max_iterations == 10, (
            f"{node_name} must use max_iterations=10, "
            f"got {captured_configs[0].max_iterations}"
        )


class TestGraphRecursionErrorHandling:
    """T-16/T-17: GraphRecursionError is caught and returns safe state."""

    @pytest.mark.asyncio
    async def test_recursion_error_returns_safe_command(self) -> None:
        """
        When subgraph.ainvoke raises GraphRecursionError, node must catch it
        and return Command(goto=END, update={"exit_reason": "max_iterations", "ai_response": ""}).
        """
        import agent.modes.expediente_nodes as mod

        state = _make_expediente_state(expediente_sub_mode="collect_element_data")

        # GraphRecursionError may be in langgraph.errors in some versions
        # We simulate it by using a generic exception class that mimics its name
        class FakeGraphRecursionError(Exception):
            pass

        async def fake_invoke_raises(initial_state, **kw):
            raise FakeGraphRecursionError("recursion limit exceeded")

        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(side_effect=fake_invoke_raises)

        # Patch GraphRecursionError in expediente_nodes module
        with (
            patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=ToolLoopResult(graph=mock_compiled, recursion_limit=35)),
            patch("agent.modes.expediente_nodes.GraphRecursionError", FakeGraphRecursionError),
        ):
            result = await mod.collect_element_data_node(state)

        from langgraph.types import Command

        assert isinstance(result, Command)
        assert result.update is not None
        assert result.update.get("exit_reason") == "max_iterations"
        assert result.update.get("ai_response") == ""

    @pytest.mark.asyncio
    async def test_generic_exception_returns_safe_command(self) -> None:
        """
        When subgraph.ainvoke raises an unexpected exception, node returns
        a safe Command without propagating.
        """
        import agent.modes.expediente_nodes as mod

        state = _make_expediente_state(expediente_sub_mode="collect_base_docs")

        async def fake_invoke_raises(initial_state, **kw):
            raise ValueError("unexpected internal error")

        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(side_effect=fake_invoke_raises)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=ToolLoopResult(graph=mock_compiled, recursion_limit=35)):
            result = await mod.collect_base_docs_node(state)

        from langgraph.types import Command

        assert isinstance(result, Command), "Node must not propagate exceptions"
        assert result.update is not None


# ---------------------------------------------------------------------------
# T-20: entry_router re-dispatches correctly after sub_mode write
# ---------------------------------------------------------------------------


class TestEntryRouterRedispatch:
    """T-20: entry_router routes to the correct node based on expediente_sub_mode."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sub_mode,expected_node,extra_state", [
        ("collect_element_data", "collect_element_data_node", None),
        ("collect_base_docs", "collect_base_docs_node", None),
        ("collect_personal", "collect_personal_node", None),
        # WS6: flexible routing requires prior collections to be done
        ("collect_vehicle", "collect_vehicle_node", {"personal_collected": True}),
        ("collect_workshop", "collect_workshop_node", {"personal_collected": True, "vehicle_collected": True}),
        ("review_summary", "review_summary_node", None),
    ])
    async def test_entry_router_routes_to_correct_node(
        self, sub_mode: str, expected_node: str, extra_state: dict | None
    ) -> None:
        """After a sub_mode write, entry_router routes to the correct node."""
        from agent.modes.expediente_nodes import entry_router

        state = _make_expediente_state(expediente_sub_mode=sub_mode, extra=extra_state)
        result = await entry_router(state)

        from langgraph.types import Command

        assert isinstance(result, Command)
        assert result.goto == expected_node, (
            f"entry_router with sub_mode={sub_mode!r} should route to "
            f"{expected_node!r}, got {result.goto!r}"
        )

    @pytest.mark.asyncio
    async def test_entry_router_unknown_sub_mode_uses_flexible_default(self) -> None:
        """WS6: unknown sub_mode enters flexible routing, defaults to collect_personal_node."""
        from agent.modes.expediente_nodes import entry_router

        state = _make_expediente_state(expediente_sub_mode="invalid_sub_mode")
        result = await entry_router(state)

        from langgraph.types import Command

        assert isinstance(result, Command)
        # WS6 flexible routing: unknown sub_modes default to personal (first in order)
        assert result.goto == "collect_personal_node"

    @pytest.mark.asyncio
    async def test_entry_router_empty_sub_mode_uses_flexible_default(self) -> None:
        """WS6: empty sub_mode enters flexible routing, defaults to collect_personal_node."""
        from agent.modes.expediente_nodes import entry_router

        state = _make_expediente_state(expediente_sub_mode="")
        result = await entry_router(state)

        from langgraph.types import Command

        assert isinstance(result, Command)
        # WS6 flexible routing: empty sub_mode defaults to personal (first in order)
        assert result.goto == "collect_personal_node"

    @pytest.mark.asyncio
    async def test_second_invocation_routes_after_transition(self) -> None:
        """
        After collect_element_data_node writes expediente_sub_mode='collect_base_docs',
        a second invocation via entry_router routes to collect_base_docs_node.
        """
        import agent.modes.expediente_nodes as mod

        # First invocation: collect_element_data — simulate completion
        state_initial = _make_expediente_state(expediente_sub_mode="collect_element_data")

        async def fake_invoke_transition(initial_state, **kw):
            return {
                "ai_response": "Elementos completados, pasamos a documentación base.",
                "exit_reason": "response",
                "tools_called": ["completar_elemento_actual"],
                "pending_state_updates": {
                    "mode_context": {
                        "expediente_sub_mode": "collect_base_docs",
                    }
                },
            }

        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(side_effect=fake_invoke_transition)

        with patch("agent.modes.expediente_nodes.build_mode_tool_loop", return_value=ToolLoopResult(graph=mock_compiled, recursion_limit=35)):
            result1 = await mod.collect_element_data_node(state_initial)

        # result1.update contains the new sub_mode — simulate it being applied to state
        from langgraph.types import Command

        assert isinstance(result1, Command)
        update = result1.update or {}

        # Build updated state (as if LangGraph applied the Command update)
        state_after = dict(state_initial)
        state_after.update(update)
        # If expediente_sub_mode was written to mode_context, extract it
        if "mode_context" in update:
            state_after.update(update["mode_context"])
        if "expediente_sub_mode" not in state_after or state_after["expediente_sub_mode"] == "collect_element_data":
            # The update may carry the key directly
            state_after["expediente_sub_mode"] = "collect_base_docs"

        # Second invocation via entry_router
        result2 = await mod.entry_router(state_after)

        assert isinstance(result2, Command)
        assert result2.goto == "collect_base_docs_node", (
            f"After transition, entry_router should route to collect_base_docs_node, "
            f"got {result2.goto!r}"
        )
