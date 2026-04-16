"""
Prompt invariant linter for MSI-a mode prompts.

Scans prompt markdown files for patterns that violate business-critical
invariant rules.  Designed to be run as a pre-deploy or CI check to
catch prompt regressions before they reach production.

Usage:
    from agent.prompts.prompt_lint import lint_all_prompts

    violations = lint_all_prompts()
    for filepath, issues in violations.items():
        for v in issues:
            print(f"{filepath}:{v.line} [{v.severity}] {v.rule_id}: {v.message}")
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LintViolation:
    """A single invariant violation found in a prompt file."""

    rule_id: str
    severity: str  # "error" | "warning"
    message: str
    line: int = 0
    context: str = ""


class InvariantRule(NamedTuple):
    """Definition of a prompt invariant rule."""

    rule_id: str
    description: str
    pattern: str  # regex pattern (case-insensitive)
    severity: str  # "error" | "warning"


# ---------------------------------------------------------------------------
# Invariant rules
#
# Each rule defines a regex that, when matched in a prompt file, signals
# a potential contradiction or anti-pattern.  Lines inside fenced code
# blocks that are explicitly marked as incorrect examples (❌, INCORRECTO,
# WRONG, ERROR, PROHIBIDO) are excluded from triggering violations.
# ---------------------------------------------------------------------------

INVARIANT_RULES: list[InvariantRule] = [
    # INV-01: Price must be communicated before images
    InvariantRule(
        rule_id="INV-01",
        description="Prompt must not instruct sending images without mentioning price-first rule",
        pattern=r"envi[aá]r?\s+(?:fotos|im[aá]genes).*(?:sin|antes\s+de)\s+(?:precio|presupuesto)",
        severity="error",
    ),
    # INV-02: Never re-identify after variant question
    # Only matches lines that positively instruct calling identificar_y_resolver_elementos
    # for variant resolution.  Lines with NUNCA/NO/❌ are excluded by the
    # negative-example detector, and this pattern requires an imperative form
    # (→ call, usa, llama) next to the function name.
    InvariantRule(
        rule_id="INV-02",
        description="Prompt must not instruct re-identification when resolving variants",
        pattern=r"(?:→|usa|llama|llamar)\s*`?identificar_y_resolver_elementos`?.*(?:variante|delantera|trasera)",
        severity="error",
    ),
    # INV-03: Never expose UPPERCASE internal element codes to user
    # Only matches ALL_CAPS codes like FARO_DELANTERO, not lowercase names.
    InvariantRule(
        rule_id="INV-03",
        description="Prompt should not show raw internal codes in user-facing example text",
        pattern=r"Bot:\s*\"[^\"]*(?:FARO_DELANTERO|SUSPENSION_DEL|ESCAPE_[A-Z]|INTERMITENTE_[A-Z]|PARAGOLPES_[A-Z])",
        severity="warning",
    ),
    # INV-04: Never invent prices — always use tool
    # Excludes lines that say NOT to do it (contain "no", "nunca", "eliminado").
    InvariantRule(
        rule_id="INV-04",
        description="Prompt must not suggest inventing or estimating prices",
        pattern=r"(?<!no\s)(?<!nunca\s)(?:da[rs]?\s+)?(?:estim(?:acion|aciones)|rango\s+de\s+precio|precio\s+aproximad|entre\s+\d+\s*[€y]\s*\d+)",
        severity="error",
    ),
    # INV-05: calcular_tarifa_con_elementos call missing skip_validation
    # Only fires when the ENTIRE LINE does NOT contain skip_validation.
    # We use a negative lookahead anchored at start-of-line via the engine.
    InvariantRule(
        rule_id="INV-05",
        description="calcular_tarifa_con_elementos call should include skip_validation=True",
        pattern=r"^(?!.*skip_validation).*calcular_tarifa_con_elementos\(",
        severity="warning",
    ),
    # INV-06: Never assume variant without asking user
    InvariantRule(
        rule_id="INV-06",
        description="Must not instruct choosing a variant without user input",
        pattern=r"(?:asum[eir]|elig[eir]|escog[eir]).*variante.*sin\s+preguntar",
        severity="error",
    ),
    # INV-07: Deleted key advertencias_comunicadas must not appear in any prompt
    # Added in refactor-cross-mode-state-separation Batch E — the key was removed
    # from the cross-mode contract; prompts must use warnings_acknowledged instead.
    InvariantRule(
        rule_id="INV-07",
        description="EXPEDIENTE prompt must not reference deleted key advertencias_comunicadas",
        pattern=r"advertencias_comunicadas",
        severity="error",
    ),
    # INV-08: Deleted UX flag presupuesto_images_shown must not appear in any prompt
    # Added in refactor-cross-mode-state-separation Batch E — the flag was removed
    # from cross-mode propagation; EXPEDIENTE photo guidance is now unconditional.
    InvariantRule(
        rule_id="INV-08",
        description="EXPEDIENTE prompt must not reference deleted UX flag presupuesto_images_shown",
        pattern=r"presupuesto_images_shown",
        severity="error",
    ),
]

# Patterns that mark a line as part of a "negative example" or prohibition.
# Lines matching these are excluded from generating violations because
# they are teaching what NOT to do or stating a prohibition.
_NEGATIVE_EXAMPLE_MARKERS = re.compile(
    r"(?:❌|INCORRECTO|WRONG|ERROR|PROHIBIDO|ELIMINADO"
    r"|←\s*(?:WRONG|FALTA|SIN)"
    r"|\bNUNCA\b|\bNO\s+(?:vuelvas|llam|uses|hagas|des\b|envíes|inventes|asumas)"
    r"|\bSIEMPRE\b.*\bNO\b)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Lint engine
# ---------------------------------------------------------------------------


def _is_inside_negative_example(lines: list[str], line_idx: int) -> bool:
    """Check if a line is inside a clearly-marked negative example block.

    Looks at the surrounding context (up to 5 lines before) for markers
    that indicate the example is illustrating what NOT to do.
    """
    start = max(0, line_idx - 5)
    for i in range(start, line_idx + 1):
        if _NEGATIVE_EXAMPLE_MARKERS.search(lines[i]):
            return True
    return False


def _is_inside_code_block(lines: list[str], line_idx: int) -> bool:
    """Check if a line is inside a fenced code block (``` ... ```)."""
    in_code = False
    for i in range(line_idx + 1):
        stripped = lines[i].strip()
        if stripped.startswith("```"):
            in_code = not in_code
    return in_code


def lint_prompt_file(filepath: str) -> list[LintViolation]:
    """Lint a single prompt markdown file against INVARIANT_RULES.

    Args:
        filepath: Path to the .md prompt file.

    Returns:
        List of LintViolation instances found.  Empty list if clean.
    """
    path = Path(filepath)
    if not path.exists():
        return [
            LintViolation(
                rule_id="LINT-ERR",
                severity="error",
                message=f"File not found: {filepath}",
            )
        ]

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    violations: list[LintViolation] = []

    for rule in INVARIANT_RULES:
        compiled = re.compile(rule.pattern, re.IGNORECASE)
        for idx, line in enumerate(lines):
            if compiled.search(line):
                # Skip if inside a negative example block
                if _is_inside_negative_example(lines, idx):
                    continue
                # Skip if inside a code block that is part of a negative example
                if _is_inside_code_block(lines, idx) and _is_inside_negative_example(
                    lines, idx
                ):
                    continue
                violations.append(
                    LintViolation(
                        rule_id=rule.rule_id,
                        severity=rule.severity,
                        message=rule.description,
                        line=idx + 1,  # 1-indexed
                        context=line.strip()[:120],
                    )
                )

    return violations


def lint_all_prompts(
    prompts_dir: str | None = None,
) -> dict[str, list[LintViolation]]:
    """Lint all prompt markdown files in the prompts directory.

    Args:
        prompts_dir: Path to the prompts directory.  Defaults to
            ``agent/prompts/`` relative to the project root.

    Returns:
        Dict mapping filepath → list of violations.
        Files with zero violations are omitted.
    """
    if prompts_dir is None:
        # Resolve relative to this file's location
        prompts_dir = str(Path(__file__).parent)

    results: dict[str, list[LintViolation]] = {}

    for root, _dirs, files in os.walk(prompts_dir):
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(root, fname)
            violations = lint_prompt_file(fpath)
            if violations:
                results[fpath] = violations

    return results


# ---------------------------------------------------------------------------
# CLI entry point (optional convenience)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    results = lint_all_prompts()
    total = sum(len(v) for v in results.values())

    if total == 0:
        print("✅ All prompts pass invariant checks.")
        sys.exit(0)

    for fpath, violations in results.items():
        for v in violations:
            line_info = f":{v.line}" if v.line else ""
            print(f"{fpath}{line_info} [{v.severity}] {v.rule_id}: {v.message}")
            if v.context:
                print(f"  → {v.context}")
        print()

    print(f"Found {total} violation(s) across {len(results)} file(s).")
    sys.exit(1)
