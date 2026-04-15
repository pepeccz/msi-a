"""
T-09: Tests for additive element_codes merge in _extract_context_from_tool.

Verifies:
- New call with codes ["ESCAPE"] when element_codes = ["SUSPENSION"] → ["SUSPENSION", "ESCAPE"]
- Re-identifying same code → no duplicate
- First identification with empty existing codes → same as before
- Partial codes (variant branch) also merge additively
"""

from __future__ import annotations

import json
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _identificar_result_no_variants(codes: list[str], categoria: str = "motos-part") -> dict:
    """Build an identificar result with only elementos_listos (no variants)."""
    return {
        "success": True,
        "categoria_slug": categoria,
        "elementos_listos": [{"codigo": c, "nombre": c.title()} for c in codes],
        "elementos_con_variantes": [],
        "preguntas_variantes": [],
        "terminos_no_reconocidos": [],
        "documentacion": {},
        "_state_update": {
            "shared_context": {
                "precio_comunicado": False,
                "imagenes_enviadas": False,
                "imagenes_enviadas_codigos": [],
            }
        },
    }


def _identificar_result_with_variants(
    ready_codes: list[str],
    variant_codes: list[str],
    categoria: str = "motos-part",
) -> dict:
    """Build an identificar result with some ready codes + variant codes."""
    preguntas = [{"codigo_base": c, "pregunta": f"¿Tipo de {c}?", "opciones": ["A", "B"]} for c in variant_codes]
    return {
        "success": True,
        "categoria_slug": categoria,
        "elementos_listos": [{"codigo": c, "nombre": c.title()} for c in ready_codes],
        "elementos_con_variantes": [{"codigo_base": c} for c in variant_codes],
        "preguntas_variantes": preguntas,
        "terminos_no_reconocidos": [],
        "documentacion": {},
        "_state_update": {
            "shared_context": {
                "precio_comunicado": False,
                "imagenes_enviadas": False,
                "imagenes_enviadas_codigos": [],
            }
        },
    }


# ===========================================================================
# Tests
# ===========================================================================


class TestAdditiveElementCodes:
    """T-09: _extract_context_from_tool merges element_codes additively."""

    def test_new_code_extends_existing(self):
        """
        Adding ESCAPE when SUSPENSION already in codes → ["SUSPENSION", "ESCAPE"].
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode as PreExpedienteMode

        result_str = json.dumps(_identificar_result_no_variants(["ESCAPE"]))
        updates = PreExpedienteMode._extract_context_from_tool(
            tool_name="identificar_y_resolver_elementos",
            tool_args={"categoria_vehiculo": "motos-part", "descripcion": "escape"},
            result=result_str,
            current_element_codes=["SUSPENSION"],
        )

        codes = updates.get("element_codes", [])
        assert "SUSPENSION" in codes, f"Existing code SUSPENSION must be preserved, got: {codes}"
        assert "ESCAPE" in codes, f"New code ESCAPE must be added, got: {codes}"
        assert len(codes) == 2, f"Expected 2 codes, got: {codes}"

    def test_re_identifying_same_code_no_duplicate(self):
        """
        Re-identifying ESCAPE when ESCAPE already in codes → no duplicates.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode as PreExpedienteMode

        result_str = json.dumps(_identificar_result_no_variants(["ESCAPE"]))
        updates = PreExpedienteMode._extract_context_from_tool(
            tool_name="identificar_y_resolver_elementos",
            tool_args={"categoria_vehiculo": "motos-part", "descripcion": "escape"},
            result=result_str,
            current_element_codes=["ESCAPE"],
        )

        codes = updates.get("element_codes", [])
        escape_count = codes.count("ESCAPE")
        assert escape_count == 1, f"ESCAPE must appear exactly once, got count={escape_count} in {codes}"

    def test_first_identification_empty_existing(self):
        """
        First identification with no existing codes → works same as before.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode as PreExpedienteMode

        result_str = json.dumps(_identificar_result_no_variants(["ESCAPE", "MANILLAR"]))
        updates = PreExpedienteMode._extract_context_from_tool(
            tool_name="identificar_y_resolver_elementos",
            tool_args={"categoria_vehiculo": "motos-part", "descripcion": "escape y manillar"},
            result=result_str,
            current_element_codes=[],
        )

        codes = updates.get("element_codes", [])
        assert "ESCAPE" in codes
        assert "MANILLAR" in codes
        assert len(codes) == 2

    def test_first_identification_none_existing(self):
        """
        current_element_codes=None (first call) → works same as before.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode as PreExpedienteMode

        result_str = json.dumps(_identificar_result_no_variants(["ESCAPE"]))
        updates = PreExpedienteMode._extract_context_from_tool(
            tool_name="identificar_y_resolver_elementos",
            tool_args={"categoria_vehiculo": "motos-part", "descripcion": "escape"},
            result=result_str,
            current_element_codes=None,
        )

        codes = updates.get("element_codes", [])
        assert "ESCAPE" in codes

    def test_variant_branch_also_merges(self):
        """
        When some elements have variants, ready codes from this call merge with existing.
        PLACA_SOLAR (ready) should merge with ESCAPE (existing) even if SUSPENSION has variants.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode as PreExpedienteMode

        result_str = json.dumps(
            _identificar_result_with_variants(
                ready_codes=["PLACA_SOLAR"],
                variant_codes=["SUSPENSION"],
            )
        )
        updates = PreExpedienteMode._extract_context_from_tool(
            tool_name="identificar_y_resolver_elementos",
            tool_args={"categoria_vehiculo": "motos-part", "descripcion": "placa solar y suspension"},
            result=result_str,
            current_element_codes=["ESCAPE"],
        )

        codes = updates.get("element_codes", [])
        assert "ESCAPE" in codes, f"Existing ESCAPE must be preserved, got: {codes}"
        assert "PLACA_SOLAR" in codes, f"New PLACA_SOLAR must be added, got: {codes}"

    def test_multiple_new_codes_all_added(self):
        """
        Multiple new codes at once — all are merged with existing.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode as PreExpedienteMode

        result_str = json.dumps(_identificar_result_no_variants(["ESCAPE", "MANILLAR", "SUBCHASIS"]))
        updates = PreExpedienteMode._extract_context_from_tool(
            tool_name="identificar_y_resolver_elementos",
            tool_args={"categoria_vehiculo": "motos-part", "descripcion": "escape manillar subchasis"},
            result=result_str,
            current_element_codes=["SUSPENSION"],
        )

        codes = updates.get("element_codes", [])
        for code in ["SUSPENSION", "ESCAPE", "MANILLAR", "SUBCHASIS"]:
            assert code in codes, f"Code '{code}' must be in element_codes, got: {codes}"
        assert len(codes) == 4
