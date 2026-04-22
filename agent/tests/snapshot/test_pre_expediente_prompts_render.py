"""
Snapshot tests for PRE_EXPEDIENTE prompt files (Batch B).

Covers AC-4.2: pre_expediente_post_price.md contains explicit no-repeat rule.
Covers AC-4.3: CTA instruction in prompt matches _CTA_5 constant.

These tests read the rendered markdown content and assert structural invariants.
They are prompt-snapshot tests: they fail when the prompt drifts from the spec.

Design: pure file-content assertions. No mocks, no async. Acts as living spec.
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


def _load_post_price() -> str:
    return _POST_PRICE_MD.read_text(encoding="utf-8")


def _get_cta5() -> str:
    from agent.modes.pre_expediente_mode import _CTA_5
    return _CTA_5


# ---------------------------------------------------------------------------
# AC-4.2 — No-repeat rule explicitly present in POST_PRICE prompt
# ---------------------------------------------------------------------------


class TestNoRepeatRuleInPostPrice:
    """AC-4.2: post_price prompt must contain explicit no-repeat instruction."""

    def test_prompt_contains_no_repeat_for_price(self):
        """
        GIVEN the pre_expediente_post_price.md markdown
        WHEN inspected for a no-repeat instruction for price
        THEN the file MUST contain a rule forbidding price repetition.
        """
        content = _load_post_price()
        has_no_repeat_price = any(
            phrase in content.lower()
            for phrase in [
                "no repitas precio",
                "no lo repitas",
                "no repetir",
                "precio ya comunicado",
                "no vuelvas a comunicar",
            ]
        )
        assert has_no_repeat_price, (
            "pre_expediente_post_price.md must contain an explicit no-repeat rule for price. "
            "AC-4.2."
        )

    def test_prompt_contains_no_repeat_for_docs_and_warnings(self):
        """
        GIVEN the pre_expediente_post_price.md markdown
        WHEN inspected for a no-repeat instruction covering docs and warnings
        THEN the file MUST contain a rule covering documents or warnings repetition.
        """
        content = _load_post_price()
        has_no_repeat_docs_or_warnings = any(
            phrase in content.lower()
            for phrase in [
                "advertencias",
                "documentos",
                "documentación",
                "lista de doc",
                "no repitas",
                "no vuelvas",
            ]
        )
        assert has_no_repeat_docs_or_warnings, (
            "pre_expediente_post_price.md must reference docs/warnings in its no-repeat rule. "
            "AC-4.2."
        )

    def test_no_repeat_rule_covers_all_three_elements(self):
        """
        GIVEN the pre_expediente_post_price.md markdown
        WHEN the images_branch section is inspected
        THEN it MUST reference price, docs (documentos/lista), AND warnings (advertencias)
        in a no-repeat context.

        This is the strongest form of AC-4.2: all three must be covered.
        """
        content = _load_post_price()
        images_start = content.find("<images_branch>")
        images_end = content.find("</images_branch>")
        assert images_start != -1, "<images_branch> not found in post_price.md"
        images_section = content[images_start:images_end].lower()

        # Check price no-repeat
        assert any(
            p in images_section for p in ["precio", "price"]
        ), "images_branch must reference price in no-repeat rule. AC-4.2."

        # Check docs no-repeat
        assert any(
            p in images_section for p in ["documentos", "lista de doc", "documentación", "lista"]
        ), "images_branch must reference docs in no-repeat rule. AC-4.2."

        # Check warnings no-repeat
        assert any(
            p in images_section for p in ["advertencias", "warnings"]
        ), "images_branch must reference warnings in no-repeat rule. AC-4.2."


# ---------------------------------------------------------------------------
# AC-4.3 — CTA instruction matches _CTA_5 constant
# ---------------------------------------------------------------------------


class TestCtaMatchesConstant:
    """AC-4.3: the CTA in the prompt must match the _CTA_5 constant exactly."""

    def test_images_branch_cta_matches_constant(self):
        """
        GIVEN the _CTA_5 constant and the images_branch section
        WHEN the success path CTA is inspected
        THEN either the exact _CTA_5 string OR its {{CTA_5}} placeholder MUST appear
        in the success path instruction.

        Since centralize-pre-expediente-prompts, the raw prompt file uses {{CTA_5}}
        placeholders (substituted by the loader at runtime). Both forms are valid.
        AC-4.3.
        """
        cta5 = _get_cta5()
        content = _load_post_price()
        images_start = content.find("<images_branch>")
        images_end = content.find("</images_branch>")
        images_section = content[images_start:images_end]
        assert (cta5 in images_section or "{{CTA_5}}" in images_section), (
            f"Neither the _CTA_5 literal {cta5!r} nor the {{{{CTA_5}}}} placeholder "
            "was found in the images_branch section. AC-4.3."
        )

    def test_prompt_does_not_contain_old_closed_cta_as_success_cta(self):
        """
        GIVEN the pre_expediente_post_price.md markdown
        WHEN the images_branch success line is inspected
        THEN it MUST NOT use '¿Empezamos con el expediente?' as the success CTA.

        Triangulation: ensures the old closed form is gone from the primary CTA point.
        """
        content = _load_post_price()
        images_start = content.find("<images_branch>")
        images_end = content.find("</images_branch>")
        images_section = content[images_start:images_end]
        # The success line: "success=true → tu texto es SOLO el CTA ÚNICO: ..."
        success_line = next(
            (line for line in images_section.splitlines() if "success=true" in line),
            None,
        )
        assert success_line is not None, "success=true line not found in images_branch."
        assert "¿Empezamos con el expediente?" not in success_line, (
            "The success=true CTA line must NOT use '¿Empezamos con el expediente?' — "
            "that is the old closed form. AC-4.3."
        )


# ---------------------------------------------------------------------------
# F4 — Anti-confirmación post-identificar (sdd/fix-pricing-gate-self-heal-loop)
# ---------------------------------------------------------------------------

_DISCOVERY_MD = (
    Path(__file__).parents[3]
    / "agent"
    / "prompts"
    / "modes"
    / "pre_expediente_discovery.md"
)


def _load_discovery() -> str:
    return _DISCOVERY_MD.read_text(encoding="utf-8")


class TestF4AntiConfirmationClause:
    """The L4 block of `pre_expediente_discovery.md` MUST list the literal
    confirmation phrasings the LLM has emitted in production violations of
    L2 (PROCEED → calcular_tarifa same turn) and L4 (no post-identificar
    confirmation).
    """

    def test_clause_block_present(self) -> None:
        text = _load_discovery()
        assert "anti-confirmación post-identificar" in text

    def test_forbidden_phrases_enumerated(self) -> None:
        text = _load_discovery().lower()
        for forbidden in (
            "necesito una confirmación",
            "confirmación rápida",
            "antes de calcularte el presupuesto",
            "¿quieres homologar los dos elementos",
        ):
            assert forbidden in text, (
                f"Forbidden phrase {forbidden!r} must be enumerated in L4"
            )

    def test_clause_states_proceed_in_same_turn(self) -> None:
        text = _load_discovery()
        assert "EN ESTE MISMO TURNO" in text or "este mismo turno" in text.lower()

    def test_clause_no_voseo(self) -> None:
        # F4 prompt addition must use Castilian tuteo (per commit 415963c)
        text = _load_discovery().lower()
        for voseo in ("tenés", "podés", "querés", "necesitás"):
            assert voseo not in text, (
                f"Voseo form {voseo!r} leaked into discovery prompt"
            )

