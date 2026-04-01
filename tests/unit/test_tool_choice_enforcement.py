"""
Tests for fix-tool-choice-enforcement — Phase 1: RED tests.

Covers:
  1.1 — _get_llm(tools, tool_choice=None) calls bind_tools(tools) with NO extra kwarg  [PASS baseline]
  1.2 — _get_llm(tools, tool_choice="required") passes tool_choice to bind_tools       [FAIL — not impl]
  1.3 — presupuesto: pending variants → _get_llm called with tool_choice="required"    [FAIL — not impl]
  1.4 — presupuesto: no pending variants → _get_llm NOT called with tool_choice        [PASS/FAIL TBD]
  1.5 — loop_engine: COLLECT_PERSONAL, iteration=0 (kickoff), no tool calls → NO reprompt [PASS baseline]
  1.6 — loop_engine: COLLECT_PERSONAL, iteration=1, no tool calls → reprompt injected   [FAIL — not impl]
  1.7 — loop_engine: COLLECT_VEHICLE, iteration=1, no tool calls → reprompt injected    [FAIL — not impl]
  1.8 — presupuesto_mode.md contains "B y B" example for multi-variant resolution       [FAIL — not impl]

All unit tests — no DB, no Redis, no real LLM required.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap (matches existing test files pattern)
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PRESUPUESTO_PROMPT_PATH = (
    _PROJECT_ROOT / "agent" / "prompts" / "modes" / "presupuesto_mode.md"
)


def _make_mock_tool(name: str) -> MagicMock:
    """Create a minimal mock LangChain-compatible tool."""
    t = MagicMock()
    t.name = name
    return t


def _make_tools() -> list:
    return [
        _make_mock_tool("identificar_y_resolver_elementos"),
        _make_mock_tool("calcular_tarifa_con_elementos"),
        _make_mock_tool("escalar_a_humano"),
    ]


# ===========================================================================
# GROUP 1 — base_mode._get_llm() tool_choice threading
# ===========================================================================


class TestGetLlmToolChoice:
    """
    Tests for BaseModeNode._get_llm() tool_choice parameter threading.

    Baseline (1.1) should PASS now.
    Production code change (1.2) should FAIL now.
    """

    def _make_base_node(self):
        """Instantiate a concrete BaseModeNode subclass for testing."""
        from agent.modes.base_mode import BaseModeNode

        class _TestNode(BaseModeNode):
            def __init__(self):
                super().__init__("TEST_MODE")

            async def _process_message(self, message, state):
                return {"ai_response": "ok"}

            def get_tools(self, mode_context=None):
                return []

        return _TestNode()

    # -----------------------------------------------------------------------
    # 1.1 — baseline: tool_choice=None → bind_tools called WITHOUT extra kwargs
    # -----------------------------------------------------------------------

    def test_1_1_get_llm_no_tool_choice_calls_bind_tools_without_kwarg(self):
        """
        1.1 — BASELINE (should PASS already).

        When _get_llm(tools) is called without tool_choice,
        bind_tools must be called as bind_tools(tools) with NO tool_choice kwarg.

        This is the current production behavior — we lock it as a regression guard.
        """
        node = self._make_base_node()
        tools = _make_tools()

        mock_bind_tools_result = MagicMock()
        mock_llm_instance = MagicMock()
        mock_llm_instance.bind_tools = MagicMock(return_value=mock_bind_tools_result)

        with patch(
            "agent.modes.base_mode.BaseModeNode._get_llm",
            wraps=node._get_llm,
        ):
            with patch("langchain_openai.ChatOpenAI") as mock_chat_cls:
                mock_chat_cls.return_value = mock_llm_instance

                # Call without tool_choice (current signature)
                node._get_llm(tools)

        # bind_tools must have been called with tools as the only positional arg
        mock_llm_instance.bind_tools.assert_called_once()
        call_args, call_kwargs = mock_llm_instance.bind_tools.call_args
        assert call_args[0] is tools, "bind_tools first arg must be the tools list"
        assert "tool_choice" not in call_kwargs, (
            "bind_tools must NOT receive tool_choice when _get_llm called without it. "
            f"Got kwargs: {call_kwargs}"
        )

    # -----------------------------------------------------------------------
    # 1.2 — _get_llm accepts tool_choice and passes it to bind_tools
    # -----------------------------------------------------------------------

    def test_1_2_get_llm_signature_accepts_tool_choice_param(self):
        """
        1.2 — SIGNATURE CHECK (should PASS — already implemented as of Phase 2).

        _get_llm() must accept a 'tool_choice' parameter with default None.

        Production code at base_mode.py line 343:
            def _get_llm(self, tools: list, tool_choice: str | None = None)

        This test locks the signature contract so it can't be accidentally removed.
        It PASSES because Phase 2 (task 2.1) was already implemented.
        """
        import inspect

        node = self._make_base_node()

        sig = inspect.signature(node._get_llm)
        params = list(sig.parameters.keys())

        assert "tool_choice" in params, (
            f"_get_llm() must accept a 'tool_choice' parameter. "
            f"Current signature parameters: {params}. "
            f"This param is required for G1 enforcement (pending_variants)."
        )

        # Also verify it defaults to None (backward-compatible)
        tool_choice_param = sig.parameters.get("tool_choice")
        assert tool_choice_param is not None
        assert tool_choice_param.default is None, (
            f"tool_choice must default to None for backward compat. "
            f"Got default: {tool_choice_param.default!r}"
        )

    def test_1_2b_get_llm_tool_choice_required_forwarded_to_bind_tools(self):
        """
        1.2b — When tool_choice="required" is passed, bind_tools receives it.

        This test verifies the implementation: when tool_choice="required" is passed
        to _get_llm(), it must be forwarded to bind_tools() as a kwarg.

        PASSES because Phase 2 (task 2.1) was already implemented with bind_kwargs.
        """
        node = self._make_base_node()
        tools = _make_tools()

        mock_bind_tools_result = MagicMock()
        mock_llm_instance = MagicMock()
        mock_llm_instance.bind_tools = MagicMock(return_value=mock_bind_tools_result)

        with patch("shared.config.get_settings") as mock_settings:
            mock_s = MagicMock()
            mock_s.LLM_MODEL = "test-model"
            mock_s.OPENROUTER_API_KEY = "test-key"
            mock_s.SITE_URL = "http://test"
            mock_s.SITE_NAME = "test"
            mock_s.LLM_REQUEST_TIMEOUT_SECONDS = 30
            mock_s.LLM_MAX_RETRIES = 1
            mock_settings.return_value = mock_s

            with patch("langchain_openai.ChatOpenAI") as mock_chat_cls:
                mock_chat_cls.return_value = mock_llm_instance
                node._get_llm(tools, tool_choice="required")

        # bind_tools must receive tool_choice="required"
        mock_llm_instance.bind_tools.assert_called_once()
        call_args, call_kwargs = mock_llm_instance.bind_tools.call_args
        assert call_args[0] is tools, "bind_tools first arg must be the tools list"
        assert call_kwargs.get("tool_choice") == "required", (
            "bind_tools must receive tool_choice='required' when passed to _get_llm. "
            f"Got kwargs: {call_kwargs}"
        )


# ===========================================================================
# GROUP 2 — presupuesto_mode: pending_variants → tool_choice routing
# ===========================================================================


class TestPresupuestoToolChoice:
    """
    Tests for PresupuestoModeNode using tool_choice="required"
    when pending_variants has unresolved entries.

    Tests 1.3 and 1.4.
    """

    def _make_presupuesto_node(self):
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        return PresupuestoModeNode()

    # -----------------------------------------------------------------------
    # 1.3 — pending variants → _get_llm called with tool_choice="required"
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_1_3_pending_variants_causes_tool_choice_required(self):
        """
        1.3 — NEW BEHAVIOR (should FAIL until production code is changed).

        When mode_context has pending_variants with at least one unresolved entry,
        the call to self._get_llm() in _process_message MUST include
        tool_choice="required".

        This tests the decision at presupuesto_mode.py line ~481:
            _has_unresolved = any(v.get("status") != "resolved" for v in ...)
            llm = self._get_llm(tools, tool_choice="required" if _has_unresolved else None)

        Currently FAILS because that code hasn't been written yet:
        - Current code: llm = self._get_llm(tools)  (no tool_choice kwarg)
        - Required code: llm = self._get_llm(tools, tool_choice=...)

        We spy on _get_llm via patch.object to capture its actual call signature
        from within _process_message execution.
        """
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        node = PresupuestoModeNode()
        captured_calls: list[dict] = []

        # Intercept _get_llm and record kwargs WITHOUT replacing the node's method
        # We use patch.object to spy on the class method
        original_get_llm = node._get_llm

        def _capturing_get_llm(tools, **kwargs):
            captured_calls.append({"tools": tools, "kwargs": dict(kwargs)})
            # Return a mock LLM so _process_message can continue
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "Tengo variantes pendientes..."
            mock_response.tool_calls = None
            mock_response.usage_metadata = None
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            return mock_llm

        node._get_llm = _capturing_get_llm  # type: ignore[method-assign]

        # State with pending variants
        state = {
            "conversation_id": "test-1-3",
            "user_message": "delantera",
            "messages": [],
            "mode_context": {
                "pending_variants": [
                    {
                        "codigo_base": "SUSPENSION",
                        "pregunta": "¿Delantera o trasera?",
                        "opciones": ["Delantera", "Trasera"],
                        "status": "pending",
                    }
                ],
                "categoria_slug": "motos-part",
            },
            "user_id": "user-123",
            "user_phone": "+34600000001",
            "retry_state": None,
        }

        # Patch out heavy dependencies so _process_message can run
        # Note: get_settings is imported INSIDE _get_llm function body,
        # so we patch shared.config.get_settings (not agent.modes.*.get_settings)
        with (
            patch(
                "agent.modes.presupuesto_mode.assemble_system_prompt",
                return_value="[MOCK PROMPT]",
            ),
            patch(
                "agent.modes.presupuesto_mode.format_messages_for_llm", return_value=[]
            ),
            patch("agent.modes.presupuesto_mode.set_current_state"),
            patch("agent.modes.presupuesto_mode.clear_current_state"),
            patch("agent.modes.presupuesto_mode.set_current_state_for_image_tools"),
            patch("agent.modes.presupuesto_mode.clear_image_tools_state"),
            patch("shared.config.get_settings") as mock_settings,
        ):
            mock_settings_obj = MagicMock()
            mock_settings_obj.LLM_MODEL = "test-model"
            mock_settings_obj.OPENROUTER_API_KEY = "test-key"
            mock_settings_obj.SITE_URL = "http://test"
            mock_settings_obj.SITE_NAME = "test"
            mock_settings_obj.LLM_REQUEST_TIMEOUT_SECONDS = 30
            mock_settings_obj.LLM_MAX_RETRIES = 1
            mock_settings_obj.ENABLE_LATENCY_GATING = False
            mock_settings_obj.MAX_TOOL_ITERATIONS_PRESUPUESTO = 10
            mock_settings_obj.AGENT_TURN_TIMEOUT_SECONDS = 60
            mock_settings_obj.ENABLE_STATE_CONTRACT_ENFORCEMENT = False
            mock_settings_obj.ENABLE_LLM_VARIANT_INTERPRETATION = False
            mock_settings.return_value = mock_settings_obj

            await node._process_message("delantera", state)

        # Assert _get_llm was called
        assert len(captured_calls) >= 1, (
            f"_get_llm was not called during _process_message. "
            f"This is unexpected — check presupuesto_mode._process_message flow."
        )

        # The FIRST call to _get_llm must include tool_choice="required"
        # because pending_variants has an unresolved entry (line ~514 in presupuesto_mode.py).
        first_call = captured_calls[0]
        assert first_call["kwargs"].get("tool_choice") == "required", (
            f"_get_llm must be called with tool_choice='required' when pending_variants "
            f"has unresolved entries. "
            f"Got kwargs={first_call['kwargs']}. "
            f"Expected: llm = self._get_llm(tools, tool_choice='required' if _has_unresolved else None)"
        )

    # -----------------------------------------------------------------------
    # 1.4 — no pending variants → _get_llm called WITHOUT tool_choice
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_1_4_no_pending_variants_no_tool_choice(self):
        """
        1.4 — COMPLEMENTARY BEHAVIOR (locks the negative branch).

        When mode_context has NO unresolved pending_variants,
        _get_llm must NOT be called with tool_choice="required"
        (i.e., tool_choice must be None or absent).

        This test may PASS or FAIL depending on implementation:
        - Before Phase 3 (3.1): calls _get_llm(tools) — no kwarg — PASS
        - After Phase 3 (3.1): calls _get_llm(tools, tool_choice=None) — PASS

        Either way the negative branch must NOT have tool_choice="required".
        """
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        node = PresupuestoModeNode()
        captured_calls: list[dict] = []

        def _capturing_get_llm(tools, **kwargs):
            captured_calls.append({"tools": tools, "kwargs": dict(kwargs)})
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "Tienes algo que quieres homologar?"
            mock_response.tool_calls = None
            mock_response.usage_metadata = None
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            return mock_llm

        node._get_llm = _capturing_get_llm  # type: ignore[method-assign]

        state = {
            "conversation_id": "test-1-4",
            "user_message": "quiero homologar el escape",
            "messages": [],
            "mode_context": {
                "pending_variants": [],  # empty = no pending variants
                "categoria_slug": "motos-part",
            },
            "user_id": "user-123",
            "user_phone": "+34600000001",
            "retry_state": None,
        }

        with (
            patch(
                "agent.modes.presupuesto_mode.assemble_system_prompt",
                return_value="[MOCK PROMPT]",
            ),
            patch(
                "agent.modes.presupuesto_mode.format_messages_for_llm", return_value=[]
            ),
            patch("agent.modes.presupuesto_mode.set_current_state"),
            patch("agent.modes.presupuesto_mode.clear_current_state"),
            patch("agent.modes.presupuesto_mode.set_current_state_for_image_tools"),
            patch("agent.modes.presupuesto_mode.clear_image_tools_state"),
            patch("shared.config.get_settings") as mock_settings,
        ):
            mock_settings_obj = MagicMock()
            mock_settings_obj.LLM_MODEL = "test-model"
            mock_settings_obj.OPENROUTER_API_KEY = "test-key"
            mock_settings_obj.SITE_URL = "http://test"
            mock_settings_obj.SITE_NAME = "test"
            mock_settings_obj.LLM_REQUEST_TIMEOUT_SECONDS = 30
            mock_settings_obj.LLM_MAX_RETRIES = 1
            mock_settings_obj.ENABLE_LATENCY_GATING = False
            mock_settings_obj.MAX_TOOL_ITERATIONS_PRESUPUESTO = 10
            mock_settings_obj.AGENT_TURN_TIMEOUT_SECONDS = 60
            mock_settings_obj.ENABLE_STATE_CONTRACT_ENFORCEMENT = False
            mock_settings_obj.ENABLE_LLM_VARIANT_INTERPRETATION = False
            mock_settings.return_value = mock_settings_obj

            await node._process_message("quiero homologar el escape", state)

        assert len(captured_calls) >= 1, "_get_llm must have been called"

        first_call = captured_calls[0]
        tool_choice_arg = first_call["kwargs"].get("tool_choice")
        assert tool_choice_arg != "required", (
            f"_get_llm must NOT be called with tool_choice='required' when "
            f"pending_variants is empty. Got tool_choice={tool_choice_arg!r}"
        )

    @pytest.mark.asyncio
    async def test_1_4_all_resolved_variants_no_tool_choice(self):
        """
        1.4 variant — All variants have status='resolved'.

        _get_llm must still NOT be called with tool_choice="required".
        """
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        node = PresupuestoModeNode()
        captured_calls: list[dict] = []

        def _capturing_get_llm(tools, **kwargs):
            captured_calls.append({"tools": tools, "kwargs": dict(kwargs)})
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "ok"
            mock_response.tool_calls = None
            mock_response.usage_metadata = None
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            return mock_llm

        node._get_llm = _capturing_get_llm  # type: ignore[method-assign]

        state = {
            "conversation_id": "test-1-4b",
            "user_message": "vale",
            "messages": [],
            "mode_context": {
                "pending_variants": [
                    {"codigo_base": "PLACA_SOLAR", "status": "resolved"},
                    {"codigo_base": "TOLDO_LAT", "status": "resolved"},
                ],
                "categoria_slug": "motos-part",
            },
            "user_id": "user-123",
            "user_phone": "+34600000001",
            "retry_state": None,
        }

        with (
            patch(
                "agent.modes.presupuesto_mode.assemble_system_prompt",
                return_value="[MOCK PROMPT]",
            ),
            patch(
                "agent.modes.presupuesto_mode.format_messages_for_llm", return_value=[]
            ),
            patch("agent.modes.presupuesto_mode.set_current_state"),
            patch("agent.modes.presupuesto_mode.clear_current_state"),
            patch("agent.modes.presupuesto_mode.set_current_state_for_image_tools"),
            patch("agent.modes.presupuesto_mode.clear_image_tools_state"),
            patch("shared.config.get_settings") as mock_settings,
        ):
            mock_settings_obj = MagicMock()
            mock_settings_obj.LLM_MODEL = "test-model"
            mock_settings_obj.OPENROUTER_API_KEY = "test-key"
            mock_settings_obj.SITE_URL = "http://test"
            mock_settings_obj.SITE_NAME = "test"
            mock_settings_obj.LLM_REQUEST_TIMEOUT_SECONDS = 30
            mock_settings_obj.LLM_MAX_RETRIES = 1
            mock_settings_obj.ENABLE_LATENCY_GATING = False
            mock_settings_obj.MAX_TOOL_ITERATIONS_PRESUPUESTO = 10
            mock_settings_obj.AGENT_TURN_TIMEOUT_SECONDS = 60
            mock_settings_obj.ENABLE_STATE_CONTRACT_ENFORCEMENT = False
            mock_settings_obj.ENABLE_LLM_VARIANT_INTERPRETATION = False
            mock_settings.return_value = mock_settings_obj

            await node._process_message("vale", state)

        assert len(captured_calls) >= 1, "_get_llm must have been called"
        first_call = captured_calls[0]
        assert first_call["kwargs"].get("tool_choice") != "required", (
            "All variants resolved → must NOT pass tool_choice='required'. "
            f"Got kwargs={first_call['kwargs']}"
        )


# ===========================================================================
# GROUP 3 — loop_engine: data-collection guard (reprompt injection)
# ===========================================================================


class TestLoopEngineDataCollectionGuard:
    """
    Tests for the post-loop data-collection guard in ExpedienteLoopEngine.

    When sub_mode in {COLLECT_PERSONAL, COLLECT_VEHICLE} AND iteration > 0
    AND LLM returns no tool calls → reprompt must be injected.

    Tests 1.5 (PASS baseline), 1.6, 1.7 (FAIL — not impl).
    """

    @pytest.fixture
    def mock_parent(self) -> MagicMock:
        """
        Mock parent (ExpedienteModeNode) matching the pattern from
        tests/agent/modes/test_expediente_loop_engine.py.
        """
        parent = MagicMock()

        parent._execute_and_log_tool = AsyncMock(return_value='{"success": true}')
        parent._invoke_with_fallback = AsyncMock()
        parent._track_token_usage = AsyncMock()
        parent._validate_response_constraints = AsyncMock(return_value=(True, None))
        parent._guard_photo_completion_intent = AsyncMock(return_value=False)
        parent._is_validation_error = MagicMock(return_value=(False, None))
        parent._handle_validation_retry = MagicMock(return_value=(False, {}))
        parent._get_element_state_svc = MagicMock(return_value=None)

        # LLM mock
        _mock_llm = MagicMock()
        _mock_ai_response = MagicMock()
        _mock_ai_response.content = "Hola, ¿me puedes dar tu nombre?"
        _mock_ai_response.tool_calls = None  # No tool calls!
        _mock_ai_response.usage_metadata = None
        _mock_llm.ainvoke = AsyncMock(return_value=_mock_ai_response)
        parent._get_llm = MagicMock(return_value=_mock_llm)

        parent._logger = MagicMock()
        parent._fallback = MagicMock()
        parent._policy = MagicMock()
        parent._tool_dedup_cache = None
        parent.mode_name = "EXPEDIENTE_MODE"

        return parent

    @pytest.fixture
    def mock_state(self) -> dict:
        return {
            "conversation_id": "test-guard-001",
            "messages": [],
            "incoming_attachments": [],
            "mode_context": {},
            "retry_state": None,
        }

    # -----------------------------------------------------------------------
    # 1.5 — COLLECT_PERSONAL, iteration=0 (kickoff), no tool calls → NO reprompt
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_1_5_collect_personal_kickoff_no_reprompt(
        self, mock_parent: MagicMock, mock_state: dict
    ):
        """
        1.5 — BASELINE (should PASS already).

        In COLLECT_PERSONAL at iteration=0 (kickoff turn), the LLM may send
        a question without calling tools. No reprompt should be injected.

        This is a deliberate exception: the kickoff question itself is a valid
        no-tool response.
        """
        from agent.modes.submodos.loop_engine import ExpedienteLoopEngine

        engine = ExpedienteLoopEngine(parent=mock_parent)

        mode_context = {
            "expediente_sub_mode": "collect_personal",
            "case_id": "abc-123",
            "element_codes": [],
        }

        # LLM returns text-only (no tool calls) — kickoff question
        mock_response = MagicMock()
        mock_response.content = "¡Hola! Voy a necesitar algunos datos personales. ¿Me puedes dar tu nombre completo?"
        mock_response.tool_calls = None
        mock_response.usage_metadata = None
        mock_parent._get_llm.return_value.ainvoke = AsyncMock(
            return_value=mock_response
        )

        result = await engine.run(
            message="quiero abrir el expediente",
            state=mock_state,
            mode_context=mode_context,
            tools=[],
            sub_mode_name="COLLECT_PERSONAL",
        )

        # The response should go through without reprompt injection
        assert result.get("ai_response"), "Should have an ai_response"

        # Verify the LLM was called EXACTLY ONCE (no retry loop injected)
        llm_invoke_call_count = mock_parent._get_llm.return_value.ainvoke.call_count
        assert llm_invoke_call_count == 1, (
            f"On kickoff (iteration=0) with no tools, LLM must be called exactly once "
            f"(no reprompt retry). Got {llm_invoke_call_count} calls."
        )

    # -----------------------------------------------------------------------
    # 1.6 — COLLECT_PERSONAL, iteration=1 (data turn), no tool calls → reprompt
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_1_6_collect_personal_data_turn_no_tools_injects_reprompt(
        self, mock_parent: MagicMock, mock_state: dict
    ):
        """
        1.6 — NEW BEHAVIOR (should FAIL until production code is changed).

        In COLLECT_PERSONAL after the kickoff (iteration > 0), when the LLM
        returns no tool calls AND the user has provided personal data,
        a system reprompt MUST be injected and the loop MUST retry.

        The reprompt should instruct the LLM to call actualizar_datos_expediente.

        Currently FAILS because the data-collection guard hasn't been implemented
        in loop_engine.py (inside the `if not tool_calls:` block after line 407).
        """
        from agent.modes.submodos.loop_engine import ExpedienteLoopEngine

        engine = ExpedienteLoopEngine(parent=mock_parent)

        mode_context = {
            "expediente_sub_mode": "collect_personal",
            "case_id": "abc-123",
            "element_codes": [],
            # kickoff_question_asked=True implies we already did kickoff
        }

        # First LLM call (iteration=0): kickoff question (no tool calls) — allowed
        # Second LLM call (iteration=1): user sends data, LLM replies with text only
        #   → should trigger reprompt
        # Third LLM call: retry after reprompt → this time we make it call a tool

        from agent.tools.case_tools import actualizar_datos_expediente as _adte

        mock_tool = _make_mock_tool("actualizar_datos_expediente")

        kickoff_response = MagicMock()
        kickoff_response.content = "¿Cuál es tu nombre completo?"
        kickoff_response.tool_calls = None
        kickoff_response.usage_metadata = None

        data_turn_response_no_tools = MagicMock()
        data_turn_response_no_tools.content = "Gracias, te anoto."
        data_turn_response_no_tools.tool_calls = None
        data_turn_response_no_tools.usage_metadata = None

        tool_call_response = MagicMock()
        tool_call_response.content = ""
        tool_call_response.tool_calls = [
            {
                "id": "tc_001",
                "name": "actualizar_datos_expediente",
                "args": {"field": "nombre", "value": "Juan García"},
            }
        ]
        tool_call_response.usage_metadata = None

        final_response = MagicMock()
        final_response.content = "Perfecto, he guardado tu nombre: Juan García."
        final_response.tool_calls = None
        final_response.usage_metadata = None

        mock_parent._get_llm.return_value.ainvoke = AsyncMock(
            side_effect=[
                kickoff_response,  # iteration=0: kickoff (allowed no-tool)
                data_turn_response_no_tools,  # iteration=1: no tools → reprompt
                tool_call_response,  # iteration=2: after reprompt → tool call
                final_response,  # iteration=3: final text response
            ]
        )

        # Mock tool execution
        mock_parent._execute_and_log_tool = AsyncMock(
            return_value='{"success": true, "message": "Datos guardados"}'
        )

        # Run with user message that contains personal data (triggers data-turn guard)
        result = await engine.run(
            message="Me llamo Juan García, mi DNI es 12345678A",
            state=mock_state,
            mode_context=mode_context,
            tools=[mock_tool],
            sub_mode_name="COLLECT_PERSONAL",
        )

        # The LLM must have been called MORE than once due to reprompt
        llm_invoke_call_count = mock_parent._get_llm.return_value.ainvoke.call_count
        assert llm_invoke_call_count >= 2, (
            f"When LLM skips tool call on data turn (iteration>0) in COLLECT_PERSONAL, "
            f"a reprompt must be injected and the loop must retry. "
            f"Expected >= 2 LLM calls, got {llm_invoke_call_count}."
        )

        # Verify the reprompt contains instruction to use actualizar_datos_expediente
        # We check this by inspecting the ainvoke calls — the second call should
        # include a system message with the reprompt
        all_invocations = mock_parent._get_llm.return_value.ainvoke.call_args_list
        # At least one call after the first should have a system message about tools
        found_reprompt = False
        for inv in all_invocations[1:]:  # skip first kickoff call
            messages_passed = inv[0][0]  # first positional arg = messages list
            if isinstance(messages_passed, list):
                for msg in messages_passed:
                    if (
                        isinstance(msg, dict)
                        and msg.get("role") == "system"
                        and "actualizar_datos_expediente" in msg.get("content", "")
                    ):
                        found_reprompt = True
                        break
            if found_reprompt:
                break

        assert found_reprompt, (
            "After no-tool response on data turn, a system reprompt containing "
            "'actualizar_datos_expediente' must be injected into llm_messages. "
            f"Inspected {len(all_invocations)} LLM invocations — reprompt not found."
        )

    # -----------------------------------------------------------------------
    # 1.7 — COLLECT_VEHICLE, iteration=1, no tool calls → reprompt injected
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_1_7_collect_vehicle_data_turn_no_tools_injects_reprompt(
        self, mock_parent: MagicMock, mock_state: dict
    ):
        """
        1.7 — NEW BEHAVIOR (should FAIL until production code is changed).

        Same as 1.6 but for COLLECT_VEHICLE sub-mode.

        When the LLM skips calling actualizar_datos_expediente on a data turn
        in COLLECT_VEHICLE, the guard must inject a reprompt.
        """
        from agent.modes.submodos.loop_engine import ExpedienteLoopEngine

        engine = ExpedienteLoopEngine(parent=mock_parent)

        mode_context = {
            "expediente_sub_mode": "collect_vehicle",
            "case_id": "abc-456",
            "element_codes": [],
        }

        mock_tool = _make_mock_tool("actualizar_datos_expediente")

        kickoff_response = MagicMock()
        kickoff_response.content = "¿Cuál es la marca de tu vehículo?"
        kickoff_response.tool_calls = None
        kickoff_response.usage_metadata = None

        data_turn_response_no_tools = MagicMock()
        data_turn_response_no_tools.content = "Bien, una Honda CBR."
        data_turn_response_no_tools.tool_calls = None
        data_turn_response_no_tools.usage_metadata = None

        tool_call_response = MagicMock()
        tool_call_response.content = ""
        tool_call_response.tool_calls = [
            {
                "id": "tc_002",
                "name": "actualizar_datos_expediente",
                "args": {"field": "marca", "value": "Honda"},
            }
        ]
        tool_call_response.usage_metadata = None

        final_response = MagicMock()
        final_response.content = "He guardado: Honda CBR."
        final_response.tool_calls = None
        final_response.usage_metadata = None

        mock_parent._get_llm.return_value.ainvoke = AsyncMock(
            side_effect=[
                kickoff_response,
                data_turn_response_no_tools,  # should trigger reprompt
                tool_call_response,
                final_response,
            ]
        )

        mock_parent._execute_and_log_tool = AsyncMock(
            return_value='{"success": true, "message": "Datos guardados"}'
        )

        result = await engine.run(
            message="Es una Honda CBR 600, matrícula 1234ABC",
            state=mock_state,
            mode_context=mode_context,
            tools=[mock_tool],
            sub_mode_name="COLLECT_VEHICLE",
        )

        llm_invoke_call_count = mock_parent._get_llm.return_value.ainvoke.call_count
        assert llm_invoke_call_count >= 2, (
            f"COLLECT_VEHICLE: reprompt must be injected when LLM skips tool on "
            f"data turn (iteration>0). Expected >= 2 LLM calls, got "
            f"{llm_invoke_call_count}."
        )

        # Verify reprompt message was injected for COLLECT_VEHICLE
        all_invocations = mock_parent._get_llm.return_value.ainvoke.call_args_list
        found_reprompt = False
        for inv in all_invocations[1:]:
            messages_passed = inv[0][0]
            if isinstance(messages_passed, list):
                for msg in messages_passed:
                    if (
                        isinstance(msg, dict)
                        and msg.get("role") == "system"
                        and "actualizar_datos_expediente" in msg.get("content", "")
                    ):
                        found_reprompt = True
                        break
            if found_reprompt:
                break

        assert found_reprompt, (
            "COLLECT_VEHICLE: after no-tool response on data turn, a system reprompt "
            "containing 'actualizar_datos_expediente' must be injected into llm_messages. "
            f"Inspected {len(all_invocations)} LLM invocations — reprompt not found."
        )


# ===========================================================================
# GROUP 4 — Prompt lint: presupuesto_mode.md "B y B" example
# ===========================================================================


class TestPresupuestomodePromptLint:
    """
    Test 1.8 — presupuesto_mode.md must contain a "B y B" multi-variant example.

    The "B y B" example demonstrates sequential resolution of two pending variants
    in a single turn (calling seleccionar_variante_por_respuesta twice).

    Currently FAILS because the example hasn't been added to the prompt yet.
    """

    def _read_presupuesto_prompt(self) -> str:
        assert _PRESUPUESTO_PROMPT_PATH.exists(), (
            f"presupuesto_mode.md not found at {_PRESUPUESTO_PROMPT_PATH}"
        )
        return _PRESUPUESTO_PROMPT_PATH.read_text(encoding="utf-8")

    # -----------------------------------------------------------------------
    # 1.8 — prompt must contain "B y B" example (multi-variant resolution)
    # -----------------------------------------------------------------------

    def test_1_8_presupuesto_mode_md_contains_byb_example(self):
        """
        1.8 — NEW CONTENT (should FAIL until prompt is updated).

        presupuesto_mode.md must contain an explicit "B y B" example showing
        that when the user answers for multiple pending variants in one message
        (e.g. "B y B" meaning variant B for first question AND variant B for second),
        the agent MUST call seleccionar_variante_por_respuesta TWICE — once per
        pending variant.

        This test proves the example is present in the prompt so the LLM sees
        the correct pattern during inference.

        FAILS because the "B y B" example doesn't exist in the prompt yet
        (Phase 5 task 5.1 will add it).
        """
        content = self._read_presupuesto_prompt()
        assert "B y B" in content, (
            "presupuesto_mode.md must contain a 'B y B' multi-variant example "
            "showing sequential calls to seleccionar_variante_por_respuesta for "
            "each pending variant. This example is required so the LLM learns "
            "to resolve multiple variants in a single turn. "
            f"Prompt path: {_PRESUPUESTO_PROMPT_PATH}"
        )

    def test_1_8_byb_example_includes_dual_seleccionar_calls(self):
        """
        1.8 complementary — The "B y B" section must reference two separate
        seleccionar_variante_por_respuesta calls to make the pattern explicit.

        FAILS until prompt is updated.
        """
        content = self._read_presupuesto_prompt()

        # The section around "B y B" should show two tool calls
        # We check by counting occurrences of seleccionar_variante_por_respuesta
        # in the context of the multi-variant example
        by_b_pos = content.find("B y B")
        if by_b_pos == -1:
            pytest.fail(
                "presupuesto_mode.md does not contain 'B y B' example yet. "
                "Add the multi-variant resolution example in Phase 5."
            )

        # Extract a window around "B y B" to verify dual calls
        window = content[max(0, by_b_pos - 200) : by_b_pos + 800]
        call_count = window.count("seleccionar_variante_por_respuesta")
        assert call_count >= 2, (
            f"The 'B y B' example section must show >= 2 calls to "
            f"seleccionar_variante_por_respuesta (one per pending variant). "
            f"Found {call_count} call(s) in the surrounding context. "
            f"Window: {window!r}"
        )

    def test_1_9_slug_leak_note_present_in_category_table(self) -> None:
        """
        1.9 — presupuesto_mode.md must contain an explicit note instructing
        the LLM never to expose internal slug suffixes (-prof, -part) in natural
        language toward the user.

        The bug: LLM read the 'aseicars-prof' slug and said "autocaravana
        profesional" to the user — a confusing leak of internal nomenclature.
        """
        content = self._read_presupuesto_prompt()
        # The note must be present near the category table
        assert "Nota interna" in content or "NUNCA" in content and "-prof" in content, (
            "presupuesto_mode.md must contain a note warning the LLM not to "
            "expose internal slug suffixes (-prof, -part) to the user. "
            "Expected a 'Nota interna' or equivalent directive near the category table."
        )
        # The note must explicitly mention that slugs are internal codes
        assert any(
            phrase in content
            for phrase in [
                "NUNCA los menciones al usuario",
                "NUNCA menciones al usuario",
                "no menciones al usuario",
                "códigos internos",
                "código interno",
            ]
        ), (
            "The slug-leak note must explicitly tell the LLM not to mention "
            "internal codes to the user. Check the category table section."
        )
