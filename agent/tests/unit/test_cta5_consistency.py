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


_CTA5_PLACEHOLDER = "{{CTA_5}}"


def _content_has_cta5(content: str) -> bool:
    """Return True if content contains _CTA_5 literal OR its canonical {{CTA_5}} placeholder.

    Since the centralize-pre-expediente-prompts change, prompt files use {{CTA_5}}
    instead of the literal string. The loader substitutes the placeholder at load time.
    Both forms are valid — the drift guard is that CTA_5 is referenced somehow.
    """
    cta5 = _get_cta5()
    return cta5 in content or _CTA5_PLACEHOLDER in content


class TestCta5ConstantInPrompt:
    """AC-4.3: the CTA literal in pre_expediente_post_price.md must reference _CTA_5.

    Updated for centralize-pre-expediente-prompts: prompt files now use {{CTA_5}} placeholder
    (substituted by loader at runtime). Both the literal AND the placeholder are accepted.
    """

    def test_post_price_md_contains_cta5_literal(self):
        """
        GIVEN the _CTA_5 constant from pre_expediente_mode.py
        WHEN pre_expediente_post_price.md is inspected
        THEN either the literal string OR {{CTA_5}} placeholder MUST appear.

        Since centralize-pre-expediente-prompts, literal CTAs are replaced with
        {{CTA_5}} placeholders (substituted by loader at runtime). AC-4.3.
        """
        content = _load_post_price()
        assert _content_has_cta5(content), (
            f"Neither _CTA_5 literal nor {{{{CTA_5}}}} placeholder found in pre_expediente_post_price.md. "
            "The prompt and constant have drifted. Update one to match the other. AC-4.3."
        )

    def test_post_price_md_contains_cta5_in_images_branch(self):
        """
        GIVEN the _CTA_5 constant
        WHEN the images_branch section of pre_expediente_post_price.md is inspected
        THEN either the literal value OR {{CTA_5}} placeholder MUST appear in that section.

        The images_branch is the primary CTA point. AC-4.3.
        """
        content = _load_post_price()
        # Extract images_branch section
        images_branch_start = content.find("<images_branch>")
        images_branch_end = content.find("</images_branch>")
        assert images_branch_start != -1, "images_branch section not found in post_price.md"
        images_section = content[images_branch_start:images_branch_end]
        assert _content_has_cta5(images_section), (
            f"Neither _CTA_5 literal nor {{{{CTA_5}}}} placeholder found in <images_branch> section of "
            "pre_expediente_post_price.md. The drift guard requires CTA_5 to appear there. AC-4.3."
        )

    def test_post_price_md_contains_cta5_in_natural_ctas(self):
        """
        GIVEN the _CTA_5 constant
        WHEN the natural_ctas section of pre_expediente_post_price.md is inspected
        THEN either the literal value OR {{CTA_5}} placeholder MUST appear in that section.
        """
        content = _load_post_price()
        natural_ctas_start = content.find("<natural_ctas>")
        natural_ctas_end = content.find("</natural_ctas>")
        assert natural_ctas_start != -1, "natural_ctas section not found in post_price.md"
        natural_section = content[natural_ctas_start:natural_ctas_end]
        assert _content_has_cta5(natural_section), (
            f"Neither _CTA_5 literal nor {{{{CTA_5}}}} placeholder found in <natural_ctas> of "
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
            "Update it to an open-ended CTA (e.g. '¿Abrimos expediente o tienes alguna duda?'). "
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
# Fix A — Tuteo/voseo drift tolerance (regression guard for double-CTA bug)
# ---------------------------------------------------------------------------


class TestCta5TuteoVoseoDrift:
    """
    Regression guard: when the LLM drifts to tuteo ("tienes") instead of voseo
    ("tenés"), _enforce_cta5_if_needed must NOT duplicate the CTA. It should
    recognise the semantically equivalent tail and normalise it to the canonical
    voseo form.

    Bug that motivated this: conv=1 @ 2026-04-19 23:15 — LLM produced
    '...¿Abrimos expediente o tienes alguna duda?' (tuteo, 77 chars), the
    strict-endswith check failed, and the enforce function appended a second
    canonical CTA → user received two separate messages in WhatsApp.
    """

    def test_tuteo_tail_is_normalised_not_duplicated(self):
        """
        GIVEN a response ending with the tuteo form '¿Abrimos expediente o tienes alguna duda?'
        WHEN _enforce_cta5_if_needed is called with preconditions met
        THEN the canonical CTA MUST appear exactly once (the tuteo tail is replaced,
             NOT the canonical CTA appended after it).
        """
        from agent.modes.pre_expediente_mode import _CTA_5, _enforce_cta5_if_needed

        tuteo_response = (
            "No he podido enviarte los ejemplos. "
            "¿Abrimos expediente o tienes alguna duda?"
        )
        result = _enforce_cta5_if_needed(
            ai_response=tuteo_response,
            precio_comunicado=True,
            imagenes_enviadas_codigos=["placa_solar"],
        )

        # Canonical CTA appears exactly once — no duplication
        assert result.count(_CTA_5) == 1, (
            f"Expected exactly 1 occurrence of _CTA_5, got {result.count(_CTA_5)}. "
            f"Result was: {result!r}. The tuteo variant must be normalised, not duplicated."
        )
        # The tuteo phrasing must NOT appear more than once (not duplicated alongside the canonical CTA).
        # Note: _CTA_5 itself contains "tienes alguna duda", so we check the count of the full
        # canonical phrase, not the substring.
        assert result.count("tienes alguna duda") == 1, (
            f"'tienes alguna duda' must appear exactly once (from _CTA_5 itself). "
            f"If it appears twice, the tuteo tail was duplicated. Result: {result!r}"
        )
        # And the response ends with the canonical CTA
        assert result.endswith(_CTA_5), (
            f"Response must end with canonical _CTA_5. Got: {result!r}"
        )

    def test_canonical_voseo_tail_is_passthrough(self):
        """
        GIVEN a response already ending with the canonical _CTA_5
        WHEN _enforce_cta5_if_needed is called with preconditions met
        THEN the function is a no-op (CTA not duplicated).
        """
        from agent.modes.pre_expediente_mode import _CTA_5, _enforce_cta5_if_needed

        already_canonical = f"Listo. {_CTA_5}"
        result = _enforce_cta5_if_needed(
            ai_response=already_canonical,
            precio_comunicado=True,
            imagenes_enviadas_codigos=["placa_solar"],
        )
        assert result == already_canonical, (
            f"Passthrough expected when response already ends with _CTA_5. Got: {result!r}"
        )

    def test_tuteo_only_response_normalised_to_voseo_alone(self):
        """
        GIVEN a response that IS only the tuteo CTA (no preceding text)
        WHEN _enforce_cta5_if_needed is called with preconditions met
        THEN the result is exactly the canonical _CTA_5 (no leading newlines, no duplication).
        """
        from agent.modes.pre_expediente_mode import _CTA_5, _enforce_cta5_if_needed

        result = _enforce_cta5_if_needed(
            ai_response="¿Abrimos expediente o tienes alguna duda?",
            precio_comunicado=True,
            imagenes_enviadas_codigos=["placa_solar"],
        )
        assert result == _CTA_5, (
            f"Tuteo-only response must be normalised to bare _CTA_5. Got: {result!r}"
        )


# ---------------------------------------------------------------------------
# Fix B — success=false branch must NOT contain literal CTA combo
# ---------------------------------------------------------------------------


class TestSuccessFalseBranchHasNoCtaLiteral:
    """
    Fix B drift guard: the success=false instruction line in
    pre_expediente_post_price.md must NOT embed the canonical CTA literal
    alongside the failure phrase. Motivation: the LLM copied the combo verbatim
    (alucinating the wrong branch), producing 'No he podido enviarte los
    ejemplos. ¿Abrimos expediente o tienes alguna duda?' — the CTA is added by
    _enforce_cta5_if_needed, not by the LLM.
    """

    _BAD_COMBO = (
        'success=false → "No he podido enviarte los ejemplos. '
        '¿Abrimos expediente o tienes alguna duda?"'
    )

    def test_success_false_line_has_no_cta_combo(self):
        content = _load_post_price()
        assert self._BAD_COMBO not in content, (
            "The success=false branch must not embed the canonical CTA literal "
            "combined with the failure phrase — the LLM copies combos verbatim. "
            "Let _enforce_cta5_if_needed append the CTA automatically."
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
        assert _content_has_cta5(natural_section), (
            f"Neither _CTA_5 literal nor {{{{CTA_5}}}} placeholder found in <natural_ctas> of "
            "pre_expediente_pricing.md. The 'Precio comunicado + imágenes enviadas' row must "
            "reference CTA_5 (literal or {{{{CTA_5}}}} placeholder). AC-A.2."
        )
