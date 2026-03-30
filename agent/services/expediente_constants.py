"""Single source of truth for expediente step labels and progress helpers.

This module is a **leaf dependency** — it imports NOTHING from the ``agent``
package so that any module in the agent tree can import it without risk of
circular references.

The canonical labels are taken from the user-facing intro overview
(``expediente_onboarding.EXPEDIENTE_PHASE_OVERVIEW``) so that the step
prefix shown during collection always matches the overview the user saw
when the expediente was opened.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Canonical step mapping
# ---------------------------------------------------------------------------
# Keys are the sub_mode constants used in mode_context["expediente_sub_mode"].
# Values are ``(step_number, label)`` tuples where *label* is the
# user-facing text that appears in the intro overview and progress prefix.

STEP_LABELS: dict[str, tuple[int, str]] = {
    "collect_element_data": (1, "Fotos y datos de cada elemento"),
    "collect_base_docs": (2, "Documentación base del vehículo"),
    "collect_personal": (3, "Datos personales"),
    "collect_vehicle": (4, "Datos del vehículo"),
    "collect_workshop": (5, "Certificado del taller"),
    "review_summary": (6, "Revisión y confirmación"),
}

TOTAL_STEPS: int = len(STEP_LABELS)
"""Total number of expediente steps (derived from ``STEP_LABELS``)."""

# Supplement added to tariff when workshop issues certificate themselves
CERT_SUPPLEMENT_EUR: int = 85


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def step_prefix(sub_mode: str) -> str:
    """Return the progress prefix for a given sub-mode.

    Format: ``"📍 Paso X/6 — Label"``

    Returns an empty string when *sub_mode* is not a recognised key so that
    callers can safely concatenate without guarding.

    Args:
        sub_mode: Lower-case sub-mode constant (e.g. ``"collect_personal"``).

    Returns:
        Formatted progress prefix, or ``""`` if *sub_mode* is unknown.
    """
    entry = STEP_LABELS.get(sub_mode)
    if entry is None:
        return ""
    step_number, label = entry
    return f"📍 Paso {step_number}/{TOTAL_STEPS} — {label}"


def phase_overview_lines() -> tuple[str, ...]:
    """Return the ordered intro overview lines for all expediente steps.

    Each line has the format ``"📍 Paso X/6 - Label"`` (note the hyphen,
    matching the canonical intro message style).

    Returns:
        Tuple of 6 formatted strings, ordered by step number.
    """
    sorted_entries = sorted(STEP_LABELS.values(), key=lambda e: e[0])
    return tuple(
        f"📍 Paso {step_number}/{TOTAL_STEPS} - {label}"
        for step_number, label in sorted_entries
    )
