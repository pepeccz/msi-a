"""Unit tests for first-turn IA intro finalizer in PRESUPUESTO_MODE."""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from agent.modes.presupuesto_mode import PresupuestoModeNode
from agent.modes.presupuesto_mode import _finalize_first_turn_intro


def test_first_turn_variant_question_gets_intro_prefix() -> None:
    mode_context = {"_is_first_interaction": True}
    response = "¿La placa solar incluye regulador propio o usa el del vehículo?"

    finalized = _finalize_first_turn_intro(response, mode_context)

    assert "asistente con ia" in finalized.lower()
    assert "placa solar" in finalized.lower()
    assert "¿la placa solar incluye regulador propio" in finalized.lower()


def test_first_turn_intro_is_idempotent_when_already_present() -> None:
    mode_context = {"_is_first_interaction": True}
    response = (
        "¡Hola! Soy el asistente con IA de MSI Automotive. "
        "¿La placa solar incluye regulador propio o usa el del vehículo?"
    )

    finalized = _finalize_first_turn_intro(response, mode_context)

    assert finalized == response
    assert finalized.lower().count("asistente con ia") == 1


def test_non_first_turn_response_is_unchanged() -> None:
    mode_context = {"_is_first_interaction": False}
    response = "¿La placa solar incluye regulador propio o usa el del vehículo?"

    finalized = _finalize_first_turn_intro(response, mode_context)

    assert finalized == response


@pytest.mark.asyncio
async def test_process_message_first_turn_keeps_variant_question_with_legal_intro() -> None:
    node = PresupuestoModeNode()
    state = {
        "conversation_id": "test-first-turn-variant-001",
        "mode_context": {},
        "messages": [],
        "client_type": "particular",
        "is_first_interaction": True,
    }
    llm_response = AIMessage(
        content="¿La placa solar incluye regulador propio o usa el del vehículo?"
    )
    llm_response.tool_calls = []

    with patch.object(node, "_get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=llm_response)
        mock_get_llm.return_value = mock_llm

        result = await node._process_message("Quiero homologar placa solar", state)

    response = result["ai_response"]
    assert "asistente con ia" in response.lower()
    assert "¿la placa solar incluye regulador propio" in response.lower()
    assert response.count("?") >= 1
