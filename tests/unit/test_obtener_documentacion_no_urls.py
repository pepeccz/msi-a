"""
T-04: Tests for obtener_documentacion_elemento — no image URLs in response.

Verifies:
- The "imagenes" key is absent from the response (stripped)
- The "texto" key is present with expected content
- Error paths also return no "imagenes" key
- obtener_documentacion_elemento is NOT in PRE_EXPEDIENTE tool list

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


def _make_element_with_images(code: str, name: str, images: list[dict] = None) -> dict:
    return {
        "id": f"id-{code.lower()}",
        "code": code,
        "name": name,
        "images": images or [],
    }


def _make_doc_image(url: str, title: str = "Foto ejemplo", is_required: bool = False) -> dict:
    return {
        "image_url": url,
        "image_type": "frontal",
        "title": title,
        "description": f"Descripción de {title}",
        "is_required": is_required,
    }


def _make_category_data(base_doc_url: str | None = None) -> dict:
    base_docs = []
    if base_doc_url:
        base_docs.append({"description": "Ficha técnica", "image_url": base_doc_url})
    return {"base_documentation": base_docs}


# ---------------------------------------------------------------------------
# T-04: "imagenes" key absent (stripped)
# ---------------------------------------------------------------------------


class TestObtenerDocumentacionNoImagenes:
    """T-04: obtener_documentacion_elemento must NOT return 'imagenes' key."""

    @pytest.mark.asyncio
    async def test_imagenes_key_absent_from_response(self):
        """T-04: 'imagenes' key must NOT be present in the response."""
        from agent.tools.element_tools import obtener_documentacion_elemento

        elements = [_make_element("ESCAPE", "Escape")]
        elem_with_images = _make_element_with_images("ESCAPE", "Escape", [
            _make_doc_image("http://img.example.com/escape1.jpg", "Foto frontal"),
        ])

        mock_element_service = AsyncMock()
        mock_element_service.get_elements_by_category = AsyncMock(return_value=elements)
        mock_element_service.get_element_with_images = AsyncMock(return_value=elem_with_images)
        mock_element_service.get_element_warnings = AsyncMock(return_value=[])

        mock_tarifa_service = AsyncMock()
        mock_tarifa_service.get_category_data = AsyncMock(return_value=_make_category_data())

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=mock_element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=mock_tarifa_service),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-id-1"),
        ):
            result = await obtener_documentacion_elemento.ainvoke({
                "categoria_vehiculo": "motos-part",
                "codigo_elemento": "ESCAPE",
            })

        assert "imagenes" not in result, (
            f"'imagenes' key must be absent from obtener_documentacion_elemento response. "
            f"Got keys: {list(result.keys())}"
        )

    @pytest.mark.asyncio
    async def test_texto_key_present(self):
        """T-04: 'texto' key must be present with expected content."""
        from agent.tools.element_tools import obtener_documentacion_elemento

        elements = [_make_element("ESCAPE", "Escape")]
        elem_with_images = _make_element_with_images("ESCAPE", "Escape", [
            _make_doc_image("http://img.example.com/escape1.jpg", "Foto frontal"),
        ])

        mock_element_service = AsyncMock()
        mock_element_service.get_elements_by_category = AsyncMock(return_value=elements)
        mock_element_service.get_element_with_images = AsyncMock(return_value=elem_with_images)
        mock_element_service.get_element_warnings = AsyncMock(return_value=[])

        mock_tarifa_service = AsyncMock()
        mock_tarifa_service.get_category_data = AsyncMock(return_value=_make_category_data())

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=mock_element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=mock_tarifa_service),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-id-1"),
        ):
            result = await obtener_documentacion_elemento.ainvoke({
                "categoria_vehiculo": "motos-part",
                "codigo_elemento": "ESCAPE",
            })

        assert "texto" in result, "Response must have 'texto' key"
        assert isinstance(result["texto"], str), "'texto' must be a string"
        assert len(result["texto"]) > 0, "'texto' must be non-empty"
        assert "ESCAPE" in result["texto"].upper(), "'texto' must mention the element code"

    @pytest.mark.asyncio
    async def test_base_doc_images_not_returned_as_urls(self):
        """T-04: Base documentation images (with URLs) must NOT be in the response."""
        from agent.tools.element_tools import obtener_documentacion_elemento

        elements = [_make_element("ESCAPE", "Escape")]
        elem_with_images = _make_element_with_images("ESCAPE", "Escape", [])
        category_data_with_base = _make_category_data(
            base_doc_url="http://img.example.com/ficha.jpg"
        )

        mock_element_service = AsyncMock()
        mock_element_service.get_elements_by_category = AsyncMock(return_value=elements)
        mock_element_service.get_element_with_images = AsyncMock(return_value=elem_with_images)
        mock_element_service.get_element_warnings = AsyncMock(return_value=[])

        mock_tarifa_service = AsyncMock()
        mock_tarifa_service.get_category_data = AsyncMock(return_value=category_data_with_base)

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=mock_element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=mock_tarifa_service),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-id-1"),
        ):
            result = await obtener_documentacion_elemento.ainvoke({
                "categoria_vehiculo": "motos-part",
                "codigo_elemento": "ESCAPE",
            })

        assert "imagenes" not in result, "'imagenes' key must not be present"
        # The base doc description should be in text
        assert "texto" in result
        assert "Ficha técnica" in result["texto"] or "base" in result["texto"].lower()

    @pytest.mark.asyncio
    async def test_error_path_no_imagenes(self):
        """T-04: Error paths also must not return 'imagenes' key."""
        from agent.tools.element_tools import obtener_documentacion_elemento

        mock_element_service = AsyncMock()
        mock_element_service.get_elements_by_category = AsyncMock(return_value=[])

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=mock_element_service),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-id-1"),
        ):
            result = await obtener_documentacion_elemento.ainvoke({
                "categoria_vehiculo": "motos-part",
                "codigo_elemento": "NONEXISTENT",
            })

        assert "imagenes" not in result, (
            f"Error path also must not return 'imagenes'. Got: {list(result.keys())}"
        )
        assert "texto" in result

    @pytest.mark.asyncio
    async def test_invalid_category_error_no_imagenes(self):
        """T-04: Invalid category slug error also must not return 'imagenes' key."""
        from agent.tools.element_tools import obtener_documentacion_elemento

        result = await obtener_documentacion_elemento.ainvoke({
            "categoria_vehiculo": "INVALID SLUG WITH SPACES",
            "codigo_elemento": "ESCAPE",
        })

        assert "imagenes" not in result, f"Got unexpected 'imagenes' key. Keys: {list(result.keys())}"
        assert "texto" in result

    @pytest.mark.asyncio
    async def test_category_not_found_no_imagenes(self):
        """T-04: Category not found returns texto without imagenes."""
        from agent.tools.element_tools import obtener_documentacion_elemento

        with patch("agent.tools.element_tools.get_or_fetch_category_id", return_value=None):
            result = await obtener_documentacion_elemento.ainvoke({
                "categoria_vehiculo": "motos-part",
                "codigo_elemento": "ESCAPE",
            })

        assert "imagenes" not in result
        assert "texto" in result


# ---------------------------------------------------------------------------
# T-04: obtener_documentacion NOT in PRE_EXPEDIENTE tool list
# ---------------------------------------------------------------------------


class TestObtenerDocumentacionNotInPreExpediente:
    """T-04: obtener_documentacion_elemento must not be in PRE_EXPEDIENTE tool list."""

    def test_not_in_pre_expediente_tools(self):
        """T-04: _get_pre_expediente_tools() must not include obtener_documentacion_elemento."""
        from agent.modes.pre_expediente_mode import _get_pre_expediente_tools

        tools = _get_pre_expediente_tools()
        names = {t.name if hasattr(t, "name") else t.__name__ for t in tools}
        assert "obtener_documentacion_elemento" not in names, (
            "T-04: obtener_documentacion_elemento must be removed from PRE_EXPEDIENTE tool set"
        )

    def test_tool_count_after_removal(self):
        """T-04: PRE_EXPEDIENTE should have 10 tools after removal."""
        from agent.modes.pre_expediente_mode import _get_pre_expediente_tools

        tools = _get_pre_expediente_tools()
        assert len(tools) == 10, (
            f"Expected 10 tools after T-04 removal, got {len(tools)}: "
            f"{[t.name if hasattr(t, 'name') else t.__name__ for t in tools]}"
        )
