"""
Tests for PDF security validation in shared/image_security.py

TDD Cycle: Phase 2 of pdf-support-full change.

Tests:
  - validate_pdf_content(): valid PDF, JS-embedded, oversized, too many pages, corrupt
  - validate_image_full() PDF routing branch: pikepdf path taken, PIL path skipped
  - validate_filename() accepting .pdf extension
  - Integration: PDF download flow with correct MIME and extension
"""

from __future__ import annotations

import sys
import types
from io import BytesIO
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Minimal valid PDF bytes (used as a fixture throughout)
# A real minimal PDF is ~67 bytes; this one is hand-crafted and valid enough
# for magic byte checks. For structural validation tests we use a mock.
# ---------------------------------------------------------------------------

# Minimal PDF content — starts with %PDF-1.4, has a basic structure
MINIMAL_PDF_BYTES: bytes = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000068 00000 n \n0000000125 00000 n \n"
    b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n210\n%%EOF\n"
)

# Not a PDF — starts with JPEG magic bytes
FAKE_PDF_BYTES: bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 200

# Oversized content (> 10MB) — starts with PDF magic to pass magic check
OVERSIZED_PDF_BYTES: bytes = b"%PDF-1.4\n" + b"\x00" * (11 * 1024 * 1024)


# ---------------------------------------------------------------------------
# Helper: build a mock pikepdf.Pdf object
# ---------------------------------------------------------------------------

def _make_mock_pdf(page_count: int = 1) -> MagicMock:
    """Return a MagicMock that behaves like a pikepdf.Pdf instance."""
    mock_pdf = MagicMock()
    mock_pages = MagicMock()
    mock_pages.__len__ = MagicMock(return_value=page_count)
    mock_pdf.pages = mock_pages
    # Context manager support
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    return mock_pdf


def _make_mock_pikepdf(page_count: int = 1, raises: Exception | None = None) -> MagicMock:
    """Return a MagicMock module that mimics pikepdf."""
    mock_pikepdf = MagicMock()
    if raises:
        mock_pikepdf.open.side_effect = raises
        mock_pikepdf.PasswordError = Exception
        mock_pikepdf.PdfError = Exception
    else:
        mock_pdf = _make_mock_pdf(page_count)
        mock_pikepdf.open.return_value = mock_pdf
        mock_pikepdf.PasswordError = Exception
        mock_pikepdf.PdfError = Exception
    return mock_pikepdf


# ===========================================================================
# Task 2.1 (RED) + 2.2 (GREEN): validate_pdf_content()
# ===========================================================================


class TestValidatePdfContentMagicBytes:
    """validate_pdf_content() must reject content without %PDF magic bytes."""

    def test_rejects_non_pdf_magic_bytes(self) -> None:
        """Content not starting with %PDF must raise ImageSecurityError."""
        from shared.image_security import ImageSecurityError, validate_pdf_content

        mock_pikepdf = _make_mock_pikepdf()
        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            with pytest.raises(ImageSecurityError, match="magic"):
                validate_pdf_content(FAKE_PDF_BYTES)

    def test_accepts_valid_pdf_magic_bytes(self) -> None:
        """Content starting with %PDF must pass magic bytes check."""
        from shared.image_security import validate_pdf_content

        mock_pikepdf = _make_mock_pikepdf(page_count=1)
        # No JavaScript in the mock PDF objects
        mock_pdf = mock_pikepdf.open.return_value
        mock_pdf.pages.__len__ = MagicMock(return_value=1)
        # Make pikepdf object iteration return no suspicious keys
        mock_pdf.objects = []

        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            result = validate_pdf_content(MINIMAL_PDF_BYTES)

        assert result["mime_type"] == "application/pdf"

    def test_triangulate_jpeg_bytes_rejected(self) -> None:
        """A JPEG file masquerading as PDF must be rejected at magic bytes stage."""
        from shared.image_security import ImageSecurityError, validate_pdf_content

        jpeg_bytes = b"\xff\xd8\xff\xe1" + b"\x00" * 200
        mock_pikepdf = _make_mock_pikepdf()
        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            with pytest.raises(ImageSecurityError):
                validate_pdf_content(jpeg_bytes)


class TestValidatePdfContentSizeCheck:
    """validate_pdf_content() must reject PDFs exceeding 10MB BEFORE pikepdf parsing."""

    def test_rejects_oversized_pdf(self) -> None:
        """PDF > 10MB must raise ImageSecurityError without calling pikepdf.open."""
        from shared.image_security import ImageSecurityError, validate_pdf_content

        mock_pikepdf = _make_mock_pikepdf()
        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            with pytest.raises(ImageSecurityError, match="size"):
                validate_pdf_content(OVERSIZED_PDF_BYTES)

        # pikepdf.open must NOT have been called (size check is first)
        mock_pikepdf.open.assert_not_called()

    def test_accepts_pdf_within_size_limit(self) -> None:
        """PDF at exactly 10MB threshold must NOT raise a size error."""
        from shared.image_security import validate_pdf_content

        # 10MB exactly — still within limit
        exactly_10mb = b"%PDF-1.4\n" + b"\x00" * (10 * 1024 * 1024 - 9)
        mock_pikepdf = _make_mock_pikepdf(page_count=1)
        mock_pikepdf.open.return_value.objects = []

        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            result = validate_pdf_content(exactly_10mb)

        # Size check must not have rejected it
        assert result["mime_type"] == "application/pdf"


class TestValidatePdfContentStructural:
    """validate_pdf_content() must reject corrupt / unreadable PDFs."""

    def test_rejects_corrupt_pdf(self) -> None:
        """pikepdf.open raising PdfError must result in ImageSecurityError."""
        from shared.image_security import ImageSecurityError, validate_pdf_content

        class FakePdfError(Exception):
            pass

        mock_pikepdf = MagicMock()
        mock_pikepdf.open.side_effect = FakePdfError("corrupt")
        mock_pikepdf.PdfError = FakePdfError
        mock_pikepdf.PasswordError = FakePdfError

        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            with pytest.raises(ImageSecurityError, match="corrupt|parse|invalid|open"):
                validate_pdf_content(MINIMAL_PDF_BYTES)

    def test_rejects_encrypted_pdf(self) -> None:
        """pikepdf.open raising PasswordError must result in ImageSecurityError."""
        from shared.image_security import ImageSecurityError, validate_pdf_content

        class FakePasswordError(Exception):
            pass

        mock_pikepdf = MagicMock()
        mock_pikepdf.open.side_effect = FakePasswordError("needs password")
        mock_pikepdf.PasswordError = FakePasswordError
        mock_pikepdf.PdfError = Exception

        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            with pytest.raises(ImageSecurityError, match="encrypt|password|corrupt|parse|invalid|open"):
                validate_pdf_content(MINIMAL_PDF_BYTES)


class TestValidatePdfContentPageCount:
    """validate_pdf_content() must reject PDFs with more than 30 pages."""

    def test_rejects_pdf_with_too_many_pages(self) -> None:
        """PDF with 31 pages must raise ImageSecurityError."""
        from shared.image_security import ImageSecurityError, validate_pdf_content

        mock_pikepdf = _make_mock_pikepdf(page_count=31)
        mock_pikepdf.open.return_value.objects = []

        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            with pytest.raises(ImageSecurityError, match="page"):
                validate_pdf_content(MINIMAL_PDF_BYTES)

    def test_accepts_pdf_with_exactly_30_pages(self) -> None:
        """PDF with exactly 30 pages must pass validation."""
        from shared.image_security import validate_pdf_content

        mock_pikepdf = _make_mock_pikepdf(page_count=30)
        mock_pikepdf.open.return_value.objects = []

        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            result = validate_pdf_content(MINIMAL_PDF_BYTES)

        assert result["page_count"] == 30

    def test_triangulate_single_page_pdf_accepted(self) -> None:
        """PDF with 1 page must also pass page count validation."""
        from shared.image_security import validate_pdf_content

        mock_pikepdf = _make_mock_pikepdf(page_count=1)
        mock_pikepdf.open.return_value.objects = []

        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            result = validate_pdf_content(MINIMAL_PDF_BYTES)

        assert result["page_count"] == 1


class TestValidatePdfContentJavaScript:
    """validate_pdf_content() must reject PDFs containing JavaScript or embedded files."""

    def _make_pikepdf_with_js_key(self, js_key: str) -> MagicMock:
        """Build a pikepdf mock whose objects contain the given JavaScript key."""
        mock_pikepdf = MagicMock()
        mock_pikepdf.PdfError = Exception
        mock_pikepdf.PasswordError = Exception

        # Simulate a PDF object that contains a suspicious key
        mock_obj = MagicMock()
        mock_obj.keys.return_value = [js_key]

        mock_pdf = _make_mock_pdf(page_count=1)
        mock_pdf.objects = [mock_obj]
        mock_pikepdf.open.return_value = mock_pdf

        return mock_pikepdf

    def test_rejects_pdf_with_javascript_key(self) -> None:
        """PDF containing /JavaScript key must raise ImageSecurityError."""
        from shared.image_security import ImageSecurityError, validate_pdf_content

        mock_pikepdf = self._make_pikepdf_with_js_key("/JavaScript")
        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            with pytest.raises(ImageSecurityError, match="JavaScript|malicious|dangerous"):
                validate_pdf_content(MINIMAL_PDF_BYTES)

    def test_rejects_pdf_with_js_key(self) -> None:
        """PDF containing /JS key must raise ImageSecurityError."""
        from shared.image_security import ImageSecurityError, validate_pdf_content

        mock_pikepdf = self._make_pikepdf_with_js_key("/JS")
        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            with pytest.raises(ImageSecurityError, match="JavaScript|malicious|dangerous"):
                validate_pdf_content(MINIMAL_PDF_BYTES)

    def test_rejects_pdf_with_embedded_files(self) -> None:
        """PDF containing /EmbeddedFiles key must raise ImageSecurityError."""
        from shared.image_security import ImageSecurityError, validate_pdf_content

        mock_pikepdf = self._make_pikepdf_with_js_key("/EmbeddedFiles")
        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            with pytest.raises(ImageSecurityError, match="embed|malicious|dangerous"):
                validate_pdf_content(MINIMAL_PDF_BYTES)

    def test_rejects_pdf_with_aa_action_key(self) -> None:
        """PDF containing /AA (auto-action) key must raise ImageSecurityError."""
        from shared.image_security import ImageSecurityError, validate_pdf_content

        mock_pikepdf = self._make_pikepdf_with_js_key("/AA")
        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            with pytest.raises(ImageSecurityError, match="auto.action|malicious|dangerous"):
                validate_pdf_content(MINIMAL_PDF_BYTES)

    def test_clean_pdf_passes(self) -> None:
        """PDF with no dangerous keys must pass all validation checks."""
        from shared.image_security import validate_pdf_content

        mock_pikepdf = _make_mock_pikepdf(page_count=2)
        # Safe PDF object with benign keys
        mock_obj = MagicMock()
        mock_obj.keys.return_value = ["/Type", "/Pages", "/Count"]
        mock_pikepdf.open.return_value.objects = [mock_obj]

        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            result = validate_pdf_content(MINIMAL_PDF_BYTES)

        assert result["mime_type"] == "application/pdf"
        assert result["page_count"] == 2
        assert result["width"] == 0
        assert result["height"] == 0


# ===========================================================================
# Task 2.3 (RED) + 2.4 (GREEN): validate_image_full() PDF routing branch
# ===========================================================================


class TestValidateImageFullPdfRouting:
    """validate_image_full() must route PDFs to validate_pdf_content(), skipping PIL."""

    def test_pdf_mime_routes_to_pdf_validation(self) -> None:
        """When declared_mime is application/pdf, validate_pdf_content must be called."""
        from shared.image_security import validate_image_full

        mock_pikepdf = _make_mock_pikepdf(page_count=1)
        mock_pikepdf.open.return_value.objects = []

        with (
            patch.dict("sys.modules", {"pikepdf": mock_pikepdf}),
            patch("shared.image_security.validate_pdf_content") as mock_pdf_validate,
        ):
            mock_pdf_validate.return_value = {
                "mime_type": "application/pdf",
                "page_count": 1,
                "width": 0,
                "height": 0,
            }
            result = validate_image_full(
                content=MINIMAL_PDF_BYTES,
                declared_mime="application/pdf",
            )

        mock_pdf_validate.assert_called_once_with(MINIMAL_PDF_BYTES)

    def test_pdf_routing_skips_pil(self) -> None:
        """When declared_mime is application/pdf, PIL (validate_image_content) must NOT be called."""
        from shared.image_security import validate_image_full

        with (
            patch("shared.image_security.validate_pdf_content") as mock_pdf_validate,
            patch("shared.image_security.validate_image_content") as mock_pil_validate,
        ):
            mock_pdf_validate.return_value = {
                "mime_type": "application/pdf",
                "page_count": 1,
                "width": 0,
                "height": 0,
            }
            validate_image_full(
                content=MINIMAL_PDF_BYTES,
                declared_mime="application/pdf",
            )

        mock_pil_validate.assert_not_called()

    def test_pdf_result_has_correct_fields(self) -> None:
        """validate_image_full() for PDFs must return width=0, height=0, page_count."""
        from shared.image_security import validate_image_full

        with patch("shared.image_security.validate_pdf_content") as mock_pdf_validate:
            mock_pdf_validate.return_value = {
                "mime_type": "application/pdf",
                "page_count": 3,
                "width": 0,
                "height": 0,
            }
            result = validate_image_full(
                content=MINIMAL_PDF_BYTES,
                declared_mime="application/pdf",
            )

        assert result["valid"] is True
        assert result["detected_mime"] == "application/pdf"
        assert result["width"] == 0
        assert result["height"] == 0
        assert result["page_count"] == 3

    def test_image_mime_still_uses_pil_path(self) -> None:
        """When declared_mime is image/jpeg, PIL validation path must still be used."""
        from shared.image_security import validate_image_full

        with (
            patch("shared.image_security.validate_magic_number") as mock_magic,
            patch("shared.image_security.validate_image_content") as mock_pil,
            patch("shared.image_security.validate_pdf_content") as mock_pdf,
        ):
            mock_magic.return_value = "image/jpeg"
            mock_pil.return_value = (800, 600)

            result = validate_image_full(
                content=b"\xff\xd8\xff\xe0" + b"\x00" * 200,
                declared_mime="image/jpeg",
            )

        mock_pil.assert_called_once()
        mock_pdf.assert_not_called()
        assert result["width"] == 800
        assert result["height"] == 600


# ===========================================================================
# Task 2.5 (RED) + 2.6 (GREEN): validate_filename() accepts .pdf
# ===========================================================================


class TestValidateFilenameAcceptsPdf:
    """validate_filename() must accept .pdf extension."""

    def test_accepts_pdf_extension(self) -> None:
        """validate_filename() must NOT raise for a .pdf file."""
        from shared.image_security import validate_filename

        result = validate_filename("document.pdf")
        assert result == "document.pdf"

    def test_triangulate_accepts_pdf_with_uuid_prefix(self) -> None:
        """validate_filename() must accept UUID-prefixed .pdf filenames."""
        from shared.image_security import validate_filename

        result = validate_filename("550e8400-e29b-41d4-a716-446655440000.pdf")
        assert result.endswith(".pdf")

    def test_pdf_in_allowed_extensions_constant(self) -> None:
        """ALLOWED_EXTENSIONS must contain 'pdf'."""
        from shared.image_security import ALLOWED_EXTENSIONS

        assert "pdf" in ALLOWED_EXTENSIONS


# ===========================================================================
# T1.test — PDF page limit raised from 20 to 30
# Spec: 30-page PDF accepted; 31-page PDF rejected; error message uses constant
# ===========================================================================


class TestPdfPageLimitAt30:
    """PDF_MAX_PAGES must equal 30 and validate_pdf_content must enforce that limit."""

    def test_pdf_max_pages_constant_is_30(self) -> None:
        """PDF_MAX_PAGES must be 30, not 20."""
        from shared.image_security import PDF_MAX_PAGES

        assert PDF_MAX_PAGES == 30

    def test_30_page_pdf_is_accepted(self) -> None:
        """A PDF with exactly 30 pages must pass validation (boundary case)."""
        from shared.image_security import validate_pdf_content

        mock_pikepdf = _make_mock_pikepdf(page_count=30)
        mock_pikepdf.open.return_value.objects = []

        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            result = validate_pdf_content(MINIMAL_PDF_BYTES)

        assert result["page_count"] == 30

    def test_31_page_pdf_is_rejected(self) -> None:
        """A PDF with 31 pages must raise ImageSecurityError."""
        from shared.image_security import ImageSecurityError, validate_pdf_content

        mock_pikepdf = _make_mock_pikepdf(page_count=31)
        mock_pikepdf.open.return_value.objects = []

        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            with pytest.raises(ImageSecurityError, match="page"):
                validate_pdf_content(MINIMAL_PDF_BYTES)

    def test_rejection_message_contains_max_pages_number(self) -> None:
        """Error message for too-many-pages must contain the value of PDF_MAX_PAGES (30)."""
        from shared.image_security import ImageSecurityError, PDF_MAX_PAGES, validate_pdf_content

        mock_pikepdf = _make_mock_pikepdf(page_count=31)
        mock_pikepdf.open.return_value.objects = []

        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            with pytest.raises(ImageSecurityError) as exc_info:
                validate_pdf_content(MINIMAL_PDF_BYTES)

        assert str(PDF_MAX_PAGES) in str(exc_info.value)

    def test_validate_image_full_rejects_31_page_pdf(self) -> None:
        """validate_image_full() must propagate the 31-page rejection from validate_pdf_content."""
        from shared.image_security import ImageSecurityError, validate_image_full

        mock_pikepdf = _make_mock_pikepdf(page_count=31)
        mock_pikepdf.open.return_value.objects = []

        with patch.dict("sys.modules", {"pikepdf": mock_pikepdf}):
            with pytest.raises(ImageSecurityError, match="page"):
                validate_image_full(
                    content=MINIMAL_PDF_BYTES,
                    declared_mime="application/pdf",
                )


# ===========================================================================
# Task 2.7 (RED) + 2.8 (GREEN): chatwoot_image_service PDF integration
# ===========================================================================


class TestChatwootImageServicePdfConstants:
    """chatwoot_image_service.py must include PDF in its MIME type constants."""

    def test_supported_image_types_contains_pdf(self) -> None:
        """SUPPORTED_IMAGE_TYPES must include application/pdf."""
        from api.services.chatwoot_image_service import SUPPORTED_IMAGE_TYPES

        assert "application/pdf" in SUPPORTED_IMAGE_TYPES

    def test_mime_to_ext_maps_pdf(self) -> None:
        """MIME_TO_EXT must map application/pdf → pdf."""
        from api.services.chatwoot_image_service import MIME_TO_EXT

        assert MIME_TO_EXT.get("application/pdf") == "pdf"

    @pytest.mark.asyncio
    async def test_get_image_bytes_returns_pdf_mime(self, tmp_path) -> None:
        """get_image_bytes() for a .pdf file must return mime_type=application/pdf."""
        from api.services.chatwoot_image_service import ChatwootImageService

        # Build a PDF file in tmp_path
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(MINIMAL_PDF_BYTES)

        svc = ChatwootImageService.__new__(ChatwootImageService)
        svc.case_images_dir = tmp_path
        svc.base_url = "http://localhost/images"
        svc.max_size = 10 * 1024 * 1024
        svc.chatwoot_api_url = "https://chatwoot.example.com"
        svc.chatwoot_api_token = "token"
        svc.chatwoot_storage_domain = ""
        svc.allowed_domains = ["chatwoot.example.com"]

        result = await svc.get_image_bytes("test.pdf")

        assert result is not None
        content_bytes, mime_type = result
        assert mime_type == "application/pdf"
        assert content_bytes == MINIMAL_PDF_BYTES

    def test_get_extension_for_mime_returns_pdf(self) -> None:
        """get_extension_for_mime('application/pdf') must return 'pdf'."""
        from shared.image_security import get_extension_for_mime

        assert get_extension_for_mime("application/pdf") == "pdf"


# ===========================================================================
# Task 4.4: Unknown / disallowed MIME types are still rejected after PDF changes
#
# This verifies that adding application/pdf to ALLOWED_MIME_TYPES did NOT
# accidentally open the door to other MIME types (application/msword, etc.).
# ===========================================================================


class TestUnknownMimeTypesStillRejected:
    """
    Unknown / disallowed MIME types must still be rejected after PDF support was added.

    Two levels of verification:
    1. Constant level: ALLOWED_MIME_TYPES does NOT contain disallowed types
    2. Functional level: validate_magic_number() rejects content with disallowed MIME
       (the magic-bytes detection path, which is the real runtime guard)
    """

    # MIME types that must NOT be in ALLOWED_MIME_TYPES
    _DISALLOWED = [
        ("application/msword", "Word document"),
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "DOCX",
        ),
        ("application/zip", "ZIP archive"),
        ("text/html", "HTML document"),
        ("application/javascript", "JavaScript"),
        ("application/x-executable", "ELF binary"),
        ("image/svg+xml", "SVG (disallowed)"),
    ]

    @pytest.mark.parametrize("declared_mime, description", _DISALLOWED)
    def test_disallowed_mime_types_not_in_allowed_mime_types_constant(
        self,
        declared_mime: str,
        description: str,
    ) -> None:
        """
        ALLOWED_MIME_TYPES must NOT contain any of the disallowed MIME types.

        This is a constant-level guard: adding PDF must not have expanded the allowlist
        beyond what was explicitly intended.
        """
        from shared.image_security import ALLOWED_MIME_TYPES

        assert declared_mime not in ALLOWED_MIME_TYPES, (
            f"{description} ({declared_mime!r}) must NOT be in ALLOWED_MIME_TYPES. "
            f"Current ALLOWED_MIME_TYPES: {sorted(ALLOWED_MIME_TYPES)}"
        )

    def test_application_pdf_is_in_allowed_mime_types(self) -> None:
        """Sanity check: application/pdf was successfully added to ALLOWED_MIME_TYPES."""
        from shared.image_security import ALLOWED_MIME_TYPES

        assert "application/pdf" in ALLOWED_MIME_TYPES, (
            "application/pdf must be in ALLOWED_MIME_TYPES after Phase 1 changes"
        )

    @pytest.mark.parametrize("declared_mime, description", _DISALLOWED)
    def test_validate_magic_number_rejects_disallowed_mime_content(
        self,
        declared_mime: str,
        description: str,
    ) -> None:
        """
        validate_magic_number() must raise ImageSecurityError for disallowed content.

        When content has no recognizable image/PDF magic bytes, validate_magic_number()
        raises because the detected MIME is not in ALLOWED_MIME_TYPES.
        This guard is independent of the declared_mime parameter — it checks the actual
        content bytes, so no declared MIME type can bypass it.
        """
        from shared.image_security import ImageSecurityError, validate_magic_number

        # Content with no recognizable magic bytes → detected as octet-stream
        # or unknown → not in ALLOWED_MIME_TYPES → rejected
        with pytest.raises(ImageSecurityError):
            validate_magic_number(
                content=b"\x00\x01\x02\x03" * 25,  # No known magic bytes
                declared_mime=declared_mime,
            )
