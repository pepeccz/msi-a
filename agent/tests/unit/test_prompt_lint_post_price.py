"""
Unit tests for C3 — P2/P4: post_price.md boundary rule + CTA_4 reword.

Spec: R4 — Explicit POST_PRICE Boundary Rule in Prompt.
Spec: R5 — CTA_4 Reword — No Documentation Invitation.

AC-4.1: post_price.md contains anti-narration rule within first 15 lines of <post_price>.
AC-4.2: Rule does not contain "success=true".
AC-5.1: CTA_4 does not contain "fotos que necesitaremos".
AC-5.2: CTA_4 presents binary choice ending with "?".

RED before C3:
- post_price.md does NOT have a <phase_boundary> block at the top.
- CTA_4 currently contains "fotos que necesitaremos".
"""
from __future__ import annotations

from pathlib import Path

import pytest


_PROMPT_DIR = Path(__file__).parents[2] / "prompts" / "modes"
_POST_PRICE_PATH = _PROMPT_DIR / "pre_expediente_post_price.md"


# ---------------------------------------------------------------------------
# AC-4.1 — anti-narration rule present in first 15 lines of <post_price>
# ---------------------------------------------------------------------------

class TestPostPriceBoundaryRule:
    """pre_expediente_post_price.md must have an explicit anti-narration rule."""

    def test_file_exists(self):
        assert _POST_PRICE_PATH.exists(), (
            f"pre_expediente_post_price.md not found at {_POST_PRICE_PATH}"
        )

    def test_fase_post_price_marker_present(self):
        """The boundary block must contain 'FASE POST_PRICE' in the first 15 lines."""
        content = _POST_PRICE_PATH.read_text(encoding="utf-8")
        lines = content.splitlines()
        first_15 = "\n".join(lines[:15])
        assert "FASE POST_PRICE" in first_15, (
            f"'FASE POST_PRICE' not found in first 15 lines. First 15 lines:\n{first_15}"
        )

    def test_prohibido_marker_present(self):
        """The boundary block must contain an explicit prohibition keyword."""
        content = _POST_PRICE_PATH.read_text(encoding="utf-8")
        lines = content.splitlines()
        first_15 = "\n".join(lines[:15])
        assert "PROHIBIDO" in first_15.upper(), (
            f"No PROHIBIDO keyword in first 15 lines. First 15 lines:\n{first_15}"
        )

    # AC-4.2 — no "success=true" jargon
    def test_no_success_true_jargon(self):
        """Boundary rule must NOT contain 'success=true' jargon."""
        content = _POST_PRICE_PATH.read_text(encoding="utf-8")
        # Check first 30 lines for technical jargon
        first_30 = "\n".join(content.splitlines()[:30])
        assert "success=true" not in first_30.lower(), (
            f"'success=true' jargon found in first 30 lines of post_price.md"
        )


# ---------------------------------------------------------------------------
# AC-5.1 + AC-5.2 — CTA_4 reword
# ---------------------------------------------------------------------------

class TestCta4Reword:
    """CTA_4 must not contain documentation invitation and must be binary."""

    def test_cta4_no_fotos_que_necesitaremos(self):
        from agent.prompts.ctas_catalog import CTAS

        cta4 = CTAS[4]
        assert "necesitaremos" not in cta4, (
            f"CTA_4 must NOT contain 'necesitaremos'. Got: {cta4!r}"
        )
        assert "fotos que" not in cta4.lower(), (
            f"CTA_4 must NOT contain 'fotos que'. Got: {cta4!r}"
        )

    def test_cta4_binary_choice(self):
        """CTA_4 must present two actionable options and end with '?'."""
        from agent.prompts.ctas_catalog import CTAS

        cta4 = CTAS[4]
        # Must end with question mark
        assert cta4.strip().endswith("?"), (
            f"CTA_4 must end with '?'. Got: {cta4!r}"
        )
        # Must contain both "fotos" and "expediente" (binary choice)
        assert "fotos" in cta4.lower(), (
            f"CTA_4 must contain 'fotos'. Got: {cta4!r}"
        )
        assert "expediente" in cta4.lower(), (
            f"CTA_4 must contain 'expediente'. Got: {cta4!r}"
        )

    def test_cta4_exact_value(self):
        """CTA_4 must match the design-specified literal."""
        from agent.prompts.ctas_catalog import CTAS

        expected = "¿Te enseño ejemplos de fotos o abrimos el expediente?"
        assert CTAS[4] == expected, (
            f"CTA_4 mismatch. Expected {expected!r}, got {CTAS[4]!r}"
        )
