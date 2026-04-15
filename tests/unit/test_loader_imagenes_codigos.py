"""
T-12: Tests for format_mode_context per-element image display in loader.py.

Verifies:
- Partial send: sent codes appear in "Imágenes enviadas:", pending in "Imágenes pendientes:"
- All sent: "Imágenes: todas enviadas" appears
- None sent: "Imágenes: no enviadas"
- Legacy bool only: backward compat output "(legacy)"
- _BASE_DOCS sentinel rendered as "base"
- element_codes without matching sent_codes appear as pending
"""

from __future__ import annotations

import pytest


def _format(context: dict) -> str:
    """Call format_mode_context for PRE_EXPEDIENTE_MODE."""
    from agent.prompts.loader import format_mode_context
    return format_mode_context("PRE_EXPEDIENTE_MODE", context)


class TestLoaderImagenesCodigosDisplay:
    def test_partial_send_shows_sent_and_pending(self):
        """One element sent, one pending."""
        ctx = {
            "imagenes_enviadas_codigos": ["ESCAPE"],
            "element_codes": ["ESCAPE", "SUSPENSION"],
        }
        result = _format(ctx)
        assert "Imágenes enviadas: ESCAPE" in result
        assert "Imágenes pendientes: SUSPENSION" in result

    def test_all_sent_shows_todas_enviadas(self):
        ctx = {
            "imagenes_enviadas_codigos": ["ESCAPE", "SUSPENSION"],
            "element_codes": ["ESCAPE", "SUSPENSION"],
        }
        result = _format(ctx)
        assert "Imágenes enviadas:" in result
        assert "todas enviadas" in result
        assert "Imágenes pendientes:" not in result

    def test_none_sent_shows_no_enviadas(self):
        ctx = {
            "imagenes_enviadas_codigos": [],
            "element_codes": ["ESCAPE"],
        }
        result = _format(ctx)
        assert "no enviadas" in result

    def test_legacy_bool_true_shows_legacy_label(self):
        """Old checkpoint: imagenes_enviadas=True, no list → backward compat."""
        ctx = {
            "imagenes_enviadas": True,
            "element_codes": ["ESCAPE"],
        }
        result = _format(ctx)
        assert "legacy" in result

    def test_legacy_bool_false_shows_no_enviadas(self):
        ctx = {"imagenes_enviadas": False}
        result = _format(ctx)
        assert "no enviadas" in result

    def test_base_docs_sentinel_rendered_as_base(self):
        ctx = {
            "imagenes_enviadas_codigos": ["_BASE_DOCS", "ESCAPE"],
            "element_codes": ["ESCAPE"],
        }
        result = _format(ctx)
        assert "base" in result
        assert "ESCAPE" in result

    def test_no_element_codes_no_pending_line(self):
        """All sent, no element_codes → no Imágenes pendientes section."""
        ctx = {
            "imagenes_enviadas_codigos": ["ESCAPE"],
            "element_codes": [],
        }
        result = _format(ctx)
        assert "Imágenes pendientes:" not in result

    def test_codes_list_overrides_legacy_bool(self):
        """When both fields present, codes list takes priority (codigos branch runs first)."""
        ctx = {
            "imagenes_enviadas": True,
            "imagenes_enviadas_codigos": ["SUSPENSION"],
            "element_codes": ["SUSPENSION"],
        }
        result = _format(ctx)
        # Should use the new display, NOT the legacy fallback
        assert "Imágenes enviadas: SUSPENSION" in result
        assert "legacy" not in result
