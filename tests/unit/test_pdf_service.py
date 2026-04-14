"""
Tests for PdfService — Task 5 (billing-system)

Verifies:
  - generate() returns a file path string on success
  - generate() returns None when Weasyprint raises
  - os.makedirs is called with exist_ok=True
  - _write_pdf is a static method
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_INVOICE: dict = {
    "invoice_number": "MSI-2026-001",
    "issued_at": "01/04/2026",
    "due_date": "16/04/2026",
    "company_name": "MSI Automotive S.L.",
    "company_nif": "B12345678",
    "company_address": "Calle Mayor 1, 28001 Madrid",
    "client_name": "Taller Ejemplo S.L.",
    "client_nif": "B87654321",
    "client_address": "Avenida del Puerto 10, 46023 Valencia",
    "line_items": [
        {"description": "Honorarios de mantenimiento mensual", "amount": "50.00"},
        {"description": "Consumo de IA (tokens)", "amount": "3.42"},
    ],
    "subtotal": "53.42",
    "iva_rate": "21",
    "iva_amount": "11.22",
    "total": "64.64",
}


def _make_service():
    """Return a PdfService with a mocked Jinja2 environment."""
    from api.services.pdf_service import PdfService

    svc = PdfService.__new__(PdfService)
    mock_env = MagicMock()
    mock_template = MagicMock()
    mock_template.render.return_value = "<html>invoice</html>"
    mock_env.get_template.return_value = mock_template
    svc._env = mock_env
    return svc


# ---------------------------------------------------------------------------
# Test: generate() returns a path on success
# ---------------------------------------------------------------------------


class TestGenerateSuccess:
    """generate() must return a string path when everything works."""

    @pytest.mark.asyncio
    async def test_returns_string_path(self, tmp_path: Path) -> None:
        """generate() returns a str with the output file path."""
        svc = _make_service()

        with (
            patch("api.services.pdf_service.get_settings") as mock_settings,
            patch("os.makedirs") as mock_makedirs,
            patch.object(svc, "_write_pdf") as mock_write,
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_settings.return_value.INVOICES_DIR = str(tmp_path)
            mock_stat.return_value.st_size = 12345

            result = await svc.generate(SAMPLE_INVOICE)

        assert isinstance(result, str), f"Expected str, got {type(result)}"
        assert "MSI-2026-001.pdf" in result

    @pytest.mark.asyncio
    async def test_path_contains_invoice_number(self, tmp_path: Path) -> None:
        """Returned path must embed the invoice_number."""
        svc = _make_service()

        with (
            patch("api.services.pdf_service.get_settings") as mock_settings,
            patch("os.makedirs"),
            patch.object(svc, "_write_pdf"),
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_settings.return_value.INVOICES_DIR = str(tmp_path)
            mock_stat.return_value.st_size = 1

            result = await svc.generate(SAMPLE_INVOICE)

        assert SAMPLE_INVOICE["invoice_number"] in result

    @pytest.mark.asyncio
    async def test_makedirs_called_with_exist_ok_true(self, tmp_path: Path) -> None:
        """os.makedirs must be called with exist_ok=True."""
        svc = _make_service()

        with (
            patch("api.services.pdf_service.get_settings") as mock_settings,
            patch("os.makedirs") as mock_makedirs,
            patch.object(svc, "_write_pdf"),
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_settings.return_value.INVOICES_DIR = str(tmp_path)
            mock_stat.return_value.st_size = 1

            await svc.generate(SAMPLE_INVOICE)

        mock_makedirs.assert_called_once()
        _args, kwargs = mock_makedirs.call_args
        assert kwargs.get("exist_ok") is True, (
            f"makedirs was not called with exist_ok=True — kwargs: {kwargs}"
        )


# ---------------------------------------------------------------------------
# Test: generate() returns None on failure
# ---------------------------------------------------------------------------


class TestGenerateFailure:
    """generate() must return None and log ERROR when Weasyprint raises."""

    @pytest.mark.asyncio
    async def test_returns_none_on_weasyprint_error(self, tmp_path: Path) -> None:
        """generate() must swallow Weasyprint errors and return None."""
        svc = _make_service()

        with (
            patch("api.services.pdf_service.get_settings") as mock_settings,
            patch("os.makedirs"),
            patch.object(svc, "_write_pdf", side_effect=RuntimeError("weasyprint exploded")),
            patch("api.services.pdf_service.logger") as mock_logger,
        ):
            mock_settings.return_value.INVOICES_DIR = str(tmp_path)

            result = await svc.generate(SAMPLE_INVOICE)

        assert result is None, f"Expected None on failure, got {result!r}"

    @pytest.mark.asyncio
    async def test_logs_error_on_failure(self, tmp_path: Path) -> None:
        """generate() must call logger.error with pdf_generation_failed."""
        svc = _make_service()

        with (
            patch("api.services.pdf_service.get_settings") as mock_settings,
            patch("os.makedirs"),
            patch.object(svc, "_write_pdf", side_effect=Exception("boom")),
            patch("api.services.pdf_service.logger") as mock_logger,
        ):
            mock_settings.return_value.INVOICES_DIR = str(tmp_path)

            await svc.generate(SAMPLE_INVOICE)

        mock_logger.error.assert_called_once()
        event_name = mock_logger.error.call_args[0][0]
        assert event_name == "pdf_generation_failed", (
            f"Expected 'pdf_generation_failed' but got {event_name!r}"
        )

    @pytest.mark.asyncio
    async def test_never_raises(self, tmp_path: Path) -> None:
        """generate() must never raise — any exception becomes None."""
        svc = _make_service()

        with (
            patch("api.services.pdf_service.get_settings") as mock_settings,
            patch("os.makedirs"),
            patch.object(svc, "_write_pdf", side_effect=MemoryError("OOM")),
        ):
            mock_settings.return_value.INVOICES_DIR = str(tmp_path)

            # Must not raise
            result = await svc.generate(SAMPLE_INVOICE)

        assert result is None


# ---------------------------------------------------------------------------
# Test: _write_pdf is a static method
# ---------------------------------------------------------------------------


class TestWritePdfStaticMethod:
    """_write_pdf must be declared as a static method."""

    def test_is_static_method(self) -> None:
        """PdfService._write_pdf must be a staticmethod."""
        from api.services.pdf_service import PdfService

        raw = inspect.getattr_static(PdfService, "_write_pdf")
        assert isinstance(raw, staticmethod), (
            f"Expected staticmethod but got {type(raw)}"
        )

    def test_can_be_called_without_instance(self) -> None:
        """_write_pdf must be callable without an instance (static signature)."""
        from api.services.pdf_service import PdfService

        # Patch weasyprint to avoid the actual import
        mock_html_instance = MagicMock()
        mock_html_cls = MagicMock(return_value=mock_html_instance)

        with patch.dict("sys.modules", {"weasyprint": MagicMock(HTML=mock_html_cls)}):
            # Should not raise TypeError about missing self
            PdfService._write_pdf("<html/>", "/tmp/test.pdf")

        mock_html_cls.assert_called_once_with(string="<html/>")
        mock_html_instance.write_pdf.assert_called_once_with("/tmp/test.pdf")


# ---------------------------------------------------------------------------
# Test: Weasyprint is lazy-imported
# ---------------------------------------------------------------------------


class TestWeasyPrintLazyImport:
    """weasyprint must not be imported at module load time."""

    def test_weasyprint_not_in_top_level_imports(self) -> None:
        """Importing pdf_service must not trigger a weasyprint import."""
        import sys

        # Remove weasyprint from sys.modules so we can detect if it gets loaded
        weasyprint_present_before = "weasyprint" in sys.modules

        # Force reimport of the service module (it's already imported, but
        # we verify the module itself doesn't import weasyprint at top level)
        import api.services.pdf_service  # noqa: F401

        # If weasyprint wasn't in sys.modules before, it must still not be
        # (unless it was already installed and auto-imported elsewhere)
        # We check indirectly: module source has lazy import in _write_pdf
        import ast
        import pathlib

        source = pathlib.Path(api.services.pdf_service.__file__).read_text()
        tree = ast.parse(source)

        # Top-level imports
        top_level_imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            and not isinstance(
                # Exclude imports inside function bodies
                next(
                    (
                        p
                        for p in ast.walk(tree)
                        if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and any(node is child for child in ast.walk(p))
                    ),
                    None,
                ),
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
        ]

        # A simpler check: weasyprint should NOT appear outside a function
        function_nodes = {
            id(child)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for child in ast.walk(node)
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "weasyprint" in node.module:
                    assert id(node) in function_nodes, (
                        "weasyprint must only be imported inside a function, not at module level"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "weasyprint" in alias.name:
                        assert id(node) in function_nodes, (
                            "weasyprint must only be imported inside a function, not at module level"
                        )
