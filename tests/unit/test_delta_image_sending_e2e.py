"""
T-15: End-to-end unit tests for delta image sending flow.

Tests the full delta flow using ImageService._queue_presupuesto with
different mode_context states, covering the complete conversation arc:
  1. First identification + tariff + images → all images sent, codes tracked
  2. Second identification (add element) + tariff + images → only NEW images sent
  3. All-sent scenario → allows resend (not an error)
  4. Base docs sentinel filtering works
  5. Legacy bool backward compat (old checkpoint with bool only → no delta filtering)

These are unit tests that mock nothing — they test _queue_presupuesto directly.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Fixtures / factories
# ---------------------------------------------------------------------------


def _img(element_code: str | None, tipo: str = "elemento", status: str = "active") -> dict:
    img: dict = {
        "url": f"https://cdn.example.com/{element_code or tipo}.jpg",
        "status": status,
        "tipo": tipo,
    }
    if element_code:
        img["element_code"] = element_code
    return img


def _base_img(status: str = "active") -> dict:
    return {"url": "https://cdn.example.com/base.jpg", "status": status, "tipo": "base"}


def _tarifa(element_codes: list[str], images: list[dict]) -> dict:
    return {
        "imagenes_ejemplo": images,
        "datos": {"element_codes": element_codes},
        "precio": 410.0,
    }


def _state(
    tarifa_calculada: dict,
    element_codes: list[str],
    imagenes_enviadas_codigos: list[str] | None = None,
    imagenes_enviadas: bool | None = None,
) -> dict:
    """Build a minimal state_context that mirrors what ImageService reads."""
    mc: dict = {
        "tarifa_calculada": tarifa_calculada,
        "element_codes": element_codes,
    }
    if imagenes_enviadas_codigos is not None:
        mc["imagenes_enviadas_codigos"] = imagenes_enviadas_codigos
    if imagenes_enviadas is not None:
        mc["imagenes_enviadas"] = imagenes_enviadas
    return {
        "mode_context": mc,
        "current_mode": "PRE_EXPEDIENTE_MODE",
    }


# ===========================================================================
# T-15 — Full delta flow (5 scenarios)
# ===========================================================================


class TestDeltaE2E:
    """End-to-end delta image sending scenarios."""

    # ------------------------------------------------------------------
    # Scenario 1: First identification → all images sent, codes tracked
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_first_call_all_images_queued(self):
        """
        First identification flow: imagenes_enviadas_codigos is empty.
        All active images must be queued.
        """
        from agent.services.image_service import ImageService

        images = [
            _img("ESCAPE"),
            _img("SUSPENSION"),
            _base_img(),
        ]
        tarifa = _tarifa(["ESCAPE", "SUSPENSION"], images)
        state_context = _state(
            tarifa_calculada=tarifa,
            element_codes=["ESCAPE", "SUSPENSION"],
            imagenes_enviadas_codigos=[],
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="e2e-001",
        )

        assert result["success"] is True
        queued = result["images_to_queue"]
        assert len(queued) == 3, f"All 3 images must be queued on first call, got: {len(queued)}"

        # sent_element_codes must track what was sent
        sent_codes = result.get("sent_element_codes", [])
        assert "ESCAPE" in sent_codes
        assert "SUSPENSION" in sent_codes
        assert result.get("sent_base_docs") is True

    @pytest.mark.asyncio
    async def test_first_call_no_codigos_field(self):
        """
        Old state without imagenes_enviadas_codigos field at all → behaves like empty.
        All images sent.
        """
        from agent.services.image_service import ImageService

        images = [_img("ESCAPE"), _img("SUSPENSION")]
        tarifa = _tarifa(["ESCAPE", "SUSPENSION"], images)
        state_context = _state(
            tarifa_calculada=tarifa,
            element_codes=["ESCAPE", "SUSPENSION"],
            # imagenes_enviadas_codigos NOT set
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="e2e-002",
        )

        assert result["success"] is True
        assert len(result["images_to_queue"]) == 2

    # ------------------------------------------------------------------
    # Scenario 2: New element added — only NEW element images sent
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_second_call_new_element_only_new_images(self):
        """
        Second identification: user adds SUSPENSION after ESCAPE was already sent.
        Only SUSPENSION images must be queued.
        """
        from agent.services.image_service import ImageService

        images = [
            _img("ESCAPE"),
            _img("SUSPENSION"),
        ]
        tarifa = _tarifa(["ESCAPE", "SUSPENSION"], images)
        state_context = _state(
            tarifa_calculada=tarifa,
            element_codes=["ESCAPE", "SUSPENSION"],
            imagenes_enviadas_codigos=["ESCAPE"],  # ESCAPE was already sent in previous turn
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="e2e-003",
        )

        assert result["success"] is True
        queued = result["images_to_queue"]
        codes_queued = {img.get("element_code") for img in queued}

        assert "ESCAPE" not in codes_queued, "ESCAPE was already sent — must not be re-queued"
        assert "SUSPENSION" in codes_queued, "SUSPENSION is new — must be queued"
        assert len(queued) == 1, f"Only 1 image (SUSPENSION) must be queued, got {len(queued)}"

    @pytest.mark.asyncio
    async def test_second_call_sent_codes_reflect_new_element(self):
        """
        After delta filtering, sent_element_codes must contain only the newly sent element.
        """
        from agent.services.image_service import ImageService

        images = [_img("ESCAPE"), _img("SUSPENSION")]
        tarifa = _tarifa(["ESCAPE", "SUSPENSION"], images)
        state_context = _state(
            tarifa_calculada=tarifa,
            element_codes=["ESCAPE", "SUSPENSION"],
            imagenes_enviadas_codigos=["ESCAPE"],
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="e2e-004",
        )

        assert result["success"] is True
        sent_codes = result.get("sent_element_codes", [])
        assert sent_codes == ["SUSPENSION"], (
            f"Only SUSPENSION should be in sent_element_codes for this batch, got: {sent_codes}"
        )

    # ------------------------------------------------------------------
    # Scenario 3: All sent — allows full resend (not error)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_all_sent_returns_success_with_full_resend(self):
        """
        When all element codes are in imagenes_enviadas_codigos, allow full resend.
        This is the 'user asks to see photos again' case.
        """
        from agent.services.image_service import ImageService

        images = [_img("ESCAPE"), _img("SUSPENSION")]
        tarifa = _tarifa(["ESCAPE", "SUSPENSION"], images)
        state_context = _state(
            tarifa_calculada=tarifa,
            element_codes=["ESCAPE", "SUSPENSION"],
            imagenes_enviadas_codigos=["ESCAPE", "SUSPENSION"],  # both already sent
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="e2e-005",
        )

        assert result["success"] is True, (
            f"All-sent must return success (allow resend), not error. Got: {result.get('message')}"
        )
        queued = result["images_to_queue"]
        assert len(queued) == 2, (
            f"Full resend must include all active images, got {len(queued)}: {queued}"
        )

    @pytest.mark.asyncio
    async def test_all_sent_with_base_docs_returns_success(self):
        """
        All images (element + base) sent → full resend on both.
        """
        from agent.services.image_service import ImageService

        images = [_img("ESCAPE"), _base_img()]
        tarifa = _tarifa(["ESCAPE"], images)
        state_context = _state(
            tarifa_calculada=tarifa,
            element_codes=["ESCAPE"],
            imagenes_enviadas_codigos=["ESCAPE", "_BASE_DOCS"],
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="e2e-006",
        )

        assert result["success"] is True
        assert len(result["images_to_queue"]) == 2

    # ------------------------------------------------------------------
    # Scenario 4: Base docs sentinel filtering
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_base_docs_sentinel_filters_base_images(self):
        """
        '_BASE_DOCS' in imagenes_enviadas_codigos → base images filtered.
        Non-base images are not affected.
        """
        from agent.services.image_service import ImageService

        images = [
            _img("ESCAPE"),
            _base_img(),
            _base_img(),  # two base images
        ]
        tarifa = _tarifa(["ESCAPE"], images)
        state_context = _state(
            tarifa_calculada=tarifa,
            element_codes=["ESCAPE"],
            imagenes_enviadas_codigos=["_BASE_DOCS"],
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="e2e-007",
        )

        assert result["success"] is True
        queued = result["images_to_queue"]
        base_in_queue = [img for img in queued if img.get("tipo") == "base"]
        assert len(base_in_queue) == 0, "Base docs must be filtered when '_BASE_DOCS' in sent codes"
        # ESCAPE must still be queued
        escape_in_queue = [img for img in queued if img.get("element_code") == "ESCAPE"]
        assert len(escape_in_queue) == 1, "ESCAPE must still be queued"

    @pytest.mark.asyncio
    async def test_base_docs_sentinel_not_present_base_included(self):
        """
        '_BASE_DOCS' NOT in sent codes → base images are queued normally.
        """
        from agent.services.image_service import ImageService

        images = [_img("ESCAPE"), _base_img()]
        tarifa = _tarifa(["ESCAPE"], images)
        state_context = _state(
            tarifa_calculada=tarifa,
            element_codes=["ESCAPE"],
            imagenes_enviadas_codigos=[],
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="e2e-008",
        )

        assert result["success"] is True
        queued = result["images_to_queue"]
        base_in_queue = [img for img in queued if img.get("tipo") == "base"]
        assert len(base_in_queue) == 1, "Base images must be queued when '_BASE_DOCS' not in sent codes"

    # ------------------------------------------------------------------
    # Scenario 5: Legacy bool backward compat
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_legacy_bool_only_no_delta_filtering(self):
        """
        Old checkpoint: imagenes_enviadas=True but no imagenes_enviadas_codigos list.
        The old bool guard was removed — delta logic must not filter anything
        when the list is absent/empty. All images are sent.
        """
        from agent.services.image_service import ImageService

        images = [_img("ESCAPE"), _img("SUSPENSION")]
        tarifa = _tarifa(["ESCAPE", "SUSPENSION"], images)
        # Simulate old checkpoint: bool set, list absent
        state_context = _state(
            tarifa_calculada=tarifa,
            element_codes=["ESCAPE", "SUSPENSION"],
            imagenes_enviadas=True,  # old bool — should NOT trigger delta filtering
            # imagenes_enviadas_codigos absent
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="e2e-009",
        )

        # Without the list, delta can't filter — all images sent
        assert result["success"] is True
        queued = result["images_to_queue"]
        assert len(queued) == 2, (
            "Legacy bool-only state must not trigger delta filtering — all images must be sent"
        )

    @pytest.mark.asyncio
    async def test_legacy_bool_with_empty_list_no_filtering(self):
        """
        Mixed state: imagenes_enviadas=True AND imagenes_enviadas_codigos=[].
        Empty list means 'first send' — no delta filtering, all images sent.
        """
        from agent.services.image_service import ImageService

        images = [_img("ESCAPE"), _img("SUSPENSION")]
        tarifa = _tarifa(["ESCAPE", "SUSPENSION"], images)
        state_context = _state(
            tarifa_calculada=tarifa,
            element_codes=["ESCAPE", "SUSPENSION"],
            imagenes_enviadas=True,
            imagenes_enviadas_codigos=[],
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="e2e-010",
        )

        assert result["success"] is True
        assert len(result["images_to_queue"]) == 2

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_placeholder_images_never_included(self):
        """
        Placeholder images must be excluded regardless of delta state.
        """
        from agent.services.image_service import ImageService

        images = [
            _img("ESCAPE", status="active"),
            _img("SUSPENSION", status="placeholder"),
            _base_img(status="placeholder"),
        ]
        tarifa = _tarifa(["ESCAPE", "SUSPENSION"], images)
        state_context = _state(
            tarifa_calculada=tarifa,
            element_codes=["ESCAPE", "SUSPENSION"],
            imagenes_enviadas_codigos=[],
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="e2e-011",
        )

        assert result["success"] is True
        queued = result["images_to_queue"]
        # Only ESCAPE (active) must be queued
        assert len(queued) == 1
        assert queued[0]["element_code"] == "ESCAPE"

    @pytest.mark.asyncio
    async def test_unknown_origin_image_always_included(self):
        """
        Images with no element_code and no tipo='base' are unknown origin.
        They must always be included even when other codes are filtered.
        """
        from agent.services.image_service import ImageService

        images = [
            _img("ESCAPE"),
            {"url": "https://cdn.example.com/misc.jpg", "status": "active"},  # no code, no tipo
        ]
        tarifa = _tarifa(["ESCAPE"], images)
        state_context = _state(
            tarifa_calculada=tarifa,
            element_codes=["ESCAPE"],
            imagenes_enviadas_codigos=["ESCAPE"],  # ESCAPE already sent
        )

        svc = ImageService()
        result = await svc._queue_presupuesto(
            state_context=state_context,
            follow_up_message=None,
            conversation_id="e2e-012",
        )

        # ESCAPE filtered. Unknown image → always included.
        # Since there are remaining images (unknown), this is NOT the all-sent path.
        assert result["success"] is True
        queued = result["images_to_queue"]
        unknown_present = any(
            not img.get("element_code") and not img.get("tipo") for img in queued
        )
        assert unknown_present, "Unknown-origin image must always be included in queue"
        # ESCAPE must NOT be in queue
        escape_present = any(img.get("element_code") == "ESCAPE" for img in queued)
        assert not escape_present, "ESCAPE is already sent and must be filtered"
