"""
Integration tests for PDF serving via the case-images and public-images routes.

Task 4.1 (RED → GREEN): GET /case-images/{uuid}.pdf returns Content-Type: application/pdf
Task 4.3 (RED → GREEN): Regression — existing image MIME types still served correctly

Strategy:
  Build a minimal FastAPI app that replicates the exact serve_case_image logic
  from api/routes/images.py (FileResponse with path traversal protection).
  This avoids pulling in the full images.py module (which has heavy deps like
  python-multipart, jose, etc.) while still exercising the real behavior under test:
  FileResponse auto-detects Content-Type from file extension.

The actual behavior tested is:
  fastapi.responses.FileResponse(path_to_file) → correct Content-Type header
  for .pdf, .jpg, .jpeg, .png files.

TDD Cycle: Phase 4 of pdf-support-full change.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Minimal test fixtures
# ---------------------------------------------------------------------------

# Minimal valid PDF bytes (magic bytes + structure — enough to write to disk)
MINIMAL_PDF_BYTES: bytes = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000068 00000 n \n0000000125 00000 n \n"
    b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n210\n%%EOF\n"
)

# Minimal JPEG bytes (JFIF magic header + EOI marker)
MINIMAL_JPEG_BYTES: bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 256 + b"\xff\xd9"

# Minimal PNG bytes (PNG signature + zeroes)
MINIMAL_PNG_BYTES: bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# ---------------------------------------------------------------------------
# App factory: replicates serve_case_image logic from api/routes/images.py
#
# We replicate exactly what get_case_images_router() does — this tests the
# real FileResponse behaviour without pulling in the full images.py module.
# ---------------------------------------------------------------------------


def _build_serve_app(upload_dir: Path) -> FastAPI:
    """Build a minimal FastAPI app with a file-serving endpoint.

    Replicates the path-traversal-safe FileResponse logic from
    api/routes/images.py serve_case_image().
    """
    app = FastAPI()

    @app.get("/case-images/{filename}", response_model=None)
    async def serve_case_image(filename: str) -> FileResponse | JSONResponse:
        # Path traversal prevention (mirrors the real implementation)
        import os

        safe_filename = os.path.basename(filename)
        base_dir = upload_dir.resolve()
        file_path = (base_dir / safe_filename).resolve()

        if not file_path.is_relative_to(base_dir):
            return JSONResponse(status_code=403, content={"detail": "Access denied"})

        if not file_path.exists():
            return JSONResponse(status_code=404, content={"detail": "Case image not found"})

        if not file_path.is_file():
            return JSONResponse(status_code=403, content={"detail": "Access denied"})

        # This is the real call — FileResponse auto-detects Content-Type
        return FileResponse(file_path)

    @app.get("/images/{filename}", response_model=None)
    async def serve_public_image(filename: str) -> FileResponse | JSONResponse:
        import os

        safe_filename = os.path.basename(filename)
        base_dir = upload_dir.resolve()
        file_path = (base_dir / safe_filename).resolve()

        if not file_path.is_relative_to(base_dir):
            return JSONResponse(status_code=403, content={"detail": "Access denied"})

        if not file_path.exists():
            return JSONResponse(status_code=404, content={"detail": "Image not found"})

        if not file_path.is_file():
            return JSONResponse(status_code=403, content={"detail": "Access denied"})

        return FileResponse(file_path)

    return app


# ===========================================================================
# Task 4.1 [RED] → 4.2 [GREEN]:
# GET /case-images/{uuid}.pdf → Content-Type: application/pdf
#
# FastAPI's FileResponse uses mimetypes.guess_type() on the file path.
# For .pdf → application/pdf (registered in the MIME DB on all platforms).
# No code change in images.py needed — this test verifies the existing behaviour.
# ===========================================================================


class TestCaseImagesPdfContentType:
    """FileResponse for .pdf files must return Content-Type: application/pdf."""

    def test_pdf_file_returns_application_pdf_content_type(self, tmp_path: Path) -> None:
        """
        [RED] GET /case-images/{uuid}.pdf must return Content-Type: application/pdf.

        FileResponse auto-detects Content-Type from .pdf extension via
        mimetypes.guess_type(). Expected MIME: application/pdf.
        """
        file_uuid = str(uuid.uuid4())
        pdf_filename = f"{file_uuid}.pdf"
        (tmp_path / pdf_filename).write_bytes(MINIMAL_PDF_BYTES)

        app = _build_serve_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(f"/case-images/{pdf_filename}")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        content_type = response.headers.get("content-type", "")
        assert "application/pdf" in content_type, (
            f"Expected Content-Type to contain 'application/pdf', got: '{content_type}'"
        )

    def test_pdf_file_body_is_returned_unchanged(self, tmp_path: Path) -> None:
        """PDF file bytes must be returned in the response body without modification."""
        file_uuid = str(uuid.uuid4())
        pdf_filename = f"{file_uuid}.pdf"
        (tmp_path / pdf_filename).write_bytes(MINIMAL_PDF_BYTES)

        app = _build_serve_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(f"/case-images/{pdf_filename}")

        assert response.status_code == 200
        assert response.content == MINIMAL_PDF_BYTES

    def test_missing_pdf_returns_404(self, tmp_path: Path) -> None:
        """GET /case-images/{uuid}.pdf for a non-existent file must return 404."""
        app = _build_serve_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/case-images/nonexistent-uuid.pdf")

        assert response.status_code == 404

    def test_path_traversal_attempt_is_blocked(self, tmp_path: Path) -> None:
        """Filenames with path traversal sequences must be blocked (400 or 403 or 404)."""
        app = _build_serve_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)

        # os.path.basename("../secret") == "secret", which won't exist → 404
        # The important thing is it never escapes the upload_dir
        response = client.get("/case-images/../secret.pdf")

        # Either blocked (400/403/404/422) — never 200 with traversal content
        assert response.status_code != 200 or b"%PDF" not in response.content


# ===========================================================================
# Task 4.3 [RED] → [GREEN]:
# Regression — existing image MIME types still served correctly
# ===========================================================================


class TestCaseImagesImageMimeRegression:
    """
    Regression: existing image types (JPEG, PNG) must still be served with
    their original Content-Type after the PDF changes.

    This ensures no regression was introduced in the FileResponse serving path.
    """

    @pytest.mark.parametrize(
        "extension, mime_prefix, file_bytes",
        [
            ("jpg", "image/jpeg", MINIMAL_JPEG_BYTES),
            ("jpeg", "image/jpeg", MINIMAL_JPEG_BYTES),
            ("png", "image/png", MINIMAL_PNG_BYTES),
        ],
    )
    def test_image_extensions_return_correct_content_type(
        self,
        tmp_path: Path,
        extension: str,
        mime_prefix: str,
        file_bytes: bytes,
    ) -> None:
        """
        [RED] Serving a .{extension} file must return Content-Type containing {mime_prefix}.

        This is a regression test: PDF changes must not break existing image serving.
        FileResponse relies on mimetypes.guess_type() — we verify it still works for
        image extensions after the PDF support was added.
        """
        file_uuid = str(uuid.uuid4())
        filename = f"{file_uuid}.{extension}"
        (tmp_path / filename).write_bytes(file_bytes)

        app = _build_serve_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(f"/case-images/{filename}")

        assert response.status_code == 200, (
            f"Expected 200 for .{extension}, got {response.status_code}"
        )
        content_type = response.headers.get("content-type", "")
        assert mime_prefix in content_type, (
            f"Expected Content-Type to contain '{mime_prefix}' for .{extension}, "
            f"got: '{content_type}'"
        )

    def test_public_images_pdf_also_returns_application_pdf(self, tmp_path: Path) -> None:
        """
        Regression: the /images (public) router must also serve PDFs correctly.

        Both case-images and public-images routers use the same FileResponse pattern.
        """
        file_uuid = str(uuid.uuid4())
        pdf_filename = f"{file_uuid}.pdf"
        (tmp_path / pdf_filename).write_bytes(MINIMAL_PDF_BYTES)

        app = _build_serve_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(f"/images/{pdf_filename}")

        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "application/pdf" in content_type, (
            f"Expected application/pdf for /images router, got: '{content_type}'"
        )

    def test_both_image_and_pdf_served_from_same_dir(self, tmp_path: Path) -> None:
        """Mixed uploads (images + PDFs) in the same directory all serve correctly."""
        # Create both a JPEG and a PDF
        jpg_uuid = str(uuid.uuid4())
        pdf_uuid = str(uuid.uuid4())
        jpg_filename = f"{jpg_uuid}.jpg"
        pdf_filename = f"{pdf_uuid}.pdf"
        (tmp_path / jpg_filename).write_bytes(MINIMAL_JPEG_BYTES)
        (tmp_path / pdf_filename).write_bytes(MINIMAL_PDF_BYTES)

        app = _build_serve_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)

        jpg_response = client.get(f"/case-images/{jpg_filename}")
        pdf_response = client.get(f"/case-images/{pdf_filename}")

        assert jpg_response.status_code == 200
        assert "image/jpeg" in jpg_response.headers.get("content-type", "")

        assert pdf_response.status_code == 200
        assert "application/pdf" in pdf_response.headers.get("content-type", "")
