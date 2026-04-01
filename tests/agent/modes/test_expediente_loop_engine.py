"""Unit tests for ExpedienteLoopEngine (Phase C extraction)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.modes.submodos.loop_engine import ExpedienteLoopEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_parent() -> MagicMock:
    """Mock parent (ExpedienteModeNode) with all methods the engine calls."""
    parent = MagicMock()

    # Async methods
    parent._execute_and_log_tool = AsyncMock(return_value=json.dumps({"success": True}))
    parent._invoke_with_fallback = AsyncMock()
    parent._track_token_usage = AsyncMock()
    parent._validate_response_constraints = AsyncMock(return_value=(True, None))
    parent._guard_photo_completion_intent = AsyncMock(return_value=False)

    # Sync methods
    parent._is_validation_error = MagicMock(return_value=(False, None))
    parent._handle_validation_retry = MagicMock(return_value=(False, {}))
    parent._get_element_state_svc = MagicMock(return_value=None)

    # LLM mock: _get_llm returns a mock whose ainvoke returns a simple AIMessage-like
    _mock_llm = MagicMock()
    _mock_ai_response = MagicMock()
    _mock_ai_response.content = "Respuesta de prueba"
    _mock_ai_response.tool_calls = []
    _mock_ai_response.usage_metadata = None
    _mock_llm.ainvoke = AsyncMock(return_value=_mock_ai_response)
    parent._get_llm = MagicMock(return_value=_mock_llm)

    # Attributes
    parent._logger = MagicMock()
    parent._fallback = MagicMock()
    parent._policy = MagicMock()
    parent._tool_dedup_cache = None
    parent.mode_name = "EXPEDIENTE_MODE"

    return parent


@pytest.fixture
def mock_state() -> dict:
    return {
        "conversation_id": "test-eng-001",
        "messages": [],
        "incoming_attachments": [],
        "mode_context": {},
        "retry_state": None,
    }


@pytest.fixture
def mock_mode_context() -> dict:
    return {
        "expediente_sub_mode": "collect_personal",
        "case_id": "abc-123",
        "element_codes": [],
    }


# ---------------------------------------------------------------------------
# Group 4.1 / Task 4.1: instantiation
# ---------------------------------------------------------------------------


def test_engine_instantiates_with_parent(mock_parent: MagicMock) -> None:
    """ExpedienteLoopEngine stores parent reference correctly."""
    engine = ExpedienteLoopEngine(parent=mock_parent)
    assert engine.parent is mock_parent


# ---------------------------------------------------------------------------
# Group 4.2 / Task 4.2: run() happy-path — no tool calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_returns_dict_with_ai_response(
    mock_parent: MagicMock,
    mock_state: dict,
    mock_mode_context: dict,
) -> None:
    """run() returns dict with 'ai_response' when LLM produces no tool calls."""
    engine = ExpedienteLoopEngine(parent=mock_parent)

    with (
        patch(
            "agent.modes.submodos.loop_engine.assemble_system_prompt",
            return_value="[SYS]",
        ),
        patch(
            "agent.modes.submodos.loop_engine.format_messages_for_llm", return_value=[]
        ),
        patch("agent.modes.submodos.loop_engine.set_current_state"),
        patch("agent.modes.submodos.loop_engine.set_current_state_for_image_tools"),
        patch("agent.modes.submodos.loop_engine.clear_current_state"),
        patch("agent.modes.submodos.loop_engine.clear_image_tools_state"),
        patch("agent.modes.submodos.loop_engine.get_settings") as mock_settings,
    ):
        _s = MagicMock()
        _s.EXPEDIENTE_CERTAINTY_GUARDRAILS_ENABLED = False
        _s.ENABLE_LATENCY_GATING = False
        _s.EXPEDIENTE_V2_ENABLED = False
        _s.ENABLE_SAME_TURN_TRANSITION_CLOSURE = False
        _s.ENABLE_CANONICAL_TRANSITION_ADAPTER = False
        mock_settings.return_value = _s

        result = await engine.run(
            message="hola",
            state=mock_state,
            mode_context=dict(mock_mode_context),
            tools=[],
            sub_mode_name="COLLECT_PERSONAL",
        )

    assert isinstance(result, dict)
    assert "ai_response" in result
    assert result["ai_response"] == "Respuesta de prueba"


# ---------------------------------------------------------------------------
# Group 4.3 / Task 4.3: pre_call injection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_injects_pre_call_tool_result_as_system_message(
    mock_parent: MagicMock,
    mock_state: dict,
    mock_mode_context: dict,
) -> None:
    """pre_call_tool_result kwarg is injected as a system message."""
    engine = ExpedienteLoopEngine(parent=mock_parent)
    captured_messages: list = []

    async def capture_ainvoke(msgs):
        captured_messages.extend(msgs)
        resp = MagicMock()
        resp.content = "respuesta"
        resp.tool_calls = []
        resp.usage_metadata = None
        return resp

    mock_parent._get_llm.return_value.ainvoke = capture_ainvoke

    with (
        patch(
            "agent.modes.submodos.loop_engine.assemble_system_prompt",
            return_value="[SYS]",
        ),
        patch(
            "agent.modes.submodos.loop_engine.format_messages_for_llm", return_value=[]
        ),
        patch("agent.modes.submodos.loop_engine.set_current_state"),
        patch("agent.modes.submodos.loop_engine.set_current_state_for_image_tools"),
        patch("agent.modes.submodos.loop_engine.clear_current_state"),
        patch("agent.modes.submodos.loop_engine.clear_image_tools_state"),
        patch("agent.modes.submodos.loop_engine.get_settings") as mock_settings,
    ):
        _s = MagicMock()
        _s.EXPEDIENTE_CERTAINTY_GUARDRAILS_ENABLED = False
        _s.ENABLE_LATENCY_GATING = False
        _s.EXPEDIENTE_V2_ENABLED = False
        _s.ENABLE_SAME_TURN_TRANSITION_CLOSURE = False
        _s.ENABLE_CANONICAL_TRANSITION_ADAPTER = False
        mock_settings.return_value = _s

        await engine.run(
            message="resumen",
            state=mock_state,
            mode_context=dict(mock_mode_context),
            tools=[],
            sub_mode_name="REVIEW_SUMMARY",
            pre_call_tool_result='{"status": "ok", "precio": 450}',
            pre_call_tool_name="obtener_estado_expediente",
        )

    # There should be a system message containing the pre-call result
    system_messages = [m for m in captured_messages if m.get("role") == "system"]
    pre_call_messages = [
        m for m in system_messages if "RESULTADO PRE-CARGADO" in m.get("content", "")
    ]
    assert len(pre_call_messages) >= 1
    assert "obtener_estado_expediente" in pre_call_messages[0]["content"]


# ---------------------------------------------------------------------------
# Group 4.4 / Task 4.4: TOMBSTONE for expediente_transition_marker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_tombstone_fires_for_transition_marker(
    mock_parent: MagicMock,
    mock_state: dict,
) -> None:
    """TOMBSTONE clears expediente_transition_marker when destination turn starts."""
    engine = ExpedienteLoopEngine(parent=mock_parent)

    mode_context = {
        "expediente_sub_mode": "collect_vehicle",
        "case_id": "abc-123",
        "expediente_transition_marker": {
            "from_sub_mode": "collect_personal",
            "to_sub_mode": "collect_vehicle",
            "tool_name": "completar_datos_personales",
            "requires_kickoff": True,
        },
    }

    with (
        patch(
            "agent.modes.submodos.loop_engine.assemble_system_prompt",
            return_value="[SYS]",
        ),
        patch(
            "agent.modes.submodos.loop_engine.format_messages_for_llm", return_value=[]
        ),
        patch("agent.modes.submodos.loop_engine.set_current_state"),
        patch("agent.modes.submodos.loop_engine.set_current_state_for_image_tools"),
        patch("agent.modes.submodos.loop_engine.clear_current_state"),
        patch("agent.modes.submodos.loop_engine.clear_image_tools_state"),
        patch("agent.modes.submodos.loop_engine.get_settings") as mock_settings,
    ):
        _s = MagicMock()
        _s.EXPEDIENTE_CERTAINTY_GUARDRAILS_ENABLED = False
        _s.ENABLE_LATENCY_GATING = False
        _s.EXPEDIENTE_V2_ENABLED = False
        _s.ENABLE_SAME_TURN_TRANSITION_CLOSURE = False
        _s.ENABLE_CANONICAL_TRANSITION_ADAPTER = False
        mock_settings.return_value = _s

        result = await engine.run(
            message="continuamos",
            state=mock_state,
            mode_context=mode_context,
            tools=[],
            sub_mode_name="COLLECT_VEHICLE",
        )

    updated_context = result.get("mode_context", {})
    # TOMBSTONE: the marker must be None after being consumed
    assert updated_context.get("expediente_transition_marker") is None
    assert updated_context.get("just_transitioned_from") is None


# ---------------------------------------------------------------------------
# Group 4.5 / Task 4.5: TOMBSTONE for just_transitioned_from
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_tombstone_fires_for_just_transitioned_from(
    mock_parent: MagicMock,
    mock_state: dict,
) -> None:
    """TOMBSTONE clears just_transitioned_from in the finally / cleanup path."""
    engine = ExpedienteLoopEngine(parent=mock_parent)

    mode_context = {
        "expediente_sub_mode": "collect_personal",
        "case_id": "abc-123",
        "just_transitioned_from": "collect_element_data",
    }

    with (
        patch(
            "agent.modes.submodos.loop_engine.assemble_system_prompt",
            return_value="[SYS]",
        ),
        patch(
            "agent.modes.submodos.loop_engine.format_messages_for_llm", return_value=[]
        ),
        patch("agent.modes.submodos.loop_engine.set_current_state"),
        patch("agent.modes.submodos.loop_engine.set_current_state_for_image_tools"),
        patch("agent.modes.submodos.loop_engine.clear_current_state"),
        patch("agent.modes.submodos.loop_engine.clear_image_tools_state"),
        patch("agent.modes.submodos.loop_engine.get_settings") as mock_settings,
    ):
        _s = MagicMock()
        _s.EXPEDIENTE_CERTAINTY_GUARDRAILS_ENABLED = False
        _s.ENABLE_LATENCY_GATING = False
        _s.EXPEDIENTE_V2_ENABLED = False
        _s.ENABLE_SAME_TURN_TRANSITION_CLOSURE = False
        _s.ENABLE_CANONICAL_TRANSITION_ADAPTER = False
        mock_settings.return_value = _s

        result = await engine.run(
            message="hola",
            state=mock_state,
            mode_context=mode_context,
            tools=[],
            sub_mode_name="COLLECT_PERSONAL",
        )

    updated_context = result.get("mode_context", {})
    # The legacy marker must be consumed — either None (if marker was active)
    # or absent from updates. The key point is the marker won't survive to next turn.
    # For legacy just_transitioned_from: marker triggers kickoff guard which clears it.
    assert updated_context.get("just_transitioned_from") is None


# ---------------------------------------------------------------------------
# Group 4.6 / Task 4.6: extract_context_from_tool — completar_elemento_actual
# ---------------------------------------------------------------------------


def test_extract_context_completar_elemento_actual() -> None:
    """extract_context_from_tool extracts expediente_sub_mode from _context_updates."""
    result_json = json.dumps(
        {
            "success": True,
            "all_elements_complete": True,
            "_context_updates": {"expediente_sub_mode": "collect_base_docs"},
        }
    )

    updates = ExpedienteLoopEngine.extract_context_from_tool(
        tool_name="completar_elemento_actual",
        tool_args={},
        result=result_json,
        current_context={},
    )

    assert "expediente_sub_mode" in updates
    assert updates["expediente_sub_mode"] == "collect_base_docs"


# ---------------------------------------------------------------------------
# Group 4.7 / Task 4.7: extract_context_from_tool — iniciar_expediente
# ---------------------------------------------------------------------------


def test_extract_context_iniciar_expediente() -> None:
    """extract_context_from_tool returns case_id for iniciar_expediente result."""
    result_json = json.dumps(
        {
            "success": True,
            "case_id": "abc-123",
            "_context_updates": {"case_id": "abc-123"},
        }
    )

    updates = ExpedienteLoopEngine.extract_context_from_tool(
        tool_name="iniciar_expediente",
        tool_args={},
        result=result_json,
        current_context={},
    )

    assert updates.get("case_id") == "abc-123"


# ---------------------------------------------------------------------------
# Group 4.8 / Task 4.8: static helpers importable
# ---------------------------------------------------------------------------


def test_static_helpers_importable() -> None:
    """All 8 static helpers exist as callable attributes on ExpedienteLoopEngine."""
    helper_names = [
        "_extract_pending_images",
        "_get_active_transition_marker",
        "_is_actionable_kickoff_response",
        "_build_next_element_kickoff",
        "_build_transition_kickoff_message",
        "_build_client_context",
        "_ai_message_to_dict",
        "_log_token_usage",
    ]
    for name in helper_names:
        attr = getattr(ExpedienteLoopEngine, name, None)
        assert attr is not None, f"Missing helper: {name}"
        assert callable(attr), f"Not callable: {name}"

    # Call _ai_message_to_dict with a mock AIMessage-like dict
    mock_response = MagicMock()
    mock_response.content = "hello"
    mock_response.tool_calls = []
    result = ExpedienteLoopEngine._ai_message_to_dict(mock_response)
    assert isinstance(result, dict)
    assert result.get("content") == "hello"
    assert result.get("role") == "assistant"


# ---------------------------------------------------------------------------
# Group 4.9 / Task 4.9: importable from submodos __init__
# ---------------------------------------------------------------------------


def test_loop_engine_importable_from_submodos_init() -> None:
    """ExpedienteLoopEngine is importable from agent.modes.submodos."""
    from agent.modes.submodos import ExpedienteLoopEngine as LE

    assert LE is ExpedienteLoopEngine

    import inspect

    sig = inspect.signature(LE.__init__)
    assert "parent" in sig.parameters
