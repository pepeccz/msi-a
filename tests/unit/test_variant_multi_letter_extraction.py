"""
Unit tests for the positional multi-letter extraction fix in _extract_element_fragment.

Bug: When the user responds "B y A" to a combined variant question (two elements
asked in the same message), the semantic anchor algorithm couldn't find any anchor
words (there are none in "B y A"), fell back to returning the full response, and
_normalize_to_canonical_letter("b y a") returned None — so positional_match was
never reached and the agent looped.

Fix: _extract_element_fragment now detects pure positional multi-letter responses
(N letters separated by y/and/commas) and assigns the i-th letter to the i-th
pending element via current_pending_idx.

Tests:
    1. test_b_y_a_first_element_gets_b     — PLACA_SOLAR (idx=0) with "B y A" → "b"
    2. test_b_y_a_second_element_gets_a    — TOLDO_LAT (idx=1) with "B y A" → "a"
    3. test_single_letter_unchanged        — "B" alone → no multi-letter path, fallback
    4. test_mixed_response_falls_back      — Semantic words → not a pure letter response
    5. test_a_comma_b_pattern              — "A, B" → same as "A y B"
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest


# ---------------------------------------------------------------------------
# Import the private helpers directly (no DB / Redis / LLM needed)
# ---------------------------------------------------------------------------
from agent.services.variant_interpretation_service import (
    _extract_element_fragment,
    _extract_positional_letters,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _make_pending(codigo_base: str) -> dict:
    """Minimal PendingVariantGroup for a single-unit element."""
    return {
        "codigo_base": codigo_base,
        "pregunta": f"¿Variante de {codigo_base}?",
        "opciones": ["A", "B", "C"],
        "cantidad_total": 1,
        "cantidad_resuelta": 0,
        "cantidad_pendiente": 1,
        "status": "pending",
    }


# Variants used in tests — variant_position matches letter index
PLACA_VARIANTS = [
    {"code": "PLACA_SOLAR_GALIBO", "name": "Con gálibo", "variant_position": 1},
    {
        "code": "PLACA_SOLAR_REGULADOR_INTERIOR",
        "name": "Con regulador interior",
        "variant_position": 2,
    },
    {
        "code": "PLACA_SOLAR_REGULADOR_EXTERIOR",
        "name": "Con regulador exterior",
        "variant_position": 3,
    },
]
TOLDO_VARIANTS = [
    {"code": "TOLDO_SIMPLE", "name": "Toldo simple", "variant_position": 1},
    {"code": "TOLDO_ELECTRICO", "name": "Toldo eléctrico", "variant_position": 2},
]


# ---------------------------------------------------------------------------
# 1. _extract_positional_letters unit tests
# ---------------------------------------------------------------------------


class TestExtractPositionalLetters:
    """Direct tests for the _extract_positional_letters helper."""

    def test_b_y_a_returns_b_a(self) -> None:
        result = _extract_positional_letters("B y A")
        assert result == ["b", "a"]

    def test_a_y_b_returns_a_b(self) -> None:
        result = _extract_positional_letters("a y b")
        assert result == ["a", "b"]

    def test_a_comma_b_returns_a_b(self) -> None:
        result = _extract_positional_letters("A, B")
        assert result == ["a", "b"]

    def test_b_comma_a_returns_b_a(self) -> None:
        result = _extract_positional_letters("b, a")
        assert result == ["b", "a"]

    def test_lowercase_b_y_a_returns_b_a(self) -> None:
        result = _extract_positional_letters("b y a")
        assert result == ["b", "a"]

    def test_three_letters_a_y_b_y_c(self) -> None:
        result = _extract_positional_letters("A y B y C")
        assert result == ["a", "b", "c"]

    def test_single_letter_returns_none(self) -> None:
        """Single letter must NOT activate multi-letter path — existing path handles it."""
        assert _extract_positional_letters("B") is None

    def test_single_letter_with_no_sep_returns_none(self) -> None:
        assert _extract_positional_letters("A") is None

    def test_semantic_words_return_none(self) -> None:
        """Semantic words are not single letters — should return None."""
        assert _extract_positional_letters("regulador oculto y toldo normal") is None

    def test_decorated_letter_returns_none(self) -> None:
        """'opción B' is NOT a pure letter — single token is 'opcion' which is >1 char."""
        assert _extract_positional_letters("opción B y A") is None

    def test_empty_string_returns_none(self) -> None:
        assert _extract_positional_letters("") is None

    def test_and_english_separator(self) -> None:
        result = _extract_positional_letters("B and A")
        assert result == ["b", "a"]

    def test_semicolon_separator(self) -> None:
        result = _extract_positional_letters("A; B")
        assert result == ["a", "b"]


# ---------------------------------------------------------------------------
# 2. _extract_element_fragment: first element gets B from "B y A"
# ---------------------------------------------------------------------------


class TestBYAFirstElementGetsB:
    """
    Test 1: PLACA_SOLAR (idx=0) with "B y A" → fragment = "b"
    Then positional_match maps "b" → position 2 → PLACA_SOLAR_REGULADOR_INTERIOR.
    """

    @pytest.mark.unit
    def test_b_y_a_first_element_gets_b(self) -> None:
        pending_placa = _make_pending("PLACA_SOLAR")
        # 2 total pending elements: PLACA_SOLAR at idx=0, TOLDO_LAT at idx=1
        fragment = _extract_element_fragment(
            respuesta="B y A",
            codigo_elemento_base="PLACA_SOLAR",
            base_element={"name": "Placa solar", "code": "PLACA_SOLAR"},
            current_pending=pending_placa,
            variants=PLACA_VARIANTS,
            current_pending_idx=0,  # PLACA_SOLAR is the FIRST pending element
            total_pending_count=2,  # Two pending elements total
        )
        assert fragment == "b", f"Expected 'b', got '{fragment}'"

    @pytest.mark.unit
    def test_b_y_a_first_element_uppercase_input(self) -> None:
        """Input is uppercase 'B y A' — result should still be lowercase 'b'."""
        pending_placa = _make_pending("PLACA_SOLAR")
        fragment = _extract_element_fragment(
            respuesta="B y A",
            codigo_elemento_base="PLACA_SOLAR",
            base_element=None,
            current_pending=pending_placa,
            variants=PLACA_VARIANTS,
            current_pending_idx=0,
            total_pending_count=2,
        )
        assert fragment == "b"

    @pytest.mark.unit
    def test_b_y_a_first_element_no_base_element(self) -> None:
        """Works even when base_element is None (no DB data available)."""
        pending_placa = _make_pending("PLACA_SOLAR")
        fragment = _extract_element_fragment(
            respuesta="B y A",
            codigo_elemento_base="PLACA_SOLAR",
            base_element=None,
            current_pending=None,
            variants=PLACA_VARIANTS,
            current_pending_idx=0,
            total_pending_count=2,
        )
        assert fragment == "b"


# ---------------------------------------------------------------------------
# 3. _extract_element_fragment: second element gets A from "B y A"
# ---------------------------------------------------------------------------


class TestBYASecondElementGetsA:
    """
    Test 2: TOLDO_LAT (idx=1) with "B y A" → fragment = "a"
    Then positional_match maps "a" → position 1 → TOLDO_SIMPLE.
    """

    @pytest.mark.unit
    def test_b_y_a_second_element_gets_a(self) -> None:
        pending_toldo = _make_pending("TOLDO_LAT")
        fragment = _extract_element_fragment(
            respuesta="B y A",
            codigo_elemento_base="TOLDO_LAT",
            base_element={"name": "Toldo lateral", "code": "TOLDO_LAT"},
            current_pending=pending_toldo,
            variants=TOLDO_VARIANTS,
            current_pending_idx=1,  # TOLDO_LAT is the SECOND pending element
            total_pending_count=2,  # Two pending elements total
        )
        assert fragment == "a", f"Expected 'a', got '{fragment}'"

    @pytest.mark.unit
    def test_b_y_a_second_element_lowercase_input(self) -> None:
        """'b y a' lowercase → second element extracts 'a'."""
        pending_toldo = _make_pending("TOLDO_LAT")
        fragment = _extract_element_fragment(
            respuesta="b y a",
            codigo_elemento_base="TOLDO_LAT",
            base_element=None,
            current_pending=None,
            variants=TOLDO_VARIANTS,
            current_pending_idx=1,
            total_pending_count=2,
        )
        assert fragment == "a"

    @pytest.mark.unit
    def test_a_y_b_second_element_gets_b(self) -> None:
        """'A y B' → second element (TOLDO) gets 'b'."""
        pending_toldo = _make_pending("TOLDO_LAT")
        fragment = _extract_element_fragment(
            respuesta="A y B",
            codigo_elemento_base="TOLDO_LAT",
            base_element=None,
            current_pending=None,
            variants=TOLDO_VARIANTS,
            current_pending_idx=1,
            total_pending_count=2,
        )
        assert fragment == "b"


# ---------------------------------------------------------------------------
# 4. Single letter unchanged — does NOT activate multi-letter path
# ---------------------------------------------------------------------------


class TestSingleLetterUnchanged:
    """
    Test 3: A single "B" response must NOT be altered.
    The multi-letter path requires ≥2 letters.
    The existing positional_match handles single letters.
    """

    @pytest.mark.unit
    def test_single_b_unchanged_with_pending(self) -> None:
        """Single 'B' with pending context → returned as-is (existing path applies)."""
        pending_placa = _make_pending("PLACA_SOLAR")
        fragment = _extract_element_fragment(
            respuesta="B",
            codigo_elemento_base="PLACA_SOLAR",
            base_element=None,
            current_pending=pending_placa,
            variants=PLACA_VARIANTS,
            current_pending_idx=0,
            total_pending_count=2,
        )
        # Multi-letter path NOT triggered (only 1 letter → _extract_positional_letters = None)
        # Semantic path: single clause → returned as-is
        assert fragment == "B"

    @pytest.mark.unit
    def test_single_a_unchanged_no_pending_context(self) -> None:
        """Single 'A' with no pending info → returned as-is."""
        fragment = _extract_element_fragment(
            respuesta="A",
            codigo_elemento_base="PLACA_SOLAR",
            base_element=None,
            current_pending=None,
            variants=PLACA_VARIANTS,
            current_pending_idx=-1,
            total_pending_count=0,
        )
        assert fragment == "A"

    @pytest.mark.unit
    def test_decorated_single_letter_not_altered(self) -> None:
        """'opción B' — not a pure letter response, semantic path runs normally."""
        pending_placa = _make_pending("PLACA_SOLAR")
        fragment = _extract_element_fragment(
            respuesta="opción B",
            codigo_elemento_base="PLACA_SOLAR",
            base_element={"name": "Placa solar", "code": "PLACA_SOLAR"},
            current_pending=pending_placa,
            variants=PLACA_VARIANTS,
            current_pending_idx=0,
            total_pending_count=2,
        )
        # Not a pure multi-letter response → falls through to semantic path
        # Single clause → returned as-is
        assert fragment == "opción B"


# ---------------------------------------------------------------------------
# 5. Semantic/mixed response falls back — does NOT activate multi-letter path
# ---------------------------------------------------------------------------


class TestMixedResponseFallsBack:
    """
    Test 4: "regulador oculto y toldo normal" contains semantic words.
    _extract_positional_letters returns None → existing semantic path runs.
    """

    @pytest.mark.unit
    def test_semantic_words_not_treated_as_letters(self) -> None:
        pending_placa = _make_pending("PLACA_SOLAR")
        fragment = _extract_element_fragment(
            respuesta="regulador oculto y toldo normal",
            codigo_elemento_base="PLACA_SOLAR",
            base_element={"name": "Placa solar", "code": "PLACA_SOLAR"},
            current_pending=pending_placa,
            variants=PLACA_VARIANTS,
            current_pending_idx=0,
            total_pending_count=2,
        )
        # Multi-letter path NOT activated (tokens > 1 char)
        # The semantic path returns the full response or a scored clause
        assert "regulador" in fragment or fragment == "regulador oculto y toldo normal"

    @pytest.mark.unit
    def test_partial_letters_with_words_falls_back(self) -> None:
        """'opción B y A' mixes a word token → NOT a pure multi-letter response."""
        pending_placa = _make_pending("PLACA_SOLAR")
        fragment = _extract_element_fragment(
            respuesta="opción B y A",
            codigo_elemento_base="PLACA_SOLAR",
            base_element={"name": "Placa solar", "code": "PLACA_SOLAR"},
            current_pending=pending_placa,
            variants=PLACA_VARIANTS,
            current_pending_idx=0,
            total_pending_count=2,
        )
        # Not pure multi-letter → semantic path runs (may return full or a clause)
        # The important thing: multi-letter path was NOT triggered
        # (if it were, it would return "b" — not what we want here)
        assert fragment != "b" or "opcion" in fragment.lower()

    @pytest.mark.unit
    def test_count_mismatch_falls_back(self) -> None:
        """3 letters but only 2 pending → count mismatch → multi-letter path skipped."""
        pending_placa = _make_pending("PLACA_SOLAR")
        fragment = _extract_element_fragment(
            respuesta="A y B y C",
            codigo_elemento_base="PLACA_SOLAR",
            base_element=None,
            current_pending=pending_placa,
            variants=PLACA_VARIANTS,
            current_pending_idx=0,
            total_pending_count=2,  # Only 2 pending, but 3 letters
        )
        # 3 ≠ 2 → multi-letter path NOT activated → semantic fallback
        # Single-clause check: "A y B y C" splits into clauses → semantic path runs
        # Since no meaningful anchors in letters, returns full response
        assert fragment == "A y B y C" or len(fragment) > 1


# ---------------------------------------------------------------------------
# 6. "A, B" comma-separated — same behavior as "A y B"
# ---------------------------------------------------------------------------


class TestACommaBPattern:
    """
    Test 5: "A, B" with comma separator behaves like "A y B".
    """

    @pytest.mark.unit
    def test_a_comma_b_first_element_gets_a(self) -> None:
        pending_placa = _make_pending("PLACA_SOLAR")
        fragment = _extract_element_fragment(
            respuesta="A, B",
            codigo_elemento_base="PLACA_SOLAR",
            base_element=None,
            current_pending=pending_placa,
            variants=PLACA_VARIANTS,
            current_pending_idx=0,
            total_pending_count=2,
        )
        assert fragment == "a"

    @pytest.mark.unit
    def test_a_comma_b_second_element_gets_b(self) -> None:
        pending_toldo = _make_pending("TOLDO_LAT")
        fragment = _extract_element_fragment(
            respuesta="A, B",
            codigo_elemento_base="TOLDO_LAT",
            base_element=None,
            current_pending=pending_toldo,
            variants=TOLDO_VARIANTS,
            current_pending_idx=1,
            total_pending_count=2,
        )
        assert fragment == "b"

    @pytest.mark.unit
    def test_b_comma_a_first_element_gets_b(self) -> None:
        pending_placa = _make_pending("PLACA_SOLAR")
        fragment = _extract_element_fragment(
            respuesta="B, A",
            codigo_elemento_base="PLACA_SOLAR",
            base_element=None,
            current_pending=pending_placa,
            variants=PLACA_VARIANTS,
            current_pending_idx=0,
            total_pending_count=2,
        )
        assert fragment == "b"

    @pytest.mark.unit
    def test_b_comma_a_second_element_gets_a(self) -> None:
        pending_toldo = _make_pending("TOLDO_LAT")
        fragment = _extract_element_fragment(
            respuesta="B, A",
            codigo_elemento_base="TOLDO_LAT",
            base_element=None,
            current_pending=pending_toldo,
            variants=TOLDO_VARIANTS,
            current_pending_idx=1,
            total_pending_count=2,
        )
        assert fragment == "a"


# ---------------------------------------------------------------------------
# 7. Edge cases: missing pending context doesn't crash
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Safety: function must not crash with missing/default arguments."""

    @pytest.mark.unit
    def test_no_pending_idx_skips_multi_letter_path(self) -> None:
        """current_pending_idx=-1 (default) → multi-letter path not activated."""
        fragment = _extract_element_fragment(
            respuesta="B y A",
            codigo_elemento_base="PLACA_SOLAR",
            base_element=None,
            current_pending=None,
            variants=PLACA_VARIANTS,
            # NOT passing current_pending_idx → defaults to -1
        )
        # Multi-letter path skipped (idx < 0) → semantic fallback
        # "B y A" splits into ["B", "A"] — no anchors → returns full original
        assert fragment == "B y A"

    @pytest.mark.unit
    def test_total_pending_count_1_skips_multi_letter_path(self) -> None:
        """total_pending_count=1 (only one pending) → no multi-letter context."""
        fragment = _extract_element_fragment(
            respuesta="B y A",
            codigo_elemento_base="PLACA_SOLAR",
            base_element=None,
            current_pending=None,
            variants=PLACA_VARIANTS,
            current_pending_idx=0,
            total_pending_count=1,  # Only 1 pending — but 2 letters in response
        )
        # count 2 ≠ total_pending_count 1 → multi-letter path not activated
        # Also total_pending_count < 2 guard → skipped
        assert fragment == "B y A"

    @pytest.mark.unit
    def test_out_of_bounds_idx_safe(self) -> None:
        """If idx >= len(letters), returns original (safety guard)."""
        fragment = _extract_element_fragment(
            respuesta="A y B",
            codigo_elemento_base="SOME_ELEMENT",
            base_element=None,
            current_pending=None,
            variants=[],
            current_pending_idx=5,  # WAY out of bounds for ["a", "b"]
            total_pending_count=2,
        )
        # len(letters)=2, idx=5 → guard: idx < len(letters) fails → falls through
        assert fragment == "A y B"
