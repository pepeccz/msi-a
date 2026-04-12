"""
Unit tests for enviar_imagenes_ejemplo categoria resolution from state.

fix-expediente-context-gaps Phase 2: verifies that the tool resolves
categoria from authoritative state (mode_context / shared_context)
instead of trusting the LLM-supplied parameter.

Uses mocks for get_tool_state and ImageService — no DB, no Redis.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.tools.image_tools import enviar_imagenes_ejemplo


# =============================================================================
# Helpers
# =============================================================================


def _make_state(
    conversation_id: str = "test-conv-001",
    mode_context_slug: str | None = None,
    shared_context_slug: str | None = None,
) -> dict:
    """Build a minimal state dict for tool testing."""
    state: dict = {"conversation_id": conversation_id}
    if mode_context_slug is not None:
        state["mode_context"] = {"categoria_slug": mode_context_slug}
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
    @patch("agent.tools.image_tools.get_image_service")
    @patch("agent.tools.image_tools.get_tool_state")
    async def test_state_overrides_llm_supplied_categoria(
        self,
        mock_get_state: MagicMock,
        mock_get_svc: MagicMock,
    ):
        """
        S1: State has categoria_slug='motos-part', tool called with
        categoria='wrong-slug' → queue_example_images called with 'motos-part'.
        """
        mock_get_state.return_value = _make_state(mode_context_slug="motos-part")
        mock_svc = _make_mock_image_service()
        mock_get_svc.return_value = mock_svc

        # Invoke the raw function (bypass @tool decorator)
        result = await enviar_imagenes_ejemplo.afunc(
            tipo="documentacion_base",
            categoria="wrong-slug",
        )

        # Verify ImageService was called with state categoria
        call_kwargs = mock_svc.queue_example_images.call_args
        assert call_kwargs is not None
        # categoria is passed as keyword arg
        actual_cat = call_kwargs.kwargs.get("categoria") or call_kwargs.args[2] if len(call_kwargs.args) > 2 else call_kwargs.kwargs.get("categoria")
        assert actual_cat == "motos-part"

    @pytest.mark.asyncio
    @patch("agent.tools.image_tools.get_image_service")
    @patch("agent.tools.image_tools.get_tool_state")
    async def test_state_matches_llm_no_warning(
        self,
        mock_get_state: MagicMock,
        mock_get_svc: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """
        S2: State has categoria_slug='motos-part', tool called with same
        → no override warning logged.
        """
        mock_get_state.return_value = _make_state(mode_context_slug="motos-part")
        mock_svc = _make_mock_image_service()
        mock_get_svc.return_value = mock_svc

        import logging

        with caplog.at_level(logging.WARNING, logger="agent.tools.image_tools"):
            await enviar_imagenes_ejemplo.afunc(
                tipo="documentacion_base",
                categoria="motos-part",
            )

        assert "categoria_override_from_state" not in caplog.text

    @pytest.mark.asyncio
    @patch("agent.tools.image_tools.get_image_service")
    @patch("agent.tools.image_tools.get_tool_state")
    async def test_no_state_slug_passes_through(
        self,
        mock_get_state: MagicMock,
        mock_get_svc: MagicMock,
    ):
        """
        S3: State has no categoria_slug → tool's categoria param passes through
        unchanged.
        """
        mock_get_state.return_value = _make_state()  # no slug
        mock_svc = _make_mock_image_service()
        mock_get_svc.return_value = mock_svc

        await enviar_imagenes_ejemplo.afunc(
            tipo="documentacion_base",
            categoria="motos-part",
        )

        call_kwargs = mock_svc.queue_example_images.call_args
        assert call_kwargs is not None

    @pytest.mark.asyncio
    @patch("agent.tools.image_tools.get_image_service")
    @patch("agent.tools.image_tools.get_tool_state")
    async def test_state_slug_resolves_when_tool_has_none(
        self,
        mock_get_state: MagicMock,
        mock_get_svc: MagicMock,
    ):
        """
        S4: State has categoria_slug='aseicars', tool called with categoria=None
        → resolves to 'aseicars'.
        """
        mock_get_state.return_value = _make_state(
            shared_context_slug="aseicars"
        )
        mock_svc = _make_mock_image_service()
        mock_get_svc.return_value = mock_svc

        await enviar_imagenes_ejemplo.afunc(
            tipo="documentacion_base",
            categoria=None,
        )

        call_kwargs = mock_svc.queue_example_images.call_args
        assert call_kwargs is not None
