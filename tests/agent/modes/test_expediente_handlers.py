"""Unit tests for expediente sub-mode handlers."""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.modes.submodos.collect_personal import PersonalHandler
from agent.modes.submodos.collect_vehicle import VehicleHandler
from agent.modes.submodos.collect_workshop import WorkshopHandler
from agent.modes.submodos.collect_base_docs import BaseDocsHandler
from agent.modes.submodos.review_summary import ReviewHandler
from agent.modes.submodos.collect_element_data import ElementDataHandler


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm_loop() -> AsyncMock:
    return AsyncMock(return_value={"ai_response": "test response"})


@pytest.fixture
def base_state() -> dict:
    return {
        "messages": [],
        "conversation_id": "test-123",
        "incoming_attachments": [],
    }


@pytest.fixture
def base_mode_context() -> dict:
    return {
        "expediente_sub_mode": "collect_personal",
        "case_id": None,
    }


# ---------------------------------------------------------------------------
# PersonalHandler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_personal_handler_delegates_to_llm_loop(
    mock_llm_loop: AsyncMock,
    base_state: dict,
    base_mode_context: dict,
) -> None:
    handler = PersonalHandler()
    result = await handler.handle("hola", base_state, base_mode_context, mock_llm_loop)
    mock_llm_loop.assert_called_once()
    assert result is not None


@pytest.mark.asyncio
async def test_personal_handler_passes_correct_sub_mode_name(
    mock_llm_loop: AsyncMock,
    base_state: dict,
    base_mode_context: dict,
) -> None:
    handler = PersonalHandler()
    await handler.handle("me llamo Juan", base_state, base_mode_context, mock_llm_loop)
    _, kwargs = mock_llm_loop.call_args
    assert kwargs.get("sub_mode_name") == "COLLECT_PERSONAL"


@pytest.mark.asyncio
async def test_personal_handler_returns_llm_loop_result(
    base_state: dict,
    base_mode_context: dict,
) -> None:
    expected = {"ai_response": "¿Cuál es tu nombre completo?"}
    loop = AsyncMock(return_value=expected)
    handler = PersonalHandler()
    result = await handler.handle("hola", base_state, base_mode_context, loop)
    assert result == expected


# ---------------------------------------------------------------------------
# VehicleHandler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vehicle_handler_delegates_to_llm_loop(
    mock_llm_loop: AsyncMock,
    base_state: dict,
    base_mode_context: dict,
) -> None:
    handler = VehicleHandler()
    result = await handler.handle(
        "un honda civic", base_state, base_mode_context, mock_llm_loop
    )
    mock_llm_loop.assert_called_once()
    assert result is not None


@pytest.mark.asyncio
async def test_vehicle_handler_passes_correct_sub_mode_name(
    mock_llm_loop: AsyncMock,
    base_state: dict,
    base_mode_context: dict,
) -> None:
    handler = VehicleHandler()
    await handler.handle(
        "Honda Civic 2020", base_state, base_mode_context, mock_llm_loop
    )
    _, kwargs = mock_llm_loop.call_args
    assert kwargs.get("sub_mode_name") == "COLLECT_VEHICLE"


# ---------------------------------------------------------------------------
# WorkshopHandler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workshop_handler_delegates_to_llm_loop(
    mock_llm_loop: AsyncMock,
    base_state: dict,
    base_mode_context: dict,
) -> None:
    handler = WorkshopHandler()
    result = await handler.handle(
        "taller madrid", base_state, base_mode_context, mock_llm_loop
    )
    mock_llm_loop.assert_called_once()
    assert result is not None


@pytest.mark.asyncio
async def test_workshop_handler_passes_correct_sub_mode_name(
    mock_llm_loop: AsyncMock,
    base_state: dict,
    base_mode_context: dict,
) -> None:
    handler = WorkshopHandler()
    await handler.handle(
        "usaré mi taller", base_state, base_mode_context, mock_llm_loop
    )
    _, kwargs = mock_llm_loop.call_args
    assert kwargs.get("sub_mode_name") == "COLLECT_WORKSHOP"


# ---------------------------------------------------------------------------
# BaseDocsHandler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_docs_handler_delegates_to_llm_loop(
    mock_llm_loop: AsyncMock,
    base_state: dict,
    base_mode_context: dict,
) -> None:
    handler = BaseDocsHandler()
    result = await handler.handle("ok", base_state, base_mode_context, mock_llm_loop)
    mock_llm_loop.assert_called_once()
    assert result is not None


@pytest.mark.asyncio
async def test_base_docs_image_only_turn_returns_ack_without_llm(
    mock_llm_loop: AsyncMock,
    base_mode_context: dict,
) -> None:
    """When user sends images but no text, handler must ACK without calling LLM."""
    state_with_images = {
        "messages": [],
        "conversation_id": "test-123",
        "incoming_attachments": [{"url": "http://example.com/img1.jpg"}],
    }
    handler = BaseDocsHandler()
    result = await handler.handle(
        "", state_with_images, base_mode_context, mock_llm_loop
    )
    mock_llm_loop.assert_not_called()
    assert "ai_response" in result
    assert "1 foto" in result["ai_response"]


@pytest.mark.asyncio
async def test_base_docs_text_with_images_still_delegates(
    mock_llm_loop: AsyncMock,
    base_mode_context: dict,
) -> None:
    """When message has text, delegate to LLM even if attachments present."""
    state_with_images = {
        "messages": [],
        "conversation_id": "test-123",
        "incoming_attachments": [{"url": "http://example.com/img1.jpg"}],
    }
    handler = BaseDocsHandler()
    await handler.handle("listo", state_with_images, base_mode_context, mock_llm_loop)
    mock_llm_loop.assert_called_once()


# ---------------------------------------------------------------------------
# ElementDataHandler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_element_data_handler_delegates_to_llm_loop(
    mock_llm_loop: AsyncMock,
    base_state: dict,
) -> None:
    """ElementDataHandler must delegate to llm_loop when message has text."""
    mode_context = {
        "expediente_sub_mode": "collect_element_data",
        "case_id": "case-abc",
        "element_codes": ["ESCAPE"],
        "current_element_index": 0,
        "element_display_names": {"ESCAPE": "Escape"},
    }
    mock_settings = MagicMock()
    mock_settings.EXPEDIENTE_V2_ENABLED = False

    # _clear_element_images_sent_this_turn is imported lazily inside handle(),
    # so patch it at the source module, not at the import site.
    with patch(
        "agent.modes.submodos.collect_element_data.get_settings",
        return_value=mock_settings,
    ):
        with patch("agent.tools.image_tools._clear_element_images_sent_this_turn"):
            handler = ElementDataHandler()
            result = await handler.handle(
                "ok tengo las fotos", base_state, mode_context, mock_llm_loop
            )

    mock_llm_loop.assert_called_once()
    assert result is not None


@pytest.mark.asyncio
async def test_element_data_image_only_turn_acks_without_llm(
    mock_llm_loop: AsyncMock,
) -> None:
    """Image-only turn must return ACK without calling LLM."""
    state_with_images = {
        "messages": [],
        "conversation_id": "test-123",
        "incoming_attachments": [
            {"url": "http://img.com/a.jpg"},
            {"url": "http://img.com/b.jpg"},
        ],
    }
    mode_context = {
        "element_codes": ["ESCAPE"],
        "current_element_index": 0,
        "element_display_names": {"ESCAPE": "Escape"},
    }
    mock_settings = MagicMock()
    mock_settings.EXPEDIENTE_V2_ENABLED = False

    # _clear_element_images_sent_this_turn is imported lazily inside handle(),
    # so patch it at the source module, not at the import site.
    with patch(
        "agent.modes.submodos.collect_element_data.get_settings",
        return_value=mock_settings,
    ):
        with patch("agent.tools.image_tools._clear_element_images_sent_this_turn"):
            handler = ElementDataHandler()
            result = await handler.handle(
                "", state_with_images, mode_context, mock_llm_loop
            )

    mock_llm_loop.assert_not_called()
    assert "ai_response" in result
    assert "2 foto" in result["ai_response"]


# ---------------------------------------------------------------------------
# ReviewHandler (mocked obtener_estado_expediente)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_handler_delegates_when_db_succeeds(
    mock_llm_loop: AsyncMock,
    base_state: dict,
    base_mode_context: dict,
) -> None:
    """ReviewHandler must delegate to llm_loop when DB pre-call succeeds."""
    mock_state_result = {
        "has_active_case": True,
        "precio_total": 410.0,
        "data_source": "db",
    }
    mock_precall = AsyncMock(return_value=mock_state_result)

    with patch("agent.modes.submodos.review_summary.set_current_state"):
        with patch(
            "agent.modes.submodos.review_summary.set_current_state_for_image_tools"
        ):
            with patch("agent.tools.case_tools.obtener_estado_expediente") as mock_tool:
                mock_tool.ainvoke = mock_precall
                handler = ReviewHandler()
                result = await handler.handle(
                    "ok", base_state, base_mode_context, mock_llm_loop
                )

    mock_llm_loop.assert_called_once()
    assert result is not None


@pytest.mark.asyncio
async def test_review_handler_blocks_when_fallback_data(
    mock_llm_loop: AsyncMock,
    base_state: dict,
    base_mode_context: dict,
) -> None:
    """ReviewHandler must block (not call LLM) when pre-call returns fallback data."""
    fallback_result = {"data_source": "fallback"}
    mock_precall = AsyncMock(return_value=fallback_result)

    with patch("agent.modes.submodos.review_summary.set_current_state"):
        with patch(
            "agent.modes.submodos.review_summary.set_current_state_for_image_tools"
        ):
            with patch("agent.tools.case_tools.obtener_estado_expediente") as mock_tool:
                mock_tool.ainvoke = mock_precall
                handler = ReviewHandler()
                result = await handler.handle(
                    "ok", base_state, base_mode_context, mock_llm_loop
                )

    mock_llm_loop.assert_not_called()
    assert "ai_response" in result


# ---------------------------------------------------------------------------
# mode_context mutation propagation (contract test)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mode_context_mutation_propagates(
    base_state: dict,
    base_mode_context: dict,
) -> None:
    """mode_context must be passed by reference — mutations in handler visible to caller."""

    async def mutating_loop(**kwargs: object) -> dict:
        mode_ctx = kwargs["mode_context"]
        assert isinstance(mode_ctx, dict)
        mode_ctx["_test_mutation"] = "set_by_handler"
        return {"ai_response": "ok"}

    handler = PersonalHandler()
    await handler.handle("test", base_state, base_mode_context, mutating_loop)
    assert base_mode_context.get("_test_mutation") == "set_by_handler"


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------


def test_all_handlers_importable() -> None:
    """All 6 handler classes must be importable from the submodos package."""
    from agent.modes.submodos import (
        PersonalHandler,
        VehicleHandler,
        WorkshopHandler,
        BaseDocsHandler,
        ReviewHandler,
        ElementDataHandler,
    )

    assert PersonalHandler is not None
    assert VehicleHandler is not None
    assert WorkshopHandler is not None
    assert BaseDocsHandler is not None
    assert ReviewHandler is not None
    assert ElementDataHandler is not None


def test_no_circular_import() -> None:
    """collect_element_data must not create circular import with expediente_mode."""
    mod = importlib.import_module("agent.modes.submodos.collect_element_data")
    assert hasattr(mod, "ElementDataHandler")


def test_handlers_have_get_tools_method() -> None:
    """All handlers must expose a get_tools() method."""
    handlers = [
        PersonalHandler(),
        VehicleHandler(),
        WorkshopHandler(),
        BaseDocsHandler(),
        ReviewHandler(),
        ElementDataHandler(),
    ]
    for handler in handlers:
        assert hasattr(handler, "get_tools"), (
            f"{type(handler).__name__} missing get_tools()"
        )
        tools = handler.get_tools()
        assert isinstance(tools, list), (
            f"{type(handler).__name__}.get_tools() must return list"
        )
