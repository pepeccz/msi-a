"""
Unit tests for agent/prompts/ctas_catalog.py

Covers spec Capability 1: CTA Catalog module
- CTAS is a MappingProxyType
- Exactly 5 entries, keys 1–5
- All values are non-empty strings
- CTAS[3] exact literal
- get_cta(6) raises KeyError
- Mutation raises TypeError
"""
from __future__ import annotations

import pytest
from types import MappingProxyType


class TestCtasCatalogShape:
    """Catalog structural invariants."""

    def test_ctas_is_mapping_proxy_type(self):
        """CTAS must be a MappingProxyType — immutable at the module level."""
        from agent.prompts.ctas_catalog import CTAS

        assert isinstance(CTAS, MappingProxyType), (
            f"CTAS must be MappingProxyType, got {type(CTAS).__name__}"
        )

    def test_ctas_has_exactly_5_entries(self):
        """CTAS must have exactly 5 entries — one per CTA state."""
        from agent.prompts.ctas_catalog import CTAS

        assert len(CTAS) == 5, f"Expected 5 CTAs, got {len(CTAS)}"

    def test_ctas_keys_are_1_through_5(self):
        """CTAS keys must be integers 1, 2, 3, 4, 5."""
        from agent.prompts.ctas_catalog import CTAS

        assert set(CTAS.keys()) == {1, 2, 3, 4, 5}, (
            f"Expected keys {{1, 2, 3, 4, 5}}, got {set(CTAS.keys())}"
        )

    def test_all_cta_values_are_nonempty_strings(self):
        """Every CTA value must be a non-empty str."""
        from agent.prompts.ctas_catalog import CTAS

        for k, v in CTAS.items():
            assert isinstance(v, str) and len(v) > 0, (
                f"CTAS[{k}] must be a non-empty string, got {v!r}"
            )


class TestCtasCatalogValues:
    """Exact canonical literal checks."""

    def test_cta3_exact_literal(self):
        """
        GIVEN the catalog is imported
        WHEN CTAS[3] is accessed
        THEN it must return the exact canonical string.
        """
        from agent.prompts.ctas_catalog import CTAS

        expected = "¿Te muestro ejemplos de cómo deben ser las fotos o te calculo el presupuesto?"
        assert CTAS[3] == expected, (
            f"CTAS[3] mismatch. Expected {expected!r}, got {CTAS[3]!r}"
        )

    def test_cta1_exact_literal(self):
        from agent.prompts.ctas_catalog import CTAS

        assert CTAS[1] == "¿Quieres que te ayude con alguna homologación?"

    def test_cta5_exact_literal(self):
        from agent.prompts.ctas_catalog import CTAS

        assert CTAS[5] == "¿Abrimos expediente o tienes alguna duda?"


class TestCtasCatalogImmutability:
    """Immutability contract — MappingProxyType must reject mutation."""

    def test_mutation_raises_type_error(self):
        """
        GIVEN CTAS is a MappingProxyType
        WHEN an assignment is attempted
        THEN a TypeError must be raised.
        """
        from agent.prompts.ctas_catalog import CTAS

        with pytest.raises(TypeError):
            CTAS[1] = "nuevo cta"  # type: ignore[index]


class TestGetCtaFunction:
    """get_cta() helper function."""

    def test_get_cta_returns_correct_value(self):
        from agent.prompts.ctas_catalog import get_cta

        result = get_cta(3)
        assert result == "¿Te muestro ejemplos de cómo deben ser las fotos o te calculo el presupuesto?"

    def test_get_cta_unknown_key_raises_key_error(self):
        """
        GIVEN the catalog has keys 1–5
        WHEN get_cta(6) is called
        THEN a KeyError must be raised (fail-fast).
        """
        from agent.prompts.ctas_catalog import get_cta

        with pytest.raises(KeyError):
            get_cta(6)
