"""
Unit tests for enviar_imagenes_ejemplo categoria resolution from state.

fix-expediente-context-gaps Phase 2: verifies that the tool resolves
categoria from authoritative state (mode_context / shared_context)
instead of trusting the LLM-supplied parameter.

Uses mocks for ImageService — no DB, no Redis.
"""

import json
import logging

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.tools.image_tools import (
    clear_image_tools_state,
    enviar_imagenes_ejemplo,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_tool_config(state: dict) -> dict:
    """Build a RunnableConfig that passes state to tool via get_tool_state(config)."""
    return {"configurable": {"state": state}}


def _make_state(
    conversation_id: str = "test-conv-001",
    mode_context_slug: str | None = None,
    shared_context_slug: str | None = None,
) -> dict:
    """Build a minimal state dict for tool testing."""
    state: dict = {"conversation_id": conversation_id}
    mc: dict = {}
    if mode_context_slug is not None:
        mc["categoria_slug"] = mode_context_slug
    state["mode_context"] = mc
    if shared_context_slug is not None:
        state["shared_context"] = {"categoria_slug": shared_context_slug}
    return state


def _make_mock_image_service(queue_result: dict | None = None) -> MagicMock:
    """Return a mock ImageService with async queue_example_images."""
    svc = MagicMock()
    svc.queue_example_images = AsyncMock(
        return_value=queue_result
        or {
            "success": True,
            "message": "2 imágenes encoladas",
            "queued_count": 2,
            "requested_count": 2,
        }
    )
    return svc


# =============================================================================
# Phase 2 — Task 2.1: Categoria resolution from state
# =============================================================================


class TestCategoriaResolutionFromState:
    """enviar_imagenes_ejemplo must resolve categoria from state when available."""

    @pytest.mark.asyncio
    async def test_state_overrides_llm_supplied_categoria(self):
        """
        State has categoria_slug='motos-part', tool called with
        categoria='wrong-slug' → queue_example_images called with 'motos-part'.
        """
        state = _make_state(mode_context_slug="motos-part")
        mock_svc = _make_mock_image_service()

        with patch(
            "agent.services.image_service.get_image_service",
            return_value=mock_svc,
        ):
            try:
                result_raw = await enviar_imagenes_ejemplo.ainvoke(
                    {
                        "tipo": "documentacion_base",
                        "categoria": "wrong-slug",
                    },
                    config=_make_tool_config(state),
                )
            finally:
                clear_image_tools_state()

        # Verify ImageService was called with state categoria
        mock_svc.queue_example_images.assert_called_once()
        call_kwargs = mock_svc.queue_example_images.call_args
        assert call_kwargs.kwargs.get("categoria") == "motos-part"

    @pytest.mark.asyncio
    async def test_state_matches_llm_no_warning(self, caplog):
        """
        State has categoria_slug='motos-part', tool called with same
        → no override warning logged.
        """
        state = _make_state(mode_context_slug="motos-part")
        mock_svc = _make_mock_image_service()

        with (
            patch(
                "agent.services.image_service.get_image_service",
                return_value=mock_svc,
            ),
            caplog.at_level(logging.WARNING, logger="agent.tools.image_tools"),
        ):
            try:
                await enviar_imagenes_ejemplo.ainvoke(
                    {
                        "tipo": "documentacion_base",
                        "categoria": "motos-part",
                    },
                    config=_make_tool_config(state),
                )
            finally:
                clear_image_tools_state()

        assert "categoria_override_from_state" not in caplog.text

    @pytest.mark.asyncio
    async def test_no_state_slug_passes_through(self):
        """
        State has no categoria_slug → tool's categoria param passes through
        unchanged.
        """
        state = _make_state()  # no slug
        mock_svc = _make_mock_image_service()

        with patch(
            "agent.services.image_service.get_image_service",
            return_value=mock_svc,
        ):
            try:
                await enviar_imagenes_ejemplo.ainvoke(
                    {
                        "tipo": "documentacion_base",
                        "categoria": "motos-part",
                    },
                    config=_make_tool_config(state),
                )
            finally:
                clear_image_tools_state()

        call_kwargs = mock_svc.queue_example_images.call_args
        assert call_kwargs.kwargs.get("categoria") == "motos-part"

    @pytest.mark.asyncio
    async def test_state_slug_resolves_when_tool_has_none(self):
        """
        State has categoria_slug='aseicars' (via shared_context), tool called
        with categoria=None → resolves to 'aseicars'.
        """
        state = _make_state(shared_context_slug="aseicars")
        mock_svc = _make_mock_image_service()

        with patch(
            "agent.services.image_service.get_image_service",
            return_value=mock_svc,
        ):
            try:
                await enviar_imagenes_ejemplo.ainvoke(
                    {
                        "tipo": "documentacion_base",
                        "categoria": None,
                    },
                    config=_make_tool_config(state),
                )
            finally:
                clear_image_tools_state()

        call_kwargs = mock_svc.queue_example_images.call_args
        assert call_kwargs.kwargs.get("categoria") == "aseicars"
