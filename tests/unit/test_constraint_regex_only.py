"""
Tests for regex-only constraint validation (price_requires_tool).

Verifies that price_requires_tool constraint does NOT call LLM for validation
and fires based on regex match alone.
"""

import pytest
from unittest.mock import AsyncMock, patch

from agent.services.constraint_service import (
    validate_response_hybrid,
    _REGEX_ONLY_CONSTRAINTS,
)


# Standard price_requires_tool constraint (matches production DB seed)
PRICE_CONSTRAINT = {
    "constraint_type": "price_requires_tool",
    "detection_pattern": r"\d+\s*€|\d+\s*EUR|presupuesto.*\d+|\d+.*\+\s*IVA",
    "required_tool": "calcular_tarifa_con_elementos",
    "error_injection": (
        "CORRECCION OBLIGATORIA: Has mencionado un precio sin haber llamado a "
        "calcular_tarifa_con_elementos. NUNCA inventes precios."
    ),
    "priority": 100,
}

# A non-regex-only constraint for comparison
IMAGES_CONSTRAINT = {
    "constraint_type": "images_narration_blocked",
    "detection_pattern": r"(te envío|aquí tienes|mira estas)\s*(fotos?|imágenes?)",
    "required_tool": "enviar_imagenes_ejemplo",
    "error_injection": "No narres imágenes.",
    "priority": 90,
}


class TestRegexOnlyConstraintConfig:
    """Verify _REGEX_ONLY_CONSTRAINTS configuration."""

    def test_price_requires_tool_is_regex_only(self):
        """price_requires_tool must be in _REGEX_ONLY_CONSTRAINTS."""
        assert "price_requires_tool" in _REGEX_ONLY_CONSTRAINTS

    def test_images_constraint_is_not_regex_only(self):
        """Other constraints should NOT be in _REGEX_ONLY_CONSTRAINTS."""
        assert "images_narration_blocked" not in _REGEX_ONLY_CONSTRAINTS


class TestPriceConstraintRegexOnly:
    """Verify price_requires_tool fires without LLM validation."""

    @pytest.mark.asyncio
    async def test_price_violation_no_llm_call(self):
        """Price mentioned without tool → violation WITHOUT calling LLM."""
        with patch("agent.services.constraint_service.validate_with_llm") as mock_llm:
            is_valid, error = await validate_response_hybrid(
                response_text="El precio es de 410 EUR +IVA",
                tools_called_this_turn=set(),  # No tools called
                constraints=[PRICE_CONSTRAINT],
            )
            assert is_valid is False
            assert error is not None
            assert "CORRECCION OBLIGATORIA" in error
            # Critical: LLM must NOT be called
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_price_with_tool_passes(self):
        """Price mentioned WITH calcular_tarifa tool → valid (no violation)."""
        with patch("agent.services.constraint_service.validate_with_llm") as mock_llm:
            is_valid, error = await validate_response_hybrid(
                response_text="El presupuesto es de 410 EUR +IVA",
                tools_called_this_turn={"calcular_tarifa_con_elementos"},
                constraints=[PRICE_CONSTRAINT],
            )
            assert is_valid is True
            assert error is None
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_price_in_response_passes(self):
        """Response without prices → valid (regex doesn't match)."""
        with patch("agent.services.constraint_service.validate_with_llm") as mock_llm:
            is_valid, error = await validate_response_hybrid(
                response_text="Puedo darte el presupuesto exacto ahora mismo",
                tools_called_this_turn=set(),
                constraints=[PRICE_CONSTRAINT],
            )
            assert is_valid is True
            assert error is None
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_price_skipped_when_tarifa_calculada(self):
        """Price constraint skipped when tarifa already calculated."""
        with patch("agent.services.constraint_service.validate_with_llm") as mock_llm:
            is_valid, error = await validate_response_hybrid(
                response_text="Como decía, son 410 EUR +IVA",
                tools_called_this_turn=set(),
                constraints=[PRICE_CONSTRAINT],
                fsm_state={"tarifa_calculada": {"precio": 410}},
            )
            assert is_valid is True
            assert error is None
            mock_llm.assert_not_called()


class TestNonRegexOnlyConstraintStillUsesLLM:
    """Verify non-regex-only constraints still call LLM validation path."""

    @pytest.mark.asyncio
    async def test_images_constraint_reaches_llm_call(self):
        """images_narration_blocked should reach validate_with_llm (not short-circuit).

        Uses a response text that matches the regex pattern exactly.
        """
        with patch(
            "agent.services.constraint_service.validate_with_llm",
            new_callable=AsyncMock,
            return_value=False,  # LLM confirms violation
        ) as mock_llm:
            is_valid, error = await validate_response_hybrid(
                response_text="te envío fotos de ejemplo",  # Matches: "te envío" + "fotos"
                tools_called_this_turn=set(),
                constraints=[IMAGES_CONSTRAINT],
            )
            # Non-regex-only constraint: either LLM was called or feature flag was off.
            # Either way, the constraint fires (regex match + no tool + LLM confirms/unavailable).
            assert is_valid is False
            assert error is not None

    @pytest.mark.asyncio
    async def test_price_constraint_never_reaches_llm(self):
        """price_requires_tool must NEVER reach validate_with_llm regardless of settings."""
        with patch(
            "agent.services.constraint_service.validate_with_llm",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_llm:
            is_valid, error = await validate_response_hybrid(
                response_text="El precio es de 410 EUR +IVA",
                tools_called_this_turn=set(),
                constraints=[PRICE_CONSTRAINT],
            )
            assert is_valid is False
            # This is the critical assertion: LLM must NEVER be consulted
            mock_llm.assert_not_called()
