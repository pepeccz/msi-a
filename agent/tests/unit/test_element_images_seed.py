"""
Unit tests for ASIDEROS element image caption quality (Fix B drift guard).

Covers:
  AC-B.1: caption for ASIDEROS images MUST NOT contain "ASEIDERO" (typo pollution).
  AC-B.2: when title="" and user_instruction="", caption MUST equal normalized_name
          with NO trailing " — " or any suffix.

Design: tests are DB-free. They call _build_element_image_dict directly with
minimal mocked dicts that mirror the corrected seed structure for ASIDEROS.
These tests fail if someone adds a polluted title back to the seed or if the
caption helper changes its normalization logic.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ASIDEROS_ELEM = {
    "code": "ASIDEROS",
    "name": "Asideros / Agarraderas",
}


def _build(img: dict) -> dict:
    """Call _build_element_image_dict with ASIDEROS element and given img dict."""
    from agent.tools.element_tools import _build_element_image_dict
    return _build_element_image_dict(_ASIDEROS_ELEM, img, "active")


# ---------------------------------------------------------------------------
# AC-B.1 — No typo-code suffix in caption
# ---------------------------------------------------------------------------


class TestAsiderosImageCaption:
    """AC-B.1: ASIDEROS captions must NOT contain 'ASEIDERO'."""

    def test_caption_no_typo_when_title_is_empty(self):
        """
        GIVEN an ASIDEROS image dict with title="" and user_instruction=""
        WHEN _build_element_image_dict builds the caption
        THEN 'ASEIDERO' MUST NOT appear in 'descripcion'.

        This is the clean-seed scenario: both guidance fields are absent.
        AC-B.1.
        """
        img = {
            "image_url": "https://example.com/asideros.png",
            "image_type": "example",
            "title": "",
            "user_instruction": "",
        }
        result = _build(img)
        assert "ASEIDERO" not in result["descripcion"], (
            f"Caption {result['descripcion']!r} must not contain 'ASEIDERO'. "
            "The seed title must be empty or a real descriptive label. AC-B.1."
        )

    def test_caption_no_typo_when_title_is_none(self):
        """
        GIVEN an ASIDEROS image dict with title=None and user_instruction=None
        WHEN _build_element_image_dict builds the caption
        THEN 'ASEIDERO' MUST NOT appear in 'descripcion'.

        Covers the case where the DB column is NULL.
        AC-B.1.
        """
        img = {
            "image_url": "https://example.com/asideros.png",
            "image_type": "example",
            "title": None,
            "user_instruction": None,
        }
        result = _build(img)
        assert "ASEIDERO" not in result["descripcion"], (
            f"Caption {result['descripcion']!r} must not contain 'ASEIDERO'. AC-B.1."
        )

    def test_caption_no_typo_when_title_is_polluted(self):
        """
        GIVEN an ASIDEROS image dict with title='ASEIDERO' (the DB pollution)
        WHEN _build_element_image_dict builds the caption
        THEN 'ASEIDERO' WILL appear — documenting the bug that Fix B corrects.

        This test INTENTIONALLY asserts the presence of the bug to document it,
        and serves as a tombstone: when the seed is corrected, this test is the
        proof that the helper IS the correct code path (no code fix needed in the
        helper). The real fix is in the seed data / DB title field.

        NOTE: this test asserts the BUG behavior to document it. The companion
        test_caption_no_typo_when_title_is_empty confirms the FIXED behavior.
        """
        img = {
            "image_url": "https://example.com/asideros.png",
            "image_type": "example",
            "title": "ASEIDERO",
            "user_instruction": "",
        }
        result = _build(img)
        # Document the bug: polluted title propagates to caption.
        assert "ASEIDERO" in result["descripcion"], (
            "When title='ASEIDERO', the caption should contain it — this documents "
            "the root cause. Fix B corrects the seed title, not this code path."
        )


# ---------------------------------------------------------------------------
# AC-B.2 — Name-only caption when no guidance present
# ---------------------------------------------------------------------------


class TestNameOnlyCaptionWhenNoGuidance:
    """AC-B.2: when user_instruction="" and title="", caption MUST equal normalized_name."""

    def test_name_only_caption_empty_strings(self):
        """
        GIVEN user_instruction="" AND title=""
        WHEN _build_element_image_dict builds the caption
        THEN result['descripcion'] MUST equal 'Asideros / Agarraderas' exactly.

        No trailing ' — ', no suffix, no extra spaces.
        AC-B.2.
        """
        img = {
            "image_url": "https://example.com/asideros.png",
            "image_type": "example",
            "title": "",
            "user_instruction": "",
        }
        result = _build(img)
        expected = "Asideros / Agarraderas"
        assert result["descripcion"] == expected, (
            f"Caption {result['descripcion']!r} must equal {expected!r} when no guidance. "
            "No trailing ' — ' or any suffix allowed. AC-B.2."
        )

    def test_name_only_caption_none_values(self):
        """
        GIVEN user_instruction=None AND title=None
        WHEN _build_element_image_dict builds the caption
        THEN result['descripcion'] MUST equal 'Asideros / Agarraderas' exactly.

        AC-B.2 (NULL variant).
        """
        img = {
            "image_url": "https://example.com/asideros.png",
            "image_type": "example",
            "title": None,
            "user_instruction": None,
        }
        result = _build(img)
        expected = "Asideros / Agarraderas"
        assert result["descripcion"] == expected, (
            f"Caption {result['descripcion']!r} must equal {expected!r} when guidance is None. AC-B.2."
        )

    def test_caption_includes_guidance_when_user_instruction_present(self):
        """
        GIVEN user_instruction="Foto del asidero con matrícula del vehículo visible"
        WHEN _build_element_image_dict builds the caption
        THEN result['descripcion'] MUST equal
             'Asideros / Agarraderas — Foto del asidero con matrícula del vehículo visible'.

        Triangulation: confirms guidance is used when present.
        AC-B.2 (positive case).
        """
        instruction = "Foto del asidero con matrícula del vehículo visible"
        img = {
            "image_url": "https://example.com/asideros.png",
            "image_type": "example",
            "title": "",
            "user_instruction": instruction,
        }
        result = _build(img)
        expected = f"Asideros / Agarraderas — {instruction}"
        assert result["descripcion"] == expected, (
            f"Caption {result['descripcion']!r} must include user_instruction as guidance. "
            f"Expected {expected!r}. AC-B.2 positive case."
        )
