"""Invoice PDF generation service using Weasyprint + Jinja2."""

__all__ = ["PdfService"]

import asyncio
import os
from pathlib import Path
from typing import Any

import structlog
from jinja2 import Environment, FileSystemLoader

from shared.config import get_settings

logger = structlog.get_logger(__name__)

# Template directory relative to this file
_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


class PdfService:
    """Generates invoice PDFs from HTML templates."""

    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )

    async def generate(self, invoice_data: dict[str, Any]) -> str | None:
        """Render an invoice PDF and save to disk.

        Args:
            invoice_data: Dict with keys: invoice_number, issued_at, due_date,
                company_name, company_nif, company_address,
                client_name, client_nif, client_address,
                line_items (list of {description, amount}),
                subtotal, iva_rate, iva_amount, total

        Returns:
            File path on success, None on failure (logged, never raises).
        """
        settings = get_settings()
        try:
            # Render HTML
            template = self._env.get_template("invoice.html")
            html_content = template.render(**invoice_data)

            # Create output directory
            output_dir = Path(settings.INVOICES_DIR)
            os.makedirs(output_dir, exist_ok=True)

            # Generate PDF in executor (Weasyprint is CPU-bound)
            output_path = output_dir / f"{invoice_data['invoice_number']}.pdf"

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._write_pdf, html_content, str(output_path))

            file_size = output_path.stat().st_size
            logger.info(
                "pdf_generated",
                filename=output_path.name,
                file_size_bytes=file_size,
            )
            return str(output_path)

        except Exception:
            logger.error(
                "pdf_generation_failed",
                invoice_number=invoice_data.get("invoice_number"),
                exc_info=True,
            )
            return None

    @staticmethod
    def _write_pdf(html_content: str, output_path: str) -> None:
        """Synchronous PDF writing — runs in thread pool."""
        from weasyprint import HTML  # Lazy import (heavy module)

        HTML(string=html_content).write_pdf(output_path)
