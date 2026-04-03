"""
Integration tests for T2.2 — generic_llm_loop wiring in presupuesto_mode.

Verifies that PresupuestoModeNode delegates to generic_llm_loop() when
USE_GENERIC_LOOP=True, and falls back to the old loop when False.

All tests use pure mocks — no DB, no Redis, no real LLM.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.modes.generic_loop import GenericLoopResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_minimal_state(conversation_id: str = "test-conv-001") -> dict[str, Any]:
    """
    Build a minimal ConversationState-compatible dict for testing.
    Enough to satisfy PresupuestoModeNode._process_message without
    triggering KeyError or AttributeError.
    """
    return {
        "conversation_id": conversation_id,
        "user_message": "Quiero homologar mi moto",
        "messages": [],
        "mode_context": {
            "categoria_slug": "motos-part",
            "price_communicated": False,
        },
        "client_type": "particular",
        "is_first_interaction": False,
        "retry_state": {
            "retry_count": 0,
            "consecutive_errors": 0,
            "last_error_type": None,
            "last_error_message": None,
            "last_validation_context": None,
        },
        "presupuesto_offered_count": 0,
    }


def _make_mock_settings(use_generic_loop: bool = True) -> MagicMock:
    """Build a mock Settings object for tests."""
    mock_settings = MagicMock()
    mock_settings.USE_GENERIC_LOOP = use_generic_loop
    mock_settings.ENABLE_LATENCY_GATING = False
    mock_settings.MAX_TOOL_ITERATIONS_PRESUPUESTO = 10
    mock_settings.LLM_MODEL = "test-model"
    mock_settings.OPENROUTER_API_KEY = "test-key"
    mock_settings.SITE_URL = "http://test.local"
    mock_settings.SITE_NAME = "Test"
    mock_settings.LLM_REQUEST_TIMEOUT_SECONDS = 30
    mock_settings.LLM_MAX_RETRIES = 1
    mock_settings.AGENT_TURN_TIMEOUT_SECONDS = 60
    return mock_settings


def _make_generic_loop_result(
    ai_response: str = "El presupuesto es 410€ +IVA.",
    context_updates: dict | None = None,
    tools_called: set | None = None,
    exit_reason: str = "response",
) -> GenericLoopResult:
    """Build a GenericLoopResult for mocking."""
    return GenericLoopResult(
        ai_response=ai_response,
        context_updates=context_updates or {},
        tools_called=tools_called or set(),
        tool_results=[],
        exit_reason=exit_reason,
    )


# ---------------------------------------------------------------------------
# Test 1 — precio_comunicado propagated via context_updates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_precio_comunicado_via_context_update():
    """
    When USE_GENERIC_LOOP=True and generic_llm_loop returns
    context_updates={"precio_comunicado": True}, the returned state dict
    should contain mode_context with precio_comunicado=True.
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode

    mock_result = _make_generic_loop_result(
        ai_response="El presupuesto es 410€ +IVA.",
        context_updates={"precio_comunicado": True},
    )

    state = _make_minimal_state()
    node = PresupuestoModeNode()

    with (
        patch(
            "agent.modes.presupuesto_mode.get_settings",
            return_value=_make_mock_settings(use_generic_loop=True),
        ),
        patch(
            "agent.modes.presupuesto_mode.generic_llm_loop",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_loop,
    ):
        result = await node._process_message("Quiero homologar", state)

    # The returned mode_context should contain precio_comunicado=True
    mode_ctx = result.get("mode_context", {})
    assert mode_ctx.get("precio_comunicado") is True, (
        f"Expected precio_comunicado=True in mode_context, got: {mode_ctx}"
    )
    # generic_llm_loop MUST have been called
    mock_loop.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2 — pending_variants propagated via context_updates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_variants_propagated():
    """
    When generic_llm_loop returns context_updates with pending_variants,
    the resulting mode_context should contain the correct pending_variants list.
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode

    expected_variants = [{"codigo": "TOLDO_LAT", "status": "pending"}]
    mock_result = _make_generic_loop_result(
        ai_response="¿Qué tipo de toldo quieres?",
        context_updates={"pending_variants": expected_variants},
    )

    state = _make_minimal_state()
    node = PresupuestoModeNode()

    with (
        patch(
            "agent.modes.presupuesto_mode.get_settings",
            return_value=_make_mock_settings(use_generic_loop=True),
        ),
        patch(
            "agent.modes.presupuesto_mode.generic_llm_loop",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_loop,
    ):
        result = await node._process_message("Quiero toldo", state)

    mode_ctx = result.get("mode_context", {})
    actual_variants = mode_ctx.get("pending_variants")
    assert actual_variants == expected_variants, (
        f"Expected pending_variants={expected_variants!r}, got: {actual_variants!r}"
    )
    mock_loop.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3 — No extra system message injection inside the loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_system_message_injection():
    """
    With USE_GENERIC_LOOP=True, verify that generic_llm_loop is called with
    a system_prompt string (not injected as an extra dict in the messages list).
    The 'messages' kwarg passed to generic_llm_loop should NOT contain any
    dict with role=="system" — the system prompt is passed separately.
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode

    mock_result = _make_generic_loop_result()
    state = _make_minimal_state()
    node = PresupuestoModeNode()

    captured_kwargs: list[dict] = []

    async def capturing_loop(*args, **kwargs):
        captured_kwargs.append(kwargs)
        return mock_result

    with (
        patch(
            "agent.modes.presupuesto_mode.get_settings",
            return_value=_make_mock_settings(use_generic_loop=True),
        ),
        patch(
            "agent.modes.presupuesto_mode.generic_llm_loop",
            side_effect=capturing_loop,
        ),
    ):
        await node._process_message("Hola", state)

    assert len(captured_kwargs) == 1, "generic_llm_loop should have been called once"

    call_kwargs = captured_kwargs[0]

    # system_prompt must be a non-empty string
    assert isinstance(call_kwargs.get("system_prompt"), str), (
        "system_prompt must be passed as a string kwarg"
    )
    assert len(call_kwargs["system_prompt"]) > 0, "system_prompt must not be empty"

    # messages list (conversation history) must NOT contain role="system"
    messages = call_kwargs.get("messages", [])
    system_msgs = [
        m for m in messages if isinstance(m, dict) and m.get("role") == "system"
    ]
    assert len(system_msgs) == 0, (
        f"messages passed to generic_llm_loop should not contain role='system' entries, "
        f"got: {system_msgs}"
    )


# ---------------------------------------------------------------------------
# Test 4 — Fallback to old loop when USE_GENERIC_LOOP=False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_to_old_loop_when_flag_false():
    """
    When USE_GENERIC_LOOP=False, the node should NOT call generic_llm_loop.
    The old inline loop should still handle the request.

    We verify this by mocking generic_llm_loop and asserting it was NOT called,
    while also mocking the LLM so the old loop doesn't make real API calls.
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode

    state = _make_minimal_state()
    node = PresupuestoModeNode()

    # Mock LLM response for the old loop path
    mock_llm_response = MagicMock()
    mock_llm_response.content = "Aquí está el presupuesto."
    mock_llm_response.tool_calls = []
    mock_llm_response.usage_metadata = None

    with (
        patch(
            "agent.modes.presupuesto_mode.get_settings",
            return_value=_make_mock_settings(use_generic_loop=False),
        ),
        patch(
            "agent.modes.presupuesto_mode.generic_llm_loop",
            new_callable=AsyncMock,
        ) as mock_loop,
        patch("agent.modes.base_mode.BaseModeNode._get_llm") as mock_get_llm,
        patch(
            "agent.modes.presupuesto_mode.assemble_system_prompt",
            return_value="System prompt text",
        ),
        patch("agent.modes.presupuesto_mode.set_current_state"),
        patch("agent.modes.presupuesto_mode.clear_current_state"),
        patch("agent.modes.presupuesto_mode.set_current_state_for_image_tools"),
        patch("agent.modes.presupuesto_mode.clear_image_tools_state"),
        patch(
            "agent.modes.base_mode.BaseModeNode._track_token_usage",
            new_callable=AsyncMock,
        ),
        patch(
            "agent.modes.base_mode.BaseModeNode._validate_response_constraints",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
    ):
        # Set up mock LLM for the old loop
        mock_llm_instance = AsyncMock()
        mock_llm_instance.ainvoke = AsyncMock(return_value=mock_llm_response)
        mock_get_llm.return_value = mock_llm_instance

        result = await node._process_message("Hola", state)

    # generic_llm_loop MUST NOT have been called
    mock_loop.assert_not_called()

    # The result should still have an ai_response from the old loop
    assert result.get("ai_response"), "Old loop should have produced an ai_response"
