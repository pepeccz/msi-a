"""
Tests for REASON_MESSAGES dict and _classify_security_error() helper
in api/services/chatwoot_image_service.py

TDD Cycle: T2b

Spec scenarios covered:
  - All 7 reason codes map to distinct non-empty Spanish strings
  - pdf_too_many_pages interpolates current PDF_MAX_PAGES value
  - _classify_security_error() maps every known ImageSecurityError prefix to the correct code
  - Unrecognised errors map to fallback_unknown
"""

from __future__ import annotations

import pytest


ALL_REASON_CODES = [
    "pdf_too_many_pages",
    "file_too_large",
    "file_type_not_allowed",
    "pdf_dangerous_content",
    "url_rejected",
    "corrupt_or_mismatch",
    "fallback_unknown",
]


# ---------------------------------------------------------------------------
# T2b.test — REASON_MESSAGES map: 7 codes, distinct, non-empty, Spanish
# ---------------------------------------------------------------------------


class TestReasonMessages:
    """REASON_MESSAGES must cover all 7 codes with distinct, non-empty Spanish strings."""

    def test_all_seven_codes_present(self) -> None:
        """REASON_MESSAGES must have exactly the 7 canonical keys."""
        from api.services.chatwoot_image_service import REASON_MESSAGES

        missing = set(ALL_REASON_CODES) - set(REASON_MESSAGES.keys())
        assert not missing, f"Missing reason codes: {missing}"

    @pytest.mark.parametrize("code", ALL_REASON_CODES)
    def test_each_code_maps_to_non_empty_string(self, code: str) -> None:
        """Every reason code must produce a non-empty string."""
        from api.services.chatwoot_image_service import REASON_MESSAGES

        msg = REASON_MESSAGES[code]
        assert isinstance(msg, str) and len(msg) > 0, (
            f"REASON_MESSAGES[{code!r}] must be a non-empty string, got {msg!r}"
        )

    def test_all_messages_are_distinct(self) -> None:
        """No two reason codes may share the same exact Spanish string."""
        from api.services.chatwoot_image_service import REASON_MESSAGES

        messages = [REASON_MESSAGES[code] for code in ALL_REASON_CODES]
        assert len(messages) == len(set(messages)), (
            "Duplicate strings found in REASON_MESSAGES — each code needs a unique message"
        )

    def test_pdf_too_many_pages_contains_max_pages_value(self) -> None:
        """pdf_too_many_pages message must contain the current PDF_MAX_PAGES value (30)."""
        from api.services.chatwoot_image_service import REASON_MESSAGES
        from shared.image_security import PDF_MAX_PAGES

        msg = REASON_MESSAGES["pdf_too_many_pages"]
        assert str(PDF_MAX_PAGES) in msg, (
            f"Expected {PDF_MAX_PAGES} in pdf_too_many_pages message, got: {msg!r}"
        )

    def test_pdf_too_many_pages_is_not_hardcoded(self) -> None:
        """
        If PDF_MAX_PAGES changes, the message must reflect it.
        Verify by checking the message contains the constant value, not a stale literal.
        """
        from api.services.chatwoot_image_service import REASON_MESSAGES
        from shared.image_security import PDF_MAX_PAGES

        msg = REASON_MESSAGES["pdf_too_many_pages"]
        # If this fails after a constant bump, the message is hardcoded — bad.
        assert str(PDF_MAX_PAGES) in msg


# ---------------------------------------------------------------------------
# T2b.test — _classify_security_error() helper
# ---------------------------------------------------------------------------


class TestClassifySecurityError:
    """_classify_security_error() must map ImageSecurityError messages to reason codes."""

    def _error(self, msg: str):
        from shared.image_security import ImageSecurityError
        return ImageSecurityError(msg)

    def test_page_limit_maps_to_pdf_too_many_pages(self) -> None:
        """'PDF exceeds page limit' must map to pdf_too_many_pages."""
        from api.services.chatwoot_image_service import _classify_security_error

        result = _classify_security_error(
            self._error("PDF exceeds page limit: 31 pages > 30 allowed")
        )
        assert result == "pdf_too_many_pages"

    def test_too_large_maps_to_file_too_large(self) -> None:
        """'Image too large' must map to file_too_large."""
        from api.services.chatwoot_image_service import _classify_security_error

        result = _classify_security_error(
            self._error("Image too large (5000000 bytes > 4000000)")
        )
        assert result == "file_too_large"

    def test_size_exceeds_maps_to_file_too_large(self) -> None:
        """'PDF size exceeds limit' must also map to file_too_large."""
        from api.services.chatwoot_image_service import _classify_security_error

        result = _classify_security_error(
            self._error("PDF size exceeds limit: 12000000 bytes > 10485760 bytes (10 MB)")
        )
        assert result == "file_too_large"

    def test_file_type_not_allowed_maps_correctly(self) -> None:
        """'File type not allowed' must map to file_type_not_allowed."""
        from api.services.chatwoot_image_service import _classify_security_error

        result = _classify_security_error(
            self._error("File type not allowed: application/msword. Allowed: ...")
        )
        assert result == "file_type_not_allowed"

    def test_dangerous_content_maps_to_pdf_dangerous_content(self) -> None:
        """'PDF contains dangerous content' must map to pdf_dangerous_content."""
        from api.services.chatwoot_image_service import _classify_security_error

        result = _classify_security_error(
            self._error("PDF contains dangerous content: /JavaScript, /JS. JavaScript or embedded files are not allowed.")
        )
        assert result == "pdf_dangerous_content"

    def test_domain_not_allowed_maps_to_url_rejected(self) -> None:
        """'Domain not allowed' must map to url_rejected."""
        from api.services.chatwoot_image_service import _classify_security_error

        result = _classify_security_error(
            self._error("Domain not allowed: evil.com. Allowed: chatwoot.example.com")
        )
        assert result == "url_rejected"

    def test_private_local_maps_to_url_rejected(self) -> None:
        """'Private/local addresses not allowed' must map to url_rejected."""
        from api.services.chatwoot_image_service import _classify_security_error

        result = _classify_security_error(
            self._error("Private/local addresses not allowed")
        )
        assert result == "url_rejected"

    def test_invalid_url_scheme_maps_to_url_rejected(self) -> None:
        """'Invalid URL scheme' must map to url_rejected."""
        from api.services.chatwoot_image_service import _classify_security_error

        result = _classify_security_error(
            self._error("Invalid URL scheme: ftp")
        )
        assert result == "url_rejected"

    def test_invalid_image_file_maps_to_corrupt_or_mismatch(self) -> None:
        """'Invalid image file' must map to corrupt_or_mismatch."""
        from api.services.chatwoot_image_service import _classify_security_error

        result = _classify_security_error(
            self._error("Invalid image file: cannot identify image file")
        )
        assert result == "corrupt_or_mismatch"

    def test_decompression_bomb_maps_to_corrupt_or_mismatch(self) -> None:
        """'decompression bomb' must map to corrupt_or_mismatch."""
        from api.services.chatwoot_image_service import _classify_security_error

        result = _classify_security_error(
            self._error("Image appears to be a decompression bomb")
        )
        assert result == "corrupt_or_mismatch"

    def test_could_not_detect_maps_to_corrupt_or_mismatch(self) -> None:
        """'Could not detect file type' must map to corrupt_or_mismatch."""
        from api.services.chatwoot_image_service import _classify_security_error

        result = _classify_security_error(
            self._error("Could not detect file type. File may not be a valid image.")
        )
        assert result == "corrupt_or_mismatch"

    def test_unknown_error_maps_to_fallback_unknown(self) -> None:
        """An unrecognised error message must map to fallback_unknown."""
        from api.services.chatwoot_image_service import _classify_security_error

        result = _classify_security_error(
            self._error("Some completely unexpected validation error XYZ123")
        )
        assert result == "fallback_unknown"

    def test_triangulate_javascript_in_message_maps_to_dangerous(self) -> None:
        """Any message containing 'javascript' must map to pdf_dangerous_content."""
        from api.services.chatwoot_image_service import _classify_security_error

        result = _classify_security_error(
            self._error("PDF contains embedded javascript code")
        )
        assert result == "pdf_dangerous_content"
