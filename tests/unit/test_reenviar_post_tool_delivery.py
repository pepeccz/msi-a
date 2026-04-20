"""
T06: Failing tests for `reenviar_imagenes_elemento` pending_images capture
in expediente_post_tool_hook.

Spec scenario covered:
  Scenario 8 — reenviar_imagenes_elemento sets _pending_images in result dict →
                expediente_post_tool_hook must capture it in updates["_pending_images"]

Additional coverage:
  - NOT captured when success=False (guard preserved)
  - enviar_imagenes_ejemplo path still works (regression)
  - Double-capture prevention: reenviar without _pending_images → no key added

Pattern mirrors test_expediente_post_tool_hook.py.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(mode_context: dict | None = None) -> dict:
    return {
        "messages": [HumanMessage(content="Mostrame las fotos")],
        "_mode_context": mode_context or {},
        "_conversation_id": "test-conv-reenviar-001",
    }


def _make_reenviar_result_success(images: list | None = None) -> dict:
    """Result from reenviar_imagenes_elemento with _pending_images set."""
    imgs = images or [
        {"url": "https://cdn.example.com/escape1.jpg", "tipo": "elemento"},
        {"url": "https://cdn.example.com/escape2.jpg", "tipo": "elemento"},
    ]
    return {
        "success": True,
        "message": "Aquí tienes las fotos de ejemplo de ESCAPE",
        "_pending_images": {"images": imgs},
    }


def _make_reenviar_result_error() -> dict:
    """Result from reenviar_imagenes_elemento when tool returns error."""
    return {
        "success": False,
        "error": "Element not found",
        "message": "No se encontraron fotos para ese elemento",
    }


def _make_reenviar_result_no_pending() -> dict:
    """Success result but without _pending_images (edge case)."""
    return {
        "success": True,
        "message": "Procesado",
    }


def _make_enviar_result_success() -> dict:
    """Normal enviar_imagenes_ejemplo success result with _pending_images."""
    return {
        "success": True,
        "message": "Fotos enviadas",
        "_pending_images": {
            "images": [{"url": "https://cdn.example.com/img.jpg", "tipo": "elemento"}]
        },
    }


# ===========================================================================
# Scenario 8: reenviar_imagenes_elemento → _pending_images captured
# ===========================================================================


class TestRenviarPostToolCapture:
    """expediente_post_tool_hook captures _pending_images for reenviar_imagenes_elemento."""

    @pytest.mark.asyncio
    async def test_reenviar_pending_images_captured(self):
        """
        Spec Scenario 8: reenviar_imagenes_elemento result has _pending_images →
        hook must capture it in updates["_pending_images"].
        """
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        state = _make_state()
        result = _make_reenviar_result_success()

        updates = await expediente_post_tool_hook(
            "reenviar_imagenes_elemento", result, state
        )

        assert "_pending_images" in updates, (
            "expediente_post_tool_hook must capture _pending_images "
            "for reenviar_imagenes_elemento. "
            f"Got updates keys: {list(updates.keys())}"
        )
        assert updates["_pending_images"] == result["_pending_images"], (
            "Captured _pending_images must match the tool result's _pending_images"
        )

    @pytest.mark.asyncio
    async def test_reenviar_pending_images_contains_images_list(self):
        """
        Captured _pending_images must be the dict with 'images' key
        (the shape the delivery pipeline expects).
        """
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        imgs = [
            {"url": "https://cdn.example.com/a.jpg", "tipo": "elemento"},
            {"url": "https://cdn.example.com/b.jpg", "tipo": "elemento"},
        ]
        state = _make_state()
        result = _make_reenviar_result_success(images=imgs)

        updates = await expediente_post_tool_hook(
            "reenviar_imagenes_elemento", result, state
        )

        pending = updates.get("_pending_images", {})
        assert "images" in pending, (
            f"_pending_images must contain 'images' key. Got: {pending}"
        )
        assert pending["images"] == imgs

    # ===========================================================================
    # NOT captured when success=False
    # ===========================================================================

    @pytest.mark.asyncio
    async def test_reenviar_not_captured_when_success_false(self):
        """
        When reenviar_imagenes_elemento returns success=False,
        _pending_images must NOT be captured (guard preserved).
        """
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        state = _make_state()
        result = _make_reenviar_result_error()

        updates = await expediente_post_tool_hook(
            "reenviar_imagenes_elemento", result, state
        )

        assert "_pending_images" not in updates, (
            "Hook must NOT capture _pending_images when success=False. "
            f"Got updates: {updates}"
        )

    @pytest.mark.asyncio
    async def test_reenviar_no_pending_images_in_result_no_key_added(self):
        """
        reenviar_imagenes_elemento success but no _pending_images in result →
        no _pending_images key in updates (don't add None).
        """
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        state = _make_state()
        result = _make_reenviar_result_no_pending()

        updates = await expediente_post_tool_hook(
            "reenviar_imagenes_elemento", result, state
        )

        assert "_pending_images" not in updates, (
            "Hook must not add _pending_images key when result has none. "
            f"Got updates: {updates}"
        )

    # ===========================================================================
    # Regression: enviar_imagenes_ejemplo still works
    # ===========================================================================

    @pytest.mark.asyncio
    async def test_enviar_imagenes_still_captured_regression(self):
        """
        Regression: enviar_imagenes_ejemplo path must still capture _pending_images.
        Broadening the condition must not break the original tool.
        """
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        state = _make_state()
        result = _make_enviar_result_success()

        updates = await expediente_post_tool_hook(
            "enviar_imagenes_ejemplo", result, state
        )

        assert "_pending_images" in updates, (
            "enviar_imagenes_ejemplo must still have _pending_images captured "
            "after the condition is broadened. "
            f"Got updates keys: {list(updates.keys())}"
        )
        assert updates["_pending_images"] == result["_pending_images"]

    @pytest.mark.asyncio
    async def test_enviar_imagenes_not_captured_when_success_false_regression(self):
        """
        Regression: enviar_imagenes_ejemplo with success=False must NOT capture
        _pending_images (guard preserved for both tools).
        """
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        state = _make_state()
        result = {
            "success": False,
            "already_sent": True,
            "tool_name": "enviar_imagenes_ejemplo",
            "message": "Ya enviadas",
            "_pending_images": {"images": []},  # present but success=False
        }

        updates = await expediente_post_tool_hook(
            "enviar_imagenes_ejemplo", result, state
        )

        assert "_pending_images" not in updates, (
            "Hook must NOT capture _pending_images when success=False for enviar_imagenes_ejemplo. "
            f"Got updates: {updates}"
        )

    # ===========================================================================
    # Other tools: not affected
    # ===========================================================================

    @pytest.mark.asyncio
    async def test_other_tool_with_pending_images_not_captured(self):
        """
        A random other tool that happens to have _pending_images in result →
        must NOT be captured (only _IMAGE_EMITTING_TOOLS are handled).
        """
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        state = _make_state()
        result = {
            "success": True,
            "_pending_images": {"images": [{"url": "https://x.com/img.jpg"}]},
        }

        updates = await expediente_post_tool_hook(
            "some_random_tool", result, state
        )

        assert "_pending_images" not in updates, (
            "Only image-emitting tools should have _pending_images captured. "
            f"Got updates keys: {list(updates.keys())}"
        )
