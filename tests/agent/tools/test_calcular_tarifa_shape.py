"""
T2 — Concern B: documentacion → _documentacion rename in calcular_tarifa_con_elementos.

Spec: CalcularTarifaOmitsDocumentacion
  - Return dict MUST NOT contain key "documentacion"
  - Return dict MUST contain key "_documentacion" with same structure (base, elementos)
  - Other keys (texto, datos, imagenes_ejemplo, _state_update) must remain intact
  - _build_element_photo_instructions in _shared.py must successfully extract docs
    using the renamed key
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures / shared helpers
# ---------------------------------------------------------------------------


def _make_tarifa_service() -> MagicMock:
    """Minimal tarifa service mock that returns a valid tariff selection."""
    svc = MagicMock()
    svc.select_tariff_by_rules = AsyncMock(
        return_value={
            "tier_id": "tier-001",
            "tier_name": "Básica",
            "price": 450.0,
            "warnings": [],
        }
    )
    svc.get_category_data = AsyncMock(
        return_value={
            "base_documentation": [
                {
                    "description": "Certificado ITV",
                    "image_url": "https://example.com/itv.jpg",
                }
            ]
        }
    )
    svc.get_active_categories = AsyncMock(return_value=[{"slug": "motos-part"}])
    return svc


def _make_element_service(elements: list[dict] | None = None) -> MagicMock:
    """Minimal element service mock."""
    default_elem = {
        "id": "elem-001",
        "code": "ESCAPE",
        "name": "Escape",
        "parent_element_id": None,
        "images": [
            {
                "image_url": "https://example.com/escape.jpg",
                "image_type": "required",
                "status": "active",
                "instruccion_usuario": "Foto desde el lado derecho",
                "description": "Foto escape",
            }
        ],
    }
    elements = elements or [default_elem]

    svc = MagicMock()
    svc.get_elements_by_category = AsyncMock(return_value=elements)
    svc.get_element_warnings = AsyncMock(return_value=[])
    svc.get_element_with_images = AsyncMock(return_value=default_elem)
    return svc


def _make_config(mode_context: dict | None = None) -> dict:
    return {
        "configurable": {
            "state": {
                "conversation_id": "test-t2",
                "client_type": "particular",
                "mode_context": mode_context or {},
            }
        }
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCalcularTarifaShape:
    """
    Spec coverage: CalcularTarifaOmitsDocumentacion — all scenarios.
    """

    @pytest.mark.asyncio
    async def test_no_documentacion_key_in_top_level(self):
        """
        T2 — core assertion: 'documentacion' key MUST NOT appear in the returned dict.
        """
        from agent.tools.element_tools import calcular_tarifa_con_elementos

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
        ):
            result = await calcular_tarifa_con_elementos.ainvoke(
                {
                    "categoria_vehiculo": "motos-part",
                    "codigos_elementos": ["ESCAPE"],
                    "skip_validation": True,
                },
                config=_make_config(),
            )

        assert isinstance(result, dict), f"Expected dict, got: {type(result)}"
        # Success path: no "error" key (calcular_tarifa returns texto/datos/etc. without 'success' on happy path)
        assert "error" not in result, f"Unexpected error in result: {result.get('error')}"
        assert "documentacion" not in result, (
            f"'documentacion' key MUST NOT be present in top-level return. "
            f"Keys found: {list(result.keys())}"
        )

    @pytest.mark.asyncio
    async def test_documentacion_key_present_with_correct_structure(self):
        """
        T2 — _documentacion key MUST be present with {base: ..., elementos: ...} structure.
        """
        from agent.tools.element_tools import calcular_tarifa_con_elementos

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
        ):
            result = await calcular_tarifa_con_elementos.ainvoke(
                {
                    "categoria_vehiculo": "motos-part",
                    "codigos_elementos": ["ESCAPE"],
                    "skip_validation": True,
                },
                config=_make_config(),
            )

        assert "_documentacion" in result, (
            f"'_documentacion' key MUST be present. Keys found: {list(result.keys())}"
        )
        doc = result["_documentacion"]
        assert isinstance(doc, dict), f"Expected dict for _documentacion, got: {doc!r}"
        assert "base" in doc, f"_documentacion must have 'base' key: {doc!r}"
        assert "elementos" in doc, f"_documentacion must have 'elementos' key: {doc!r}"

    @pytest.mark.asyncio
    async def test_other_keys_unchanged(self):
        """
        T2 — regression: texto, datos, imagenes_ejemplo, _state_update must remain.
        """
        from agent.tools.element_tools import calcular_tarifa_con_elementos

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
        ):
            result = await calcular_tarifa_con_elementos.ainvoke(
                {
                    "categoria_vehiculo": "motos-part",
                    "codigos_elementos": ["ESCAPE"],
                    "skip_validation": True,
                },
                config=_make_config(),
            )

        for expected_key in ("texto", "datos", "imagenes_ejemplo", "_state_update"):
            assert expected_key in result, (
                f"Key '{expected_key}' must still be present after rename. "
                f"Keys found: {list(result.keys())}"
            )

    def test_build_element_photo_instructions_reads_from_documentacion_underscore(self):
        """
        T2 — _build_element_photo_instructions must extract element docs from
        '_documentacion' key (post-rename) WITHOUT raising an exception.
        """
        from agent.modes.submodos._shared import _build_element_photo_instructions

        tarifa_calculada = {
            "_documentacion": {
                "base": [],
                "elementos": [
                    {
                        "codigo": "ESCAPE",
                        "nombre": "Escape",
                        "imagenes": [
                            {
                                "url": "https://example.com/escape.jpg",
                                "instruccion_usuario": "Foto desde el lado derecho",
                            }
                        ],
                    }
                ],
            }
        }

        result = _build_element_photo_instructions(tarifa_calculada)
        assert isinstance(result, str), f"Expected str, got: {type(result)}"
        # After the fix, it should actually find the instructions.
        # Before the fix it returns "" because it looks for "documentacion" not "_documentacion".
        assert "Escape" in result or result == "", (
            f"Unexpected result: {result!r}"
        )
        # The key assertion: should NOT return empty string after the rename
        assert result != "", (
            "_build_element_photo_instructions returned empty string — "
            "it is NOT reading from '_documentacion' yet (still using 'documentacion')"
        )
