"""
T4.test — Regression tests for prospective framing guardrail in expediente sub-mode prompts.

Each test asserts:
1. The guardrail line is present (contains "Framing prospectivo").
2. No deictic-imperative instruction to the LLM like "Describe las fotos..." is present
   outside of explicit prohibition/example contexts (lines that already say NO).
"""
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent.parent / "agent" / "prompts" / "modes"

GUARDRAIL_MARKER = "Framing prospectivo"

# Deictic phrases that must NOT appear as LLM instructions.
# Lines that contain these phrases only within a "NO uses" / PROHIBIDO context are allowed.
FORBIDDEN_DEICTIC_PATTERNS = [
    "Describe las fotos",  # elements.md original offender
    "Estas son las fotos",  # e.g. "Estas son las fotos que necesitás"
    "Estas son las",       # covers "Estas son las imágenes..."
]

# These may appear only inside quoted examples within the guardrail's own prohibition text.
# We check per-line: skip lines that contain "NO uses" or "PROHIBIDO" (they are prohibition lines).
DEICTIC_QUOTED_ALLOWED = [
    "Aquí están",  # allowed only if inside a NO/prohibition line
]


def _read_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _instruction_lines(content: str) -> list[str]:
    """Return lines that are LLM instructions (not prohibition/NO-uses lines)."""
    prohibition_markers = ("NO uses", "PROHIBIDO", "- NO uses", "no uses")
    return [
        line for line in content.splitlines()
        if not any(marker in line for marker in prohibition_markers)
    ]


class TestGuardrailPresent:
    def test_elements_has_guardrail(self):
        content = _read_prompt("expediente_elements.md")
        assert GUARDRAIL_MARKER in content, (
            f"expediente_elements.md is missing the guardrail line '{GUARDRAIL_MARKER}'"
        )

    def test_base_docs_has_guardrail(self):
        content = _read_prompt("expediente_base_docs.md")
        assert GUARDRAIL_MARKER in content, (
            f"expediente_base_docs.md is missing the guardrail line '{GUARDRAIL_MARKER}'"
        )

    def test_personal_has_guardrail(self):
        content = _read_prompt("expediente_personal.md")
        assert GUARDRAIL_MARKER in content, (
            f"expediente_personal.md is missing the guardrail line '{GUARDRAIL_MARKER}'"
        )

    def test_vehicle_has_guardrail(self):
        content = _read_prompt("expediente_vehicle.md")
        assert GUARDRAIL_MARKER in content, (
            f"expediente_vehicle.md is missing the guardrail line '{GUARDRAIL_MARKER}'"
        )

    def test_workshop_has_guardrail(self):
        content = _read_prompt("expediente_workshop.md")
        assert GUARDRAIL_MARKER in content, (
            f"expediente_workshop.md is missing the guardrail line '{GUARDRAIL_MARKER}'"
        )

    def test_review_has_guardrail(self):
        content = _read_prompt("expediente_review.md")
        assert GUARDRAIL_MARKER in content, (
            f"expediente_review.md is missing the guardrail line '{GUARDRAIL_MARKER}'"
        )


class TestNoDeicticImperatives:
    def test_elements_no_describe_las_fotos(self):
        content = _read_prompt("expediente_elements.md")
        assert "Describe las fotos" not in content, (
            "expediente_elements.md still contains deictic 'Describe las fotos' — swap to prospective form"
        )

    def _check_no_deictic(self, filename: str) -> None:
        content = _read_prompt(filename)
        instruction_text = "\n".join(_instruction_lines(content))
        for phrase in FORBIDDEN_DEICTIC_PATTERNS:
            assert phrase not in instruction_text, (
                f"{filename} contains forbidden deictic phrase in an instruction line: '{phrase}'"
            )
        # For quoted-allowed phrases, check only instruction lines
        for phrase in DEICTIC_QUOTED_ALLOWED:
            assert phrase not in instruction_text, (
                f"{filename} contains deictic phrase '{phrase}' in an instruction line (only allowed in prohibition lines)"
            )

    def test_elements_no_deictic_phrases(self):
        self._check_no_deictic("expediente_elements.md")

    def test_base_docs_no_deictic_phrases(self):
        self._check_no_deictic("expediente_base_docs.md")

    def test_personal_no_deictic_phrases(self):
        self._check_no_deictic("expediente_personal.md")

    def test_vehicle_no_deictic_phrases(self):
        self._check_no_deictic("expediente_vehicle.md")

    def test_workshop_no_deictic_phrases(self):
        self._check_no_deictic("expediente_workshop.md")

    def test_review_no_deictic_phrases(self):
        self._check_no_deictic("expediente_review.md")
