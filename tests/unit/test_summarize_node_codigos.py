"""
T-11: Tests for summarize_node.py imagenes_enviadas_codigos backward compat.

Verifies:
- imagenes_enviadas_codigos list alone triggers "Imágenes ejemplo enviadas: sí"
- Legacy imagenes_enviadas bool alone still works (backward compat)
- Both fields set → phrase appears once (no duplicate)
- Neither field → phrase absent
"""

from __future__ import annotations

import pytest


def _build_summary(mc: dict) -> str:
    from agent.graph.summarize_node import build_structured_summary
    state = {"mode_context": mc}
    return build_structured_summary(state)


class TestSummarizeNodeImagenasEnviadasCodigos:
    def test_codigos_list_triggers_phrase(self):
        """New path: imagenes_enviadas_codigos populated, no bool."""
        result = _build_summary({"imagenes_enviadas_codigos": ["ESCAPE"]})
        assert "Imágenes ejemplo enviadas: sí" in result

    def test_legacy_bool_still_works(self):
        """Backward compat: old checkpoints with only imagenes_enviadas bool."""
        result = _build_summary({"imagenes_enviadas": True})
        assert "Imágenes ejemplo enviadas: sí" in result

    def test_both_fields_phrase_appears_once(self):
        """Both fields set — phrase should appear exactly once."""
        result = _build_summary({
            "imagenes_enviadas": True,
            "imagenes_enviadas_codigos": ["ESCAPE"],
        })
        count = result.count("Imágenes ejemplo enviadas: sí")
        assert count == 1

    def test_neither_field_phrase_absent(self):
        """No fields set → phrase absent from summary."""
        result = _build_summary({})
        assert "Imágenes ejemplo enviadas" not in result

    def test_empty_codigos_list_and_no_bool_phrase_absent(self):
        """Empty list is falsy — phrase absent."""
        result = _build_summary({"imagenes_enviadas_codigos": []})
        assert "Imágenes ejemplo enviadas" not in result

    def test_multiple_codes_still_triggers(self):
        result = _build_summary({"imagenes_enviadas_codigos": ["ESCAPE", "SUSPENSION", "_BASE_DOCS"]})
        assert "Imágenes ejemplo enviadas: sí" in result
