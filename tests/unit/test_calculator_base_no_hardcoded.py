"""
Tests to verify hardcoded prices have been removed from calculator prompts
and tool docstrings.

These are regression tests for Plan 2: fix-calculator-base-hardcoded-data.
"""

import re
import pytest

from agent.prompts.calculator_base import (
    CALCULATOR_PROMPT_BASE,
    CALCULATOR_PROMPT_FORMAT,
    CALCULATOR_PROMPT_FOOTER,
    CALCULATOR_SECURITY_SECTION,
)


# Prices that MUST NOT appear in static prompts (service-specific prices)
FORBIDDEN_SERVICE_PRICES = [
    (r"\b85\b.*(?:IVA|taller|certificado)", "85€ taller certificate"),
    (r"\b100\b.*(?:IVA|urgente)", "100€ urgent expediente"),
    (r"\b375\b.*(?:frenada|ensayo)", "375€ brake test"),
    (r"\b400\b.*(?:direccion|ensayo)", "400€ steering test"),
    (r"\b725\b.*(?:combinado|ensayo)", "725€ combined test (phantom)"),
    (r"\b50\b.*(?:coordinacion|ensayo)", "50€ coordination (phantom)"),
]


class TestCalculatorBaseNoHardcodedPrices:
    """Verify all hardcoded service prices removed from calculator prompt constants."""

    @pytest.mark.parametrize("pattern,description", FORBIDDEN_SERVICE_PRICES)
    def test_prompt_format_no_service_prices(self, pattern: str, description: str):
        """CALCULATOR_PROMPT_FORMAT must not contain service prices."""
        assert not re.search(pattern, CALCULATOR_PROMPT_FORMAT, re.IGNORECASE), (
            f"Found hardcoded price '{description}' in CALCULATOR_PROMPT_FORMAT"
        )

    @pytest.mark.parametrize("pattern,description", FORBIDDEN_SERVICE_PRICES)
    def test_prompt_footer_no_service_prices(self, pattern: str, description: str):
        """CALCULATOR_PROMPT_FOOTER must not contain service prices."""
        assert not re.search(pattern, CALCULATOR_PROMPT_FOOTER, re.IGNORECASE), (
            f"Found hardcoded price '{description}' in CALCULATOR_PROMPT_FOOTER"
        )

    @pytest.mark.parametrize("pattern,description", FORBIDDEN_SERVICE_PRICES)
    def test_prompt_base_no_service_prices(self, pattern: str, description: str):
        """CALCULATOR_PROMPT_BASE must not contain service prices."""
        assert not re.search(pattern, CALCULATOR_PROMPT_BASE, re.IGNORECASE), (
            f"Found hardcoded price '{description}' in CALCULATOR_PROMPT_BASE"
        )

    @pytest.mark.parametrize("pattern,description", FORBIDDEN_SERVICE_PRICES)
    def test_security_section_no_service_prices(self, pattern: str, description: str):
        """CALCULATOR_SECURITY_SECTION must not contain service prices."""
        assert not re.search(pattern, CALCULATOR_SECURITY_SECTION, re.IGNORECASE), (
            f"Found hardcoded price '{description}' in CALCULATOR_SECURITY_SECTION"
        )


class TestAdditionalServicesInfoRemoved:
    """Verify ADDITIONAL_SERVICES_INFO constant has been removed."""

    def test_no_additional_services_info_export(self):
        """calculator_base module must not export ADDITIONAL_SERVICES_INFO."""
        import agent.prompts.calculator_base as module
        assert not hasattr(module, "ADDITIONAL_SERVICES_INFO"), (
            "ADDITIONAL_SERVICES_INFO should be removed from calculator_base.py"
        )

    def test_prompt_service_no_dead_import(self):
        """prompt_service must not import ADDITIONAL_SERVICES_INFO."""
        import inspect
        import agent.services.prompt_service as module
        source = inspect.getsource(module)
        assert "ADDITIONAL_SERVICES_INFO" not in source, (
            "prompt_service.py still imports removed ADDITIONAL_SERVICES_INFO"
        )


class TestPhantomServicesRemoved:
    """Verify phantom services (no DB backing) are gone."""

    def test_no_ensayo_combinado_in_prompts(self):
        """'Ensayo combinado' must not appear in any prompt constant."""
        all_prompts = (
            CALCULATOR_PROMPT_BASE
            + CALCULATOR_PROMPT_FORMAT
            + CALCULATOR_PROMPT_FOOTER
            + CALCULATOR_SECURITY_SECTION
        )
        assert "ensayo combinado" not in all_prompts.lower(), (
            "Phantom service 'Ensayo combinado' still in prompts"
        )

    def test_no_coordinacion_ensayo_in_prompts(self):
        """'Coordinacion ensayo' must not appear in any prompt constant."""
        all_prompts = (
            CALCULATOR_PROMPT_BASE
            + CALCULATOR_PROMPT_FORMAT
            + CALCULATOR_PROMPT_FOOTER
            + CALCULATOR_SECURITY_SECTION
        )
        assert "coordinacion ensayo" not in all_prompts.lower(), (
            "Phantom service 'Coordinacion ensayo' still in prompts"
        )


class TestToolDocstringsClean:
    """Verify tool docstrings don't contain hardcoded prices."""

    def test_actualizar_datos_taller_no_price(self):
        """actualizar_datos_taller docstring must not contain hardcoded price."""
        from agent.tools.case_tools import actualizar_datos_taller
        docstring = actualizar_datos_taller.description or ""
        assert "85" not in docstring, (
            "actualizar_datos_taller docstring still contains '85' price"
        )
        assert "+85" not in docstring, (
            "actualizar_datos_taller docstring still contains '+85' price"
        )


class TestPromptStillFunctional:
    """Verify prompt constants still contain essential instructions."""

    def test_format_mentions_taller_warning(self):
        """CALCULATOR_PROMPT_FORMAT must still mention taller certificate warning."""
        assert "taller" in CALCULATOR_PROMPT_FORMAT.lower(), (
            "Lost taller certificate warning from CALCULATOR_PROMPT_FORMAT"
        )

    def test_footer_mentions_taller_warning(self):
        """CALCULATOR_PROMPT_FOOTER must still mention taller certificate warning."""
        assert "certificado" in CALCULATOR_PROMPT_FOOTER.lower() or \
               "taller" in CALCULATOR_PROMPT_FOOTER.lower(), (
            "Lost taller certificate instruction from CALCULATOR_PROMPT_FOOTER"
        )

    def test_format_has_response_structure(self):
        """CALCULATOR_PROMPT_FORMAT must still contain response template."""
        assert "FORMATO DE RESPUESTA" in CALCULATOR_PROMPT_FORMAT, (
            "Lost response format template"
        )
        assert "mas IVA" in CALCULATOR_PROMPT_FORMAT, (
            "Lost 'mas IVA' in format template"
        )

    def test_footer_has_restrictions(self):
        """CALCULATOR_PROMPT_FOOTER must still contain critical restrictions."""
        assert "RESTRICCIONES CRITICAS" in CALCULATOR_PROMPT_FOOTER, (
            "Lost critical restrictions section"
        )
        assert "VALIDACION FINAL" in CALCULATOR_PROMPT_FOOTER, (
            "Lost final validation section"
        )
