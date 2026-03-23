"""
Unit tests for valid element codes injection in format_mode_context().

Phase 3 of fix-llm-element-codes: verifies that the preventive layer (Layer 1)
injects a closed list of valid element codes into the EXPEDIENTE_MODE prompt
when sub_mode is 'collect_element_data' and element_codes exist in context.

These are pure unit tests (no DB, no Redis, no LLM).
"""

import pytest

from agent.prompts.loader import format_mode_context


# =============================================================================
# Task 3.2: Valid element codes injection tests
# =============================================================================


class TestValidElementCodesInjection:
    """Tests for CÓDIGOS VÁLIDOS DE ELEMENTOS injection in format_mode_context."""

    def test_codes_injected_during_collect_element_data(self):
        """
        Given mode EXPEDIENTE_MODE with sub_mode collect_element_data
        and element_codes = ["ESCAPE", "SUBCHASIS", "ASIDEROS"],
        the output MUST contain 'CÓDIGOS VÁLIDOS DE ELEMENTOS: ESCAPE, SUBCHASIS, ASIDEROS'.
        """
        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["ESCAPE", "SUBCHASIS", "ASIDEROS"],
            "current_element_index": 0,
            "element_phase": "photos",
        }

        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "CÓDIGOS VÁLIDOS DE ELEMENTOS: ESCAPE, SUBCHASIS, ASIDEROS" in result

    def test_codes_injection_includes_instruction(self):
        """
        The injection block MUST include an instruction to use codes exactly.
        """
        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["ESCAPE"],
            "current_element_index": 0,
            "element_phase": "photos",
        }

        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "USA EXCLUSIVAMENTE estos códigos" in result
        assert "NO inventes ni abrevies" in result

    def test_no_injection_when_element_codes_empty(self):
        """
        When element_codes is an empty list, no CÓDIGOS VÁLIDOS line should appear.
        """
        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": [],
            "current_element_index": 0,
            "element_phase": "photos",
        }

        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "CÓDIGOS VÁLIDOS DE ELEMENTOS" not in result

    def test_no_injection_when_element_codes_missing(self):
        """
        When element_codes key is absent from context, no CÓDIGOS VÁLIDOS line should appear.
        """
        context = {
            "expediente_sub_mode": "collect_element_data",
            "current_element_index": 0,
            "element_phase": "photos",
        }

        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "CÓDIGOS VÁLIDOS DE ELEMENTOS" not in result

    def test_no_injection_when_sub_mode_is_not_collect_element_data(self):
        """
        When sub_mode is collect_workshop (not collect_element_data),
        no CÓDIGOS VÁLIDOS line should appear even if element_codes exist.
        """
        context = {
            "expediente_sub_mode": "collect_workshop",
            "element_codes": ["ESCAPE", "SUBCHASIS"],
            "current_element_index": 0,
            "element_phase": "photos",
        }

        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "CÓDIGOS VÁLIDOS DE ELEMENTOS" not in result

    def test_no_injection_when_sub_mode_is_collect_personal(self):
        """
        collect_personal sub-mode should NOT get codes injection.
        """
        context = {
            "expediente_sub_mode": "collect_personal",
            "element_codes": ["ESCAPE"],
            "current_element_index": 0,
            "element_phase": "photos",
        }

        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "CÓDIGOS VÁLIDOS DE ELEMENTOS" not in result

    def test_codes_injected_with_many_elements(self):
        """
        All codes should appear in the injection, even with many elements.
        """
        codes = [
            "ESCAPE_DELANTERO",
            "ESCAPE_TRASERO",
            "SUBCHASIS",
            "ASIDEROS",
            "PLACA_SOLAR_REGULADOR_INTERIOR",
            "TOLDO_COFRE",
            "PUERTA_LATERAL",
            "VENTANA_TECHO",
            "PORTABICICLETAS",
            "ENGANCHE",
        ]
        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": codes,
            "current_element_index": 0,
            "element_phase": "photos",
        }

        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "CÓDIGOS VÁLIDOS DE ELEMENTOS" in result
        for code in codes:
            assert code in result

    def test_codes_injected_during_data_phase(self):
        """
        Codes should be injected regardless of element_phase (photos or data).
        The sub_mode check is what gates the injection, not the phase.
        """
        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["ESCAPE", "SUBCHASIS"],
            "current_element_index": 0,
            "element_phase": "data",
        }

        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "CÓDIGOS VÁLIDOS DE ELEMENTOS: ESCAPE, SUBCHASIS" in result

    def test_codes_preserve_order_from_context(self):
        """
        The codes MUST appear in the same order as in element_codes list
        (which matches the order the user confirmed them).
        """
        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["SUBCHASIS", "ESCAPE", "ASIDEROS"],
            "current_element_index": 0,
            "element_phase": "photos",
        }

        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "CÓDIGOS VÁLIDOS DE ELEMENTOS: SUBCHASIS, ESCAPE, ASIDEROS" in result

    def test_result_contains_contexto_del_modo_header(self):
        """
        The output should be wrapped in the standard CONTEXTO DEL MODO header.
        """
        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["ESCAPE"],
            "current_element_index": 0,
            "element_phase": "photos",
        }

        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert result.startswith("# CONTEXTO DEL MODO")
