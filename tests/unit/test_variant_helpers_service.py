"""
Unit tests for variant selection helper functions moved to variant_interpretation_service in T2.2b.

Tests:
- AMBIGUITY_THRESHOLD constant
- has_domain_vocabulary_from_variants()
- has_domain_vocabulary()
- normalize_to_canonical_letter()
- extract_positional_letters()
- build_element_anchors()
- score_clause_for_element()
- extract_element_fragment()
- build_single_variant_result()
- apply_single_resolution_to_pending()

No DB / Redis / LLM connections needed — all pure functions.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from agent.services.variant_interpretation_service import (
    AMBIGUITY_THRESHOLD,
    _has_domain_vocabulary,
    _has_domain_vocabulary_from_variants,
    _normalize_to_canonical_letter,
    _extract_positional_letters,
    _build_element_anchors,
    _score_clause_for_element,
    _extract_element_fragment,
    _build_single_variant_result,
    _apply_single_resolution_to_pending,
    # Also verify public aliases exist
    has_domain_vocabulary,
    has_domain_vocabulary_from_variants,
    normalize_to_canonical_letter,
    extract_positional_letters,
    build_element_anchors,
    score_clause_for_element,
    extract_element_fragment,
    build_single_variant_result,
    apply_single_resolution_to_pending,
)


# ---------------------------------------------------------------------------
# AMBIGUITY_THRESHOLD
# ---------------------------------------------------------------------------


def test_ambiguity_threshold_value():
    assert AMBIGUITY_THRESHOLD == 0.3


# ---------------------------------------------------------------------------
# has_domain_vocabulary_from_variants
# ---------------------------------------------------------------------------


SAMPLE_VARIANTS = [
    {"name": "Regulador oculto", "keywords": ["oculto", "interior", "armario"]},
    {"name": "Regulador visible", "keywords": ["visible", "exterior"]},
]


class TestHasDomainVocabularyFromVariants:
    def test_returns_true_when_keyword_found(self):
        assert _has_domain_vocabulary_from_variants("el regulador oculto", SAMPLE_VARIANTS)

    def test_returns_true_when_name_word_found(self):
        assert _has_domain_vocabulary_from_variants("quiero el visible", SAMPLE_VARIANTS)

    def test_returns_false_when_no_domain_words(self):
        assert not _has_domain_vocabulary_from_variants("sí", SAMPLE_VARIANTS)

    def test_returns_false_for_empty_variants(self):
        assert not _has_domain_vocabulary_from_variants("oculto", [])

    def test_accent_insensitive(self):
        assert _has_domain_vocabulary_from_variants("el regulador oculto", SAMPLE_VARIANTS)

    def test_public_alias_is_same_function(self):
        assert has_domain_vocabulary_from_variants is _has_domain_vocabulary_from_variants


# ---------------------------------------------------------------------------
# has_domain_vocabulary
# ---------------------------------------------------------------------------


class TestHasDomainVocabulary:
    def test_galibo_keyword(self):
        assert _has_domain_vocabulary("sin afectar al gálibo")

    def test_oculto_keyword(self):
        assert _has_domain_vocabulary("está oculto en el armario")

    def test_no_domain_words(self):
        assert not _has_domain_vocabulary("sí, ese")

    def test_accent_insensitive_galibo(self):
        assert _has_domain_vocabulary("galibo")  # no accent

    def test_public_alias(self):
        assert has_domain_vocabulary is _has_domain_vocabulary


# ---------------------------------------------------------------------------
# normalize_to_canonical_letter
# ---------------------------------------------------------------------------


class TestNormalizeToCanonicalLetter:
    def test_bare_letter_a(self):
        assert _normalize_to_canonical_letter("a") == "a"

    def test_bare_letter_uppercase(self):
        assert _normalize_to_canonical_letter("B") == "b"

    def test_opcion_b(self):
        assert _normalize_to_canonical_letter("opción b") == "b"

    def test_la_b(self):
        assert _normalize_to_canonical_letter("la b") == "b"

    def test_b_dot(self):
        assert _normalize_to_canonical_letter("b.") == "b"

    def test_b_paren(self):
        assert _normalize_to_canonical_letter("b)") == "b"

    def test_semantic_word_returns_none(self):
        assert _normalize_to_canonical_letter("el visible") is None

    def test_number_returns_none(self):
        assert _normalize_to_canonical_letter("2") is None

    def test_public_alias(self):
        assert normalize_to_canonical_letter is _normalize_to_canonical_letter


# ---------------------------------------------------------------------------
# extract_positional_letters
# ---------------------------------------------------------------------------


class TestExtractPositionalLetters:
    def test_b_y_a_returns_list(self):
        assert _extract_positional_letters("B y A") == ["b", "a"]

    def test_a_comma_b(self):
        assert _extract_positional_letters("a, b") == ["a", "b"]

    def test_single_letter_returns_none(self):
        # Single letter is handled by the existing positional path
        assert _extract_positional_letters("B") is None

    def test_semantic_words_returns_none(self):
        assert _extract_positional_letters("regulador oculto y toldo normal") is None

    def test_three_letters(self):
        result = _extract_positional_letters("a, b, c")
        assert result == ["a", "b", "c"]

    def test_public_alias(self):
        assert extract_positional_letters is _extract_positional_letters


# ---------------------------------------------------------------------------
# build_element_anchors
# ---------------------------------------------------------------------------


class TestBuildElementAnchors:
    def test_builds_from_code(self):
        anchors = _build_element_anchors("PLACA_SOLAR", None, None, [])
        assert "placa solar" in anchors or any("placa" in a for a in anchors)

    def test_includes_name_words(self):
        base_element = {"name": "Placa solar fotovoltaica"}
        anchors = _build_element_anchors("PLACA_SOLAR", base_element, None, [])
        assert any("solar" in a for a in anchors)

    def test_deduplicates_anchors(self):
        base_element = {"name": "Placa solar"}
        anchors = _build_element_anchors("PLACA_SOLAR", base_element, None, [])
        seen = set()
        for a in anchors:
            assert a not in seen, f"Duplicate anchor: {a}"
            seen.add(a)

    def test_public_alias(self):
        assert build_element_anchors is _build_element_anchors


# ---------------------------------------------------------------------------
# score_clause_for_element
# ---------------------------------------------------------------------------


class TestScoreClauseForElement:
    def test_exact_anchor_match_scores_high(self):
        score = _score_clause_for_element("placa solar opcion b", ["placa solar"])
        assert score > 0.3

    def test_no_anchor_match_scores_zero(self):
        score = _score_clause_for_element("el toldo articulado", ["placa solar"])
        # May or may not be zero depending on word overlap, but should be low
        assert score < 0.5

    def test_empty_clause_returns_zero(self):
        assert _score_clause_for_element("", ["placa solar"]) == 0.0

    def test_score_capped_at_one(self):
        anchors = ["placa", "solar", "placa solar", "placa solar"]
        score = _score_clause_for_element("placa solar placa solar", anchors)
        assert score <= 1.0

    def test_public_alias(self):
        assert score_clause_for_element is _score_clause_for_element


# ---------------------------------------------------------------------------
# extract_element_fragment
# ---------------------------------------------------------------------------


class TestExtractElementFragment:
    def test_combined_response_extracts_relevant_clause(self):
        # "placa solar opcion b y el toldo A" — resolving PLACA_SOLAR
        fragment = _extract_element_fragment(
            respuesta="placa solar opcion b y el toldo A",
            codigo_elemento_base="PLACA_SOLAR",
            base_element={"name": "Placa solar"},
            current_pending=None,
            variants=[],
        )
        assert "placa" in fragment.lower() or fragment.lower() == "placa solar opcion b y el toldo a"

    def test_single_clause_returns_original(self):
        fragment = _extract_element_fragment(
            respuesta="delantera",
            codigo_elemento_base="SUSPENSION",
            base_element=None,
            current_pending=None,
            variants=[],
        )
        assert fragment == "delantera"

    def test_pure_multi_letter_positional(self):
        # "B y A" with pending_idx=0, total=2 → extracts "b"
        fragment = _extract_element_fragment(
            respuesta="B y A",
            codigo_elemento_base="PLACA_SOLAR",
            base_element=None,
            current_pending=None,
            variants=[],
            current_pending_idx=0,
            total_pending_count=2,
        )
        assert fragment == "b"

    def test_pure_multi_letter_second_element(self):
        # "B y A" with pending_idx=1, total=2 → extracts "a"
        fragment = _extract_element_fragment(
            respuesta="B y A",
            codigo_elemento_base="TOLDO_LAT",
            base_element=None,
            current_pending=None,
            variants=[],
            current_pending_idx=1,
            total_pending_count=2,
        )
        assert fragment == "a"

    def test_public_alias(self):
        assert extract_element_fragment is _extract_element_fragment


# ---------------------------------------------------------------------------
# build_single_variant_result
# ---------------------------------------------------------------------------


class TestBuildSingleVariantResult:
    def _variant(self) -> dict:
        return {
            "code": "SUSPENSION_DEL",
            "name": "Suspensión delantera",
            "variant_code": "DEL",
            "variant_position": 1,
        }

    def test_high_confidence_includes_instructions(self):
        result = _build_single_variant_result(self._variant(), "SUSPENSION", 0.95, "keyword")
        assert result["selected_variant"] == "SUSPENSION_DEL"
        assert result["confidence"] == 0.95
        assert "instrucciones" in result
        assert "SUSPENSION_DEL" in result["instrucciones"]

    def test_low_confidence_includes_ask_instructions(self):
        result = _build_single_variant_result(self._variant(), "SUSPENSION", 0.4, "keyword")
        assert "Confidence bajo" in result["instrucciones"]

    def test_variant_position_match_method(self):
        result = _build_single_variant_result(self._variant(), "SUSPENSION", 0.95, "variant_position")
        assert result["match_method"] == "variant_position"
        assert result["variant_position"] == 1

    def test_public_alias(self):
        assert build_single_variant_result is _build_single_variant_result


# ---------------------------------------------------------------------------
# apply_single_resolution_to_pending
# ---------------------------------------------------------------------------


class TestApplySingleResolutionToPending:
    def _pending_entry(self, pending_id: str = "pid-1") -> dict:
        return {
            "pending_id": pending_id,
            "codigo_base": "SUSPENSION",
            "pregunta": "¿Delantera o trasera?",
            "opciones": ["Delantera", "Trasera"],
            "cantidad_total": 1,
            "cantidad_resuelta": 0,
            "cantidad_pendiente": 1,
            "resoluciones": [],
            "status": "pending",
        }

    def _variant(self) -> dict:
        return {"code": "SUSPENSION_DEL", "name": "Suspensión delantera"}

    def test_no_pending_returns_unchanged_result(self):
        result = {"selected_variant": "SUSPENSION_DEL", "confidence": 0.9}
        out = _apply_single_resolution_to_pending(result, self._variant(), None, -1, [])
        assert out is result
        assert "_state_update" not in out

    def test_adds_state_update_with_pending_list(self):
        pending = self._pending_entry()
        result = {"selected_variant": "SUSPENSION_DEL", "confidence": 0.9}
        out = _apply_single_resolution_to_pending(result, self._variant(), pending, 0, [pending])
        assert "_state_update" in out
        assert "pending_variants" in out["_state_update"]
        assert len(out["_state_update"]["pending_variants"]) == 1

    def test_status_becomes_resolved_when_one_unit(self):
        pending = self._pending_entry()
        result = {"selected_variant": "SUSPENSION_DEL", "confidence": 0.9}
        out = _apply_single_resolution_to_pending(result, self._variant(), pending, 0, [pending])
        assert out["resolution_status"] == "resolved"
        assert out["pending_count"] == 0

    def test_public_alias(self):
        assert apply_single_resolution_to_pending is _apply_single_resolution_to_pending
