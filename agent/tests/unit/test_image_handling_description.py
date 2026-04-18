"""
Unit tests for the content-type-aware CaseImage description helpers in image_handling.

Covers:
- B1: _get_case_image_description for save path (reconciliation=False)
- B3: _get_case_image_description for reconciliation path (reconciliation=True)

Both paths use the same pure helper — parametrize over both for coverage.

spec refs:
  - Scenario "PDF upload" → description == "Documento enviado por usuario via WhatsApp"
  - Scenario "Image upload (unchanged behavior)" → "Imagen enviada por usuario via WhatsApp"
  - Scenario "PDF reconciliation" → "Documento recuperado por reconciliación"
  - Scenario "Image reconciliation" → "Imagen recuperada por reconciliación"
"""

import pytest


# ---------------------------------------------------------------------------
# Import the pure helper (does NOT exist yet → tests FAIL with ImportError).
# ---------------------------------------------------------------------------
from agent.services.image_handling import _get_case_image_description


# ---------------------------------------------------------------------------
# Constants (mirrors the production strings — if they drift, tests catch it)
# ---------------------------------------------------------------------------

_DESC_DOC_SAVE = "Documento enviado por usuario via WhatsApp"
_DESC_IMG_SAVE = "Imagen enviada por usuario via WhatsApp"
_DESC_DOC_RECON = "Documento recuperado por reconciliación"
_DESC_IMG_RECON = "Imagen recuperada por reconciliación"


# ---------------------------------------------------------------------------
# Tests — primary save path
# ---------------------------------------------------------------------------


class TestGetCaseImageDescriptionSave:
    """B1: description at primary save time (reconciliation=False)."""

    def test_pdf_attachment_returns_documento_description(self):
        """
        GIVEN a document attachment (file_type=="file")
        WHEN _get_case_image_description(is_doc=True, reconciliation=False)
        THEN returns the Documento save string
        """
        result = _get_case_image_description(is_doc=True, reconciliation=False)
        assert result == _DESC_DOC_SAVE

    def test_image_attachment_returns_imagen_description(self):
        """
        GIVEN a photo attachment (file_type != "file" and type != "document")
        WHEN _get_case_image_description(is_doc=False, reconciliation=False)
        THEN returns the Imagen save string (unchanged behavior)
        """
        result = _get_case_image_description(is_doc=False, reconciliation=False)
        assert result == _DESC_IMG_SAVE


# ---------------------------------------------------------------------------
# Tests — reconciliation path
# ---------------------------------------------------------------------------


class TestGetCaseImageDescriptionReconciliation:
    """B3: description at reconciliation time (reconciliation=True)."""

    def test_pdf_reconciliation_returns_documento_recon_description(self):
        """
        GIVEN a document attachment recovered during reconciliation
        WHEN _get_case_image_description(is_doc=True, reconciliation=True)
        THEN returns "Documento recuperado por reconciliación"
        """
        result = _get_case_image_description(is_doc=True, reconciliation=True)
        assert result == _DESC_DOC_RECON

    def test_image_reconciliation_returns_imagen_recon_description(self):
        """
        GIVEN a photo attachment recovered during reconciliation
        WHEN _get_case_image_description(is_doc=False, reconciliation=True)
        THEN returns "Imagen recuperada por reconciliación"
        """
        result = _get_case_image_description(is_doc=False, reconciliation=True)
        assert result == _DESC_IMG_RECON


# ---------------------------------------------------------------------------
# Triangulation: ensure the function branches correctly for all 4 combinations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "is_doc, reconciliation, expected",
    [
        (True, False, _DESC_DOC_SAVE),
        (False, False, _DESC_IMG_SAVE),
        (True, True, _DESC_DOC_RECON),
        (False, True, _DESC_IMG_RECON),
    ],
    ids=["doc-save", "img-save", "doc-recon", "img-recon"],
)
def test_get_case_image_description_all_combinations(
    is_doc: bool, reconciliation: bool, expected: str
) -> None:
    """All four branches must map to the correct description string."""
    assert _get_case_image_description(is_doc=is_doc, reconciliation=reconciliation) == expected
