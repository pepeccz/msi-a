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


# ─────────────────────────────────────────────────────────────────────────────
# Token Budget Tests (msia-prompts-skill)
# Budgets: current file size + 10% headroom. Token estimate = len(text) // 4
# ─────────────────────────────────────────────────────────────────────────────

_BUDGET_PARAMS = [
    # (relative path from agent/prompts/, char_budget)
    ("core/01_security.md",                          2_000),
    ("core/02_identity.md",                          4_600),
    ("core/03_format_style.md",                      1_840),
    ("core/04_anti_patterns.md",                     9_840),
    ("core/05_tools_efficiency.md",                  2_800),
    ("core/06_escalation.md",                        1_960),
    ("core/07_pricing_rules.md",                     7_880),
    ("core/08_documentation.md",                     2_800),
    ("core/09_inline_questions.md",                    920),
    ("modes/presupuesto_mode.md",                   43_200),
    ("modes/consulta_mode.md",                       8_600),
    ("modes/expediente_documentacion_elementos.md", 15_120),
    ("modes/expediente_documentacion_base.md",       5_720),
    ("modes/expediente_datos_personales.md",         5_760),
    ("modes/expediente_datos_vehiculo.md",           4_080),
    ("modes/expediente_taller.md",                   5_520),
    ("modes/expediente_revision.md",                 6_280),
]

_CORE_FILES = [p for p, _ in _BUDGET_PARAMS if p.startswith("core/")]
_MODE_FILES  = [p for p, _ in _BUDGET_PARAMS if p.startswith("modes/")]

_BUDGET_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "agent" / "prompts"


class TestTokenBudgets:
    """Enforce per-file token budgets for agent/prompts/ files.

    Token estimate: len(text) // 4  (matches loader.py:get_prompt_stats convention).
    Budgets = current size + 10% headroom.
    """

    @pytest.mark.parametrize(
        "rel_path,char_budget",
        _BUDGET_PARAMS,
        ids=[Path(p).name for p, _ in _BUDGET_PARAMS],
    )
    def test_file_within_budget(self, rel_path: str, char_budget: int) -> None:
        file_path = _BUDGET_PROMPTS_DIR / rel_path
        assert file_path.exists(), f"Prompt file not found: {file_path}"
        size = len(file_path.read_text(encoding="utf-8"))
        assert size <= char_budget, (
            f"{rel_path}: {size} chars ({size // 4} tokens) exceeds budget "
            f"of {char_budget} chars ({char_budget // 4} tokens). "
            f"Reduce content or request a budget increase via msia-prompts-skill."
        )

    def test_core_total_within_budget(self) -> None:
        """Sum of all 9 core modules must not exceed 8,600 tokens (34,400 chars)."""
        total = sum(
            len((_BUDGET_PROMPTS_DIR / p).read_text(encoding="utf-8"))
            for p in _CORE_FILES
        )
        budget = 34_400  # 8,600 tokens × 4
        assert total <= budget, (
            f"Core total: {total} chars ({total // 4} tokens) exceeds "
            f"budget of {budget} chars (8,600 tokens)."
        )

    @pytest.mark.parametrize(
        "rel_path",
        _MODE_FILES,
        ids=[Path(p).name for p in _MODE_FILES],
    )
    def test_mode_file_hard_cap(self, rel_path: str) -> None:
        """No single mode file may exceed 10,800 tokens (43,200 chars) — hard cap."""
        file_path = _BUDGET_PROMPTS_DIR / rel_path
        assert file_path.exists(), f"Prompt file not found: {file_path}"
        size = len(file_path.read_text(encoding="utf-8"))
        hard_cap = 43_200  # 10,800 tokens × 4
        assert size <= hard_cap, (
            f"{rel_path}: {size} chars ({size // 4} tokens) exceeds hard cap "
            f"of {hard_cap} chars (10,800 tokens). "
            f"This file MUST be split. See msia-prompts-skill Large File Split Guidance."
        )
