"""
Tests for normalize_pending_variants() in agent/state/helpers.py — Task 4.2.

Covers:
- Legacy entry up-conversion (only codigo_base/pregunta/opciones → enriched)
- Already-normalized entries returned as-is
- Idempotency (calling twice produces same result)
- Empty list handling

All tests are synchronous — no external services needed.
"""

import copy

import pytest

from agent.state.conversation_state import PendingVariantGroup, VariantResolution
from agent.state.helpers import normalize_pending_variants


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_legacy_entry(
    codigo_base: str = "SUSPENSION",
    pregunta: str = "¿Suspensión delantera o trasera?",
    opciones: list[str] | None = None,
) -> dict:
    """Build a legacy pending variant entry (only codigo_base, pregunta, opciones)."""
    return {
        "codigo_base": codigo_base,
        "pregunta": pregunta,
        "opciones": opciones or ["Delantera", "Trasera"],
    }


def _make_normalized_entry(
    codigo_base: str = "PLACA_SOLAR",
    cantidad_total: int = 3,
    cantidad_resuelta: int = 1,
    status: str = "partial",
) -> PendingVariantGroup:
    """Build an already-normalized PendingVariantGroup."""
    return PendingVariantGroup(
        pending_id=f"{codigo_base}_0",
        codigo_base=codigo_base,
        pregunta="¿La placa solar incluye regulador?",
        opciones=["Con regulador propio", "Regulador existente"],
        cantidad_total=cantidad_total,
        cantidad_resuelta=cantidad_resuelta,
        cantidad_pendiente=cantidad_total - cantidad_resuelta,
        resoluciones=[
            VariantResolution(
                variant_code="Con regulador propio",
                quantity=1,
                confidence=0.9,
                source="user_explicit",
            ),
        ] if cantidad_resuelta > 0 else [],
        status=status,
    )


# ===========================================================================
# Test cases
# ===========================================================================


class TestNormalizePendingVariants:
    """Tests for normalize_pending_variants() utility function."""

    def test_normalize_legacy_entry(self):
        """Dict with only codigo_base/pregunta/opciones → gets enriched fields."""
        legacy = _make_legacy_entry(
            codigo_base="SUSPENSION",
            pregunta="¿Delantera o trasera?",
            opciones=["Delantera", "Trasera"],
        )

        result = normalize_pending_variants([legacy])

        assert len(result) == 1
        entry = result[0]

        # New fields should be populated
        assert entry["pending_id"] == "SUSPENSION_0"
        assert entry["codigo_base"] == "SUSPENSION"
        assert entry["pregunta"] == "¿Delantera o trasera?"
        assert entry["opciones"] == ["Delantera", "Trasera"]
        assert entry["cantidad_total"] == 1  # Default for legacy
        assert entry["cantidad_resuelta"] == 0
        assert entry["cantidad_pendiente"] == 1
        assert entry["resoluciones"] == []
        assert entry["status"] == "pending"

    def test_normalize_already_normalized(self):
        """Entry with pending_id → returned as-is (with derived fields recalculated)."""
        normalized_entry = _make_normalized_entry(
            cantidad_total=3,
            cantidad_resuelta=1,
            status="partial",
        )

        result = normalize_pending_variants([normalized_entry])

        assert len(result) == 1
        entry = result[0]

        # Should keep existing values
        assert entry["pending_id"] == "PLACA_SOLAR_0"
        assert entry["codigo_base"] == "PLACA_SOLAR"
        assert entry["cantidad_total"] == 3
        assert entry["cantidad_resuelta"] == 1
        # Derived field recalculated
        assert entry["cantidad_pendiente"] == 2
        assert entry["status"] == "partial"

    def test_normalize_idempotent(self):
        """Calling twice produces same result."""
        legacy = _make_legacy_entry()

        first_pass = normalize_pending_variants([legacy])
        second_pass = normalize_pending_variants(first_pass)

        assert len(first_pass) == len(second_pass)
        for first, second in zip(first_pass, second_pass):
            assert first["pending_id"] == second["pending_id"]
            assert first["codigo_base"] == second["codigo_base"]
            assert first["cantidad_total"] == second["cantidad_total"]
            assert first["cantidad_resuelta"] == second["cantidad_resuelta"]
            assert first["cantidad_pendiente"] == second["cantidad_pendiente"]
            assert first["status"] == second["status"]
            assert first["resoluciones"] == second["resoluciones"]

    def test_normalize_empty_list(self):
        """Empty list → empty list."""
        result = normalize_pending_variants([])
        assert result == []

    def test_normalize_multiple_legacy_entries(self):
        """Multiple legacy entries get unique pending_ids."""
        entries = [
            _make_legacy_entry("SUSPENSION"),
            _make_legacy_entry("PLACA_SOLAR"),
        ]

        result = normalize_pending_variants(entries)

        assert len(result) == 2
        assert result[0]["pending_id"] == "SUSPENSION_0"
        assert result[1]["pending_id"] == "PLACA_SOLAR_1"

    def test_normalize_mixed_legacy_and_normalized(self):
        """Mix of legacy and already-normalized entries handled correctly."""
        entries: list[dict] = [
            _make_legacy_entry("ESCAPE"),
            _make_normalized_entry("PLACA_SOLAR", cantidad_total=2, cantidad_resuelta=0, status="pending"),
        ]

        result = normalize_pending_variants(entries)

        assert len(result) == 2
        # First: legacy up-converted
        assert result[0]["pending_id"] == "ESCAPE_0"
        assert result[0]["cantidad_total"] == 1
        assert result[0]["status"] == "pending"
        # Second: already normalized
        assert result[1]["pending_id"] == "PLACA_SOLAR_0"
        assert result[1]["cantidad_total"] == 2

    def test_normalize_recalculates_derived_status_resolved(self):
        """Status is recalculated from quantities — resolved case."""
        entry = PendingVariantGroup(
            pending_id="TEST_0",
            codigo_base="TEST",
            pregunta="test?",
            opciones=["A", "B"],
            cantidad_total=2,
            cantidad_resuelta=2,
            cantidad_pendiente=0,  # Will be recalculated
            resoluciones=[],
            status="pending",  # Wrong — should become "resolved"
        )

        result = normalize_pending_variants([entry])
        assert result[0]["status"] == "resolved"
        assert result[0]["cantidad_pendiente"] == 0

    def test_normalize_recalculates_derived_status_pending(self):
        """Status recalculated — pending case (resuelta == 0)."""
        entry = PendingVariantGroup(
            pending_id="TEST_0",
            codigo_base="TEST",
            pregunta="test?",
            opciones=["A", "B"],
            cantidad_total=3,
            cantidad_resuelta=0,
            cantidad_pendiente=3,
            resoluciones=[],
            status="resolved",  # Wrong — should become "pending"
        )

        result = normalize_pending_variants([entry])
        assert result[0]["status"] == "pending"

    def test_normalize_legacy_without_codigo_base(self):
        """Legacy entry missing codigo_base gets fallback UNKNOWN_N."""
        entry: dict = {
            "pregunta": "¿Qué tipo?",
            "opciones": ["A", "B"],
        }

        result = normalize_pending_variants([entry])

        assert len(result) == 1
        assert result[0]["pending_id"] == "UNKNOWN_0_0"
        assert result[0]["codigo_base"] == "UNKNOWN_0"

    def test_normalize_does_not_mutate_input(self):
        """Original list is not mutated."""
        legacy = _make_legacy_entry()
        original = copy.deepcopy(legacy)

        normalize_pending_variants([legacy])

        # Legacy entry should not have been mutated in-place
        assert "pending_id" not in legacy
        assert legacy == original
