"""
T-07: Tests for delta-aware _queue_presupuesto in ImageService.

Verifies:
- Images for already-sent element codes are filtered out
- Base docs filtered when "_BASE_DOCS" in sent codes
- All-sent returns full list (allow resend), NOT error
- sent_element_codes and sent_base_docs in success result
- Empty imagenes_enviadas_codigos → no filtering (original behavior)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_image(element_code: str | None, tipo: str = "elemento", status: str = "active") -> dict:
    img = {"url": f"https://example.com/{element_code or tipo}.jpg", "status": status, "tipo": tipo}
    if element_code:
        img["element_code"] = element_code
    return img


def _make_base_image(status: str = "active") -> dict:
    return {"url": "https://example.com/base.jpg", "status": status, "tipo": "base"}


def _make_tarifa_calculada(images: list[dict]) -> dict:
    return {
        "imagenes_ejemplo": images,
        "datos": {"element_codes": ["ESCAPE", "SUSPENSION"]},
    }


def _make_state_context(
    tarifa_calculada: dict | None = None,
    imagenes_enviadas_codigos: list[str] | None = None,
    current_mode: str = "PRE_EXPEDIENTE_MODE",
) -> dict:
    mode_context: dict = {}
    if tarifa_calculada is not None:
        mode_context["tarifa_calculada"] = tarifa_calculada
    if imagenes_enviadas_codigos is not None:
        mode_context["imagenes_enviadas_codigos"] = imagenes_enviadas_codigos
    mode_context["element_codes"] = ["ESCAPE", "SUSPENSION"]
    return {
        "mode_context": mode_context,
        "current_mode": current_mode,
    }


# ===========================================================================
# Tests
# ===========================================================================


class TestDeltaFiltering:
    """T-07: Delta filtering removes already-sent images."""

    @pytest.mark.asyncio
    async def test_empty_sent_codes_no_filtering(self):
        """When imagenes_enviadas_codigos is empty, all active images are queued."""
        from agent.services.image_service import ImageService

        images = [
            _make_image("ESCAPE"),
            _make_image("SUSPENSION"),
            _make_base_image(),
        ]
        tarifa = _make_tarifa_calculada(images)
        state_context = _make_state_context(
            tarifa_calculada=tarifa,
            imagenes_enviadas_codigos=[],
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="conv-001",
        )

        assert result["success"] is True
        queued = result["images_to_queue"]
        assert len(queued) == 3, f"Expected 3 images, got {len(queued)}: {queued}"

    @pytest.mark.asyncio
    async def test_already_sent_element_filtered_out(self):
        """Images for already-sent element codes must be filtered from the queue."""
        from agent.services.image_service import ImageService

        images = [
            _make_image("ESCAPE"),
            _make_image("SUSPENSION"),
        ]
        tarifa = _make_tarifa_calculada(images)
        state_context = _make_state_context(
            tarifa_calculada=tarifa,
            imagenes_enviadas_codigos=["ESCAPE"],  # ESCAPE already sent
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="conv-001",
        )

        assert result["success"] is True
        queued = result["images_to_queue"]
        # Only SUSPENSION should remain
        codes_in_queue = {img.get("element_code") for img in queued}
        assert "ESCAPE" not in codes_in_queue, (
            f"ESCAPE was already sent and must be filtered out, but found in: {codes_in_queue}"
        )
        assert "SUSPENSION" in codes_in_queue, (
            f"SUSPENSION was not sent and must remain in queue, but missing from: {codes_in_queue}"
        )

    @pytest.mark.asyncio
    async def test_base_docs_filtered_when_sentinel_present(self):
        """Base-doc images must be filtered when '_BASE_DOCS' in imagenes_enviadas_codigos."""
        from agent.services.image_service import ImageService

        images = [
            _make_image("ESCAPE"),
            _make_base_image(),
        ]
        tarifa = _make_tarifa_calculada(images)
        state_context = _make_state_context(
            tarifa_calculada=tarifa,
            imagenes_enviadas_codigos=["_BASE_DOCS"],  # base docs already sent
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="conv-001",
        )

        assert result["success"] is True
        queued = result["images_to_queue"]
        base_in_queue = [img for img in queued if img.get("tipo") == "base"]
        assert len(base_in_queue) == 0, (
            f"Base docs must be filtered when '_BASE_DOCS' in sent codes, but found: {base_in_queue}"
        )

    @pytest.mark.asyncio
    async def test_all_sent_allows_full_resend(self):
        """When all images are already sent, full resend must be allowed (not an error)."""
        from agent.services.image_service import ImageService

        images = [
            _make_image("ESCAPE"),
            _make_image("SUSPENSION"),
        ]
        tarifa = _make_tarifa_calculada(images)
        state_context = _make_state_context(
            tarifa_calculada=tarifa,
            imagenes_enviadas_codigos=["ESCAPE", "SUSPENSION"],  # all sent
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="conv-001",
        )

        # Must return success, NOT error
        assert result["success"] is True, (
            f"All-sent must return success (allow resend), got: {result.get('message')}"
        )
        queued = result["images_to_queue"]
        assert len(queued) == 2, (
            f"Full resend must queue all active images, got {len(queued)}: {queued}"
        )

    @pytest.mark.asyncio
    async def test_sent_element_codes_in_success_result(self):
        """Success result must include 'sent_element_codes' key."""
        from agent.services.image_service import ImageService

        images = [
            _make_image("ESCAPE"),
            _make_image("ESCAPE"),  # duplicate code — should dedup
            _make_image("SUSPENSION"),
        ]
        tarifa = _make_tarifa_calculada(images)
        state_context = _make_state_context(
            tarifa_calculada=tarifa,
            imagenes_enviadas_codigos=[],
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="conv-001",
        )

        assert result["success"] is True
        assert "sent_element_codes" in result, (
            "Success result must contain 'sent_element_codes'"
        )
        sent = result["sent_element_codes"]
        assert isinstance(sent, list), f"sent_element_codes must be a list, got: {type(sent)}"
        assert "ESCAPE" in sent
        assert "SUSPENSION" in sent
        # No duplicates
        assert len([c for c in sent if c == "ESCAPE"]) == 1, "sent_element_codes must not have duplicates"

    @pytest.mark.asyncio
    async def test_sent_base_docs_in_success_result_when_base_present(self):
        """sent_base_docs must be True when base images are queued."""
        from agent.services.image_service import ImageService

        images = [
            _make_image("ESCAPE"),
            _make_base_image(),
        ]
        tarifa = _make_tarifa_calculada(images)
        state_context = _make_state_context(
            tarifa_calculada=tarifa,
            imagenes_enviadas_codigos=[],
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="conv-001",
        )

        assert result["success"] is True
        assert result.get("sent_base_docs") is True, (
            "sent_base_docs must be True when base images were queued"
        )

    @pytest.mark.asyncio
    async def test_placeholder_images_never_queued(self):
        """Placeholder images must never be queued regardless of delta state."""
        from agent.services.image_service import ImageService

        images = [
            _make_image("ESCAPE", status="active"),
            _make_image("SUSPENSION", status="placeholder"),
        ]
        tarifa = _make_tarifa_calculada(images)
        state_context = _make_state_context(
            tarifa_calculada=tarifa,
            imagenes_enviadas_codigos=[],
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="conv-001",
        )

        assert result["success"] is True
        queued = result["images_to_queue"]
        placeholder_codes = [img.get("element_code") for img in queued if img.get("element_code") == "SUSPENSION"]
        assert len(placeholder_codes) == 0, "Placeholder images must never be queued"

    @pytest.mark.asyncio
    async def test_image_without_element_code_always_included(self):
        """Images with no element_code and no tipo='base' must always be included."""
        from agent.services.image_service import ImageService

        images = [
            {"url": "https://example.com/unknown.jpg", "status": "active"},  # no element_code, no tipo
            _make_image("ESCAPE"),
        ]
        tarifa = _make_tarifa_calculada(images)
        state_context = _make_state_context(
            tarifa_calculada=tarifa,
            imagenes_enviadas_codigos=["ESCAPE", "_BASE_DOCS"],  # aggressive filter
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="conv-001",
        )

        # ESCAPE is filtered. The unknown image has no code → must be included.
        # But all_sent check kicks in (ESCAPE filtered, unknown unknown code → included → not empty)
        assert result["success"] is True
        queued = result["images_to_queue"]
        unknown_present = any(not img.get("element_code") and not img.get("tipo") for img in queued)
        assert unknown_present, "Image with unknown origin must always be included"
