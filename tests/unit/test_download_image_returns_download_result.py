"""
Tests for T2c: download_image() and download_multiple_images() return DownloadResult.

TDD Cycle: T2c — Migrate return types from bytes|None/list[dict] to DownloadResult/list[DownloadResult]

Spec scenarios covered:
  - download_image() success → DownloadResult with success=True and data dict
  - download_image() failure (security error) → DownloadResult with success=False and reason_code
  - download_image() failure (http error) → DownloadResult with success=False
  - download_multiple_images() returns list[DownloadResult] (not list[dict])
  - Callsites that access .data["stored_filename"] etc. still work via .data
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# T2c: download_image returns DownloadResult
# ---------------------------------------------------------------------------


class TestDownloadImageReturnsDownloadResult:
    """download_image() must return DownloadResult (not dict | None)."""

    @pytest.mark.asyncio
    async def test_success_returns_download_result_type(self) -> None:
        """On success, download_image() must return a DownloadResult instance."""
        from api.services.chatwoot_image_service import (
            ChatwootImageService,
            DownloadResult,
        )

        service = _make_service()
        payload = _fake_payload()

        with patch.object(service, "_download_with_retry", new_callable=AsyncMock) as mock_download:
            mock_download.return_value = DownloadResult.ok(payload)
            result = await service.download_image("http://example.com/img.jpg", "test")

        assert isinstance(result, DownloadResult)

    @pytest.mark.asyncio
    async def test_success_result_has_success_true(self) -> None:
        """On success, the DownloadResult must have success=True."""
        from api.services.chatwoot_image_service import (
            ChatwootImageService,
            DownloadResult,
        )

        service = _make_service()
        payload = _fake_payload()

        with patch.object(service, "_download_with_retry", new_callable=AsyncMock) as mock_download:
            mock_download.return_value = DownloadResult.ok(payload)
            result = await service.download_image("http://example.com/img.jpg", "test")

        assert result.success is True

    @pytest.mark.asyncio
    async def test_success_result_data_carries_stored_filename(self) -> None:
        """On success, result.data must carry the stored_filename key."""
        from api.services.chatwoot_image_service import (
            ChatwootImageService,
            DownloadResult,
        )

        service = _make_service()
        payload = _fake_payload()

        with patch.object(service, "_download_with_retry", new_callable=AsyncMock) as mock_download:
            mock_download.return_value = DownloadResult.ok(payload)
            result = await service.download_image("http://example.com/img.jpg", "test")

        assert result.data is not None
        assert result.data["stored_filename"] == "abc123.jpg"

    @pytest.mark.asyncio
    async def test_failure_returns_download_result_with_reason(self) -> None:
        """On security error, download_image() returns DownloadResult with success=False."""
        from api.services.chatwoot_image_service import DownloadResult
        from shared.image_security import ImageSecurityError

        service = _make_service()

        with patch.object(service, "_download_with_retry", new_callable=AsyncMock) as mock_download:
            mock_download.side_effect = ImageSecurityError("File type not allowed: application/x-exe")
            result = await service.download_image("http://example.com/virus.exe", "test")

        assert isinstance(result, DownloadResult)
        assert result.success is False
        assert result.reason_code is not None

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_returns_failure_download_result(self) -> None:
        """When all 3 retries fail, download_image() returns a failed DownloadResult."""
        from api.services.chatwoot_image_service import DownloadResult

        service = _make_service()

        with patch.object(service, "_download_with_retry", new_callable=AsyncMock) as mock_download:
            mock_download.side_effect = Exception("network error")
            result = await service.download_image("http://example.com/img.jpg", "test")

        assert isinstance(result, DownloadResult)
        assert result.success is False


# ---------------------------------------------------------------------------
# T2c: download_multiple_images returns list[DownloadResult]
# ---------------------------------------------------------------------------


class TestDownloadMultipleImagesReturnsListDownloadResult:
    """download_multiple_images() must return list[DownloadResult]."""

    @pytest.mark.asyncio
    async def test_returns_list_of_download_result(self) -> None:
        """download_multiple_images() must return a list of DownloadResult, not dicts."""
        from api.services.chatwoot_image_service import DownloadResult

        service = _make_service()
        images = [
            {"data_url": "http://example.com/1.jpg", "display_name": "img1"},
            {"data_url": "http://example.com/2.jpg", "display_name": "img2"},
        ]

        with patch.object(service, "download_image", new_callable=AsyncMock) as mock_dl:
            mock_dl.side_effect = [
                DownloadResult.ok(_fake_payload()),
                DownloadResult.ok({**_fake_payload(), "stored_filename": "def456.jpg"}),
            ]
            results = await service.download_multiple_images(images)

        assert isinstance(results, list)
        assert len(results) == 2
        assert all(isinstance(r, DownloadResult) for r in results)

    @pytest.mark.asyncio
    async def test_includes_failures_in_result_list(self) -> None:
        """download_multiple_images() must include failure DownloadResults (not filter them out)."""
        from api.services.chatwoot_image_service import DownloadResult

        service = _make_service()
        images = [
            {"data_url": "http://example.com/1.jpg", "display_name": "img1"},
            {"data_url": "http://example.com/2.pdf", "display_name": "img2"},
        ]

        with patch.object(service, "download_image", new_callable=AsyncMock) as mock_dl:
            mock_dl.side_effect = [
                DownloadResult.ok(_fake_payload()),
                DownloadResult.fail("file_type_not_allowed"),
            ]
            results = await service.download_multiple_images(images)

        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False
        assert results[1].reason_code == "file_type_not_allowed"

    @pytest.mark.asyncio
    async def test_exception_in_one_task_returns_failure_result(self) -> None:
        """If one download raises an exception, it becomes a failure DownloadResult."""
        from api.services.chatwoot_image_service import DownloadResult

        service = _make_service()
        images = [
            {"data_url": "http://example.com/1.jpg", "display_name": "img1"},
            {"data_url": "http://example.com/2.jpg", "display_name": "img2"},
        ]

        with patch.object(service, "download_image", new_callable=AsyncMock) as mock_dl:
            mock_dl.side_effect = [
                DownloadResult.ok(_fake_payload()),
                Exception("unexpected crash"),
            ]
            results = await service.download_multiple_images(images)

        # Exception cases become a failure DownloadResult in the new API
        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service():
    """Create a ChatwootImageService without calling __init__ (avoids settings dependency)."""
    from api.services.chatwoot_image_service import ChatwootImageService
    from pathlib import Path

    service = ChatwootImageService.__new__(ChatwootImageService)
    service.case_images_dir = Path("/tmp/test_images")
    service.base_url = "http://localhost:8000/images"
    service.max_size = 15 * 1024 * 1024
    service.chatwoot_api_url = "http://chatwoot.example.com"
    service.chatwoot_api_token = "test-token"
    service.chatwoot_storage_domain = ""
    service.allowed_domains = ["chatwoot.example.com"]
    return service


def _fake_payload() -> dict[str, Any]:
    return {
        "stored_filename": "abc123.jpg",
        "original_filename": "photo.jpg",
        "mime_type": "image/jpeg",
        "file_size": 1024,
        "width": 800,
        "height": 600,
        "display_name": "test",
        "element_code": None,
        "file_path": "/tmp/test_images/abc123.jpg",
    }
