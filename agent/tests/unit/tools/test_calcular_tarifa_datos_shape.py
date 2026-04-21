"""
Unit tests for C1 — T1: calcular_tarifa_con_elementos datos shape.

Spec: R2 — Structured Tariff Tool Return.
AC-2.1: datos has all 5 sub-keys (advertencias_por_elemento, advertencias_generales,
         docs_base, docs_por_elemento, instrucciones_usuario).
AC-2.2: texto is compact: no €, no ⚠️, length < 250 chars.
AC-2.3: message field present and <= 120 chars.
AC-2.4 (regression): _documentacion and imagenes_ejemplo top-level keys still present.

These tests are RED before C1 implementation because:
- datos currently lacks advertencias_por_elemento, advertencias_generales,
  docs_base, docs_por_elemento, instrucciones_usuario sub-keys.
- texto currently contains the full narration with €, ⚠️, and DOCUMENTACION headers.
- message key does not exist in the current return shape.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_config(mode_context: dict | None = None) -> dict:
    return {
        "configurable": {
            "state": {
                "conversation_id": "test-datos-shape",
                "client_type": "particular",
                "mode_context": mode_context or {},
                "shared_context": {},
            }
        }
    }


def _make_tarifa_service() -> MagicMock:
    """Tarifa service with one element warning (ESCAPE) + one general warning."""
    svc = MagicMock()
    svc.select_tariff_by_rules = AsyncMock(
        return_value={
            "tier_id": "tier-1",
            "tier_name": "Tier Base",
            "price": 410.0,
            "conditions": None,
            "warnings": [
                {
                    "code": "WARN-01",
                    "message": "Advertencia de elemento",
                    "severity": "warning",
                    "element_code": "ESCAPE",
                    "element_name": "Escape",
                },
                {
                    "code": "WARN-GEN",
                    "message": "Advertencia general",
                    "severity": "info",
                    "element_code": None,
                    "element_name": None,
                },
            ],
            "additional_services": [],
            "element_validation": {"valid": True, "missing_elements": []},
        }
    )
    svc.get_category_data = AsyncMock(
        return_value={
            "base_documentation": [
                {"description": "Ficha técnica", "image_url": "https://example.com/ficha.jpg"},
                {"description": "Permiso de circulación", "image_url": None},
            ]
        }
    )
    return svc


def _make_element_service() -> MagicMock:
    default_elem = {
        "id": "elem-1",
        "code": "ESCAPE",
        "name": "Escape",
        "parent_element_id": None,
        "images": [
            {
                "image_url": "https://example.com/escape.jpg",
                "image_type": "element",
                "title": "Foto escape",
                "description": "Foto del escape con matrícula visible",
                "is_required": True,
                "user_instruction": "Sube foto del escape lateral",
                "status": "active",
            }
        ],
    }
    svc = MagicMock()
    svc.get_elements_by_category = AsyncMock(return_value=[default_elem])
    svc.get_element_warnings = AsyncMock(return_value=[])
    svc.get_element_with_images = AsyncMock(return_value=default_elem)
    return svc


async def _invoke() -> dict:
    with (
        patch(
            "agent.tools.element_tools.get_tarifa_service",
            return_value=_make_tarifa_service(),
        ),
        patch(
            "agent.tools.element_tools.get_element_service",
            return_value=_make_element_service(),
        ),
        patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new_callable=AsyncMock,
            return_value="cat-001",
        ),
        patch(
            "agent.tools.element_tools.validate_category_slug",
            return_value=None,
        ),
        patch(
            "agent.tools.element_tools.normalize_element_codes",
            return_value=(["ESCAPE"], [], []),
        ),
        patch(
            "agent.tools.element_tools._fire_and_forget_draft_quote",
            new=AsyncMock(),
        ),
    ):
        from agent.tools.element_tools import calcular_tarifa_con_elementos

        return await calcular_tarifa_con_elementos.ainvoke(
            {
                "categoria_vehiculo": "motos-part",
                "codigos_elementos": ["ESCAPE"],
                "skip_validation": True,
            },
            config=_make_config(),
        )


# ---------------------------------------------------------------------------
# AC-2.1 — datos sub-keys
# ---------------------------------------------------------------------------

class TestDatosShape:
    """datos must contain all 5 new structured sub-keys."""

    @pytest.mark.asyncio
    async def test_datos_has_advertencias_por_elemento(self):
        result = await _invoke()
        datos = result["datos"]
        assert "advertencias_por_elemento" in datos, (
            f"datos must have 'advertencias_por_elemento'. Keys: {list(datos.keys())}"
        )
        assert isinstance(datos["advertencias_por_elemento"], dict)
        # ESCAPE should be present (we seeded a warning for it)
        assert "ESCAPE" in datos["advertencias_por_elemento"], (
            f"ESCAPE not in advertencias_por_elemento: {datos['advertencias_por_elemento']}"
        )

    @pytest.mark.asyncio
    async def test_datos_has_advertencias_generales(self):
        result = await _invoke()
        datos = result["datos"]
        assert "advertencias_generales" in datos, (
            f"datos must have 'advertencias_generales'. Keys: {list(datos.keys())}"
        )
        assert isinstance(datos["advertencias_generales"], list)
        # We seeded one general warning (element_code=None)
        assert len(datos["advertencias_generales"]) == 1, (
            f"Expected 1 general warning, got {datos['advertencias_generales']}"
        )

    @pytest.mark.asyncio
    async def test_datos_has_docs_base(self):
        result = await _invoke()
        datos = result["datos"]
        assert "docs_base" in datos, (
            f"datos must have 'docs_base'. Keys: {list(datos.keys())}"
        )
        assert isinstance(datos["docs_base"], list)
        assert len(datos["docs_base"]) == 2, (
            f"Expected 2 base docs, got {datos['docs_base']}"
        )

    @pytest.mark.asyncio
    async def test_datos_has_docs_por_elemento(self):
        result = await _invoke()
        datos = result["datos"]
        assert "docs_por_elemento" in datos, (
            f"datos must have 'docs_por_elemento'. Keys: {list(datos.keys())}"
        )
        assert isinstance(datos["docs_por_elemento"], dict)
        assert "ESCAPE" in datos["docs_por_elemento"], (
            f"ESCAPE not in docs_por_elemento: {datos['docs_por_elemento']}"
        )

    @pytest.mark.asyncio
    async def test_datos_has_instrucciones_usuario(self):
        result = await _invoke()
        datos = result["datos"]
        assert "instrucciones_usuario" in datos, (
            f"datos must have 'instrucciones_usuario'. Keys: {list(datos.keys())}"
        )
        assert isinstance(datos["instrucciones_usuario"], list)


# ---------------------------------------------------------------------------
# AC-2.2 — texto is compact
# ---------------------------------------------------------------------------

class TestTextoIsCompact:
    """texto must be a compact operational marker: no €, no ⚠️, < 250 chars."""

    @pytest.mark.asyncio
    async def test_texto_no_euro_sign(self):
        result = await _invoke()
        texto = result.get("texto", "")
        assert "€" not in texto, (
            f"texto must NOT contain '€'. texto={texto!r}"
        )

    @pytest.mark.asyncio
    async def test_texto_no_warning_emoji(self):
        result = await _invoke()
        texto = result.get("texto", "")
        assert "⚠️" not in texto, (
            f"texto must NOT contain '⚠️'. texto={texto!r}"
        )

    @pytest.mark.asyncio
    async def test_texto_length_under_250_chars(self):
        result = await _invoke()
        texto = result.get("texto", "")
        assert len(texto) < 250, (
            f"texto must be < 250 chars. len={len(texto)}. texto={texto!r}"
        )


# ---------------------------------------------------------------------------
# AC-2.3 — message field <= 120 chars
# ---------------------------------------------------------------------------

class TestMessageField:
    """message must be a concise operational string <= 120 chars."""

    @pytest.mark.asyncio
    async def test_message_key_present(self):
        result = await _invoke()
        assert "message" in result, (
            f"result must have 'message' key. Keys: {list(result.keys())}"
        )

    @pytest.mark.asyncio
    async def test_message_under_120_chars(self):
        result = await _invoke()
        message = result.get("message", "")
        assert isinstance(message, str), "message must be a string"
        assert len(message) <= 120, (
            f"message must be <= 120 chars. len={len(message)}. message={message!r}"
        )


# ---------------------------------------------------------------------------
# AC-2.4 — backward compat: _documentacion and imagenes_ejemplo still present
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    """_documentacion and imagenes_ejemplo top-level keys must remain unchanged."""

    @pytest.mark.asyncio
    async def test_documentacion_key_present(self):
        result = await _invoke()
        assert "_documentacion" in result, (
            f"_documentacion must remain present. Keys: {list(result.keys())}"
        )

    @pytest.mark.asyncio
    async def test_imagenes_ejemplo_key_present(self):
        result = await _invoke()
        assert "imagenes_ejemplo" in result, (
            f"imagenes_ejemplo must remain present. Keys: {list(result.keys())}"
        )

    @pytest.mark.asyncio
    async def test_datos_price_still_present(self):
        """datos.price must remain (post_tool_hooks.py reads it)."""
        result = await _invoke()
        assert "price" in result["datos"], (
            f"datos.price must remain. datos keys: {list(result['datos'].keys())}"
        )
        assert result["datos"]["price"] == 410.0
