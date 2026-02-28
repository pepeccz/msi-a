"""
Prompt invariant lint tests.

Verifies the prompt_lint module correctly scans prompt files for
business-critical invariant violations and that the production prompts
pass without false positives.

Phase 5, Task 5.2 — agent-harmony-latency-hardening.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from agent.prompts.prompt_lint import (
    INVARIANT_RULES,
    LintViolation,
    lint_all_prompts,
    lint_prompt_file,
)

# Resolve the actual prompts directory once
_PROMPTS_DIR = str(Path(__file__).resolve().parents[3] / "agent" / "prompts")


# =============================================================================
# Task 5.2.1 — lint_all_prompts runs without crashing
# =============================================================================


class TestLintAllPromptsRuns:
    """Verify lint_all_prompts can scan agent/prompts/ without errors."""

    def test_lint_all_prompts_does_not_crash(self):
        """lint_all_prompts() must complete without raising."""
        results = lint_all_prompts(_PROMPTS_DIR)
        # Should return a dict (possibly empty if all prompts are clean)
        assert isinstance(results, dict)

    def test_lint_all_prompts_returns_dict_of_lists(self):
        """Each value in the results dict must be a list of LintViolation."""
        results = lint_all_prompts(_PROMPTS_DIR)
        for filepath, violations in results.items():
            assert isinstance(filepath, str), f"Key must be str, got {type(filepath)}"
            assert isinstance(violations, list), f"Value must be list, got {type(violations)}"
            for v in violations:
                assert isinstance(v, LintViolation), f"Item must be LintViolation, got {type(v)}"

    def test_lint_all_prompts_only_scans_md_files(self):
        """Only .md files should appear in results."""
        results = lint_all_prompts(_PROMPTS_DIR)
        for filepath in results:
            assert filepath.endswith(".md"), f"Non-markdown file in results: {filepath}"


# =============================================================================
# Task 5.2.2 — Known good prompt files pass with 0 violations
# =============================================================================


class TestKnownGoodPromptsPass:
    """Verify that production prompt files pass without violations."""

    @pytest.mark.parametrize(
        "prompt_file",
        [
            "core/01_security.md",
            "core/02_identity.md",
            "core/03_format_style.md",
            "core/06_escalation.md",
            "core/08_documentation.md",
        ],
    )
    def test_core_prompt_passes(self, prompt_file: str):
        """Core prompt files should pass with 0 violations.

        These files don't contain pricing/variant instructions so they
        must not trigger any invariant rule.
        """
        filepath = os.path.join(_PROMPTS_DIR, prompt_file)
        if not os.path.exists(filepath):
            pytest.skip(f"Prompt file not found: {filepath}")

        violations = lint_prompt_file(filepath)
        assert violations == [], (
            f"{prompt_file} has unexpected violations: "
            + "; ".join(f"[{v.rule_id}] L{v.line}: {v.message}" for v in violations)
        )


# =============================================================================
# Task 5.2.3 — Synthetic bad prompt triggers INV-04
# =============================================================================


class TestSyntheticBadPromptINV04:
    """Verify that a prompt containing invented prices triggers INV-04."""

    def test_invented_price_range_triggers_inv04(self, tmp_path: Path):
        """A line with 'entre 200€ y 500€' should trigger INV-04."""
        bad_prompt = tmp_path / "bad_prompt.md"
        bad_prompt.write_text(
            textwrap.dedent("""\
            # Bad Prompt

            Si el usuario pregunta, da una estimacion del precio aproximado.
            El rango de precio suele estar entre 200€ y 500€ dependiendo del vehículo.
            """),
            encoding="utf-8",
        )

        violations = lint_prompt_file(str(bad_prompt))
        inv04_violations = [v for v in violations if v.rule_id == "INV-04"]

        assert len(inv04_violations) >= 1, (
            f"Expected INV-04 violation but got: "
            + "; ".join(f"[{v.rule_id}] {v.message}" for v in violations)
        )

    def test_price_estimation_triggers_inv04(self, tmp_path: Path):
        """A line instructing price estimation should trigger INV-04."""
        bad_prompt = tmp_path / "estimation_prompt.md"
        bad_prompt.write_text(
            textwrap.dedent("""\
            # Estimation Prompt

            Puedes dar estimaciones al usuario si no estás seguro del precio exacto.
            """),
            encoding="utf-8",
        )

        violations = lint_prompt_file(str(bad_prompt))
        inv04_violations = [v for v in violations if v.rule_id == "INV-04"]

        assert len(inv04_violations) >= 1, (
            f"Expected INV-04 violation for 'estimaciones' but got: "
            + "; ".join(f"[{v.rule_id}] {v.message}" for v in violations)
        )

    def test_clean_prompt_no_inv04(self, tmp_path: Path):
        """A clean prompt with no pricing language should not trigger INV-04."""
        clean_prompt = tmp_path / "clean_prompt.md"
        clean_prompt.write_text(
            textwrap.dedent("""\
            # Clean Prompt

            Usa siempre la herramienta para calcular el precio exacto.
            NUNCA inventes precios ni des estimaciones.
            """),
            encoding="utf-8",
        )

        violations = lint_prompt_file(str(clean_prompt))
        inv04_violations = [v for v in violations if v.rule_id == "INV-04"]

        assert inv04_violations == [], (
            f"Clean prompt should not trigger INV-04 but got: "
            + "; ".join(f"L{v.line}: {v.context}" for v in inv04_violations)
        )


# =============================================================================
# Task 5.2.4 — Negative examples are excluded from violations
# =============================================================================


class TestNegativeExampleExclusion:
    """Verify that lines marked as negative examples don't trigger violations."""

    def test_line_with_wrong_marker_excluded(self, tmp_path: Path):
        """Lines marked with ❌ should not trigger violations."""
        prompt = tmp_path / "negative_example.md"
        prompt.write_text(
            textwrap.dedent("""\
            # Rules

            ❌ INCORRECTO: Da estimaciones al usuario con rango de precio entre 200€ y 500€.
            ✅ CORRECTO: Usa siempre la herramienta de calculo.
            """),
            encoding="utf-8",
        )

        violations = lint_prompt_file(str(prompt))
        inv04_violations = [v for v in violations if v.rule_id == "INV-04"]

        assert inv04_violations == [], (
            f"Negative example should be excluded but triggered: "
            + "; ".join(f"L{v.line}: {v.context}" for v in inv04_violations)
        )

    def test_line_with_nunca_marker_excluded(self, tmp_path: Path):
        """Lines with NUNCA preceding the pattern should be excluded."""
        prompt = tmp_path / "nunca_example.md"
        prompt.write_text(
            textwrap.dedent("""\
            # Anti-patterns

            NUNCA des estimaciones o rango de precio al usuario.
            """),
            encoding="utf-8",
        )

        violations = lint_prompt_file(str(prompt))
        inv04_violations = [v for v in violations if v.rule_id == "INV-04"]

        assert inv04_violations == [], (
            f"NUNCA line should be excluded but triggered: "
            + "; ".join(f"L{v.line}: {v.context}" for v in inv04_violations)
        )

    def test_line_with_eliminado_marker_excluded(self, tmp_path: Path):
        """Lines with ELIMINADO marker should be excluded."""
        prompt = tmp_path / "eliminado_example.md"
        prompt.write_text(
            textwrap.dedent("""\
            # Removed Features

            ELIMINADO: rango de precio entre 100€ y 300€ ya no se usa.
            """),
            encoding="utf-8",
        )

        violations = lint_prompt_file(str(prompt))
        inv04_violations = [v for v in violations if v.rule_id == "INV-04"]

        assert inv04_violations == [], (
            f"ELIMINADO line should be excluded but triggered: "
            + "; ".join(f"L{v.line}: {v.context}" for v in inv04_violations)
        )


# =============================================================================
# Edge cases
# =============================================================================


class TestLintEdgeCases:
    """Edge case tests for the lint engine."""

    def test_nonexistent_file_returns_lint_error(self):
        """Linting a nonexistent file should return a LINT-ERR violation."""
        violations = lint_prompt_file("/nonexistent/path/prompt.md")
        assert len(violations) == 1
        assert violations[0].rule_id == "LINT-ERR"
        assert violations[0].severity == "error"

    def test_empty_file_returns_no_violations(self, tmp_path: Path):
        """An empty .md file should produce no violations."""
        empty = tmp_path / "empty.md"
        empty.write_text("", encoding="utf-8")

        violations = lint_prompt_file(str(empty))
        assert violations == []

    def test_invariant_rules_list_is_nonempty(self):
        """The INVARIANT_RULES list must contain rules."""
        assert len(INVARIANT_RULES) > 0

    def test_all_rules_have_required_fields(self):
        """Each InvariantRule must have rule_id, description, pattern, severity."""
        for rule in INVARIANT_RULES:
            assert rule.rule_id, f"Rule missing rule_id: {rule}"
            assert rule.description, f"Rule {rule.rule_id} missing description"
            assert rule.pattern, f"Rule {rule.rule_id} missing pattern"
            assert rule.severity in ("error", "warning"), (
                f"Rule {rule.rule_id} has invalid severity: {rule.severity}"
            )
