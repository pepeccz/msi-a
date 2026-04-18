"""
Tests for Content-Disposition header logic in the case-images endpoint.

The header logic is extracted to a pure function _build_content_disposition_headers
so it can be tested without the full FastAPI bootstrap overhead.

spec refs:
  - Scenario "PDF file request": response includes Content-Disposition: inline; filename=...
  - Scenario "Non-PDF file request (unchanged)": response does NOT include that header

Import strategy: load api.routes.images via spec_from_file_location, pre-stubbing
all heavy transitive deps (jose, passlib, phonenumbers, python-multipart, etc.)
to allow module collection without a live server environment.
"""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Bootstrap: load api.routes.images without full application env
# ---------------------------------------------------------------------------


def _bootstrap_images_module() -> ModuleType:
    """Load api.routes.images and return the module.

    Stubs heavy/missing transitive deps so the test can run without a live
    server. Notably stubs python-multipart (not in requirements.txt) which
    FastAPI needs for UploadFile routes.
    """
    # Stub external packages not installed in test env
    for mod in [
        "jose",
        "jose.jwt",
        "passlib",
        "passlib.hash",
        "passlib.context",
        "phonenumbers",
        # FastAPI UploadFile validation requires python-multipart at route reg time;
        # stub the module so the import chain doesn't explode
        "multipart",
        "multipart.multipart",
    ]:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

    # Stub fastapi internals that check for multipart at route registration
    # by patching ensure_multipart_is_installed to a no-op before module load
    import fastapi.dependencies.utils as _fdu
    _orig_ensure = _fdu.ensure_multipart_is_installed
    _fdu.ensure_multipart_is_installed = lambda: None  # type: ignore[assignment]

    # Stub api.routes.admin (image route imports get_current_user from there)
    if "api.routes.admin" not in sys.modules:
        admin_stub = ModuleType("api.routes.admin")
        admin_stub.get_current_user = MagicMock()  # type: ignore[attr-defined]
        admin_stub.require_role = MagicMock()  # type: ignore[attr-defined]
        sys.modules["api.routes.admin"] = admin_stub

    # Stub api.middleware.rate_limit
    if "api.middleware.rate_limit" not in sys.modules:
        rate_stub = ModuleType("api.middleware.rate_limit")
        rate_stub.get_rate_limiter = MagicMock()  # type: ignore[attr-defined]
        sys.modules["api.middleware.rate_limit"] = rate_stub

    # Load real api.models.tariff_schemas (Pydantic models must be real, not mocks)
    if "api.models.tariff_schemas" not in sys.modules:
        for mod in ["api.models", "api"]:
            if mod not in sys.modules:
                sys.modules[mod] = ModuleType(mod)
        tariff_spec = importlib.util.spec_from_file_location(
            "api.models.tariff_schemas",
            "/home/pepe/Proyectos/msi-a/api/models/tariff_schemas.py",
        )
        if tariff_spec is not None:
            tariff_mod = importlib.util.module_from_spec(tariff_spec)
            sys.modules["api.models.tariff_schemas"] = tariff_mod
            tariff_spec.loader.exec_module(tariff_mod)  # type: ignore[union-attr]

    # Stub database.models
    if "database.models" not in sys.modules:
        db_stub = ModuleType("database.models")
        db_stub.AdminUser = MagicMock()  # type: ignore[attr-defined]
        sys.modules["database.models"] = db_stub

    # Stub api.services.image_service
    if "api.services.image_service" not in sys.modules:
        img_svc_stub = ModuleType("api.services.image_service")
        img_svc_stub.get_image_service = MagicMock()  # type: ignore[attr-defined]
        sys.modules["api.services.image_service"] = img_svc_stub

    # Stub shared.config
    if "shared.config" not in sys.modules:
        cfg_stub = ModuleType("shared.config")
        cfg_stub.get_settings = MagicMock()  # type: ignore[attr-defined]
        sys.modules["shared.config"] = cfg_stub

    # Load api.routes.images via spec_from_file_location
    if "api.routes.images" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "api.routes.images",
            "/home/pepe/Proyectos/msi-a/api/routes/images.py",
        )
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["api.routes.images"] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

    # Restore the original function
    _fdu.ensure_multipart_is_installed = _orig_ensure  # type: ignore[assignment]

    return sys.modules["api.routes.images"]


images_module = _bootstrap_images_module()


# ---------------------------------------------------------------------------
# Tests — pure function _build_content_disposition_headers
# ---------------------------------------------------------------------------


class TestBuildContentDispositionHeaders:
    """C1: Content-Disposition header construction for PDF vs non-PDF files."""

    def test_pdf_filename_returns_inline_header(self) -> None:
        """
        GIVEN a filename ending in .pdf
        WHEN _build_content_disposition_headers is called
        THEN returns dict with Content-Disposition: inline; filename="<name>.pdf"
        """
        headers = images_module._build_content_disposition_headers("testfile.pdf")
        assert "Content-Disposition" in headers
        assert headers["Content-Disposition"] == 'inline; filename="testfile.pdf"'

    def test_jpeg_filename_returns_empty_headers(self) -> None:
        """
        GIVEN a filename ending in .jpg (non-PDF)
        WHEN _build_content_disposition_headers is called
        THEN returns empty dict (no Content-Disposition header added)
        """
        headers = images_module._build_content_disposition_headers("photo.jpg")
        assert headers == {}


# ---------------------------------------------------------------------------
# Triangulation — additional PDF variants and edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename, should_have_cd",
    [
        ("document.pdf", True),
        ("DOCUMENT.PDF", True),   # uppercase extension
        ("report.PDF", True),     # mixed case
        ("photo.jpg", False),
        ("image.jpeg", False),
        ("scan.png", False),
        ("archive.zip", False),
    ],
    ids=["pdf-lower", "pdf-upper", "pdf-mixed", "jpg", "jpeg", "png", "zip"],
)
def test_build_content_disposition_headers_parametrized(
    filename: str, should_have_cd: bool
) -> None:
    """All PDF variants produce the header; non-PDFs produce no header."""
    headers = images_module._build_content_disposition_headers(filename)
    if should_have_cd:
        assert "Content-Disposition" in headers
        assert "inline" in headers["Content-Disposition"]
        assert filename.lower() in headers["Content-Disposition"].lower()
    else:
        assert "Content-Disposition" not in headers
