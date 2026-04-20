"""
Unit tests for kickoff_markers module.

Spec reference: KM-1-A, KM-1-B, KM-1-C, KM-1-D
  - KM-1-A: canonical particular phrase → positive match
  - KM-1-B: canonical professional phrase → positive match
  - KM-1-C: explanatory text → negative (false-positive guard)
  - KM-1-D: CTA 5 phrase → negative (CTA 5 is not a kickoff marker)

All tests are pure unit tests — no DB, no Redis, no LLM.
Tests verify is_kickoff_hallucination() and the underlying KICKOFF_MARKERS regex tuple.
"""

from __future__ import annotations

import pytest

from agent.prompts.kickoff_markers import (
    KICKOFF_MARKERS,
    KICKOFF_MARKER_SOURCES,
    is_kickoff_hallucination,
)


# ---------------------------------------------------------------------------
# B3-T1 — KM-1-A: Positive match — canonical "particular" phrase
# ---------------------------------------------------------------------------


class TestKickoffMarkerPositiveParticular:
    """KM-1-A: the canonical phrase used in the 'particular' client path matches."""

    def test_marker_matches_particular_template(self):
        """
        KM-1-A: 'Perfecto, empezamos con el expediente. Te voy a ir pidiendo
        todo paso a paso.' must be detected as a kickoff hallucination.

        RED: fails before kickoff_markers.py exists.
        """
        phrase = (
            "Perfecto, empezamos con el expediente. "
            "Te voy a ir pidiendo todo paso a paso."
        )
        result = is_kickoff_hallucination(phrase)
        assert result is True, (
            f"KM-1-A: is_kickoff_hallucination must return True for the canonical "
            f"particular phrase. Got: {result!r}"
        )

    def test_marker_matches_particular_template_at_eos(self):
        """
        KM-1-A triangulation: phrase appears at the end of a longer response (EOS signal).
        is_kickoff_hallucination searches the last 200 chars — phrase must still match.
        """
        preamble = "Claro, el presupuesto para el escape es de 320€ +IVA con el ITV incluido. "
        phrase = "Perfecto, empezamos con el expediente. Te voy a ir pidiendo todo paso a paso."
        full_response = preamble + phrase
        result = is_kickoff_hallucination(full_response)
        assert result is True, (
            f"KM-1-A (EOS): phrase at end of response must still be detected. Got: {result!r}"
        )


# ---------------------------------------------------------------------------
# B3-T2 — KM-1-B: Positive match — canonical "professional" phrase
# ---------------------------------------------------------------------------


class TestKickoffMarkerPositiveProfessional:
    """KM-1-B: the canonical phrase used in the 'professional' client path matches."""

    def test_marker_matches_professional_template(self):
        """
        KM-1-B: 'Expediente abierto. Te pido la documentación a continuación.'
        must be detected as a kickoff hallucination.

        RED: fails before kickoff_markers.py exists.
        """
        phrase = "Expediente abierto. Te pido la documentación a continuación."
        result = is_kickoff_hallucination(phrase)
        assert result is True, (
            f"KM-1-B: is_kickoff_hallucination must return True for the canonical "
            f"professional phrase. Got: {result!r}"
        )

    def test_marker_matches_professional_variant_arrancamos(self):
        """
        KM-1-B triangulation: variant with 'arrancamos' verb — still a kickoff signal.
        """
        phrase = "Perfecto, arrancamos con el expediente. Te pido todo lo necesario."
        result = is_kickoff_hallucination(phrase)
        assert result is True, (
            f"KM-1-B (arrancamos): verb variant must be detected. Got: {result!r}"
        )


# ---------------------------------------------------------------------------
# B3-T3 — KM-1-C: Negative match — explanatory educational text
# ---------------------------------------------------------------------------


class TestKickoffMarkerNegativeEducational:
    """KM-1-C: explanatory text about the expediente must NOT trigger a match."""

    def test_marker_does_not_match_educational_text(self):
        """
        KM-1-C: 'Abrir el expediente significa empezar a recopilar toda tu
        documentación de homologación.' is NOT a kickoff — it is explanatory.

        The regex must have word-boundary / anchor rules that prevent false triggers
        on words like 'empezar', 'abrir', 'significa'.

        RED: fails before kickoff_markers.py exists.
        """
        text = (
            "Abrir el expediente significa empezar a recopilar toda tu "
            "documentación de homologación."
        )
        result = is_kickoff_hallucination(text)
        assert result is False, (
            f"KM-1-C: is_kickoff_hallucination must return False for explanatory text "
            f"about the expediente process. Got: {result!r}. "
            f"Check regex boundaries to avoid false positives."
        )

    def test_marker_does_not_match_future_tense_question(self):
        """
        KM-1-C triangulation: 'Si decides proceder, empezaríamos con el expediente.'
        — conditional, not a real kickoff transition.
        """
        text = "Si decides proceder, empezaríamos con el expediente de homologación."
        result = is_kickoff_hallucination(text)
        assert result is False, (
            f"KM-1-C (conditional): future/conditional phrasing must NOT be detected "
            f"as a kickoff. Got: {result!r}"
        )


# ---------------------------------------------------------------------------
# B3-T4 — KM-1-D: Negative match — CTA 5 phrase is NOT a kickoff
# ---------------------------------------------------------------------------


class TestKickoffMarkerNegativeCta5:
    """KM-1-D: CTA 5 literal must NOT be detected as a kickoff hallucination."""

    def test_marker_does_not_match_cta5_phrase(self):
        """
        KM-1-D: '¿Abrimos expediente o tienes alguna duda?' is CTA 5 — an
        invitation to open the expediente, NOT the kickoff phrase that signals
        the LLM has already decided to transition.

        RED: fails before kickoff_markers.py exists.
        """
        cta5_phrase = "¿Abrimos expediente o tienes alguna duda?"
        result = is_kickoff_hallucination(cta5_phrase)
        assert result is False, (
            f"KM-1-D: is_kickoff_hallucination must return False for CTA 5 literal. "
            f"Got: {result!r}. "
            f"CTA 5 is a question/invitation, not a kickoff declaration."
        )

    def test_marker_does_not_match_empty_string(self):
        """
        KM-1-D edge: empty string must return False, not crash.
        """
        result = is_kickoff_hallucination("")
        assert result is False, (
            f"KM-1-D (empty): is_kickoff_hallucination('') must return False. "
            f"Got: {result!r}"
        )

    def test_marker_does_not_match_cta5_tuteo_variant(self):
        """
        KM-1-D triangulation: tuteo CTA 5 variant — still not a kickoff.
        """
        cta5_tuteo = "¿Abrimos expediente o tienes alguna duda más?"
        result = is_kickoff_hallucination(cta5_tuteo)
        assert result is False, (
            f"KM-1-D (tuteo CTA5): tuteo variant of CTA 5 must also return False. "
            f"Got: {result!r}"
        )


# ---------------------------------------------------------------------------
# Module export sanity checks
# ---------------------------------------------------------------------------


class TestKickoffMarkersModuleExports:
    """Verify module exports are correctly shaped (structural checks)."""

    def test_kickoff_marker_sources_is_nonempty_tuple(self):
        """KICKOFF_MARKER_SOURCES must be a non-empty tuple of strings."""
        assert isinstance(KICKOFF_MARKER_SOURCES, (tuple, list)), (
            "KICKOFF_MARKER_SOURCES must be a tuple or list"
        )
        assert len(KICKOFF_MARKER_SOURCES) > 0, (
            "KICKOFF_MARKER_SOURCES must contain at least one pattern"
        )

    def test_kickoff_markers_are_compiled_patterns(self):
        """KICKOFF_MARKERS must be a non-empty tuple of compiled re.Pattern objects."""
        import re

        assert isinstance(KICKOFF_MARKERS, (tuple, list)), (
            "KICKOFF_MARKERS must be a tuple or list"
        )
        assert len(KICKOFF_MARKERS) > 0, (
            "KICKOFF_MARKERS must contain at least one compiled pattern"
        )
        for pat in KICKOFF_MARKERS:
            assert isinstance(pat, re.Pattern), (
                f"Each element in KICKOFF_MARKERS must be re.Pattern, got {type(pat)!r}"
            )
