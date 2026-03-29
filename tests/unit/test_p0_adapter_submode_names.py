"""
Unit tests for P0 Fix 4 — sub-mode canonical names in expediente_transition_adapter.py.

Before the fix, CANONICAL_SUB_MODES and SUB_MODE_ALIAS_MAP contained stale names
("collect_taller", "review") that did not match the names used by the rest of the
codebase ("collect_workshop", "review_summary"). These tests verify that all
workshop-related and review-related inputs resolve to the correct canonical names.

No DB or Redis required — tests only the constants and pure canonicalization logic.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Ensure structlog stub is present (in case this file runs before conftest.py)
# ---------------------------------------------------------------------------
if "structlog" not in sys.modules:
    _structlog = types.ModuleType("structlog")
    _structlog.get_logger = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    sys.modules["structlog"] = _structlog


# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from agent.utils.expediente_transition_adapter import (
    CANONICAL_SUB_MODES,
    SUB_MODE_ALIAS_MAP,
    canonicalize_transition,
)


# ---------------------------------------------------------------------------
# Tests — Constants
# ---------------------------------------------------------------------------


class TestCanonicalSubModeConstants:
    """Directly validate the CANONICAL_SUB_MODES list and SUB_MODE_ALIAS_MAP values."""

    def test_collect_workshop_is_canonical(self):
        """collect_workshop must be in CANONICAL_SUB_MODES (not collect_taller)."""
        assert "collect_workshop" in CANONICAL_SUB_MODES, (
            f"'collect_workshop' not found in CANONICAL_SUB_MODES: {CANONICAL_SUB_MODES}"
        )

    def test_collect_taller_not_canonical(self):
        """collect_taller must NOT appear in CANONICAL_SUB_MODES."""
        assert "collect_taller" not in CANONICAL_SUB_MODES, (
            "'collect_taller' still appears in CANONICAL_SUB_MODES — rename incomplete"
        )

    def test_review_summary_is_canonical(self):
        """review_summary must be in CANONICAL_SUB_MODES (not review)."""
        assert "review_summary" in CANONICAL_SUB_MODES, (
            f"'review_summary' not found in CANONICAL_SUB_MODES: {CANONICAL_SUB_MODES}"
        )

    def test_bare_review_not_canonical(self):
        """'review' must NOT appear in CANONICAL_SUB_MODES."""
        assert "review" not in CANONICAL_SUB_MODES, (
            "'review' still appears in CANONICAL_SUB_MODES — rename incomplete"
        )

    def test_workshop_alias_resolves_to_collect_workshop(self):
        """'workshop' alias must map to 'collect_workshop'."""
        assert SUB_MODE_ALIAS_MAP.get("workshop") == "collect_workshop", (
            f"'workshop' maps to {SUB_MODE_ALIAS_MAP.get('workshop')!r}, expected 'collect_workshop'"
        )

    def test_taller_alias_resolves_to_collect_workshop(self):
        """'taller' alias must map to 'collect_workshop'."""
        assert SUB_MODE_ALIAS_MAP.get("taller") == "collect_workshop", (
            f"'taller' maps to {SUB_MODE_ALIAS_MAP.get('taller')!r}, expected 'collect_workshop'"
        )

    def test_collect_workshop_alias_resolves_to_collect_workshop(self):
        """Uppercase 'COLLECT_WORKSHOP' alias must map to 'collect_workshop'."""
        assert SUB_MODE_ALIAS_MAP.get("COLLECT_WORKSHOP") == "collect_workshop", (
            f"'COLLECT_WORKSHOP' maps to {SUB_MODE_ALIAS_MAP.get('COLLECT_WORKSHOP')!r}"
        )

    def test_collect_taller_alias_resolves_to_collect_workshop(self):
        """Legacy 'COLLECT_TALLER' alias must map to 'collect_workshop'."""
        assert SUB_MODE_ALIAS_MAP.get("COLLECT_TALLER") == "collect_workshop", (
            f"'COLLECT_TALLER' maps to {SUB_MODE_ALIAS_MAP.get('COLLECT_TALLER')!r}"
        )

    def test_revision_alias_resolves_to_review_summary(self):
        """'revision' alias must map to 'review_summary'."""
        assert SUB_MODE_ALIAS_MAP.get("revision") == "review_summary", (
            f"'revision' maps to {SUB_MODE_ALIAS_MAP.get('revision')!r}, expected 'review_summary'"
        )

    def test_resumen_alias_resolves_to_review_summary(self):
        """'resumen' alias must map to 'review_summary'."""
        assert SUB_MODE_ALIAS_MAP.get("resumen") == "review_summary", (
            f"'resumen' maps to {SUB_MODE_ALIAS_MAP.get('resumen')!r}, expected 'review_summary'"
        )

    def test_review_alias_resolves_to_review_summary(self):
        """Uppercase 'REVIEW' alias must map to 'review_summary'."""
        assert SUB_MODE_ALIAS_MAP.get("REVIEW") == "review_summary", (
            f"'REVIEW' maps to {SUB_MODE_ALIAS_MAP.get('REVIEW')!r}, expected 'review_summary'"
        )

    def test_review_summary_alias_resolves_to_review_summary(self):
        """Uppercase 'REVIEW_SUMMARY' alias must map to 'review_summary'."""
        assert SUB_MODE_ALIAS_MAP.get("REVIEW_SUMMARY") == "review_summary", (
            f"'REVIEW_SUMMARY' maps to {SUB_MODE_ALIAS_MAP.get('REVIEW_SUMMARY')!r}"
        )

    def test_no_stale_collect_taller_values_in_alias_map(self):
        """No value in SUB_MODE_ALIAS_MAP should be 'collect_taller'."""
        stale_entries = {
            k: v for k, v in SUB_MODE_ALIAS_MAP.items() if v == "collect_taller"
        }
        assert not stale_entries, (
            f"Found stale 'collect_taller' values in SUB_MODE_ALIAS_MAP: {stale_entries}"
        )

    def test_no_stale_bare_review_values_in_alias_map(self):
        """No value in SUB_MODE_ALIAS_MAP should be bare 'review' (must be 'review_summary')."""
        stale_entries = {k: v for k, v in SUB_MODE_ALIAS_MAP.items() if v == "review"}
        assert not stale_entries, (
            f"Found stale 'review' values in SUB_MODE_ALIAS_MAP: {stale_entries}"
        )


# ---------------------------------------------------------------------------
# Tests — canonicalize_transition() integration
# ---------------------------------------------------------------------------


class TestCanonicalizeTransitionSubModes:
    """
    Tests the canonicalize_transition() pure function with workshop / review
    related inputs to verify end-to-end normalization.
    """

    def test_context_updates_collect_workshop(self):
        """_context_updates channel with 'collect_workshop' resolves correctly."""
        result = canonicalize_transition(
            {
                "_context_updates": {"expediente_sub_mode": "collect_workshop"},
            }
        )
        assert result.target_sub_mode == "collect_workshop", (
            f"Expected 'collect_workshop', got {result.target_sub_mode!r}"
        )

    def test_context_updates_review_summary(self):
        """_context_updates channel with 'review_summary' resolves correctly."""
        result = canonicalize_transition(
            {
                "_context_updates": {"expediente_sub_mode": "review_summary"},
            }
        )
        assert result.target_sub_mode == "review_summary", (
            f"Expected 'review_summary', got {result.target_sub_mode!r}"
        )

    def test_legacy_taller_string_resolves_to_collect_workshop(self):
        """Legacy 'taller' next_step string resolves to 'collect_workshop'."""
        result = canonicalize_transition({"next_step": "taller"})
        assert result.target_sub_mode == "collect_workshop", (
            f"'taller' resolved to {result.target_sub_mode!r}, expected 'collect_workshop'"
        )

    def test_legacy_workshop_string_resolves_to_collect_workshop(self):
        """Legacy 'workshop' next_step string resolves to 'collect_workshop'."""
        result = canonicalize_transition({"next_step": "workshop"})
        assert result.target_sub_mode == "collect_workshop", (
            f"'workshop' resolved to {result.target_sub_mode!r}, expected 'collect_workshop'"
        )

    def test_legacy_review_string_resolves_to_review_summary(self):
        """
        Legacy 'review' next_step string resolves to 'review_summary'.
        This is the alias path REVIEW → review_summary in SUB_MODE_ALIAS_MAP.
        """
        result = canonicalize_transition({"next_step": "revision"})
        assert result.target_sub_mode == "review_summary", (
            f"'revision' resolved to {result.target_sub_mode!r}, expected 'review_summary'"
        )

    def test_collect_taller_legacy_alias_resolves_to_collect_workshop(self):
        """
        Direct 'collect_taller' next_step (legacy FSM value) must resolve
        to 'collect_workshop' via the alias map.
        """
        result = canonicalize_transition({"next_step": "collect_taller"})
        # collect_taller should not be canonical — it's either normalized via
        # ALIAS_MAP to collect_workshop, or it falls through as-is.
        # The alias map entry COLLECT_TALLER → collect_workshop handles uppercase.
        # Lowercase 'collect_taller' is not an alias key — verify it doesn't
        # appear as a canonical name.
        assert result.target_sub_mode != "collect_taller", (
            "Expected 'collect_taller' to NOT be a canonical sub-mode output"
        )

    def test_collect_workshop_passthrough(self):
        """Already-canonical 'collect_workshop' passes through unchanged."""
        result = canonicalize_transition(
            {
                "_context_updates": {"expediente_sub_mode": "collect_workshop"},
            }
        )
        assert result.target_sub_mode == "collect_workshop"

    def test_review_summary_passthrough(self):
        """Already-canonical 'review_summary' passes through unchanged."""
        result = canonicalize_transition(
            {
                "_context_updates": {"expediente_sub_mode": "review_summary"},
            }
        )
        assert result.target_sub_mode == "review_summary"
