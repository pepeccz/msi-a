"""
Tests for CTA 5 enforcement when the CTA appears at a non-final position in the LLM response.

Bug: _CTA_5_EQUIVALENT_RE was anchored with a end-of-string anchor so it only matched when the CTA
was already at the end. If the LLM emitted CTA mid-body with trailing text, the regex
missed it and Case 1 appended a second CTA → double CTA emission.

Fix (AD-1 + AD-2): remove the end-of-string anchor so the regex matches at any position. The existing
prefix-slice in Case 2b already discards everything after match.start().

Phases:
  Phase 1 (RED)  — tests 1.1, 1.2, 1.3, 1.4
  Phase 3 (TRIANGULATE) — tests 3.1, 3.2, 3.3
"""

import pytest

from agent.modes.pre_expediente_mode import _CTA_5, _enforce_cta5_if_needed

IMAGES = ["ESCAPE"]


# ---------------------------------------------------------------------------
# Phase 1 — RED (must fail before AD-1 fix, pass after)
# ---------------------------------------------------------------------------


class TestCtaMidBodyWithTrailingSentence:
    """1.1 — CTA mid-body + trailing sentence → single canonical CTA at end."""

    def test_cta_mid_body_with_trailing_sentence(self):
        llm_text = (
            "Ya te he enviado las fotos de ejemplo. "
            "¿Abrimos expediente o tienes alguna duda? "
            "Cualquier cosa que necesites, aquí estoy."
        )
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=True, imagenes_enviadas_codigos=IMAGES)

        assert result.rstrip().endswith(_CTA_5), "Response must end with canonical CTA 5"
        assert result.count(_CTA_5) == 1, "CTA 5 must appear exactly once"

    def test_cta_mid_body_tuteo_with_trailing_sentence(self):
        """Tuteo variant mid-body + trailing text → normalized to voseo, single CTA."""
        llm_text = (
            "El presupuesto es 410€ +IVA. "
            "¿Abrimos expediente o tenés alguna duda? "
            "No dudes en consultarme."
        )
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=True, imagenes_enviadas_codigos=IMAGES)

        assert result.rstrip().endswith(_CTA_5)
        assert result.count(_CTA_5) == 1


class TestCtaMidBodyTrailingWhitespaceOnly:
    """1.2 — CTA mid-body + trailing newlines only → canonical CTA at end."""

    def test_cta_mid_body_trailing_newlines(self):
        llm_text = "¿Abrimos expediente o tienes alguna duda?\n\n\n"
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=True, imagenes_enviadas_codigos=IMAGES)

        assert result.rstrip().endswith(_CTA_5)
        assert result.count(_CTA_5) == 1

    def test_cta_mid_body_trailing_spaces(self):
        llm_text = "Ya tienes las fotos. ¿Abrimos expediente o tienes alguna duda?   "
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=True, imagenes_enviadas_codigos=IMAGES)

        assert result.rstrip().endswith(_CTA_5)
        assert result.count(_CTA_5) == 1


class TestRegressionCtaAtEndCanonical:
    """1.3 — CTA already at end → no mutation (regression guard)."""

    def test_cta_at_end_canonical_unchanged(self):
        llm_text = f"El presupuesto es 410€ +IVA. {_CTA_5}"
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=True, imagenes_enviadas_codigos=IMAGES)

        assert result.rstrip().endswith(_CTA_5)
        assert result.count(_CTA_5) == 1

    def test_cta_at_end_only_content(self):
        result = _enforce_cta5_if_needed(_CTA_5, precio_comunicado=True, imagenes_enviadas_codigos=IMAGES)

        assert result == _CTA_5


class TestRegressionCtaAtEndTuteoNormalized:
    """1.4 — tuteo at end → normalized to voseo (regression guard)."""

    def test_tuteo_at_end_normalized(self):
        llm_text = "Las fotos ya llegaron. ¿Abrimos expediente o tenés alguna duda?"
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=True, imagenes_enviadas_codigos=IMAGES)

        assert result.rstrip().endswith(_CTA_5)
        assert result.count(_CTA_5) == 1

    def test_tuteo_only_normalized(self):
        llm_text = "¿Abrimos expediente o tenés alguna duda?"
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=True, imagenes_enviadas_codigos=IMAGES)

        assert result == _CTA_5


# ---------------------------------------------------------------------------
# Phase 3 — TRIANGULATE edge cases
# ---------------------------------------------------------------------------


class TestNoCtaAppendsCanonical:
    """3.1 — no CTA in body → canonical appended with double newline."""

    def test_no_cta_appends_canonical(self):
        llm_text = "Te envié las fotos de ejemplo del catalizador."
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=True, imagenes_enviadas_codigos=IMAGES)

        assert result.endswith(f"\n\n{_CTA_5}")
        assert llm_text.strip() in result


class TestMultipleCtaOccurrences:
    """3.2 — two CTA equivalents in body → first occurrence wins, single CTA at end."""

    def test_multiple_cta_occurrences(self):
        llm_text = (
            "¿Abrimos expediente o tienes alguna duda? "
            "Como decía, ¿abrimos expediente o tienes alguna duda? Aquí estoy."
        )
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=True, imagenes_enviadas_codigos=IMAGES)

        assert result.rstrip().endswith(_CTA_5)
        assert result.count(_CTA_5) == 1


class TestOnlyCtaNoPrefixReturnedAsIs:
    """3.3 — message is CTA alone → returned as canonical (no prefix, no separator)."""

    def test_only_cta_exact_canonical(self):
        result = _enforce_cta5_if_needed(_CTA_5, precio_comunicado=True, imagenes_enviadas_codigos=IMAGES)

        assert result == _CTA_5

    def test_only_cta_tuteo_variant(self):
        result = _enforce_cta5_if_needed(
            "¿Abrimos expediente o tenés alguna duda?",
            precio_comunicado=True,
            imagenes_enviadas_codigos=IMAGES,
        )

        assert result == _CTA_5
