"""
T-05: Tests for documentacion enrichment in identificar_y_resolver_elementos.

Verifies:
- documentacion dict present in response when elementos_listos non-empty
- documentacion values contain correct keys (docs_requeridos, advertencias, num_imagenes_ejemplo)
- No URL keys anywhere in documentacion
- _state_update.shared_context contains imagenes_enviadas_codigos = []
- documentacion is {} when elementos_con_variantes is non-empty (can't show docs yet)

These are pure unit tests — DB and Redis are mocked.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_element(code: str, name: str, elem_id: str | None = None) -> dict:
    return {"id": elem_id or f"id-{code.lower()}", "code": code, "name": name, "category_id": "cat-1"}


def _make_element_with_images(code: str, name: str, images: list[dict], description: str = "") -> dict:
    return {
        "id": f"id-{code.lower()}",
        "code": code,
        "name": name,
        "description": description,
        "images": images,
    }


def _make_image(status: str = "active") -> dict:
    return {"image_url": "https://example.com/img.jpg", "status": status, "image_type": "frontal"}


def _make_warning(message: str) -> dict:
    return {"id": "w1", "code": "WARN_1", "message": message, "severity": "warning"}


def _make_state(category_id: str = "cat-uuid-1", client_type: str = "particular") -> dict:
    return {"client_type": client_type, "conversation_id": "test-conv-001"}


def _make_category_id(slug: str) -> str:
    return f"cat-id-for-{slug}"


def _make_tariff_result() -> dict:
    return {
        "tier_id": "tier-uuid",
        "tier_name": "Tier 1",
        "price": 410.0,
        "element_codes": ["ESCAPE"],
        "warnings": [],
    }


def _build_tarifa_service_mock(base_documentation: list[dict] | None = None) -> MagicMock:
    """Return a tarifa service mock with get_category_data returning base docs."""
    tarifa_service = MagicMock()
    tarifa_service.get_category_data = AsyncMock(
        return_value={"base_documentation": base_documentation or []}
    )
    tarifa_service.get_active_categories = AsyncMock(return_value=[])
    return tarifa_service


# ---------------------------------------------------------------------------
# Fixtures / Patches context manager
# ---------------------------------------------------------------------------


def _build_patches(
    *,
    matches: list[tuple],
    variants: list,
    elements: list[dict],
    element_with_images_map: dict[str, dict],
    warnings_map: dict[str, list],
    category_id: str = "cat-uuid-1",
):
    """Return a dict of patch contexts for identificar_y_resolver_elementos."""
    element_service = MagicMock()
    element_service.get_elements_by_category = AsyncMock(return_value=elements)
    element_service.match_elements_with_unmatched = AsyncMock(
        return_value={"matches": matches, "unmatched_terms": [], "ambiguous_candidates": [], "quantities": {}}
    )
    element_service.get_element_variants = AsyncMock(return_value=variants)

    async def _get_element_with_images(element_id, **kw):
        return element_with_images_map.get(element_id)

    async def _get_element_warnings(element_id, **kw):
        return warnings_map.get(element_id, [])

    element_service.get_element_with_images = AsyncMock(side_effect=_get_element_with_images)
    element_service.get_element_warnings = AsyncMock(side_effect=_get_element_warnings)

    return element_service


# ===========================================================================
# Tests
# ===========================================================================


class TestDocumentacionEnrichment:
    """T-05: documentacion dict is enriched when elementos_listos non-empty."""

    @pytest.mark.asyncio
    async def test_documentacion_key_present_in_response(self):
        """documentacion key must be present in response when elementos_listos is non-empty."""
        elem = _make_element("ESCAPE", "Escape", elem_id="id-escape")
        element_with_images = _make_element_with_images(
            "ESCAPE", "Escape",
            images=[_make_image("active"), _make_image("active")],
            description="Foto del escape",
        )
        element_service = _build_patches(
            matches=[(elem, 0.9)],
            variants=[],
            elements=[elem],
            element_with_images_map={"id-escape": element_with_images},
            warnings_map={"id-escape": [_make_warning("Posible pérdida de plaza")]},
        )

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=_build_tarifa_service_mock()),
            patch("agent.tools.element_tools.get_tool_state", return_value=_make_state()),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-uuid-1"),
            patch("agent.tools.element_tools.validate_category_slug", return_value="motos-part"),
        ):
            from agent.tools.element_tools import identificar_y_resolver_elementos

            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "motos-part", "descripcion": "escape"}
            )

        assert "documentacion" in result, "Response must contain 'documentacion' key"

    @pytest.mark.asyncio
    async def test_documentacion_values_have_correct_keys(self):
        """Each documentacion entry must have docs_requeridos, advertencias, num_imagenes_ejemplo."""
        elem = _make_element("ESCAPE", "Escape", elem_id="id-escape")
        element_with_images = _make_element_with_images(
            "ESCAPE", "Escape",
            images=[_make_image("active"), _make_image("placeholder")],
            description="Foto del escape con matrícula",
        )
        element_service = _build_patches(
            matches=[(elem, 0.9)],
            variants=[],
            elements=[elem],
            element_with_images_map={"id-escape": element_with_images},
            warnings_map={"id-escape": [_make_warning("Advertencia 1")]},
        )

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=_build_tarifa_service_mock()),
            patch("agent.tools.element_tools.get_tool_state", return_value=_make_state()),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-uuid-1"),
            patch("agent.tools.element_tools.validate_category_slug", return_value="motos-part"),
        ):
            from agent.tools.element_tools import identificar_y_resolver_elementos

            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "motos-part", "descripcion": "escape"}
            )

        doc = result.get("documentacion", {})
        assert "ESCAPE" in doc, f"Expected 'ESCAPE' in documentacion, got keys: {list(doc.keys())}"

        escape_doc = doc["ESCAPE"]
        assert "docs_requeridos" in escape_doc, "Missing 'docs_requeridos'"
        assert isinstance(escape_doc["docs_requeridos"], list), "'docs_requeridos' must be a list"
        assert "advertencias" in escape_doc, "Missing 'advertencias'"
        assert "num_imagenes_ejemplo" in escape_doc, "Missing 'num_imagenes_ejemplo'"

    @pytest.mark.asyncio
    async def test_documentacion_num_imagenes_only_counts_active(self):
        """num_imagenes_ejemplo must only count images with status='active'."""
        elem = _make_element("ESCAPE", "Escape", elem_id="id-escape")
        element_with_images = _make_element_with_images(
            "ESCAPE", "Escape",
            images=[_make_image("active"), _make_image("placeholder"), _make_image("active")],
        )
        element_service = _build_patches(
            matches=[(elem, 0.9)],
            variants=[],
            elements=[elem],
            element_with_images_map={"id-escape": element_with_images},
            warnings_map={},
        )

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=_build_tarifa_service_mock()),
            patch("agent.tools.element_tools.get_tool_state", return_value=_make_state()),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-uuid-1"),
            patch("agent.tools.element_tools.validate_category_slug", return_value="motos-part"),
        ):
            from agent.tools.element_tools import identificar_y_resolver_elementos

            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "motos-part", "descripcion": "escape"}
            )

        doc = result.get("documentacion", {})
        assert doc.get("ESCAPE", {}).get("num_imagenes_ejemplo") == 2, (
            "num_imagenes_ejemplo must be 2 (only active images counted)"
        )

    @pytest.mark.asyncio
    async def test_documentacion_no_url_keys(self):
        """No URL-related keys must appear in documentacion values."""
        elem = _make_element("ESCAPE", "Escape", elem_id="id-escape")
        element_with_images = _make_element_with_images(
            "ESCAPE", "Escape",
            images=[_make_image("active")],
        )
        element_service = _build_patches(
            matches=[(elem, 0.9)],
            variants=[],
            elements=[elem],
            element_with_images_map={"id-escape": element_with_images},
            warnings_map={"id-escape": []},
        )

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=_build_tarifa_service_mock()),
            patch("agent.tools.element_tools.get_tool_state", return_value=_make_state()),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-uuid-1"),
            patch("agent.tools.element_tools.validate_category_slug", return_value="motos-part"),
        ):
            from agent.tools.element_tools import identificar_y_resolver_elementos

            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "motos-part", "descripcion": "escape"}
            )

        doc = result.get("documentacion", {})
        # Recursively check for URL keys
        result_str = json.dumps(doc)
        url_keys = ["url", "image_url", "imagenes", "_inherited_from"]
        for key in url_keys:
            assert f'"{key}"' not in result_str, (
                f"documentacion must not contain '{key}' key, found in: {result_str[:300]}"
            )

    @pytest.mark.asyncio
    async def test_documentacion_advertencias_list(self):
        """advertencias must be a list of strings (warning messages)."""
        elem = _make_element("ESCAPE", "Escape", elem_id="id-escape")
        element_with_images = _make_element_with_images("ESCAPE", "Escape", images=[])
        warnings = [_make_warning("Perdida de 2a plaza"), _make_warning("Requiere ITV")]
        element_service = _build_patches(
            matches=[(elem, 0.9)],
            variants=[],
            elements=[elem],
            element_with_images_map={"id-escape": element_with_images},
            warnings_map={"id-escape": warnings},
        )

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=_build_tarifa_service_mock()),
            patch("agent.tools.element_tools.get_tool_state", return_value=_make_state()),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-uuid-1"),
            patch("agent.tools.element_tools.validate_category_slug", return_value="motos-part"),
        ):
            from agent.tools.element_tools import identificar_y_resolver_elementos

            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "motos-part", "descripcion": "escape"}
            )

        doc = result.get("documentacion", {})
        advertencias = doc.get("ESCAPE", {}).get("advertencias", [])
        assert isinstance(advertencias, list), "advertencias must be a list"
        assert "Perdida de 2a plaza" in advertencias
        assert "Requiere ITV" in advertencias

    @pytest.mark.asyncio
    async def test_documentacion_empty_when_variantes_pending(self):
        """documentacion must be {} when elementos_con_variantes is non-empty."""
        elem = _make_element("SUSPENSION", "Suspensión", elem_id="id-suspension")
        variants = [
            {"code": "SUSPENSION_DEL", "name": "Delantera", "variant_position": 1},
            {"code": "SUSPENSION_TRA", "name": "Trasera", "variant_position": 2},
        ]
        element_service = MagicMock()
        element_service.get_elements_by_category = AsyncMock(return_value=[elem])
        element_service.match_elements_with_unmatched = AsyncMock(
            return_value={
                "matches": [(elem, 0.9)],
                "unmatched_terms": [],
                "ambiguous_candidates": [],
                "quantities": {},
            }
        )
        element_service.get_element_variants = AsyncMock(return_value=variants)
        element_service.get_element_by_code = AsyncMock(return_value={
            "code": "SUSPENSION",
            "name": "Suspensión",
            "question_hint": "¿Delantera o trasera?",
        })
        element_service.get_element_with_images = AsyncMock(return_value=None)
        element_service.get_element_warnings = AsyncMock(return_value=[])

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=_build_tarifa_service_mock()),
            patch("agent.tools.element_tools.get_tool_state", return_value=_make_state()),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-uuid-1"),
            patch("agent.tools.element_tools.validate_category_slug", return_value="motos-part"),
        ):
            from agent.tools.element_tools import identificar_y_resolver_elementos

            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "motos-part", "descripcion": "suspension"}
            )

        assert "elementos_con_variantes" in result
        assert len(result["elementos_con_variantes"]) > 0, "Should have variants pending"

        doc = result.get("documentacion", {})
        assert doc == {}, (
            f"documentacion must be {{}} when variants are pending, got: {doc}"
        )

    @pytest.mark.asyncio
    async def test_state_update_resets_imagenes_enviadas_codigos(self):
        """_state_update.shared_context must contain imagenes_enviadas_codigos=[] on success."""
        elem = _make_element("ESCAPE", "Escape", elem_id="id-escape")
        element_with_images = _make_element_with_images("ESCAPE", "Escape", images=[])
        element_service = _build_patches(
            matches=[(elem, 0.9)],
            variants=[],
            elements=[elem],
            element_with_images_map={"id-escape": element_with_images},
            warnings_map={},
        )

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=_build_tarifa_service_mock()),
            patch("agent.tools.element_tools.get_tool_state", return_value=_make_state()),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-uuid-1"),
            patch("agent.tools.element_tools.validate_category_slug", return_value="motos-part"),
        ):
            from agent.tools.element_tools import identificar_y_resolver_elementos

            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "motos-part", "descripcion": "escape"}
            )

        state_update = result.get("_state_update", {})
        sc = state_update.get("shared_context", {})
        assert "imagenes_enviadas_codigos" in sc, (
            "_state_update.shared_context must contain 'imagenes_enviadas_codigos'"
        )
        assert sc["imagenes_enviadas_codigos"] == [], (
            f"imagenes_enviadas_codigos must be [] on re-identification, got: {sc['imagenes_enviadas_codigos']}"
        )


class TestInstruccionesCondicionales:
    """T-06: instrucciones field must be conditional when elementos_listos and no unmatched terms."""

    @pytest.mark.asyncio
    async def test_instrucciones_contains_both_paths_when_elementos_listos(self):
        """When elementos_listos and no unmatched_terms, instrucciones must contain
        BOTH the PRECIO/PRESUPUESTO path AND the DOCUMENTACIÓN/INFORMACIÓN path.
        It must NOT be a simple unconditional 'calcular' directive.
        """
        elem = _make_element("ESCAPE", "Escape", elem_id="id-escape")
        element_with_images = _make_element_with_images(
            "ESCAPE", "Escape",
            images=[_make_image("active")],
        )
        element_service = _build_patches(
            matches=[(elem, 0.9)],
            variants=[],
            elements=[elem],
            element_with_images_map={"id-escape": element_with_images},
            warnings_map={},
        )

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=_build_tarifa_service_mock()),
            patch("agent.tools.element_tools.get_tool_state", return_value=_make_state()),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-uuid-1"),
            patch("agent.tools.element_tools.validate_category_slug", return_value="motos-part"),
        ):
            from agent.tools.element_tools import identificar_y_resolver_elementos

            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "motos-part", "descripcion": "escape"}
            )

        instrucciones = result.get("instrucciones", "")
        assert instrucciones, "instrucciones must be present when elementos_listos and no unmatched_terms"

        # Must contain the PRECIO/PRESUPUESTO conditional path
        assert "PRECIO" in instrucciones or "PRESUPUESTO" in instrucciones, (
            f"instrucciones must contain PRECIO or PRESUPUESTO conditional path, got: {instrucciones}"
        )

        # Must contain the DOCUMENTACIÓN/INFORMACIÓN path
        assert "DOCUMENTACIÓN" in instrucciones or "INFORMACIÓN" in instrucciones, (
            f"instrucciones must contain DOCUMENTACIÓN or INFORMACIÓN path, got: {instrucciones}"
        )

        # Must contain the explicit prohibition against auto-calculating
        assert "NO calcules el precio" in instrucciones, (
            f"instrucciones must explicitly prohibit auto-calculating price, got: {instrucciones}"
        )

        # Must NOT be the old unconditional directive (only pointing to calcular)
        assert "Todos los elementos están listos" not in instrucciones, (
            "instrucciones must NOT be the old unconditional 'Todos los elementos están listos' directive"
        )


class TestDocumentacionFallbackCanonical:
    """Task 1.4 — docs_requeridos fallback for imageless elements must use the canonical constant."""

    @pytest.mark.asyncio
    async def test_docs_requeridos_no_images_uses_canonical_constant(self):
        """Element with no DB image rows → docs_requeridos must contain canonical string (with accent)."""
        elem = _make_element("ESCAPE", "Escape", elem_id="id-escape")
        # Provide element data but with NO images
        element_with_images = _make_element_with_images("ESCAPE", "Escape", images=[])
        element_service = _build_patches(
            matches=[(elem, 0.9)],
            variants=[],
            elements=[elem],
            element_with_images_map={"id-escape": element_with_images},
            warnings_map={},
        )

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=element_service),
            patch("agent.tools.element_tools.get_tarifa_service", return_value=_build_tarifa_service_mock()),
            patch("agent.tools.element_tools.get_tool_state", return_value=_make_state()),
            patch("agent.tools.element_tools.get_or_fetch_category_id", return_value="cat-uuid-1"),
            patch("agent.tools.element_tools.validate_category_slug", return_value="motos-part"),
        ):
            from agent.tools.element_tools import identificar_y_resolver_elementos

            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "motos-part", "descripcion": "escape"}
            )

        doc = result.get("documentacion", {})
        assert "ESCAPE" in doc, f"ESCAPE must be in documentacion, got: {list(doc.keys())}"

        docs_requeridos = doc["ESCAPE"].get("docs_requeridos", [])
        assert isinstance(docs_requeridos, list), "docs_requeridos must be a list"
        assert len(docs_requeridos) >= 1, (
            f"docs_requeridos must have at least 1 entry for imageless element, got: {docs_requeridos}"
        )
        assert "Foto del elemento con matrícula visible" in docs_requeridos, (
            f"docs_requeridos must contain canonical constant (with accent on í). "
            f"Got: {docs_requeridos!r}"
        )
