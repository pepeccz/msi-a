"""
Unit tests for element image dict caption normalization (Batch A, tasks A5–A8)
and DOCUMENTACION REQUERIDA bullet construction (A1, A2, A3).

Covers:
- AC-5.1: img["elemento"] equals the DB element `name` field, not user description
- AC-5.2: caption (descripcion) does NOT contain raw user-input tokens
- AC-5.3: when visual guidance metadata exists, it appears in the caption
- AC-5.4: when visual guidance is absent, caption is valid (normalized name only)

Design: tests target a pure helper `_build_element_image_dict` extracted from
`calcular_tarifa_con_elementos`. This avoids 10+ mocks to test a one-line
transformation (Extract-Before-Mock Rule from strict-tdd.md).

The helper takes (elem, img, img_status) and returns the image dict that ends
up in `element_images`. The caption field "descripcion" is what `main.py` reads
to build the Chatwoot caption.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Import the pure helper — does NOT exist yet → all tests FAIL with ImportError.
# ---------------------------------------------------------------------------
from agent.tools.element_tools import _build_element_image_dict, _build_docs_bullets


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_ELEM_NORMALIZED = {"id": "uuid-1", "name": "Asidero lateral", "code": "ASIDERO"}
_ELEM_TYPO = {"id": "uuid-2", "name": "Escape deportivo", "code": "ESCAPE"}

_IMG_FULL = {
    "image_url": "https://example.com/asidero.jpg",
    "image_type": "ejemplo",
    "title": "Foto del asidero",
    "description": "aseidero roto viejo",  # user typo / wrong description
    "is_required": True,
    "user_instruction": "Fotografía el asidero de frente, asegúrate de que se vea el tornillo.",
    "status": "active",
}

_IMG_NO_GUIDANCE = {
    "image_url": "https://example.com/escape.jpg",
    "image_type": "ejemplo",
    "title": "",
    "description": "some raw desc",
    "is_required": False,
    "user_instruction": "",
    "status": "active",
}

_IMG_TITLE_ONLY = {
    "image_url": "https://example.com/escape2.jpg",
    "image_type": "ejemplo",
    "title": "Vista lateral del escape",
    "description": "",
    "is_required": False,
    "user_instruction": "",
    "status": "active",
}


# ---------------------------------------------------------------------------
# AC-5.1 — img["elemento"] equals DB elem["name"]
# ---------------------------------------------------------------------------


class TestElementoFieldUsesNormalizedName:
    """AC-5.1: the 'elemento' key in the built dict MUST be the DB name."""

    def test_elemento_equals_db_name_not_user_description(self):
        """
        GIVEN an element with DB name 'Asidero lateral'
        AND an image whose description contains user typo 'aseidero roto viejo'
        WHEN _build_element_image_dict is called
        THEN img['elemento'] MUST equal 'Asidero lateral' (the DB name)
        AND MUST NOT contain the user typo 'aseidero'
        """
        result = _build_element_image_dict(_ELEM_NORMALIZED, _IMG_FULL, "active")
        assert result["elemento"] == "Asidero lateral", (
            f"Expected 'Asidero lateral' but got {result['elemento']!r}. "
            "The 'elemento' field must use DB elem['name'], not image description."
        )
        assert "aseidero" not in result["elemento"].lower(), (
            "User typo 'aseidero' leaked into the 'elemento' field."
        )

    def test_elemento_equals_db_name_for_second_element(self):
        """
        GIVEN an element with DB name 'Escape deportivo'
        WHEN _build_element_image_dict is called
        THEN img['elemento'] equals 'Escape deportivo'
        """
        result = _build_element_image_dict(_ELEM_TYPO, _IMG_FULL, "active")
        assert result["elemento"] == "Escape deportivo"


# ---------------------------------------------------------------------------
# AC-5.2 — caption (descripcion) does NOT contain raw user-input tokens
# ---------------------------------------------------------------------------


class TestDescripcionDoesNotContainUserInput:
    """AC-5.2: the 'descripcion' (Chatwoot caption) must NOT contain user-supplied text."""

    def test_descripcion_does_not_use_image_description_field_raw(self):
        """
        GIVEN an image with description='aseidero roto viejo' (user typo)
        WHEN _build_element_image_dict is called
        THEN result['descripcion'] MUST NOT contain 'aseidero roto viejo'
        """
        result = _build_element_image_dict(_ELEM_NORMALIZED, _IMG_FULL, "active")
        assert "aseidero roto viejo" not in result["descripcion"], (
            "User-typed description leaked into the caption (descripcion). "
            "Caption must be derived from DB normalized name."
        )

    def test_descripcion_starts_with_normalized_element_name(self):
        """
        GIVEN any element with DB name 'Asidero lateral'
        WHEN _build_element_image_dict is called
        THEN result['descripcion'] MUST start with 'Asidero lateral'
        """
        result = _build_element_image_dict(_ELEM_NORMALIZED, _IMG_FULL, "active")
        assert result["descripcion"].startswith("Asidero lateral"), (
            f"Caption should start with normalized name 'Asidero lateral'. "
            f"Got: {result['descripcion']!r}"
        )


# ---------------------------------------------------------------------------
# AC-5.3 — visual guidance (from user_instruction or title) appears in caption
# ---------------------------------------------------------------------------


class TestVisualGuidanceInCaption:
    """AC-5.3: when visual guidance metadata exists, it appears in the caption."""

    def test_user_instruction_included_in_descripcion(self):
        """
        GIVEN an image with user_instruction='Fotografía el asidero de frente...'
        WHEN _build_element_image_dict is called
        THEN result['descripcion'] MUST contain the user_instruction text
        """
        result = _build_element_image_dict(_ELEM_NORMALIZED, _IMG_FULL, "active")
        assert "Fotografía el asidero de frente" in result["descripcion"], (
            "user_instruction should appear in descripcion when present. "
            f"Got: {result['descripcion']!r}"
        )

    def test_title_used_as_guidance_when_no_user_instruction(self):
        """
        GIVEN an image with title='Vista lateral del escape' and no user_instruction
        WHEN _build_element_image_dict is called
        THEN result['descripcion'] MUST contain the title text as guidance
        """
        result = _build_element_image_dict(_ELEM_TYPO, _IMG_TITLE_ONLY, "active")
        assert "Vista lateral del escape" in result["descripcion"], (
            "title should be used as guidance when user_instruction is absent. "
            f"Got: {result['descripcion']!r}"
        )


# ---------------------------------------------------------------------------
# AC-5.4 — absent visual guidance → valid caption (normalized name only)
# ---------------------------------------------------------------------------


class TestAbsentVisualGuidanceFallback:
    """AC-5.4: when visual guidance is absent, caption is the normalized name only."""

    def test_descripcion_is_normalized_name_when_no_guidance(self):
        """
        GIVEN an image with no title and no user_instruction
        WHEN _build_element_image_dict is called
        THEN result['descripcion'] MUST equal the DB element name exactly
        AND MUST NOT contain any error text or placeholder
        """
        result = _build_element_image_dict(_ELEM_TYPO, _IMG_NO_GUIDANCE, "active")
        assert result["descripcion"] == "Escape deportivo", (
            f"When no guidance is available, descripcion must be exactly the "
            f"normalized name. Got: {result['descripcion']!r}"
        )

    def test_no_error_text_in_descripcion_when_no_guidance(self):
        """
        GIVEN an image with no guidance metadata
        WHEN _build_element_image_dict is called
        THEN result['descripcion'] MUST NOT contain error markers like 'None',
        'undefined', 'error', or empty string.
        """
        result = _build_element_image_dict(_ELEM_TYPO, _IMG_NO_GUIDANCE, "active")
        descripcion = result["descripcion"]
        assert descripcion, "descripcion must not be empty"
        assert "None" not in descripcion
        assert "undefined" not in descripcion.lower()
        assert "error" not in descripcion.lower()


# ---------------------------------------------------------------------------
# Triangulation: element_code passthrough stays intact (non-regression)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "elem, img, expected_code",
    [
        (_ELEM_NORMALIZED, _IMG_FULL, "ASIDERO"),
        (_ELEM_TYPO, _IMG_FULL, "ESCAPE"),
    ],
    ids=["asidero", "escape"],
)
def test_element_code_passthrough(elem: dict, img: dict, expected_code: str) -> None:
    """
    The 'element_code' field MUST be the DB elem['code'] — unaffected by the
    caption normalization change.
    """
    result = _build_element_image_dict(elem, img, "active")
    assert result["element_code"] == expected_code


# ===========================================================================
# Tests for _build_docs_bullets (A1, A2, A3) — RED phase
# These import a pure helper that does NOT exist yet → ImportError until
# Phase 4 GREEN implements _build_docs_bullets in element_tools.py.
# ===========================================================================

_ELEM_DOC_SINGLE = {
    "nombre": "Escape deportivo",
    "imagenes": [
        {
            "descripcion": "Foto del escape",
            "titulo": "Escape",
            "status": "active",
            "_inherited_from": None,
        }
    ],
}

_ELEM_DOC_MULTI_PARA = {
    "nombre": "Escape deportivo",
    "imagenes": [
        {
            "descripcion": "Foto frontal\n\nFoto lateral",
            "titulo": "Escape",
            "status": "active",
            "_inherited_from": None,
        }
    ],
}

_ELEM_DOC_TRAILING_EMPTY = {
    "nombre": "Escape deportivo",
    "imagenes": [
        {
            "descripcion": "Foto frontal\n\n",
            "titulo": "Escape",
            "status": "active",
            "_inherited_from": None,
        }
    ],
}

_ELEM_DOC_OWN_ACTIVE_PLUS_INHERITED_PLACEHOLDER = {
    "nombre": "Catalizador",
    "imagenes": [
        {
            "descripcion": "Foto propia activa",
            "titulo": "Catalizador propio",
            "status": "active",
            "_inherited_from": None,
        },
        {
            "descripcion": "Foto heredada placeholder",
            "titulo": "Herencia",
            "status": "placeholder",
            "_inherited_from": "ESCAPE",
        },
    ],
}

_ELEM_DOC_NO_OWN_INHERITED_ACTIVE = {
    "nombre": "Catalizador",
    "imagenes": [
        {
            "descripcion": "Foto heredada activa",
            "titulo": "Herencia activa",
            "status": "active",
            "_inherited_from": "ESCAPE",
        },
    ],
}

_ELEM_DOC_NO_OWN_INHERITED_PLACEHOLDER = {
    "nombre": "Catalizador",
    "imagenes": [
        {
            "descripcion": "Foto heredada placeholder",
            "titulo": "Herencia placeholder",
            "status": "placeholder",
            "_inherited_from": "ESCAPE",
        },
    ],
}

_ELEM_DOC_TWO_OWN_ACTIVE_PLUS_INHERITED_PLACEHOLDER = {
    "nombre": "Catalizador",
    "imagenes": [
        {
            "descripcion": "Foto propia activa 1",
            "titulo": "Propia 1",
            "status": "active",
            "_inherited_from": None,
        },
        {
            "descripcion": "Foto propia activa 2",
            "titulo": "Propia 2",
            "status": "active",
            "_inherited_from": None,
        },
        {
            "descripcion": "Foto heredada placeholder",
            "titulo": "Herencia",
            "status": "placeholder",
            "_inherited_from": "ESCAPE",
        },
    ],
}


def _bullets_for(elem_doc: dict) -> list[str]:
    """Extract the bullet lines from _build_docs_bullets for a single elem_doc."""
    lines = _build_docs_bullets([elem_doc])
    # Return only lines that start with "    - " (the bullet lines)
    return [ln for ln in lines if ln.startswith("    - ")]


# ---------------------------------------------------------------------------
# A1: No "reformula" in prefix; new prefix "Fuente DB" used
# ---------------------------------------------------------------------------


class TestA1NoPhraseReformula:
    """A1: instruction prefix must NOT contain 'reformula'; must contain 'Fuente DB'."""

    def test_single_desc_bullet_has_fuente_db_prefix(self):
        """
        GIVEN single-paragraph descripcion
        WHEN _build_docs_bullets is called
        THEN bullet contains '(Fuente DB — usa íntegra' prefix
        AND does NOT contain 'reformula'
        (Scenario A1-1, A2-2)
        """
        bullets = _bullets_for(_ELEM_DOC_SINGLE)
        assert len(bullets) == 1
        assert "(Fuente DB — usa íntegra" in bullets[0]
        assert "reformula" not in bullets[0]

    def test_multi_para_bullets_all_have_fuente_db_prefix(self):
        """
        GIVEN two-paragraph descripcion
        WHEN _build_docs_bullets is called
        THEN both bullets carry the 'Fuente DB' prefix (Scenario A1-2)
        """
        bullets = _bullets_for(_ELEM_DOC_MULTI_PARA)
        assert len(bullets) == 2
        for b in bullets:
            assert "(Fuente DB — usa íntegra" in b
            assert "reformula" not in b


# ---------------------------------------------------------------------------
# A2: One bullet per \n\n-paragraph
# ---------------------------------------------------------------------------


class TestA2BulletsPerParagraph:
    """A2: descripcion split on \\n\\n → one bullet per non-empty paragraph."""

    def test_multi_paragraph_yields_two_bullets(self):
        """
        GIVEN descripcion = 'Foto frontal\\n\\nFoto lateral'
        WHEN _build_docs_bullets is called
        THEN exactly 2 bullets emitted (Scenario A2-1)
        """
        bullets = _bullets_for(_ELEM_DOC_MULTI_PARA)
        assert len(bullets) == 2
        assert "Foto frontal" in bullets[0]
        assert "Foto lateral" in bullets[1]

    def test_single_paragraph_yields_one_bullet(self):
        """
        GIVEN descripcion with no \\n\\n
        WHEN _build_docs_bullets is called
        THEN exactly 1 bullet (Scenario A2-2)
        """
        bullets = _bullets_for(_ELEM_DOC_SINGLE)
        assert len(bullets) == 1

    def test_trailing_empty_segment_skipped(self):
        """
        GIVEN descripcion = 'Foto frontal\\n\\n' (trailing separator)
        WHEN _build_docs_bullets is called
        THEN exactly 1 bullet, empty segment skipped (Scenario A2-3)
        """
        bullets = _bullets_for(_ELEM_DOC_TRAILING_EMPTY)
        assert len(bullets) == 1
        assert "Foto frontal" in bullets[0]


# ---------------------------------------------------------------------------
# A3: Placeholder inherited image suppression
# ---------------------------------------------------------------------------


class TestA3PlaceholderInheritedSuppression:
    """A3: placeholder inherited images skipped when child has active own image."""

    def test_own_active_present_placeholder_inherited_skipped(self):
        """
        GIVEN child has own active image AND inherited placeholder
        WHEN _build_docs_bullets is called
        THEN only 1 bullet (own active); inherited placeholder excluded (Scenario A3-1)
        """
        bullets = _bullets_for(_ELEM_DOC_OWN_ACTIVE_PLUS_INHERITED_PLACEHOLDER)
        assert len(bullets) == 1
        assert "Foto propia activa" in bullets[0]
        assert "Foto heredada placeholder" not in " ".join(bullets)

    def test_no_own_image_inherited_active_rendered(self):
        """
        GIVEN child has no own images, only inherited active
        WHEN _build_docs_bullets is called
        THEN inherited active IS rendered (Scenario A3-2)
        """
        bullets = _bullets_for(_ELEM_DOC_NO_OWN_INHERITED_ACTIVE)
        assert len(bullets) == 1
        assert "Foto heredada activa" in bullets[0]

    def test_no_own_image_inherited_placeholder_rendered_as_fallback(self):
        """
        GIVEN child has no own images, only inherited placeholder
        WHEN _build_docs_bullets is called
        THEN inherited placeholder IS rendered (fallback — Scenario A3-3)
        """
        bullets = _bullets_for(_ELEM_DOC_NO_OWN_INHERITED_PLACEHOLDER)
        assert len(bullets) == 1
        assert "Foto heredada placeholder" in bullets[0]

    def test_two_own_active_all_placeholders_suppressed(self):
        """
        GIVEN child has 2 own active images + 1 inherited placeholder
        WHEN _build_docs_bullets is called
        THEN only 2 bullets (own active); inherited placeholder excluded (Scenario A3-4)
        """
        bullets = _bullets_for(_ELEM_DOC_TWO_OWN_ACTIVE_PLUS_INHERITED_PLACEHOLDER)
        assert len(bullets) == 2
        assert "Foto propia activa 1" in bullets[0]
        assert "Foto propia activa 2" in bullets[1]
        assert "Foto heredada placeholder" not in " ".join(bullets)
