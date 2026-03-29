"""
Unit regression tests for fix-expediente-state-integrity — Track D (pure-logic subset).

These tests cover the Fix B and Fix C regression scenarios that require only
pure Python logic and do NOT need the full agent stack (no langchain_openai,
no Redis, no database).

For tool-level tests (D1/D3 full flow), see:
  tests/integration/test_expediente_state_integrity.py

Track D regression coverage here:
- D2-B: tombstone protocol prevents marker resurrection (Fix B regression)
- D2-C: Fix C step-mismatch and advancement-language guard (Fix C regression)
- D2-map: _SUBMODE_STEP_MAP completeness and correctness

Note on _SUBMODE_STEP_MAP: The constant is defined in agent/modes/expediente_mode.py
which requires langchain_openai. Here we replicate the EXPECTED mapping as a local
constant — the integration test file (test_expediente_state_integrity.py) exercises
the actual imported constant in Docker where langchain_openai is available.

Usage (runs without Docker stack):
    pytest tests/unit/test_expediente_state_integrity_regression.py -v
"""

from __future__ import annotations

import re
import sys
import types

# ---------------------------------------------------------------------------
# Stub optional heavy dependencies so tests run without full Docker stack
# ---------------------------------------------------------------------------
sys.modules.setdefault("phonenumbers", types.ModuleType("phonenumbers"))

import pytest

from agent.state.conversation_state import merge_dicts


# ---------------------------------------------------------------------------
# Local replica of _SUBMODE_STEP_MAP (spec-level constant)
#
# This must match agent/modes/expediente_mode.py _SUBMODE_STEP_MAP exactly.
# The integration test suite verifies the actual import matches this.
# ---------------------------------------------------------------------------

_EXPECTED_SUBMODE_STEP_MAP: dict[str, int] = {
    "collect_element_data": 1,
    "collect_base_docs": 2,
    "collect_personal": 3,
    "collect_vehicle": 4,
    "collect_workshop": 5,
    "review_summary": 6,
}

# Guard patterns replicated from expediente_mode.py (Fix C)
_STEP_MISMATCH_RE = re.compile(r"[Pp]aso\s+(\d)\s*/\s*6")
_ADVANCEMENT_RE = re.compile(
    r"siguiente\s+paso|pasemos\s+a"
    r"|continuamos\s+con\s+el\s+paso"
    r"|hemos\s+completado|ya\s+tenemos\s+todo",
    re.IGNORECASE,
)


def _apply_fix_c_guard(
    sub_mode: str,
    response: str,
    step_map: dict[str, int] | None = None,
) -> tuple[str, bool, bool]:
    """
    Apply Fix C guard logic (phase-truthfulness check).
    Mirrors the exact logic from expediente_mode.py kickoff branch.

    Returns:
        (cleaned_response, step_mismatch_fired, advancement_fired)
    """
    if step_map is None:
        step_map = _EXPECTED_SUBMODE_STEP_MAP

    step_mismatch_fired = False
    advancement_fired = False

    expected_step = step_map.get(sub_mode.lower() if sub_mode else "")
    step_match = _STEP_MISMATCH_RE.search(response)
    if (
        step_match
        and expected_step is not None
        and int(step_match.group(1)) != expected_step
    ):
        response = _STEP_MISMATCH_RE.sub("", response).strip()
        step_mismatch_fired = True

    if _ADVANCEMENT_RE.search(response):
        response = _ADVANCEMENT_RE.sub("", response).strip()
        advancement_fired = True

    return response, step_mismatch_fired, advancement_fired


# ---------------------------------------------------------------------------
# D2-B: Production incident regression — Fix B (tombstone protocol)
# ---------------------------------------------------------------------------


class TestD2ProductionIncidentFixB:
    """
    Verify Fix B (tombstone protocol) prevents the F2 component of the
    production incident: stale expediente_transition_marker resurrecting
    from the checkpoint and causing sub_mode to get stuck.

    Incident replay:
    - Turn N: mode sets transition_marker = "collect_vehicle"
    - Turn N+1: mode consumes marker via pop() — BUT without tombstone
    - Turn N+2: merge_dicts resurrects old value from checkpoint!
    - Result: mode keeps triggering on the same marker → sub_mode stuck

    With Fix B:
    - Turn N+1: mode pops marker AND assigns None (tombstone)
    - Turn N+2: merge_dicts keeps the None → marker is gone
    """

    def test_without_tombstone_marker_resurrects(self):
        """
        Control test: demonstrates the pre-fix bug.
        pop() alone does NOT prevent resurrection — this is the root cause.
        """
        turn_n_context = {
            "expediente_transition_marker": "collect_vehicle",
            "expediente_sub_mode": "collect_personal",
            "other_data": "kept",
        }

        # BUG pattern: pop without tombstone
        turn_n1_update = dict(turn_n_context)
        turn_n1_update.pop("expediente_transition_marker")  # No tombstone!

        turn_n1_checkpoint = merge_dicts(current=turn_n_context, update=turn_n1_update)

        # With the bug: absent key in update → checkpoint value survives
        assert (
            turn_n1_checkpoint["expediente_transition_marker"] == "collect_vehicle"
        ), (
            "Control test: absent key in update means checkpoint value survives (pre-fix bug)"
        )

    def test_with_tombstone_marker_stays_none(self):
        """
        Fix B applied: pop() + tombstone (= None) keeps the key as None.
        """
        turn_n_context = {
            "expediente_transition_marker": "collect_vehicle",
            "expediente_sub_mode": "collect_personal",
            "other_data": "kept",
        }

        # Fix B pattern: pop + tombstone
        turn_n1_update = dict(turn_n_context)
        consumed = turn_n1_update.pop("expediente_transition_marker")
        assert consumed == "collect_vehicle"
        turn_n1_update["expediente_transition_marker"] = None  # TOMBSTONE (Fix B)

        turn_n1_checkpoint = merge_dicts(current=turn_n_context, update=turn_n1_update)

        assert turn_n1_checkpoint["expediente_transition_marker"] is None, (
            "After tombstone, merge_dicts must store None"
        )

    def test_tombstoned_marker_does_not_resurrect_on_turn_n2(self):
        """
        Key scenario from the spec: turn N+2 with no marker update must stay None.

        This is the exact production incident scenario: WITHOUT this fix,
        the marker resurfaces on turn N+2 and triggers re-consumption.
        """
        turn_n_context = {
            "expediente_transition_marker": "collect_vehicle",
            "current_step": "collect_vehicle",
            "expediente_sub_mode": "collect_personal",
        }

        # Turn N+1: consume + tombstone
        turn_n1_update = dict(turn_n_context)
        turn_n1_update.pop("expediente_transition_marker")
        turn_n1_update["expediente_transition_marker"] = None  # TOMBSTONE

        turn_n1_checkpoint = merge_dicts(current=turn_n_context, update=turn_n1_update)
        assert turn_n1_checkpoint["expediente_transition_marker"] is None

        # Turn N+2: nothing touches the marker this turn (normal processing)
        turn_n2_update = {
            "expediente_sub_mode": "collect_personal",
            "current_step": "collect_personal",
        }
        turn_n2_checkpoint = merge_dicts(
            current=turn_n1_checkpoint, update=turn_n2_update
        )

        assert turn_n2_checkpoint.get("expediente_transition_marker") is None, (
            "Tombstoned None MUST persist to turn N+2. "
            f"Got: {turn_n2_checkpoint.get('expediente_transition_marker')!r} — "
            "this is the production incident: stale marker resurfaces and triggers re-consumption"
        )

    def test_just_transitioned_from_tombstone(self):
        """just_transitioned_from follows the same tombstone pattern."""
        turn_n_context = {
            "just_transitioned_from": "collect_personal",
            "expediente_sub_mode": "collect_vehicle",
        }

        # Fix B pattern for just_transitioned_from
        turn_n1_update = dict(turn_n_context)
        turn_n1_update.pop("just_transitioned_from")
        turn_n1_update["just_transitioned_from"] = None  # TOMBSTONE

        turn_n1_checkpoint = merge_dicts(current=turn_n_context, update=turn_n1_update)
        assert turn_n1_checkpoint["just_transitioned_from"] is None

        # Turn N+2 — must not resurrect
        turn_n2_update = {"expediente_sub_mode": "collect_vehicle"}
        turn_n2_checkpoint = merge_dicts(
            current=turn_n1_checkpoint, update=turn_n2_update
        )
        assert turn_n2_checkpoint["just_transitioned_from"] is None, (
            "just_transitioned_from must not resurrect after tombstone"
        )

    def test_unrelated_keys_always_survive_tombstone(self):
        """Tombstoning one key must never affect unrelated keys."""
        turn_n_context = {
            "expediente_transition_marker": "collect_vehicle",
            "expediente_sub_mode": "collect_personal",
            "personal_data": {"nombre": "Ana"},
            "case_id": "abc-123",
        }

        turn_n1_update = dict(turn_n_context)
        turn_n1_update.pop("expediente_transition_marker")
        turn_n1_update["expediente_transition_marker"] = None

        checkpoint = merge_dicts(current=turn_n_context, update=turn_n1_update)

        assert checkpoint["expediente_sub_mode"] == "collect_personal"
        assert checkpoint["personal_data"] == {"nombre": "Ana"}
        assert checkpoint["case_id"] == "abc-123"


# ---------------------------------------------------------------------------
# D2-C: Production incident regression — Fix C (kickoff phase guard)
# ---------------------------------------------------------------------------


class TestD2ProductionIncidentFixC:
    """
    Verify Fix C prevents the F3 component of the production incident:
    LLM hallucinates wrong-phase content on kickoff no-tool turns.

    Incident replay:
    - Turn N: sub_mode=collect_personal, no tools called (kickoff turn)
    - LLM generates "Paso 5/6 — Taller de montaje\n¿Quién realizó...?"
    - Without Fix C: response sent verbatim → user sees wrong phase content
    - With Fix C: "Paso 5/6" stripped → user sees sanitized content

    Note: Uses local replica of _SUBMODE_STEP_MAP (no agent import needed).
    Actual imported constant is verified in test_expediente_state_integrity.py.
    """

    def test_production_incident_wrong_phase_stripped(self):
        """
        The exact production incident response: "Paso 5/6 — Taller" in collect_personal.
        Fix C strips it and preserves the rest of the content.
        """
        sub_mode = "collect_personal"
        incident_response = (
            "📍 Paso 5/6 — Taller de montaje\n"
            "¿Quién realizó la instalación del elemento?"
        )

        cleaned, step_mismatch_fired, _ = _apply_fix_c_guard(
            sub_mode, incident_response
        )

        assert step_mismatch_fired is True, (
            "Fix C must detect the step mismatch (5 ≠ 3)"
        )
        assert "Paso 5/6" not in cleaned, (
            "Wrong-phase 'Paso 5/6' must be stripped from collect_personal response"
        )
        assert "Taller de montaje" in cleaned, (
            "Phase content after the wrong-step prefix must be preserved"
        )
        assert "instalación" in cleaned, (
            "Question content must survive the strip operation"
        )

    def test_correct_phase_not_stripped(self):
        """Correct 'Paso 3/6' in collect_personal must NOT be stripped."""
        sub_mode = "collect_personal"
        correct_response = (
            "📍 Paso 3/6 — Datos personales\n¿Me podrías dar tu nombre completo?"
        )

        cleaned, step_mismatch_fired, _ = _apply_fix_c_guard(sub_mode, correct_response)

        assert step_mismatch_fired is False, (
            "Correct step number must NOT trigger the guard"
        )
        assert "Paso 3/6" in cleaned, "Correct step number must survive"
        assert "Datos personales" in cleaned

    @pytest.mark.parametrize(
        "sub_mode,correct_step,wrong_step",
        [
            ("collect_element_data", 1, 5),
            ("collect_base_docs", 2, 6),
            ("collect_personal", 3, 5),
            ("collect_vehicle", 4, 1),
            ("collect_workshop", 5, 3),
            ("review_summary", 6, 2),
        ],
    )
    def test_all_submodes_mismatch_detection(self, sub_mode, correct_step, wrong_step):
        """
        Parametrized: Fix C correctly identifies mismatches for all 6 sub-modes.
        This validates the guard works across all phases.
        """
        # Validate the local spec map
        assert _EXPECTED_SUBMODE_STEP_MAP.get(sub_mode) == correct_step, (
            f"_EXPECTED_SUBMODE_STEP_MAP[{sub_mode!r}] should be {correct_step}"
        )

        # Wrong step MUST be stripped
        wrong_response = f"Paso {wrong_step}/6 — contenido del paso {wrong_step}"
        cleaned_wrong, fired_wrong, _ = _apply_fix_c_guard(sub_mode, wrong_response)
        assert fired_wrong, (
            f"Guard must fire for sub_mode={sub_mode!r}, wrong step {wrong_step}"
        )
        assert f"Paso {wrong_step}/6" not in cleaned_wrong

        # Correct step must NOT be stripped
        correct_response = f"Paso {correct_step}/6 — contenido correcto"
        cleaned_correct, fired_correct, _ = _apply_fix_c_guard(
            sub_mode, correct_response
        )
        assert not fired_correct, (
            f"Guard must NOT fire for sub_mode={sub_mode!r}, correct step {correct_step}"
        )
        assert f"Paso {correct_step}/6" in cleaned_correct

    @pytest.mark.parametrize(
        "phrase,expected_stripped",
        [
            ("Pasemos al siguiente paso.", True),
            ("Siguiente paso: datos del vehículo.", True),
            ("Continuamos con el paso de datos personales.", True),
            ("Hemos completado la sección de datos personales.", True),
            ("Ya tenemos todo lo necesario para continuar.", True),
            # Phrases that should NOT trigger the guard
            ("¿Cuál es tu nombre completo?", False),
            ("Perfecto, muchas gracias.", False),
            ("¿Me puedes dar tu DNI?", False),
        ],
    )
    def test_advancement_language_detection(self, phrase, expected_stripped):
        """
        Advancement language on kickoff no-tool turns must be stripped.
        Non-advancement phrases must pass through unchanged.
        """
        # Use collect_personal (no step number involved) to isolate advancement guard
        sub_mode = "collect_personal"

        _, _, advancement_fired = _apply_fix_c_guard(sub_mode, phrase)

        assert advancement_fired == expected_stripped, (
            f"Advancement guard for {phrase!r}: expected fired={expected_stripped}, "
            f"got fired={advancement_fired}"
        )

    def test_combined_wrong_step_and_advancement_phrase(self):
        """
        A response with BOTH a wrong step number AND advancement language:
        both guards must fire and both artifacts must be stripped.
        """
        sub_mode = "collect_personal"
        # Wrong step (5) + advancement language in collect_personal
        response = "Paso 5/6 — Taller\nHemos completado los datos, pasemos al taller."

        cleaned, step_mismatch_fired, advancement_fired = _apply_fix_c_guard(
            sub_mode, response
        )

        assert step_mismatch_fired is True, "Step mismatch guard must fire"
        assert advancement_fired is True, "Advancement guard must fire"
        assert "Paso 5/6" not in cleaned
        assert "pasemos al" not in cleaned.lower()


# ---------------------------------------------------------------------------
# D2-map: _SUBMODE_STEP_MAP spec-level constant integrity
# ---------------------------------------------------------------------------


class TestD2SubmodestepMapSpecIntegrity:
    """
    Verify the _SUBMODE_STEP_MAP spec-level mapping is complete and correct.

    These tests exercise the LOCAL constant. The integration test suite
    (test_expediente_state_integrity.py) exercises the actual imported constant
    from expediente_mode.py against this same spec.

    If these tests fail, it means the spec mapping has drifted from the tests —
    update _EXPECTED_SUBMODE_STEP_MAP to match the spec.
    """

    def test_expected_map_has_all_six_submodes(self):
        """All 6 sub-modes must be present."""
        required = {
            "collect_element_data",
            "collect_base_docs",
            "collect_personal",
            "collect_vehicle",
            "collect_workshop",
            "review_summary",
        }
        for sub_mode in required:
            assert sub_mode in _EXPECTED_SUBMODE_STEP_MAP, (
                f"Missing sub_mode in _EXPECTED_SUBMODE_STEP_MAP: {sub_mode!r}"
            )

    def test_expected_map_steps_are_1_through_6(self):
        """Steps must be exactly 1–6 with no duplicates."""
        step_values = list(_EXPECTED_SUBMODE_STEP_MAP.values())
        assert sorted(step_values) == [1, 2, 3, 4, 5, 6], (
            f"_EXPECTED_SUBMODE_STEP_MAP must contain steps 1–6. Got: {sorted(step_values)}"
        )

    def test_expected_map_no_duplicate_steps(self):
        """Each step number must map to exactly one sub-mode."""
        step_values = list(_EXPECTED_SUBMODE_STEP_MAP.values())
        assert len(step_values) == len(set(step_values)), (
            "Each step number must be unique — no two sub-modes share a step"
        )
