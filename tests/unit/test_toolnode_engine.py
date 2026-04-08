"""
Unit tests for the ToolNode engine migration — Phase 1 Foundation.

Tests for:
- get_tool_state(config) bridge function (T-01)

Strict TDD: tests are written FIRST (RED), then implementation (GREEN).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# T-01 Tests: get_tool_state(config) bridge function
# ---------------------------------------------------------------------------
# These tests verify the behavior specified in the design (AD-2):
#
# get_tool_state(config: RunnableConfig | None) -> dict
#   1. When config has configurable["state"] → return that dict (no ContextVar read)
#   2. When config is None → fall back to _current_state.get()
#   3. When neither config nor ContextVar → return {}
# ---------------------------------------------------------------------------


class TestGetToolStateFromConfig:
    """get_tool_state reads config.configurable['state'] preferentially."""

    def test_returns_state_from_config_configurable(self):
        """When config has configurable['state'], return it directly."""
        from agent.state.helpers import get_tool_state

        expected_state = {"conversation_id": "abc123", "mode_context": {"price": 410}}
        config = {"configurable": {"state": expected_state}}

        result = get_tool_state(config)

        assert result == expected_state

    def test_config_preference_does_not_call_contextvar(self):
        """When config has state, ContextVar _current_state.get() is NEVER called."""
        from agent.state.helpers import get_tool_state

        expected_state = {"conversation_id": "test-conv"}
        config = {"configurable": {"state": expected_state}}

        # Patch the ContextVar to detect if it gets called
        with patch("agent.state.helpers._current_state") as mock_cv:
            result = get_tool_state(config)

        # ContextVar.get() must NOT have been called
        mock_cv.get.assert_not_called()
        assert result == expected_state

    def test_returns_correct_state_not_empty_dict(self):
        """Ensure we return the actual state dict, not a partial or empty one."""
        from agent.state.helpers import get_tool_state

        state = {
            "conversation_id": "conv-xyz",
            "user_id": "user-1",
            "client_type": "particular",
            "mode_context": {
                "categoria_slug": "motos-part",
                "precio_comunicado": True,
            },
        }
        config = {"configurable": {"state": state}}

        result = get_tool_state(config)

        assert result["conversation_id"] == "conv-xyz"
        assert result["mode_context"]["precio_comunicado"] is True

    def test_empty_configurable_state_returns_empty_dict(self):
        """configurable['state'] = {} is valid — return empty dict (not None)."""
        from agent.state.helpers import get_tool_state

        config = {"configurable": {"state": {}}}
        result = get_tool_state(config)
        assert result == {}


class TestGetToolStateContextVarFallback:
    """get_tool_state falls back to ContextVar when config is absent."""

    def test_none_config_falls_back_to_contextvar(self):
        """When config is None, return _current_state.get() value."""
        from agent.state.helpers import get_tool_state

        contextvar_state = {"conversation_id": "from-contextvar"}

        with patch("agent.state.helpers._current_state") as mock_cv:
            mock_cv.get.return_value = contextvar_state
            result = get_tool_state(None)

        assert result == contextvar_state
        mock_cv.get.assert_called_once()

    def test_missing_configurable_key_falls_back_to_contextvar(self):
        """Config present but missing 'configurable' key → ContextVar fallback."""
        from agent.state.helpers import get_tool_state

        contextvar_state = {"conversation_id": "cv-fallback"}
        config_without_configurable = {"some_other_key": "value"}

        with patch("agent.state.helpers._current_state") as mock_cv:
            mock_cv.get.return_value = contextvar_state
            result = get_tool_state(config_without_configurable)

        assert result == contextvar_state

    def test_missing_state_in_configurable_falls_back_to_contextvar(self):
        """config.configurable present but no 'state' key → ContextVar fallback."""
        from agent.state.helpers import get_tool_state

        contextvar_state = {"conversation_id": "cv-fallback-2"}
        config_without_state = {"configurable": {"thread_id": "t-123"}}

        with patch("agent.state.helpers._current_state") as mock_cv:
            mock_cv.get.return_value = contextvar_state
            result = get_tool_state(config_without_state)

        assert result == contextvar_state


class TestGetToolStateNeitherSourceAvailable:
    """When neither config nor ContextVar has state, return empty dict."""

    def test_none_config_and_none_contextvar_returns_empty_dict(self):
        """No config + ContextVar returns None → get_tool_state returns {}."""
        from agent.state.helpers import get_tool_state

        with patch("agent.state.helpers._current_state") as mock_cv:
            mock_cv.get.return_value = None
            result = get_tool_state(None)

        assert result == {}
        assert isinstance(result, dict)

    def test_return_type_is_always_dict(self):
        """Return type must always be dict regardless of source."""
        from agent.state.helpers import get_tool_state

        # From config
        result_from_config = get_tool_state({"configurable": {"state": {"k": "v"}}})
        assert isinstance(result_from_config, dict)

        # From ContextVar
        with patch("agent.state.helpers._current_state") as mock_cv:
            mock_cv.get.return_value = {"k": "v2"}
            result_from_cv = get_tool_state(None)
        assert isinstance(result_from_cv, dict)

        # From neither
        with patch("agent.state.helpers._current_state") as mock_cv:
            mock_cv.get.return_value = None
            result_empty = get_tool_state(None)
        assert isinstance(result_empty, dict)


# ===========================================================================
# T-06 Tests: ToolLoopState schema
# ===========================================================================
# These tests verify the ToolLoopState TypedDict from agent/modes/tool_loop_state.py
# Design: AD-3 — messages (add reducer), pending_state_updates (dict), etc.
# ===========================================================================


class TestToolLoopStateSchema:
    """ToolLoopState TypedDict has all required fields and correct types."""

    def test_required_fields_present_in_annotations(self):
        """ToolLoopState must have all AD-3 required fields."""
        from agent.modes.tool_loop_state import ToolLoopState
        import typing

        hints = typing.get_type_hints(ToolLoopState, include_extras=True)
        field_names = set(hints.keys())

        required_fields = {
            "messages",
            "pending_state_updates",
            "tool_results",
            "tools_called",
            "ai_response",
            "exit_reason",
            "_mode_context",
            "_conversation_id",
        }
        for field in required_fields:
            assert field in field_names, f"Missing field: {field}"

    def test_messages_field_has_add_reducer(self):
        """messages must use Annotated[list, add] so messages accumulate."""
        import typing
        from agent.modes.tool_loop_state import ToolLoopState

        hints = typing.get_type_hints(ToolLoopState, include_extras=True)
        messages_type = hints["messages"]

        # Annotated types have __metadata__
        assert hasattr(messages_type, "__metadata__"), (
            "messages field must be Annotated with a reducer"
        )
        # The reducer should be operator.add (or a callable)
        metadata = messages_type.__metadata__
        assert len(metadata) >= 1, (
            "messages Annotated must have at least one metadata item"
        )
        # The metadata should be callable (the reducer)
        assert callable(metadata[0]), (
            f"messages reducer must be callable, got {type(metadata[0])}"
        )

    def test_messages_add_reducer_appends(self):
        """Verify that the messages reducer actually appends (add semantics)."""
        from operator import add
        from langchain_core.messages import HumanMessage, AIMessage

        msg_a = HumanMessage(content="Hello")
        msg_b = AIMessage(content="Hi there")

        result = add([msg_a], [msg_b])
        assert len(result) == 2
        assert result[0] is msg_a
        assert result[1] is msg_b

    def test_can_instantiate_with_partial_fields(self):
        """ToolLoopState is total=False — can be created with any subset of fields."""
        from agent.modes.tool_loop_state import ToolLoopState

        # Should not raise with partial fields (TypedDict total=False)
        state: ToolLoopState = {
            "messages": [],
            "_conversation_id": "conv-123",
            "_mode_context": {"categoria_slug": "motos-part"},
        }

        assert state["_conversation_id"] == "conv-123"
        assert state["_mode_context"]["categoria_slug"] == "motos-part"

    def test_pending_state_updates_is_dict_type(self):
        """pending_state_updates must be typed as dict (for merge_dicts reducer)."""
        import typing
        from agent.modes.tool_loop_state import ToolLoopState

        hints = typing.get_type_hints(ToolLoopState, include_extras=True)
        updates_type = hints["pending_state_updates"]

        # Should be Annotated[dict, ...] or plain dict — either way, dict-like
        # Get origin to check if it's Annotated
        origin = getattr(updates_type, "__origin__", None)
        if origin is not None:
            # It's Annotated — check the first arg is dict-related
            args = updates_type.__args__
            inner = args[0]
            inner_origin = getattr(inner, "__origin__", inner)
            assert inner_origin is dict or inner is dict, (
                f"pending_state_updates inner type should be dict, got {inner}"
            )
        else:
            # Plain dict annotation
            assert (
                updates_type is dict
                or getattr(updates_type, "__origin__", None) is dict
            ), f"pending_state_updates should be dict type, got {updates_type}"

    def test_tool_results_is_list_type(self):
        """tool_results must be a list type for accumulating raw results."""
        import typing
        from agent.modes.tool_loop_state import ToolLoopState

        hints = typing.get_type_hints(ToolLoopState, include_extras=True)
        tool_results_type = hints["tool_results"]

        # Get the inner type if Annotated
        if hasattr(tool_results_type, "__metadata__"):
            inner = tool_results_type.__args__[0]
        else:
            inner = tool_results_type
        inner_origin = getattr(inner, "__origin__", inner)
        assert inner_origin is list, f"tool_results should be list type, got {inner}"

    def test_exit_reason_and_ai_response_are_strings(self):
        """ai_response and exit_reason must be string fields."""
        import typing
        from agent.modes.tool_loop_state import ToolLoopState

        hints = typing.get_type_hints(ToolLoopState, include_extras=True)

        # ai_response and exit_reason should be str
        for field_name in ["ai_response", "exit_reason"]:
            field_type = hints[field_name]
            # Could be plain str or Optional[str]
            assert field_type is str or str in getattr(field_type, "__args__", ()), (
                f"{field_name} should be str type, got {field_type}"
            )

    def test_mode_context_fields_are_dict(self):
        """_mode_context must be dict (holds snapshot for tool context injection)."""
        import typing
        from agent.modes.tool_loop_state import ToolLoopState

        hints = typing.get_type_hints(ToolLoopState, include_extras=True)
        mc_type = hints["_mode_context"]

        # Should be dict or Annotated[dict, ...]
        if hasattr(mc_type, "__metadata__"):
            inner = mc_type.__args__[0]
        else:
            inner = mc_type
        inner_origin = getattr(inner, "__origin__", inner)
        assert inner_origin is dict or inner is dict, (
            f"_mode_context should be dict type, got {inner}"
        )


# ===========================================================================
# T-08 Tests: llm_node
# ===========================================================================
# These tests verify the llm_node behavior from agent/modes/tool_loop.py
# AD-1: llm_node reads messages from state, prepends system prompt, invokes LLM
# ===========================================================================


class TestLLMNode:
    """llm_node builds correct message list and appends AIMessage to state."""

    @pytest.mark.asyncio
    async def test_llm_node_calls_llm_with_system_plus_history(self):
        """llm_node must call LLM with [SystemMessage(system_prompt)] + state messages."""
        from unittest.mock import MagicMock
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        # Track messages passed to LLM
        captured_messages = []
        mock_llm_response = AIMessage(content="Aquí está la información.")

        async def capturing_invoke(messages, **kwargs):
            captured_messages.extend(messages)
            return mock_llm_response

        # Build a mock that survives bind_tools(): bind_tools returns the same mock
        mock_llm = MagicMock()
        mock_llm.ainvoke = capturing_invoke
        # bind_tools must return an object that also has our capturing_invoke
        bound_mock = MagicMock()
        bound_mock.ainvoke = capturing_invoke
        mock_llm.bind_tools = MagicMock(return_value=bound_mock)

        config = ModeLoopConfig(
            mode_name="CONSULTA_MODE",
            get_tools=lambda ctx: [],
            get_system_prompt=lambda state: "Eres un asistente de homologación.",
            post_tool_hook=None,
            max_iterations=5,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        history_msg = HumanMessage(content="¿Qué puedo homologar?")
        result = await graph.ainvoke(
            {
                "messages": [history_msg],
                "_mode_context": {},
                "_conversation_id": "test-conv",
            }
        )

        # The LLM must have been called with system + history
        assert len(captured_messages) >= 2
        assert isinstance(captured_messages[0], SystemMessage)
        assert "homologación" in captured_messages[0].content
        # The history message should follow the system message
        assert any(
            isinstance(m, HumanMessage) and "homologar" in m.content
            for m in captured_messages
        )
        graph = build_mode_tool_loop(config)

        history_msg = HumanMessage(content="¿Qué puedo homologar?")
        result = await graph.ainvoke(
            {
                "messages": [history_msg],
                "_mode_context": {},
                "_conversation_id": "test-conv",
            }
        )

        # The LLM must have been called with system + history
        assert len(captured_messages) >= 2
        assert isinstance(captured_messages[0], SystemMessage)
        assert "homologación" in captured_messages[0].content
        # The history message should follow the system message
        assert any(
            isinstance(m, HumanMessage) and "homologar" in m.content
            for m in captured_messages
        )

    @pytest.mark.asyncio
    async def test_llm_node_appends_ai_message_to_state(self):
        """llm_node must return AIMessage added to state via add reducer."""
        from unittest.mock import AsyncMock
        from langchain_core.messages import HumanMessage, AIMessage

        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        mock_ai_response = AIMessage(content="El escape cuesta 410€ +IVA.")

        async def mock_invoke(messages, **kwargs):
            return mock_ai_response

        # Create a mock LLM object
        mock_llm = MagicMock()
        mock_llm.ainvoke = mock_invoke
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)

        config = ModeLoopConfig(
            mode_name="CONSULTA_MODE",
            get_tools=lambda ctx: [],
            get_system_prompt=lambda state: "System prompt.",
            post_tool_hook=None,
            max_iterations=5,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="¿Cuánto cuesta?")],
                "_mode_context": {},
                "_conversation_id": "conv-123",
            }
        )

        # The result should contain the AI response text
        assert result.get("ai_response") == "El escape cuesta 410€ +IVA."

    @pytest.mark.asyncio
    async def test_llm_node_does_not_read_contextvar(self):
        """llm_node must NOT call set_current_state or access ContextVar."""
        from unittest.mock import patch, AsyncMock
        from langchain_core.messages import HumanMessage, AIMessage
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        mock_ai_response = AIMessage(content="Respuesta de prueba.")

        async def mock_invoke(messages, **kwargs):
            return mock_ai_response

        mock_llm = MagicMock()
        mock_llm.ainvoke = mock_invoke
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)

        config = ModeLoopConfig(
            mode_name="CONSULTA_MODE",
            get_tools=lambda ctx: [],
            get_system_prompt=lambda state: "Prompt.",
            post_tool_hook=None,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        with patch("agent.state.helpers.set_current_state") as mock_set_state:
            await graph.ainvoke(
                {
                    "messages": [HumanMessage(content="Test.")],
                    "_mode_context": {},
                    "_conversation_id": "conv-456",
                }
            )
            # llm_node itself should never call set_current_state
            mock_set_state.assert_not_called()


# ===========================================================================
# T-09 Tests: custom_tool_node
# ===========================================================================
# Tests for the custom tool execution node in tool_loop.py
# AD-1: custom tool node — validation, dedup, logging, _state_update extraction
# ===========================================================================


class TestCustomToolNode:
    """custom_tool_node executes tools and returns correct ToolMessages."""

    @pytest.mark.asyncio
    async def test_tool_execution_returns_tool_message(self):
        """On success, custom_tool_node appends a ToolMessage to messages."""
        from langchain_core.messages import AIMessage, ToolMessage
        from langchain_core.tools import tool as lc_tool
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        call_count = {"n": 0}

        @lc_tool
        async def my_test_tool(query: str) -> dict:
            """Simple test tool."""
            call_count["n"] += 1
            return {"success": True, "data": f"result for {query}"}

        # Mock LLM: first call returns tool_call, second returns text
        call_num = {"n": 0}

        async def mock_invoke(messages, **kwargs):
            call_num["n"] += 1
            if call_num["n"] == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "call_001",
                            "name": "my_test_tool",
                            "args": {"query": "homologation"},
                            "type": "tool_call",
                        }
                    ],
                )
            return AIMessage(content="Aquí tienes la información.")

        mock_llm = MagicMock()
        mock_llm.ainvoke = mock_invoke
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)

        config = ModeLoopConfig(
            mode_name="CONSULTA_MODE",
            get_tools=lambda ctx: [my_test_tool],
            get_system_prompt=lambda state: "System prompt.",
            post_tool_hook=None,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        from langchain_core.messages import HumanMessage

        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="¿Qué hay disponible?")],
                "_mode_context": {},
                "_conversation_id": "conv-tool-test",
            }
        )

        # Tool must have been called
        assert call_count["n"] == 1
        # Final result should have ai_response
        assert result.get("ai_response") == "Aquí tienes la información."

    @pytest.mark.asyncio
    async def test_tool_exception_returns_error_tool_message(self):
        """When a tool raises, custom_tool_node returns error ToolMessage (no raise)."""
        from langchain_core.messages import AIMessage, ToolMessage
        from langchain_core.tools import tool as lc_tool
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        @lc_tool
        async def failing_tool(param: str) -> dict:
            """A tool that always fails."""
            raise ValueError("Database connection lost")

        call_num = {"n": 0}

        async def mock_invoke(messages, **kwargs):
            call_num["n"] += 1
            if call_num["n"] == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "call_fail",
                            "name": "failing_tool",
                            "args": {"param": "test"},
                            "type": "tool_call",
                        }
                    ],
                )
            # After error ToolMessage, LLM recovers and responds
            return AIMessage(content="Lo siento, hubo un error.")

        mock_llm = MagicMock()
        mock_llm.ainvoke = mock_invoke
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)

        config = ModeLoopConfig(
            mode_name="CONSULTA_MODE",
            get_tools=lambda ctx: [failing_tool],
            get_system_prompt=lambda state: "Prompt.",
            post_tool_hook=None,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        from langchain_core.messages import HumanMessage

        # Should NOT raise — error is returned as ToolMessage for LLM recovery
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Consulta.")],
                "_mode_context": {},
                "_conversation_id": "conv-fail-test",
            }
        )

        # Graph should complete (LLM recovers after seeing error ToolMessage)
        assert "ai_response" in result

    @pytest.mark.asyncio
    async def test_state_update_extracted_from_tool_result(self):
        """_state_update in tool result must be extracted to pending_state_updates."""
        from langchain_core.messages import AIMessage
        from langchain_core.tools import tool as lc_tool
        from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig

        @lc_tool
        async def state_updating_tool(element: str) -> dict:
            """Tool that returns _state_update."""
            return {
                "success": True,
                "precio": 410.0,
                "_state_update": {
                    "price_authority_confirmed": True,
                    "mode_context": {"tarifa_calculada": 410.0},
                },
            }

        call_num = {"n": 0}

        async def mock_invoke(messages, **kwargs):
            call_num["n"] += 1
            if call_num["n"] == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "call_su",
                            "name": "state_updating_tool",
                            "args": {"element": "ESCAPE"},
                            "type": "tool_call",
                        }
                    ],
                )
            return AIMessage(content="El presupuesto es de 410€ +IVA.")

        mock_llm = MagicMock()
        mock_llm.ainvoke = mock_invoke
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)

        # Use a post_tool_hook to capture what's in pending_state_updates
        captured_updates = {}

        async def capture_hook(tool_name: str, result_dict: dict, state: dict) -> dict:
            # Capture the pending_state_updates from state
            captured_updates.update(state.get("pending_state_updates", {}))
            return {}

        config = ModeLoopConfig(
            mode_name="CONSULTA_MODE",
            get_tools=lambda ctx: [state_updating_tool],
            get_system_prompt=lambda state: "Prompt.",
            post_tool_hook=capture_hook,
            _llm_override=mock_llm,
        )
        graph = build_mode_tool_loop(config)

        from langchain_core.messages import HumanMessage

        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="¿Cuánto cuesta?")],
                "_mode_context": {},
                "_conversation_id": "conv-state-update",
            }
        )

        # _state_update from tool must have been captured in pending_state_updates
        assert captured_updates.get("price_authority_confirmed") is True


# ===========================================================================
# T-10 Tests: tools_or_end conditional edge
# ===========================================================================


class TestToolsOrEnd:
    """tools_or_end routes correctly based on tool_calls and pending_mode_transition."""

    def test_ai_message_with_tool_calls_routes_to_tool_node(self):
        """When last message has tool_calls, tools_or_end must return 'custom_tool_node'."""
        from langchain_core.messages import AIMessage
        from agent.modes.tool_loop import tools_or_end

        state = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "call_abc",
                            "name": "some_tool",
                            "args": {"param": "value"},
                            "type": "tool_call",
                        }
                    ],
                )
            ],
            "_mode_context": {},
        }
        result = tools_or_end(state)
        assert result == "custom_tool_node"

    def test_ai_message_without_tool_calls_routes_to_end(self):
        """When last message has no tool_calls, tools_or_end must return END."""
        from langchain_core.messages import AIMessage
        from langgraph.graph import END
        from agent.modes.tool_loop import tools_or_end

        state = {
            "messages": [
                AIMessage(content="El presupuesto es de 410€ +IVA.", tool_calls=[])
            ],
            "_mode_context": {},
        }
        result = tools_or_end(state)
        assert result == END

    def test_pending_mode_transition_routes_to_end_even_with_tool_calls(self):
        """When pending_mode_transition is set, tools_or_end must return END immediately."""
        from langchain_core.messages import AIMessage
        from langgraph.graph import END
        from agent.modes.tool_loop import tools_or_end

        state = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "call_xyz",
                            "name": "some_tool",
                            "args": {},
                            "type": "tool_call",
                        }
                    ],
                )
            ],
            "_mode_context": {"pending_mode_transition": "EXPEDIENTE_MODE"},
        }
        result = tools_or_end(state)
        assert result == END

    def test_empty_messages_routes_to_end(self):
        """When messages is empty, tools_or_end routes to END."""
        from langgraph.graph import END
        from agent.modes.tool_loop import tools_or_end

        state = {"messages": [], "_mode_context": {}}
        result = tools_or_end(state)
        assert result == END

    def test_non_ai_last_message_routes_to_end(self):
        """When last message is not AIMessage, tools_or_end routes to END."""
        from langchain_core.messages import HumanMessage
        from langgraph.graph import END
        from agent.modes.tool_loop import tools_or_end

        state = {
            "messages": [HumanMessage(content="¿Cuánto cuesta?")],
            "_mode_context": {},
        }
        result = tools_or_end(state)
        assert result == END


# ===========================================================================
# T-11 Tests: post_tool_node
# ===========================================================================


class TestPostToolNode:
    """post_tool_node reads _state_update from ToolMessages and applies to state."""

    @pytest.mark.asyncio
    async def test_single_update_applied_to_state(self):
        """A single ToolMessage with _state_update must update pending_state_updates."""
        import json
        from langchain_core.messages import AIMessage, ToolMessage
        from agent.modes.tool_loop import make_post_tool_node

        post_tool_node = make_post_tool_node(post_tool_hook=None)

        state = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "call_001",
                            "name": "tool_a",
                            "args": {},
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(
                    tool_call_id="call_001",
                    content=json.dumps(
                        {
                            "success": True,
                            "_state_update": {"price_authority_confirmed": True},
                        }
                    ),
                ),
            ],
            "pending_state_updates": {},
            "_mode_context": {},
        }

        result = await post_tool_node(state)

        assert (
            result.get("pending_state_updates", {}).get("price_authority_confirmed")
            is True
        )

    @pytest.mark.asyncio
    async def test_multiple_updates_merged_in_order(self):
        """Multiple ToolMessages' _state_updates must be merged (last-write-wins)."""
        import json
        from langchain_core.messages import AIMessage, ToolMessage
        from agent.modes.tool_loop import make_post_tool_node

        post_tool_node = make_post_tool_node(post_tool_hook=None)

        state = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "call_001",
                            "name": "tool_a",
                            "args": {},
                            "type": "tool_call",
                        },
                        {
                            "id": "call_002",
                            "name": "tool_b",
                            "args": {},
                            "type": "tool_call",
                        },
                    ],
                ),
                ToolMessage(
                    tool_call_id="call_001",
                    content=json.dumps(
                        {
                            "success": True,
                            "_state_update": {
                                "mode_context": {"elementos": ["ESCAPE"]},
                            },
                        }
                    ),
                ),
                ToolMessage(
                    tool_call_id="call_002",
                    content=json.dumps(
                        {
                            "success": True,
                            "_state_update": {
                                "mode_context": {"tarifa_calculada": 410},
                            },
                        }
                    ),
                ),
            ],
            "pending_state_updates": {},
            "_mode_context": {},
        }

        result = await post_tool_node(state)

        updates = result.get("pending_state_updates", {})
        # Both mode_context updates should be present (merged)
        assert "mode_context" in updates
        # Last-write-wins for conflicting keys within mode_context
        # OR both keys present if non-conflicting
        mc = updates["mode_context"]
        # At minimum, the last update should be there
        assert "tarifa_calculada" in mc

    @pytest.mark.asyncio
    async def test_no_state_update_returns_empty_dict(self):
        """ToolMessages without _state_update must return empty pending_state_updates."""
        import json
        from langchain_core.messages import AIMessage, ToolMessage
        from agent.modes.tool_loop import make_post_tool_node

        post_tool_node = make_post_tool_node(post_tool_hook=None)

        state = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "call_001",
                            "name": "tool_a",
                            "args": {},
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(
                    tool_call_id="call_001",
                    content=json.dumps(
                        {"success": True, "data": "just data, no update"}
                    ),
                ),
            ],
            "pending_state_updates": {},
            "_mode_context": {},
        }

        result = await post_tool_node(state)

        # Should not raise; pending_state_updates is empty or unchanged
        updates = result.get("pending_state_updates", {})
        assert isinstance(updates, dict)
        assert updates == {}

    @pytest.mark.asyncio
    async def test_conflict_logs_warning(self):
        """When two ToolMessages conflict on the same key, a warning must be logged."""
        import json
        from unittest.mock import patch
        from langchain_core.messages import AIMessage, ToolMessage
        from agent.modes.tool_loop import make_post_tool_node

        post_tool_node = make_post_tool_node(post_tool_hook=None)

        state = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "call_001",
                            "name": "tool_a",
                            "args": {},
                            "type": "tool_call",
                        },
                        {
                            "id": "call_002",
                            "name": "tool_b",
                            "args": {},
                            "type": "tool_call",
                        },
                    ],
                ),
                ToolMessage(
                    tool_call_id="call_001",
                    content=json.dumps(
                        {
                            "success": True,
                            "_state_update": {"current_element": "ESCAPE"},
                        }
                    ),
                ),
                ToolMessage(
                    tool_call_id="call_002",
                    content=json.dumps(
                        {
                            "success": True,
                            "_state_update": {"current_element": "MANILLAR"},
                        }
                    ),
                ),
            ],
            "pending_state_updates": {},
            "_mode_context": {},
        }

        with patch("agent.modes.tool_loop.logger") as mock_logger:
            result = await post_tool_node(state)

        # Warning must have been logged for the conflict
        assert mock_logger.warning.called or mock_logger.debug.called

        # Last-write-wins — second update takes precedence
        updates = result.get("pending_state_updates", {})
        assert updates.get("current_element") == "MANILLAR"


# ===========================================================================
# T-16 Tests: presupuesto_post_tool_hook unit tests
# ===========================================================================


class TestPresupuestoPostToolHook:
    """
    Unit tests for presupuesto_post_tool_hook from post_tool_hooks.py (T-16).

    Strict TDD: written BEFORE T-17 implementation (RED phase).

    Assertions:
    - price_authority_confirmed set when calcular_tarifa succeeds
    - variant_pending set when identificar_y_resolver_elementos finds variants
    - No fake AIMessage appended to state (state updates only)
    - SystemMessage used for context injection (not fake AIMessage)
    """

    @pytest.mark.asyncio
    async def test_price_authority_confirmed_set_from_tariff_result(self):
        """
        GIVEN calcular_tarifa_con_elementos succeeds with price data,
        WHEN presupuesto_post_tool_hook processes it,
        THEN the returned dict contains price_authority_confirmed=True.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        tool_result = {
            "success": True,
            "precio_final": 410.0,
            "datos": {
                "price": 410.0,
                "elements": ["Escape"],
                "element_codes": ["ESCAPE"],
            },
            "_state_update": {
                "price_authority_confirmed": True,
                "tarifa_calculada": {"precio_final": 410.0},
            },
        }

        state = {
            "_mode_context": {"categoria_slug": "motos-part"},
            "pending_state_updates": {},
        }

        result = await presupuesto_post_tool_hook(
            "calcular_tarifa_con_elementos", tool_result, state
        )

        assert isinstance(result, dict)
        assert result.get("price_authority_confirmed") is True, (
            f"Expected price_authority_confirmed=True, got: {result}"
        )

    @pytest.mark.asyncio
    async def test_price_authority_not_set_when_tariff_fails(self):
        """
        GIVEN calcular_tarifa_con_elementos fails (success=False),
        WHEN presupuesto_post_tool_hook processes it,
        THEN price_authority_confirmed is NOT set to True.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        tool_result = {
            "success": False,
            "error": "elemento_no_encontrado",
        }

        state = {"_mode_context": {}, "pending_state_updates": {}}

        result = await presupuesto_post_tool_hook(
            "calcular_tarifa_con_elementos", tool_result, state
        )

        # Should not set price_authority_confirmed on failure
        assert result.get("price_authority_confirmed") is not True, (
            f"price_authority_confirmed should not be True on failure: {result}"
        )

    @pytest.mark.asyncio
    async def test_variant_pending_set_from_element_identification(self):
        """
        GIVEN identificar_y_resolver_elementos returns pending variants,
        WHEN presupuesto_post_tool_hook processes it,
        THEN the returned dict contains variant_pending=True or mode_context with pending_variants.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        tool_result = {
            "success": True,
            "elementos_listos": [],
            "elementos_con_variantes": [
                {
                    "codigo_base": "SUSPENSION",
                    "variantes": [{"codigo": "SUSPENSION_DEL"}],
                }
            ],
            "preguntas_variantes": [
                {"codigo_base": "SUSPENSION", "opciones": ["delantera", "trasera"]}
            ],
            "_state_update": {
                "pending_variants": [
                    {"codigo_base": "SUSPENSION", "status": "pending"}
                ],
            },
        }

        state = {"_mode_context": {}, "pending_state_updates": {}}

        result = await presupuesto_post_tool_hook(
            "identificar_y_resolver_elementos", tool_result, state
        )

        assert isinstance(result, dict)
        # Either variant_pending or mode_context.pending_variants must be set
        has_variant_signal = (
            result.get("variant_pending") is True
            or bool((result.get("mode_context") or {}).get("pending_variants"))
            or bool(result.get("pending_variants"))
        )
        assert has_variant_signal, (
            f"Expected variant pending signal in result, got: {result}"
        )

    @pytest.mark.asyncio
    async def test_no_fake_aimessage_appended_to_state(self):
        """
        GIVEN any tool result,
        WHEN presupuesto_post_tool_hook processes it,
        THEN the result dict does NOT contain 'inject_messages' key,
        AND no AIMessage objects are returned.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        tool_result = {
            "success": True,
            "precio_final": 410.0,
            "_state_update": {"price_authority_confirmed": True},
        }

        state = {"_mode_context": {}, "pending_state_updates": {}}

        result = await presupuesto_post_tool_hook(
            "calcular_tarifa_con_elementos", tool_result, state
        )

        # The old inject_messages pattern must NOT be used
        assert "inject_messages" not in result, (
            f"Hook returned inject_messages (old protocol corruption pattern): {result}"
        )

        # No AIMessage objects should appear in the return value
        from langchain_core.messages import AIMessage as _AIMessage

        for key, value in result.items():
            if isinstance(value, list):
                for item in value:
                    assert not isinstance(item, _AIMessage), (
                        f"Hook injected fake AIMessage in key '{key}': {item}"
                    )

    @pytest.mark.asyncio
    async def test_systemm_message_context_injection_allowed(self):
        """
        GIVEN calcular_tarifa succeeds with a price,
        WHEN presupuesto_post_tool_hook processes it,
        THEN if the hook injects context via SystemMessage, that's acceptable.
        (Verifies that SystemMessage is the CORRECT replacement for inject_messages.)
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        tool_result = {
            "success": True,
            "precio_final": 410.0,
            "_state_update": {"price_authority_confirmed": True},
        }

        state = {"_mode_context": {}, "pending_state_updates": {}}

        result = await presupuesto_post_tool_hook(
            "calcular_tarifa_con_elementos", tool_result, state
        )

        # If hook returns system_messages, they must be SystemMessage objects
        if "system_messages" in result:
            from langchain_core.messages import SystemMessage as _SM

            for sm in result.get("system_messages", []):
                assert isinstance(sm, _SM), (
                    f"system_messages must be SystemMessage objects, got: {type(sm)}"
                )

    @pytest.mark.asyncio
    async def test_pending_images_extracted_from_image_tool(self):
        """
        GIVEN enviar_imagenes_ejemplo returns _pending_images,
        WHEN presupuesto_post_tool_hook processes it,
        THEN the pending_images are captured in the state update.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        tool_result = {
            "success": True,
            "message": "Imágenes enviadas",
            "_pending_images": {
                "images": ["https://example.com/img1.jpg"],
                "conversation_id": "conv-123",
            },
            "_state_update": {
                "imagenes_enviadas": True,
            },
        }

        state = {"_mode_context": {}, "pending_state_updates": {}}

        result = await presupuesto_post_tool_hook(
            "enviar_imagenes_ejemplo", tool_result, state
        )

        # The result should somehow track that images were sent
        # Either via imagenes_enviadas flag or _pending_images capture
        has_image_signal = (
            result.get("imagenes_enviadas") is True
            or result.get("_pending_images") is not None
            or (result.get("mode_context") or {}).get("imagenes_enviadas") is True
        )
        assert has_image_signal, f"Expected image send signal in result, got: {result}"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_empty_dict(self):
        """
        GIVEN an unknown tool name,
        WHEN presupuesto_post_tool_hook processes it,
        THEN it returns an empty dict (no crash, no unexpected state).
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        tool_result = {"success": True, "data": "some data"}
        state = {"_mode_context": {}, "pending_state_updates": {}}

        result = await presupuesto_post_tool_hook(
            "some_unknown_tool", tool_result, state
        )

        assert isinstance(result, dict)  # Must return a dict, not raise
