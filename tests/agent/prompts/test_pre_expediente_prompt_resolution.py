"""
Unit tests for PRE_EXPEDIENTE_MODE prompt phase resolution.

Tests _resolve_mode_key() from agent/prompts/loader.py.

3-phase resolution logic:
  - No context or element_codes empty → PRE_EXPEDIENTE_DISCOVERY
  - element_codes populated, precio_comunicado=False → PRE_EXPEDIENTE_PRICING
  - precio_comunicado=True → PRE_EXPEDIENTE_POST_PRICE

All tests are pure unit tests — no DB, no Redis, no LLM, no I/O.
"""

import pytest

from agent.prompts.loader import _resolve_mode_key


# ---------------------------------------------------------------------------
# Discovery phase
# ---------------------------------------------------------------------------


class TestDiscoveryPhase:
    """No elements identified yet → PRE_EXPEDIENTE_DISCOVERY."""

    def test_discovery_phase_no_context(self):
        result = _resolve_mode_key("PRE_EXPEDIENTE_MODE", mode_context=None)
        assert result == "PRE_EXPEDIENTE_DISCOVERY"

    def test_discovery_phase_empty_context(self):
        result = _resolve_mode_key("PRE_EXPEDIENTE_MODE", mode_context={})
        assert result == "PRE_EXPEDIENTE_DISCOVERY"

    def test_discovery_phase_no_elements(self):
        result = _resolve_mode_key(
            "PRE_EXPEDIENTE_MODE",
            mode_context={"element_codes": []},
        )
        assert result == "PRE_EXPEDIENTE_DISCOVERY"

    def test_discovery_phase_no_elements_no_price(self):
        result = _resolve_mode_key(
            "PRE_EXPEDIENTE_MODE",
            mode_context={"element_codes": [], "precio_comunicado": False},
        )
        assert result == "PRE_EXPEDIENTE_DISCOVERY"

    def test_discovery_phase_missing_element_codes_key(self):
        # Context present but element_codes key absent
        result = _resolve_mode_key(
            "PRE_EXPEDIENTE_MODE",
            mode_context={"categoria_slug": "motos-part"},
        )
        assert result == "PRE_EXPEDIENTE_DISCOVERY"


# ---------------------------------------------------------------------------
# Pricing phase
# ---------------------------------------------------------------------------


class TestPricingPhase:
    """Elements identified, price not communicated → PRE_EXPEDIENTE_PRICING."""

    def test_pricing_phase_elements_no_price(self):
        result = _resolve_mode_key(
            "PRE_EXPEDIENTE_MODE",
            mode_context={"element_codes": ["SUSPENSION-DELANTERA"], "precio_comunicado": False},
        )
        assert result == "PRE_EXPEDIENTE_PRICING"

    def test_pricing_phase_elements_price_falsy(self):
        result = _resolve_mode_key(
            "PRE_EXPEDIENTE_MODE",
            mode_context={"element_codes": ["ESCAPE"]},
        )
        assert result == "PRE_EXPEDIENTE_PRICING"

    def test_pricing_phase_multiple_elements(self):
        result = _resolve_mode_key(
            "PRE_EXPEDIENTE_MODE",
            mode_context={"element_codes": ["SUSPENSION-DEL", "ESCAPE"]},
        )
        assert result == "PRE_EXPEDIENTE_PRICING"


# ---------------------------------------------------------------------------
# Post-price phase
# ---------------------------------------------------------------------------


class TestPostPricePhase:
    """precio_comunicado=True → PRE_EXPEDIENTE_POST_PRICE (highest priority)."""

    def test_post_price_phase(self):
        result = _resolve_mode_key(
            "PRE_EXPEDIENTE_MODE",
            mode_context={"precio_comunicado": True},
        )
        assert result == "PRE_EXPEDIENTE_POST_PRICE"

    def test_post_price_phase_with_elements(self):
        result = _resolve_mode_key(
            "PRE_EXPEDIENTE_MODE",
            mode_context={
                "element_codes": ["SUSPENSION"],
                "precio_comunicado": True,
                "tarifa_calculada": {"precio_final": 410},
            },
        )
        assert result == "PRE_EXPEDIENTE_POST_PRICE"

    def test_post_price_takes_priority_over_elements(self):
        """precio_comunicado=True should win even when element_codes are present."""
        result = _resolve_mode_key(
            "PRE_EXPEDIENTE_MODE",
            mode_context={
                "element_codes": ["ESCAPE"],
                "precio_comunicado": True,
            },
        )
        assert result == "PRE_EXPEDIENTE_POST_PRICE"


# ---------------------------------------------------------------------------
# Non-PRE_EXPEDIENTE_MODE — no regressions
# ---------------------------------------------------------------------------


class TestNonPreExpedienteMode:
    """Other modes should pass through without phase resolution."""

    def test_expediente_mode_with_sub_mode(self):
        result = _resolve_mode_key(
            "EXPEDIENTE_MODE",
            sub_mode="DATOS_PERSONALES",
        )
        assert result == "EXPEDIENTE_DATOS_PERSONALES"

    def test_unknown_mode_passthrough(self):
        result = _resolve_mode_key("ESCALATION")
        assert result == "ESCALATION"

    def test_expediente_mode_no_sub_mode(self):
        result = _resolve_mode_key("EXPEDIENTE_MODE")
        assert result == "EXPEDIENTE_MODE"
