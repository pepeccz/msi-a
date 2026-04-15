"""
T-02: Tests for element_code field in calcular_tarifa_con_elementos image dicts.

Verifies:
- Each element image in imagenes_ejemplo has "element_code" set to the element code
- Each base documentation image has "element_code" set to "_BASE_DOCS"
- Both element images and base images have the key present

These are pure unit tests that mock the services — no DB, no Redis.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_element(code: str, name: str, elem_id: str = None) -> dict:
    return {"id": elem_id or f"id-{code.lower()}", "code": code, "name": name}


def _make_image(image_url: str, image_type: str = "frontal", status: str = "active") -> dict:
    return {
        "image_url": image_url,
        "image_type": image_type,
        "description": f"Foto {image_type}",
        "title": f"Imagen {image_type}",
        "is_required": False,
        "user_instruction": "",
        "status": status,
    }


def _make_element_with_images(code: str, name: str, images: list[dict]) -> dict:
    return {
        "id": f"id-{code.lower()}",
        "code": code,
        "name": name,
        "images": images,
    }


def _make_tariff_result(tier_name: str = "Tier 1", price: float = 410.0) -> dict:
    return {
        "tier_id": "tier-uuid-1",
        "tier_name": tier_name,
        "price": price,
        "conditions": None,
        "warnings": [],
    }


def _make_category_data(base_doc_url: str | None = None) -> dict:
    base_docs = []
    if base_doc_url:
        base_docs.append({"description": "Ficha técnica", "image_url": base_doc_url})
    return {"base_documentation": base_docs}


def _build_mocks(elements, elem_with_images, tariff_result, category_data):
    """Build a common set of service mocks for calcular_tarifa tests."""
    mock_element_service = AsyncMock()
    mock_element_service.get_elements_by_category = AsyncMock(return_value=elements)
    mock_element_service.get_element_with_images = AsyncMock(return_value=elem_with_images)
    mock_element_service.get_element_warnings = AsyncMock(return_value=[])

    mock_tarifa_service = AsyncMock()
    mock_tarifa_service.select_tariff_by_rules = AsyncMock(return_value=tariff_result)
    mock_tarifa_service.get_category_data = AsyncMock(return_value=category_data)

    return mock_element_service, mock_tarifa_service


# ---------------------------------------------------------------------------
# T-02: element_code in element images
# ---------------------------------------------------------------------------


class TestElementCodeInImages:
    """T-02: element_code field is present on all images in calcular_tarifa response."""

    @pytest.mark.asyncio
    async def test_element_images_have_element_code(self):
        """Each element image dict has element_code matching the element code."""
        from agent.tools.element_tools import calcular_tarifa_con_elementos

        elements = [_make_element("ESCAPE", "Escape")]
        elem_with_images = _make_element_with_images("ESCAPE", "Escape", [
            _make_image("http://img.example.com/escape1.jpg"),
            _make_image("http://img.example.com/escape2.jpg"),
        ])
        mock_element_service, mock_tarifa_service = _build_mocks(
            elements, elem_with_images, _make_tariff_result(), _make_category_data()
        )

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=mock_element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=mock_tarifa_service),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-id-1"),
            patch("agent.tools.element_tools._validate_element_codes", return_value={"valid": ["ESCAPE"]}),
            patch("agent.tools.element_tools.get_tool_state", return_value={}),
        ):
            result = await calcular_tarifa_con_elementos.ainvoke({
                "categoria_vehiculo": "motos-part",
                "codigos_elementos": ["ESCAPE"],
                "skip_validation": True,
            })

        assert "imagenes_ejemplo" in result
        element_images = [img for img in result["imagenes_ejemplo"] if img.get("tipo") != "base"]
        assert len(element_images) == 2, f"Expected 2 element images, got {len(element_images)}"
        for img in element_images:
            assert "element_code" in img, f"element_code missing from image: {img}"
            assert img["element_code"] == "ESCAPE", f"Expected 'ESCAPE', got {img['element_code']}"

    @pytest.mark.asyncio
    async def test_multiple_elements_have_correct_element_codes(self):
        """Each element image has element_code matching its own element's code."""
        from agent.tools.element_tools import calcular_tarifa_con_elementos

        elements = [
            _make_element("ESCAPE", "Escape"),
            _make_element("SUSPENSION", "Suspensión"),
        ]

        async def get_elem_with_images_side_effect(elem_id: str):
            if elem_id == "id-escape":
                return _make_element_with_images("ESCAPE", "Escape", [
                    _make_image("http://img.example.com/escape1.jpg"),
                ])
            elif elem_id == "id-suspension":
                return _make_element_with_images("SUSPENSION", "Suspensión", [
                    _make_image("http://img.example.com/susp1.jpg"),
                ])
            return None

        mock_element_service = AsyncMock()
        mock_element_service.get_elements_by_category = AsyncMock(return_value=elements)
        mock_element_service.get_element_with_images = AsyncMock(
            side_effect=get_elem_with_images_side_effect
        )
        mock_element_service.get_element_warnings = AsyncMock(return_value=[])

        mock_tarifa_service = AsyncMock()
        mock_tarifa_service.select_tariff_by_rules = AsyncMock(return_value=_make_tariff_result())
        mock_tarifa_service.get_category_data = AsyncMock(return_value=_make_category_data())

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=mock_element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=mock_tarifa_service),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-id-1"),
            patch("agent.tools.element_tools._validate_element_codes", return_value={"valid": ["ESCAPE", "SUSPENSION"]}),
            patch("agent.tools.element_tools.get_tool_state", return_value={}),
        ):
            result = await calcular_tarifa_con_elementos.ainvoke({
                "categoria_vehiculo": "motos-part",
                "codigos_elementos": ["ESCAPE", "SUSPENSION"],
                "skip_validation": True,
            })

        assert "imagenes_ejemplo" in result
        element_images = [img for img in result["imagenes_ejemplo"] if img.get("tipo") != "base"]

        codes_in_images = {img["element_code"] for img in element_images}
        assert "ESCAPE" in codes_in_images, "ESCAPE missing from element_codes in images"
        assert "SUSPENSION" in codes_in_images, "SUSPENSION missing from element_codes in images"

    @pytest.mark.asyncio
    async def test_base_images_have_base_docs_sentinel(self):
        """T-02: Base documentation images have element_code='_BASE_DOCS'."""
        from agent.tools.element_tools import calcular_tarifa_con_elementos

        elements = [_make_element("ESCAPE", "Escape")]
        elem_with_images = _make_element_with_images("ESCAPE", "Escape", [
            _make_image("http://img.example.com/escape1.jpg"),
        ])
        category_data_with_base = _make_category_data(base_doc_url="http://img.example.com/ficha.jpg")
        mock_element_service, mock_tarifa_service = _build_mocks(
            elements, elem_with_images, _make_tariff_result(), category_data_with_base
        )

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=mock_element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=mock_tarifa_service),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-id-1"),
            patch("agent.tools.element_tools._validate_element_codes", return_value={"valid": ["ESCAPE"]}),
            patch("agent.tools.element_tools.get_tool_state", return_value={}),
        ):
            result = await calcular_tarifa_con_elementos.ainvoke({
                "categoria_vehiculo": "motos-part",
                "codigos_elementos": ["ESCAPE"],
                "skip_validation": True,
            })

        assert "imagenes_ejemplo" in result
        base_images = [img for img in result["imagenes_ejemplo"] if img.get("tipo") == "base"]
        assert len(base_images) >= 1, "Expected at least one base image"
        for img in base_images:
            assert "element_code" in img, f"element_code missing from base image: {img}"
            assert img["element_code"] == "_BASE_DOCS", f"Expected '_BASE_DOCS', got {img['element_code']}"

    @pytest.mark.asyncio
    async def test_all_images_have_element_code(self):
        """T-02: Every image in imagenes_ejemplo has element_code (no missing keys)."""
        from agent.tools.element_tools import calcular_tarifa_con_elementos

        elements = [_make_element("ESCAPE", "Escape")]
        elem_with_images = _make_element_with_images("ESCAPE", "Escape", [
            _make_image("http://img.example.com/escape1.jpg"),
            _make_image("http://img.example.com/escape2.jpg", status="placeholder"),
        ])
        category_data_with_base = _make_category_data(base_doc_url="http://img.example.com/ficha.jpg")
        mock_element_service, mock_tarifa_service = _build_mocks(
            elements, elem_with_images, _make_tariff_result(), category_data_with_base
        )

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=mock_element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=mock_tarifa_service),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-id-1"),
            patch("agent.tools.element_tools._validate_element_codes", return_value={"valid": ["ESCAPE"]}),
            patch("agent.tools.element_tools.get_tool_state", return_value={}),
        ):
            result = await calcular_tarifa_con_elementos.ainvoke({
                "categoria_vehiculo": "motos-part",
                "codigos_elementos": ["ESCAPE"],
                "skip_validation": True,
            })

        assert "imagenes_ejemplo" in result
        for img in result["imagenes_ejemplo"]:
            assert "element_code" in img, (
                f"element_code missing from image: {img}. "
                "All images must have element_code (T-02)."
            )
