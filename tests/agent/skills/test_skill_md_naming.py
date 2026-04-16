"""
Guard: skills/msia-agent/SKILL.md must NOT reference stale sub-mode names.

This test is expected to FAIL until Batch E updates the SKILL.md file to use
current sub-mode names (collect_*, review_summary) instead of the legacy names
(DOCUMENTACION_ELEMENTOS, DOCUMENTACION_BASE, DATOS_PERSONALES, DATOS_VEHICULO,
EXPEDIENTE_TALLER, EXPEDIENTE_REVISION).

Requirements: R5.1 — No stale sub-mode names in SKILL.md
              R5.2 — SKILL.md uses current convention (collect_*, review_summary)

Note on word-boundary matching:
  - TALLER and REVISION are common Spanish words. We only reject them as sub-mode
    names, so we match the full prefixed form: EXPEDIENTE_TALLER, EXPEDIENTE_REVISION.
  - DOCUMENTACION_ELEMENTOS, DOCUMENTACION_BASE, DATOS_PERSONALES, DATOS_VEHICULO
    are unique enough to reject directly.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SKILL_MD_PATH = Path(__file__).parents[3] / "skills" / "msia-agent" / "SKILL.md"

# Forbidden sub-mode tokens — these are legacy names replaced by collect_*/review_summary.
# Use word-boundary patterns to avoid partial matches.
_FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    # (pattern, human-readable name for error messages)
    (r"\bDOCUMENTACION_ELEMENTOS\b", "DOCUMENTACION_ELEMENTOS"),
    (r"\bDOCUMENTACION_BASE\b", "DOCUMENTACION_BASE"),
    (r"\bDATOS_PERSONALES\b", "DATOS_PERSONALES"),
    (r"\bDATOS_VEHICULO\b", "DATOS_VEHICULO"),
    # Use full prefixed form to avoid false positives on common Spanish words.
    (r"\bEXPEDIENTE_TALLER\b", "EXPEDIENTE_TALLER"),
    (r"\bEXPEDIENTE_REVISION\b", "EXPEDIENTE_REVISION"),
]


@pytest.fixture(scope="module")
def skill_md_content() -> str:
    """Read SKILL.md content once per test session."""
    assert _SKILL_MD_PATH.is_file(), (
        f"SKILL.md not found at {_SKILL_MD_PATH}. "
        "Ensure the skills/msia-agent/SKILL.md file exists."
    )
    return _SKILL_MD_PATH.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "pattern,label",
    _FORBIDDEN_PATTERNS,
    ids=[label for _, label in _FORBIDDEN_PATTERNS],
)
def test_skill_md_does_not_contain_stale_submode_name(
    skill_md_content: str,
    pattern: str,
    label: str,
) -> None:
    """
    SKILL.md must not contain the stale sub-mode name as a token.

    Current naming convention:
      collect_element_data, collect_base_docs, collect_personal,
      collect_vehicle, collect_workshop, review_summary
    """
    matches = re.findall(pattern, skill_md_content)
    assert not matches, (
        f"skills/msia-agent/SKILL.md still contains stale sub-mode name "
        f"{label!r} ({len(matches)} occurrence(s)). "
        f"Update SKILL.md in Batch E to use the current naming convention."
    )
