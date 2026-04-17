"""
Tests for DownloadResult dataclass in api/services/chatwoot_image_service.py

TDD Cycle: T2a — DownloadResult dataclass + factory helpers

Spec scenarios covered:
  - DownloadResult.ok() returns success=True, data=payload, reason_code=None, reason_message=None
  - DownloadResult.fail(code) returns success=False, data=None, reason_code=code, reason_message from REASON_MESSAGES
  - All 7 canonical reason codes are accepted by fail()
  - frozen=True: instances are immutable
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# T2a: DownloadResult.ok() shape
# ---------------------------------------------------------------------------


class TestDownloadResultOk:
    """DownloadResult.ok(payload) must return a success result with the payload."""

    def test_ok_sets_success_true(self) -> None:
        """ok() must set success=True."""
        from api.services.chatwoot_image_service import DownloadResult

        result = DownloadResult.ok({"stored_filename": "abc.jpg"})
        assert result.success is True

    def test_ok_carries_payload_in_data(self) -> None:
        """ok() must set data to the provided payload dict."""
        from api.services.chatwoot_image_service import DownloadResult

        payload = {"stored_filename": "abc.jpg", "mime_type": "image/jpeg"}
        result = DownloadResult.ok(payload)
        assert result.data == payload

    def test_ok_reason_code_is_none(self) -> None:
        """ok() must set reason_code=None (no failure reason on success)."""
        from api.services.chatwoot_image_service import DownloadResult

        result = DownloadResult.ok({"stored_filename": "abc.jpg"})
        assert result.reason_code is None

    def test_ok_reason_message_is_none(self) -> None:
        """ok() must set reason_message=None (no error message on success)."""
        from api.services.chatwoot_image_service import DownloadResult

        result = DownloadResult.ok({"stored_filename": "abc.jpg"})
        assert result.reason_message is None

    def test_ok_is_frozen(self) -> None:
        """DownloadResult must be frozen (immutable)."""
        from api.services.chatwoot_image_service import DownloadResult

        result = DownloadResult.ok({"stored_filename": "abc.jpg"})
        with pytest.raises((AttributeError, TypeError)):
            result.success = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# T2a: DownloadResult.fail(code) shape — one test per reason code
# ---------------------------------------------------------------------------

ALL_REASON_CODES = [
    "pdf_too_many_pages",
    "file_too_large",
    "file_type_not_allowed",
    "pdf_dangerous_content",
    "url_rejected",
    "corrupt_or_mismatch",
    "fallback_unknown",
]


class TestDownloadResultFail:
    """DownloadResult.fail(code) must return a failure result with reason fields populated."""

    @pytest.mark.parametrize("code", ALL_REASON_CODES)
    def test_fail_sets_success_false(self, code: str) -> None:
        """fail() must set success=False for all 7 reason codes."""
        from api.services.chatwoot_image_service import DownloadResult

        result = DownloadResult.fail(code)
        assert result.success is False

    @pytest.mark.parametrize("code", ALL_REASON_CODES)
    def test_fail_data_is_none(self, code: str) -> None:
        """fail() must set data=None (no payload on failure)."""
        from api.services.chatwoot_image_service import DownloadResult

        result = DownloadResult.fail(code)
        assert result.data is None

    @pytest.mark.parametrize("code", ALL_REASON_CODES)
    def test_fail_sets_reason_code(self, code: str) -> None:
        """fail() must echo the provided code back in reason_code."""
        from api.services.chatwoot_image_service import DownloadResult

        result = DownloadResult.fail(code)
        assert result.reason_code == code

    @pytest.mark.parametrize("code", ALL_REASON_CODES)
    def test_fail_populates_reason_message(self, code: str) -> None:
        """fail() must populate reason_message from REASON_MESSAGES (non-empty string)."""
        from api.services.chatwoot_image_service import DownloadResult

        result = DownloadResult.fail(code)
        assert isinstance(result.reason_message, str)
        assert len(result.reason_message) > 0

    def test_fail_pdf_too_many_pages_message_contains_page_limit(self) -> None:
        """fail('pdf_too_many_pages') reason_message must include the PDF_MAX_PAGES value."""
        from api.services.chatwoot_image_service import DownloadResult
        from shared.image_security import PDF_MAX_PAGES

        result = DownloadResult.fail("pdf_too_many_pages")
        assert str(PDF_MAX_PAGES) in result.reason_message  # type: ignore[arg-type]
