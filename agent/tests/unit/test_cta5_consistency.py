"""
Drift-guard tests for _CTA_5 constant (Batch B).

Covers AC-1.4: the CTA after image delivery must be open-ended (contains '?'
and is NOT a yes/no binary question).
Covers AC-4.3: pre_expediente_post_price.md CTA instruction must match the
constant and be open-ended.

Design: single source of truth is _CTA_5 in pre_expediente_mode.py.
These tests assert:
  1. The constant value is open-ended (contains '?' and ≠ old closed CTA).
  2. The constant value appears verbatim in pre_expediente_post_price.md
     (both the images_branch and natural_ctas sections).
  3. _enforce_cta5_if_needed appends exactly the constant value.

If anyone changes the constant, the prompt tests break.
If anyone changes the prompt, the constant-presence tests break.
This is the atomic drift guard (design Q5).
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_POST_PRICE_MD = (
    Path(__file__).parents[3]
    / "agent"
    / "prompts"
    / "modes"
    / "pre_expediente_post_price.md"
)

_PRICING_MD = (
    Path(__file__).parents[3]
    / "agent"
    / "prompts"
    / "modes"
    / "pre_expediente_pricing.md"
)


def _load_post_price() -> str:
    return _POST_PRICE_MD.read_text(encoding="utf-8")


def _load_pricing() -> str:
    return _PRICING_MD.read_text(encoding="utf-8")


def _get_cta5() -> str:
    from agent.modes.pre_expediente_mode import _CTA_5
    return _CTA_5


# ---------------------------------------------------------------------------
# B4 — Drift guard: constant appears verbatim in prompt markdown
# ---------------------------------------------------------------------------


class TestCta5ConstantInPrompt:
    """AC-4.3: the CTA literal in pre_expediente_post_price.md must match _CTA_5."""

    def test_post_price_md_contains_cta5_literal(self):
        """
        GIVEN the _CTA_5 constant from pre_expediente_mode.py
        WHEN pre_expediente_post_price.md is inspected
        THEN the constant's exact string MUST appear in the markdown.

        This ensures prompt and code stay in sync (drift guard per design Q5).
        """
        cta5 = _get_cta5()
        content = _load_post_price()
        assert cta5 in content, (
            f"_CTA_5 constant value {cta5!r} not found in pre_expediente_post_price.md. "
            "The prompt and constant have drifted. Update one to match the other. AC-4.3."
        )

    def test_post_price_md_contains_cta5_in_images_branch(self):
        """
        GIVEN the _CTA_5 constant
        WHEN the images_branch section of pre_expediente_post_price.md is inspected
        THEN the constant value MUST appear in that section.

        The images_branch is the primary CTA point (design Q5 says both
        images_branch line 37 and natural_ctas line 87 must match the constant).
        """
        cta5 = _get_cta5()
        content = _load_post_price()
        # Extract images_branch section
        images_branch_start = content.find("<images_branch>")
        images_branch_end = content.find("</images_branch>")
        assert images_branch_start != -1, "images_branch section not found in post_price.md"
        images_section = content[images_branch_start:images_branch_end]
        assert cta5 in images_section, (
            f"_CTA_5 value {cta5!r} not found in <images_branch> section of "
            "pre_expediente_post_price.md. The drift guard requires the constant "
            "to appear there. AC-4.3."
        )

    def test_post_price_md_contains_cta5_in_natural_ctas(self):
        """
        GIVEN the _CTA_5 constant
        WHEN the natural_ctas section of pre_expediente_post_price.md is inspected
        THEN the constant value MUST appear in that section.
        """
        cta5 = _get_cta5()
        content = _load_post_price()
        natural_ctas_start = content.find("<natural_ctas>")
        natural_ctas_end = content.find("</natural_ctas>")
        assert natural_ctas_start != -1, "natural_ctas section not found in post_price.md"
        natural_section = content[natural_ctas_start:natural_ctas_end]
        assert cta5 in natural_section, (
            f"_CTA_5 value {cta5!r} not found in <natural_ctas> section of "
            "pre_expediente_post_price.md. AC-4.3."
        )


# ---------------------------------------------------------------------------
# B5 — Open-ended CTA: must contain '?' and NOT be the old closed form
# ---------------------------------------------------------------------------


class TestCta5IsOpenEnded:
    """AC-1.4: the CTA must be open-ended (not a closed yes/no question)."""

    _OLD_CLOSED_CTA = "¿Empezamos con el expediente?"

    def test_cta5_contains_question_mark(self):
        """
        GIVEN the _CTA_5 constant
        WHEN its value is inspected
        THEN it MUST contain '?' — it is a question, not a statement.
        """
        cta5 = _get_cta5()
        assert "?" in cta5, (
            f"_CTA_5 {cta5!r} must contain '?' (it is a CTA question). AC-1.4."
        )

    def test_cta5_is_not_old_closed_form(self):
        """
        GIVEN the _CTA_5 constant
        WHEN compared to the old closed form '¿Empezamos con el expediente?'
        THEN it MUST NOT equal the old form — the spec requires an open-ended CTA.

        AC-1.4: CTA must NOT be a binary yes/no question.
        '¿Empezamos con el expediente?' was a closed binary question.
        """
        cta5 = _get_cta5()
        assert cta5 != self._OLD_CLOSED_CTA, (
            f"_CTA_5 is still the old closed form {cta5!r}. "
            "Update it to an open-ended CTA (e.g. '¿Abrimos expediente o tenés alguna duda?'). "
            "AC-1.4."
        )

    def test_cta5_enforce_function_appends_constant(self):
        """
        GIVEN a response that does NOT end with _CTA_5
        WHEN _enforce_cta5_if_needed is called with precio_comunicado=True and images sent
        THEN the returned string MUST end with exactly _CTA_5 (not some other CTA).

        This ensures the enforcement function uses the constant, not a hardcoded string.
        Triangulation: also verifies the function is a no-op when preconditions not met.
        """
        from agent.modes.pre_expediente_mode import _CTA_5, _enforce_cta5_if_needed

        # Preconditions met → CTA appended
        result = _enforce_cta5_if_needed(
            ai_response="Aquí tienes los ejemplos de fotos.",
            precio_comunicado=True,
            imagenes_enviadas_codigos=["asidero"],
        )
        assert result.endswith(_CTA_5), (
            f"_enforce_cta5_if_needed must append the current _CTA_5 constant {_CTA_5!r}. "
            "AC-1.4."
        )

        # Preconditions NOT met → no-op
        unchanged = _enforce_cta5_if_needed(
            ai_response="Precio: 350€.",
            precio_comunicado=False,
            imagenes_enviadas_codigos=[],
        )
        assert unchanged == "Precio: 350€.", (
            "_enforce_cta5_if_needed must be a no-op when preconditions not met. Triangulation."
        )


# ---------------------------------------------------------------------------
# A1 (RED→GREEN) — Drift guard: _CTA_5 appears in pricing.md <natural_ctas>
# ---------------------------------------------------------------------------


class TestCta5InPricingMd:
    """
    AC-A.1, AC-A.2: pre_expediente_pricing.md must use _CTA_5 in <natural_ctas>
    and must NOT contain the old closed CTA.

    Fix A drift guard — ensures the one-line edit in pricing.md is never regressed.
    """

    _OLD_CLOSED_CTA = "¿Empezamos con el expediente?"

    def test_pricing_md_no_old_cta(self):
        """
        GIVEN pre_expediente_pricing.md is read verbatim
        WHEN the file content is searched for the old closed CTA
        THEN the string MUST NOT be found anywhere in the file.

        AC-A.1. The old CTA '¿Empezamos con el expediente?' was replaced by _CTA_5.
        """
        content = _load_pricing()
        assert self._OLD_CLOSED_CTA not in content, (
            f"Old CTA {self._OLD_CLOSED_CTA!r} found in pre_expediente_pricing.md. "
            "This CTA was replaced by _CTA_5. Update line ~90 in pricing.md. AC-A.1."
        )

    def test_pricing_md_contains_cta5_in_natural_ctas(self):
        """
        GIVEN the _CTA_5 constant from pre_expediente_mode.py
        WHEN the <natural_ctas> section of pre_expediente_pricing.md is inspected
        THEN the exact value of _CTA_5 MUST appear in that section.

        AC-A.2. The 'Precio comunicado + imágenes enviadas' row must use _CTA_5.
        """
        cta5 = _get_cta5()
        content = _load_pricing()
        natural_ctas_start = content.find("<natural_ctas>")
        natural_ctas_end = content.find("</natural_ctas>")
        assert natural_ctas_start != -1, (
            "<natural_ctas> section not found in pre_expediente_pricing.md"
        )
        natural_section = content[natural_ctas_start:natural_ctas_end]
        assert cta5 in natural_section, (
            f"_CTA_5 value {cta5!r} not found in <natural_ctas> of pre_expediente_pricing.md. "
            "Update the 'Precio comunicado + imágenes enviadas' row to use _CTA_5. AC-A.2."
        )
