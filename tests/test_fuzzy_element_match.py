"""
Tests for fuzzy element code matching in normalize_element_code().

Verifies the _fuzzy_best_match() helper and its integration into the
normalize_element_code() pipeline (exact → plural → fuzzy → None).

Run with: pytest tests/test_fuzzy_element_match.py -v
"""

import pytest

from agent.tools.element_tools import _fuzzy_best_match, normalize_element_code


# ---------------------------------------------------------------------------
# Valid codes fixture (representative subset from real categories)
# ---------------------------------------------------------------------------

VALID_CODES: set[str] = {
    "ESCAPE",
    "ESCAPE_DELANTERO",
    "ESCAPE_TRASERO",
    "SUBCHASIS",
    "ASIDEROS",
    "PLACA_SOLAR_REGULADOR_INTERIOR",
    "TOLDO_SIMPLE",
    "TOLDO_COFRE",
    "SUSPENSION_DELANTERA",
    "SUSPENSION_TRASERA",
    "DEFENSA_DELANTERA",
    "DEFENSA_TRASERA",
}


# ---------------------------------------------------------------------------
# 1. _fuzzy_best_match — unit tests
# ---------------------------------------------------------------------------


class TestFuzzyBestMatch:
    """Direct tests for the _fuzzy_best_match helper."""

    @pytest.mark.parametrize(
        "code, expected",
        [
            # (a) Partial-overlap code corrected via combined scoring
            ("PLACA_SOLAR_REG_OCULTO", "PLACA_SOLAR_REGULADOR_INTERIOR"),
            # Single-token abbreviation with high token overlap
            ("SUSPENSION_DELANT", "SUSPENSION_DELANTERA"),
        ],
        ids=["partial-overlap-placa-solar", "abbreviated-suspension"],
    )
    def test_true_positive_matches(self, code: str, expected: str) -> None:
        result = _fuzzy_best_match(code, VALID_CODES)
        assert result == expected, f"Expected '{expected}', got '{result}'"

    @pytest.mark.parametrize(
        "code",
        [
            # (b) Ambiguous / low-overlap — should return None
            "TOLDO_SIN_GALIBO",
            # Completely unrelated code
            "RANDOM_CODE_INVENTADO",
            # Single generic token
            "COSA",
        ],
        ids=["ambiguous-toldo", "unrelated-code", "generic-single-token"],
    )
    def test_true_negative_no_match(self, code: str) -> None:
        result = _fuzzy_best_match(code, VALID_CODES)
        assert result is None, f"Expected None, got '{result}'"

    def test_tie_returns_none(self) -> None:
        """(c) When two candidates score identically, return None (ambiguous)."""
        # Construct a symmetric pair: same prefix, same-length suffixes
        # that produce identical SequenceMatcher ratios and identical Jaccard.
        tied_codes: set[str] = {"PREFIX_ALPHA", "PREFIX_BRAVO"}
        # "PREFIX_XXXXX" shares the same token overlap (1/3) and same
        # character similarity with both candidates.
        result = _fuzzy_best_match("PREFIX_XXXXX", tied_codes, threshold=0.0)
        assert result is None, f"Expected None (tie), got '{result}'"

    def test_empty_code_returns_none(self) -> None:
        assert _fuzzy_best_match("", VALID_CODES) is None

    def test_empty_valid_codes_returns_none(self) -> None:
        assert _fuzzy_best_match("ESCAPE", set()) is None

    def test_custom_threshold(self) -> None:
        """Very high threshold should reject everything."""
        result = _fuzzy_best_match("PLACA_SOLAR_REG_OCULTO", VALID_CODES, threshold=0.99)
        assert result is None


# ---------------------------------------------------------------------------
# 2. normalize_element_code — integration: exact/plural still wins over fuzzy
# ---------------------------------------------------------------------------


class TestNormalizeElementCodeFuzzyIntegration:
    """Ensure fuzzy is only reached as a last resort."""

    def test_exact_match_wins_over_fuzzy(self) -> None:
        """(d) Exact match takes priority — fuzzy never reached."""
        matched, was_corrected = normalize_element_code("ESCAPE", VALID_CODES)
        assert matched == "ESCAPE"
        assert was_corrected is False

    def test_s_heuristic_wins_over_fuzzy(self) -> None:
        """(d) S-heuristic resolves ASIDERO → ASIDEROS before fuzzy."""
        matched, was_corrected = normalize_element_code("ASIDERO", VALID_CODES)
        assert matched == "ASIDEROS"
        assert was_corrected is True

    def test_case_insensitive_exact_wins(self) -> None:
        """Lowercase exact match is step 1, not fuzzy."""
        matched, was_corrected = normalize_element_code("escape", VALID_CODES)
        assert matched == "ESCAPE"
        assert was_corrected is True

    def test_fuzzy_fires_when_heuristics_fail(self) -> None:
        """Fuzzy match is used when exact + plural heuristics all miss."""
        matched, was_corrected = normalize_element_code(
            "PLACA_SOLAR_REG_OCULTO", VALID_CODES
        )
        assert matched == "PLACA_SOLAR_REGULADOR_INTERIOR"
        assert was_corrected is True

    def test_no_match_returns_none(self) -> None:
        """Completely invalid code returns None after all steps."""
        matched, was_corrected = normalize_element_code(
            "CODIGO_TOTALMENTE_INVENTADO", VALID_CODES
        )
        assert matched is None
        assert was_corrected is False

    def test_empty_code_returns_none(self) -> None:
        matched, was_corrected = normalize_element_code("", VALID_CODES)
        assert matched is None
        assert was_corrected is False

    def test_empty_valid_codes_returns_none(self) -> None:
        matched, was_corrected = normalize_element_code("ESCAPE", set())
        assert matched is None
        assert was_corrected is False

    def test_fuzzy_correction_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Fuzzy corrections emit a warning log."""
        import logging

        with caplog.at_level(logging.WARNING):
            normalize_element_code("PLACA_SOLAR_REG_OCULTO", VALID_CODES)
        assert any("Fuzzy-corrected" in msg for msg in caplog.messages)
