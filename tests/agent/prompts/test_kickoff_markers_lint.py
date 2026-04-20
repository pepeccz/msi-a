"""
Lint-tests for kickoff marker drift guard.

B1-T3 [RED/GREEN]:
  test_pp_prompt_no_kickoff_templates — aserta que pre_expediente_post_price.md
  NO contiene líneas con plantillas kickoff copyable ("particular:" / "professional:")
  dentro de <expediente_branch>.

Spec: KM-2-A, PP-1-A
"""

from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_PP_PROMPT_PATH = (
    _PROJECT_ROOT / "agent" / "prompts" / "modes" / "pre_expediente_post_price.md"
)
_MODES_DIR = _PROJECT_ROOT / "agent" / "prompts" / "modes"


# ---------------------------------------------------------------------------
# B1-T3 — PP-1-A: prompt limpio de plantillas kickoff
# ---------------------------------------------------------------------------


class TestPreExpedientePostPricePromptClean:
    """
    Scenario PP-1-A: pre_expediente_post_price.md must NOT contain the old
    copyable kickoff template lines ("particular:" / "professional:") inside
    <expediente_branch>.

    These lines act as LLM attractors that cause hallucinated transitions.
    """

    def test_pp_prompt_no_kickoff_templates(self):
        """
        PP-1-A: pre_expediente_post_price.md no debe contener 'particular:'
        ni 'professional:' dentro del bloque <expediente_branch>.

        Falla HOY: las líneas 47-49 del archivo contienen esas plantillas.
        Pasa después de B1-I1: esas líneas se reemplazan por instrucción vacía.
        """
        assert _PP_PROMPT_PATH.exists(), (
            f"Prompt file not found: {_PP_PROMPT_PATH}"
        )
        content = _PP_PROMPT_PATH.read_text(encoding="utf-8")

        # Extraer el bloque <expediente_branch> ... </expediente_branch>
        branch_match = re.search(
            r"<expediente_branch>(.*?)</expediente_branch>",
            content,
            re.DOTALL,
        )
        assert branch_match is not None, (
            "<expediente_branch> block not found in pre_expediente_post_price.md"
        )
        branch_content = branch_match.group(1)

        # Las plantillas copyable deben haber sido eliminadas
        assert "particular:" not in branch_content, (
            "pre_expediente_post_price.md still contains 'particular:' template line "
            "inside <expediente_branch>. This line acts as a kickoff hallucination attractor. "
            "Remove it as part of B1-I1 (PP-1-A)."
        )
        assert "professional:" not in branch_content, (
            "pre_expediente_post_price.md still contains 'professional:' template line "
            "inside <expediente_branch>. This line acts as a kickoff hallucination attractor. "
            "Remove it as part of B1-I1 (PP-1-A)."
        )


# ---------------------------------------------------------------------------
# B3-T5 — KM-2-B: lint scanner over agent/prompts/modes/*.md
# Fails when any .md file contains a kickoff phrase (anti-drift guard).
# ---------------------------------------------------------------------------


def _scan_modes_for_kickoff_phrases() -> list[tuple[str, int, str]]:
    """
    Scan all .md files under agent/prompts/modes/ for lines that match
    any kickoff marker pattern.

    Returns a list of (file_path, line_number, line_content) tuples for
    every offending line found.

    Requires kickoff_markers.py to exist (Batch 3 B3-I1).
    """
    from agent.prompts.kickoff_markers import KICKOFF_MARKERS

    findings: list[tuple[str, int, str]] = []

    for md_file in sorted(_MODES_DIR.glob("*.md")):
        lines = md_file.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, start=1):
            for pat in KICKOFF_MARKERS:
                if pat.search(line):
                    findings.append((str(md_file), lineno, line.strip()))
                    break  # one finding per line is enough

    return findings


class TestKickoffMarkersLintScanner:
    """
    KM-2-B: the lint scanner MUST report failures when a .md prompt file
    contains a kickoff phrase outside the shared markers module.

    Two tests:
      1. Inject a fake kickoff phrase into a temporary string (unit-level) →
         the scanner helper correctly identifies it as a match.
      2. Run the real glob over agent/prompts/modes/ → all production files
         must be clean (no kickoff phrase leakage after B1-I1).
    """

    def test_lint_fails_if_any_md_contains_kickoff_phrase(self):
        """
        KM-2-B: injecting a canonical kickoff phrase into a fake 'file' that is
        parsed by the same KICKOFF_MARKERS regex must produce at least one match.

        This test verifies the scanner's detection capability, not production files.
        It passes once kickoff_markers.py exists (B3-I1).

        RED: fails before kickoff_markers.py exists.
        """
        from agent.prompts.kickoff_markers import KICKOFF_MARKERS

        # Simulate a line that would exist in a prompt file with a kickoff phrase
        offending_lines = [
            "particular: Perfecto, empezamos con el expediente. Te voy a ir pidiendo todo paso a paso.",
            "professional: Expediente abierto. Te pido la documentación a continuación.",
        ]

        found_matches = []
        for line in offending_lines:
            for pat in KICKOFF_MARKERS:
                if pat.search(line):
                    found_matches.append(line)
                    break

        assert len(found_matches) > 0, (
            "KM-2-B: KICKOFF_MARKERS regex must detect at least one of the canonical "
            "kickoff phrases when they appear in a prompt file line. "
            f"Tested lines: {offending_lines!r}. "
            "Check that KICKOFF_MARKERS patterns cover the canonical phrases."
        )

    def test_production_prompt_files_are_clean(self):
        """
        KM-2-B (production): all files in agent/prompts/modes/*.md must NOT
        contain any kickoff marker phrase after B1-I1 stripped them from
        pre_expediente_post_price.md.

        Fails if any drift is introduced (e.g. someone re-adds kickoff templates
        to a prompt file directly instead of going through kickoff_markers.py).

        RED: fails before kickoff_markers.py exists (import error).
        GREEN: passes after B3-I1 (module exists) AND after B1-I1 (prompt cleaned).
        """
        findings = _scan_modes_for_kickoff_phrases()

        if findings:
            lines_report = "\n".join(
                f"  {fpath}:{lineno}: {content}"
                for fpath, lineno, content in findings
            )
            pytest.fail(
                f"KM-2-B: {len(findings)} kickoff phrase(s) found in prompt .md files.\n"
                f"These phrases belong ONLY in agent/prompts/kickoff_markers.py.\n"
                f"Offending lines:\n{lines_report}"
            )

    def test_expediente_branch_exists_in_prompt(self):
        """
        Sanity check: <expediente_branch> block must exist in the prompt file.
        This is a pre-condition for the main lint test above.
        """
        assert _PP_PROMPT_PATH.exists(), (
            f"Prompt file not found: {_PP_PROMPT_PATH}"
        )
        content = _PP_PROMPT_PATH.read_text(encoding="utf-8")
        assert "<expediente_branch>" in content, (
            "pre_expediente_post_price.md must contain an <expediente_branch> tag. "
            "The lint test depends on this structure."
        )
