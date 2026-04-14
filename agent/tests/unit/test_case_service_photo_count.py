"""
Unit tests for get_case_status photo count per element.

T6 — fix-image-batch-ux:
  - element_status entries include a "photos" key
  - photos count reflects actual images per element_code from DB
  - elements with no photos get photos=0
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.utils.expediente_types import CollectionStep

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_CASE_ID = "00000000-0000-0000-0000-000000000002"


def _make_case_image(element_code: str | None) -> MagicMock:
    img = MagicMock()
    img.element_code = element_code
    return img


def _make_db_case(
    element_codes: list[str],
    element_data_statuses: dict[str, str],
    images: list[MagicMock],
) -> MagicMock:
    db_case = MagicMock()
    db_case.id = _FAKE_CASE_ID
    db_case.status = "open"
    db_case.element_codes = element_codes
    db_case.images = images
    db_case.tariff_amount = None
    db_case.taller_propio = None
    db_case.taller_nombre = None
    db_case.itv_nombre = None
    db_case.vehiculo_marca = "Honda"
    db_case.vehiculo_modelo = "CBR"
    db_case.vehiculo_anio = "2020"
    db_case.vehiculo_matricula = "1234ABC"
    db_case.vehiculo_bastidor = "WVWZZZ3CZWE123456"
    db_case.user = None

    ced_list = []
    for code, status in element_data_statuses.items():
        ced = MagicMock()
        ced.element_code = code
        ced.status = status
        ced_list.append(ced)
    db_case.element_data = ced_list

    return db_case


def _patch_get_case_status(db_case: MagicMock, case_id: str = _FAKE_CASE_ID):
    """Minimal patches to make get_case_status reach the element_status block."""
    _mc = {
        "mode": "EXPEDIENTE_MODE",
        "case_collection_state": {
            "case_id": case_id,
            "current_step": CollectionStep.COLLECT_ELEMENT_DATA.value,
            "element_codes": db_case.element_codes,
            "element_data_status": {},
            "personal_data": {},
            "vehicle_data": {},
            "taller_propio": None,
        },
    }

    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none = MagicMock(return_value=db_case)

    mock_session_cm = AsyncMock()
    mock_session_cm.execute = AsyncMock(return_value=mock_scalar)

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session_cm)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

    return [
        patch(
            "agent.services.case_service.is_collection_active",
            return_value=True,
        ),
        patch(
            "agent.services.case_service.get_mode_context",
            return_value=_mc["case_collection_state"],
        ),
        patch(
            "agent.services.case_service._get_case_id_with_fallback",
            return_value=case_id,
        ),
        patch(
            "agent.services.case_service.get_async_session",
            return_value=mock_session_ctx,
        ),
        patch(
            "agent.services.case_service.get_current_step",
            return_value=CollectionStep.COLLECT_ELEMENT_DATA,
        ),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetCaseStatusPhotoCount:
    @pytest.mark.asyncio
    async def test_element_status_includes_photos_key(self):
        """Every entry in element_status must have a 'photos' key."""
        from agent.services.case_service import get_case_status

        images = [_make_case_image("SUSPENSION"), _make_case_image("SUSPENSION")]
        db_case = _make_db_case(
            element_codes=["SUSPENSION"],
            element_data_statuses={"SUSPENSION": "pending_photos"},
            images=images,
        )
        patches = _patch_get_case_status(db_case)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = await get_case_status(state={})

        assert result["success"] is True
        element_status = result["element_status"]
        assert len(element_status) == 1
        assert "photos" in element_status[0], (
            f"'photos' key missing in element_status entry: {element_status[0]}"
        )

    @pytest.mark.asyncio
    async def test_photo_count_matches_db_images(self):
        """photos count must equal the number of images with that element_code."""
        from agent.services.case_service import get_case_status

        images = [
            _make_case_image("FRENOS"),
            _make_case_image("FRENOS"),
            _make_case_image("FRENOS"),
            _make_case_image("SUSPENSION"),
        ]
        db_case = _make_db_case(
            element_codes=["FRENOS", "SUSPENSION"],
            element_data_statuses={},
            images=images,
        )
        patches = _patch_get_case_status(db_case)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = await get_case_status(state={})

        element_status = {e["code"]: e for e in result["element_status"]}
        assert element_status["FRENOS"]["photos"] == 3
        assert element_status["SUSPENSION"]["photos"] == 1

    @pytest.mark.asyncio
    async def test_element_with_no_photos_gets_zero(self):
        """Elements not present in any image get photos=0."""
        from agent.services.case_service import get_case_status

        images = [_make_case_image("FRENOS")]
        db_case = _make_db_case(
            element_codes=["FRENOS", "LUCES"],
            element_data_statuses={},
            images=images,
        )
        patches = _patch_get_case_status(db_case)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = await get_case_status(state={})

        element_status = {e["code"]: e for e in result["element_status"]}
        assert element_status["LUCES"]["photos"] == 0

    @pytest.mark.asyncio
    async def test_images_without_element_code_ignored(self):
        """Images with element_code=None must not be counted for any element."""
        from agent.services.case_service import get_case_status

        images = [
            _make_case_image(None),
            _make_case_image(None),
            _make_case_image("FRENOS"),
        ]
        db_case = _make_db_case(
            element_codes=["FRENOS"],
            element_data_statuses={},
            images=images,
        )
        patches = _patch_get_case_status(db_case)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = await get_case_status(state={})

        element_status = result["element_status"]
        assert element_status[0]["photos"] == 1
