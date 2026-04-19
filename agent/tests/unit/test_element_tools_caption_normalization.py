"""
Unit tests for element image dict caption normalization (Batch A, tasks A5–A8).

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
from agent.tools.element_tools import _build_element_image_dict


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
