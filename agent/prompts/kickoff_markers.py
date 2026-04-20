"""
Kickoff markers module — canonical detection of hallucinated EXPEDIENTE kickoff phrases.

This module is the SINGLE SOURCE OF TRUTH for:
  1. The compiled regex patterns that detect when the LLM emits a kickoff declaration
     WITHOUT having called confirmar_presupuesto (hallucinated transition).
  2. The literal source patterns used by the lint anti-drift test
     (tests/agent/prompts/test_kickoff_markers_lint.py).

Design decisions (see design artifact sdd/hallucinated-transition-self-heal/design):
  - Regex per phrase variant with \\b word-boundary anchors to prevent false positives
    on explanatory text ("abrir el expediente significa...") or conditional phrasing.
  - Patterns anchored conceptually to end-of-response (caller slices last 200 chars).
  - Case-insensitive to cover normalised output from different LLM quantizations.
  - CTA 5 literal ("¿Abrimos expediente o tienes alguna duda?") must NOT match.

Scenarios covered:
  KM-1-A: "Perfecto, empezamos con el expediente. Te voy a ir pidiendo..." → True
  KM-1-B: "Expediente abierto. Te pido la documentación a continuación." → True
  KM-1-C: "Abrir el expediente significa empezar a recopilar..." → False
  KM-1-D: "¿Abrimos expediente o tienes alguna duda?" → False (CTA 5)
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Source patterns (str) — used by the lint anti-drift test to scan prompt files.
# Each string is a raw regex pattern. Keep them as the canonical reference.
# ---------------------------------------------------------------------------

KICKOFF_MARKER_SOURCES: tuple[str, ...] = (
    # Pattern 1: "empezamos/vamos/arrancamos/iniciamos/comenzamos con el expediente"
    # Covers both voseo and tuteo verb conjugations.
    # Negative: "empezaríamos" (conditional, subjunctive) — excluded by simple stem check.
    # Positive: "empezamos con el expediente", "arrancamos con el expediente".
    # Negative: "empezar a recopilar" — "empezar" is infinitive, not conjugated first-plural.
    r"\b(empezamos|vamos|arrancamos|iniciamos|comenzamos)\s+con\s+(el\s+)?expediente\b",
    # Pattern 2: "expediente abierto/comenzado/creado/iniciado"
    # Covers the professional path declarative form.
    # Positive: "Expediente abierto.", "expediente comenzado".
    # Negative: "Abrimos expediente" (CTA 5 form — different word order, "abrimos" is verb here).
    r"\bexpediente\s+(abierto|comenzado|creado|iniciado|listo)\b",
    # Pattern 3: "te voy a ir pidiendo" / "te pido la documentación / todo"
    # Auxiliary signal — occurs in the kickoff declaration after the main phrase.
    # Positive: "Te voy a ir pidiendo todo paso a paso."
    # Positive: "Te pido la documentación a continuación."
    r"\bte\s+(voy\s+a\s+ir\s+)?pid(iendo|o)\s+(todo|la\s+documentaci[oó]n)\b",
)

# ---------------------------------------------------------------------------
# Compiled patterns — used at runtime in is_kickoff_hallucination().
# ---------------------------------------------------------------------------

KICKOFF_MARKERS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(src, re.IGNORECASE) for src in KICKOFF_MARKER_SOURCES
)


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------


def is_kickoff_hallucination(ai_response: str) -> bool:
    """Return True if *ai_response* contains a kickoff marker phrase.

    Only the last 200 characters are examined — kickoff phrases are a
    conclusion signal (the LLM wraps up by declaring the transition).
    This window also prevents false positives from earlier educational text
    that may quote kickoff vocabulary.

    Args:
        ai_response: The raw text produced by the LLM for the current turn.

    Returns:
        True  — if any KICKOFF_MARKERS pattern matches the tail of the response.
        False — for empty input, CTA 5 only, or explanatory/conditional text.
    """
    if not ai_response:
        return False

    tail = ai_response.strip()[-200:]
    return any(pat.search(tail) for pat in KICKOFF_MARKERS)
