"""
Integration tests for T2.4 — generic_llm_loop wiring in consulta_mode.

Verifies that ConsultaModeNode delegates to generic_llm_loop() when
USE_GENERIC_LOOP=True, and falls back to the old inline loop when False.

All tests use pure mocks — no DB, no Redis, no real LLM.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.modes.generic_loop import GenericLoopResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_minimal_state(conversation_id: str = "test-consulta-001") -> dict[str, Any]:
    """
    Build a minimal ConversationState-compatible dict for testing consulta_mode.
    Enough to satisfy ConsultaModeNode._process_message without triggering
    KeyError or AttributeError.
    """
    return {
        "conversation_id": conversation_id,
        "user_message": "¿Cuánto cuesta homologar un escape?",
        "messages": [],
        "mode_context": {},
        "client_type": "particular",
        "is_first_interaction": False,
        "retry_state": {
            "retry_count": 0,
            "consecutive_errors": 0,
            "last_error_type": None,
            "last_error_message": None,
            "last_validation_context": None,
        },
    }


def _make_mock_settings(use_generic_loop: bool = True) -> MagicMock:
    """Build a mock Settings object for consulta tests."""
    mock_settings = MagicMock()
    mock_settings.USE_GENERIC_LOOP = use_generic_loop
    mock_settings.ENABLE_LATENCY_GATING = False
    mock_settings.MAX_TOOL_ITERATIONS_CONSULTA = 8
    mock_settings.LLM_MODEL = "test-model"
    mock_settings.OPENROUTER_API_KEY = "test-key"
    mock_settings.SITE_URL = "http://test.local"
    mock_settings.SITE_NAME = "Test"
    mock_settings.LLM_REQUEST_TIMEOUT_SECONDS = 30
    mock_settings.LLM_MAX_RETRIES = 1
    mock_settings.AGENT_TURN_TIMEOUT_SECONDS = 60
    return mock_settings


# ---------------------------------------------------------------------------
# Test 1 — consulta exits on no tool calls (generic loop path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consulta_exits_on_no_tool_calls():
    """
    When USE_GENERIC_LOOP=True and generic_llm_loop returns
    GenericLoopResult(ai_response="Respuesta RAG", exit_reason="response"),
    consulta_mode should return ai_response="Respuesta RAG".
    """
    from agent.modes.consulta_mode import ConsultaModeNode

    mock_result = GenericLoopResult(
        ai_response="Respuesta RAG",
        context_updates={},
        tools_called=set(),
        tool_results=[],
        exit_reason="response",
    )

    state = _make_minimal_state()
    node = ConsultaModeNode()

    with (
        patch(
            "agent.modes.consulta_mode.get_settings",
            return_value=_make_mock_settings(use_generic_loop=True),
        ),
        patch(
            "agent.modes.consulta_mode.generic_llm_loop",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_loop,
    ):
        result = await node._process_message("¿Cuánto cuesta?", state)

    # The returned ai_response should come from the generic loop
    assert result.get("ai_response") == "Respuesta RAG", (
        f"Expected ai_response='Respuesta RAG', got: {result.get('ai_response')!r}"
    )
    # generic_llm_loop MUST have been called
    mock_loop.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2 — Fallback to old loop when USE_GENERIC_LOOP=False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_to_old_loop_when_flag_false():
    """
    When USE_GENERIC_LOOP=False, ConsultaModeNode should NOT call
    generic_llm_loop. The old inline loop should handle the request.

    We verify by mocking generic_llm_loop and asserting it was NOT called,
    while mocking the LLM so the old loop doesn't make real API calls.
    """
    from agent.modes.consulta_mode import ConsultaModeNode

    state = _make_minimal_state()
    node = ConsultaModeNode()

    # Mock LLM response for the old loop path
    mock_llm_response = MagicMock()
    mock_llm_response.content = "El escape cuesta 350€ +IVA."
    mock_llm_response.tool_calls = []
    mock_llm_response.usage_metadata = None

    with (
        patch(
            "agent.modes.consulta_mode.get_settings",
            return_value=_make_mock_settings(use_generic_loop=False),
        ),
        patch(
            "agent.modes.consulta_mode.generic_llm_loop",
            new_callable=AsyncMock,
        ) as mock_loop,
        patch("agent.modes.base_mode.BaseModeNode._get_llm") as mock_get_llm,
        patch(
            "agent.modes.consulta_mode.assemble_system_prompt",
            return_value="System prompt text",
        ),
        patch("agent.modes.consulta_mode.set_current_state"),
        patch("agent.modes.consulta_mode.clear_current_state"),
        patch("agent.modes.consulta_mode.set_current_state_for_image_tools"),
        patch("agent.modes.consulta_mode.clear_image_tools_state"),
        patch(
            "agent.modes.base_mode.BaseModeNode._track_token_usage",
            new_callable=AsyncMock,
        ),
        patch(
            "agent.modes.base_mode.BaseModeNode._validate_response_constraints",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch(
            "agent.services.entity_extraction_service.get_entity_extraction_service",
        ) as mock_entity_svc,
    ):
        # Set up mock LLM for the old loop
        mock_llm_instance = AsyncMock()
        mock_llm_instance.ainvoke = AsyncMock(return_value=mock_llm_response)
        mock_get_llm.return_value = mock_llm_instance

        # Entity extraction service mock
        mock_svc_instance = MagicMock()
        mock_svc_instance.extract_entities = AsyncMock(
            return_value={"elementos": [], "marca": None, "modelo": None}
        )
        mock_entity_svc.return_value = mock_svc_instance

        result = await node._process_message("¿Qué es la homologación?", state)

    # generic_llm_loop MUST NOT have been called
    mock_loop.assert_not_called()

    # The result should still have an ai_response from the old loop
    assert result.get("ai_response"), "Old loop should have produced an ai_response"
