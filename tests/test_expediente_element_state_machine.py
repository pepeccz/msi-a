"""
Tests for TASK-05 (7-state element state machine) and TASK-06 (progress prefix injection)
— expediente-flow-redesign change.

Module-level helpers tested:
  - _get_element_state()        : read state with legacy backward-compat fallback
  - _set_element_state()        : write state (validate, partial update, create-on-write)
  - _initialize_element_states(): idempotent init from legacy flags
  - _inject_step_prefix()       : prepend "📍 Paso X/6" header (TASK-06)

All tests are pure unit tests — no DB, Redis or LLM calls required.
"""

import pytest
from typing import Any

from agent.modes.expediente_mode import (
    # TASK-05 helpers
    ELEMENT_STATE_AWAITING_PHOTOS,
    ELEMENT_STATE_PHOTOS_RECEIVED,
    ELEMENT_STATE_CONFIRMING_PHOTOS,
    ELEMENT_STATE_RETRY_PHOTOS,
    ELEMENT_STATE_PHOTOS_CONFIRMED,
    ELEMENT_STATE_DATA_COLLECTION,
    ELEMENT_STATE_ELEMENT_COMPLETE,
    ELEMENT_STATES,
    _get_element_state,
    _set_element_state,
    _initialize_element_states,
    # TASK-06 helpers
    EXPEDIENTE_STEP_PREFIX,
    _inject_step_prefix,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mc(**kwargs: Any) -> dict[str, Any]:
    """Build a minimal mode_context dict for testing."""
    return dict(kwargs)


def _entry(state: str, photos_count: int = 0, data_complete: bool = False) -> dict[str, Any]:
    """Build an element_states entry dict."""
    return {"state": state, "photos_count": photos_count, "data_complete": data_complete}


# ===========================================================================
# TestGetElementState
# ===========================================================================

class TestGetElementState:
    """Unit tests for _get_element_state()."""

    # ------------------------------------------------------------------
    # Happy-path: reading from element_states dict
    # ------------------------------------------------------------------

    def test_returns_state_when_present_in_element_states(self):
        """
        GIVEN mode_context["element_states"]["ESCAPE"]["state"] == "photos_received"
        WHEN  _get_element_state is called
        THEN  returns "photos_received"
        """
        mc = _mc(element_states={"ESCAPE": _entry(ELEMENT_STATE_PHOTOS_RECEIVED)})
        assert _get_element_state(mc, "ESCAPE") == ELEMENT_STATE_PHOTOS_RECEIVED

    def test_returns_correct_state_for_requested_code_among_many(self):
        """
        GIVEN multiple elements in element_states
        WHEN  _get_element_state is called for a specific code
        THEN  returns only that element's state
        """
        mc = _mc(element_states={
            "ESCAPE":    _entry(ELEMENT_STATE_ELEMENT_COMPLETE, data_complete=True),
            "SUSPENSION": _entry(ELEMENT_STATE_AWAITING_PHOTOS),
        })
        assert _get_element_state(mc, "ESCAPE") == ELEMENT_STATE_ELEMENT_COMPLETE
        assert _get_element_state(mc, "SUSPENSION") == ELEMENT_STATE_AWAITING_PHOTOS

    @pytest.mark.parametrize("state", list(ELEMENT_STATES))
    def test_all_valid_states_are_readable(self, state: str):
        """
        GIVEN each of the 7 valid ELEMENT_STATE_* strings stored in element_states
        WHEN  _get_element_state is called
        THEN  returns that exact state string
        """
        mc = _mc(element_states={"ELEM": _entry(state)})
        assert _get_element_state(mc, "ELEM") == state

    # ------------------------------------------------------------------
    # Legacy fallback: element_states absent or empty
    # ------------------------------------------------------------------

    def test_legacy_fallback_completed_maps_to_element_complete(self):
        """
        GIVEN element_states is absent (legacy checkpoint)
        AND   element_data_status["SUBCHASIS"] == "completed"
        WHEN  _get_element_state is called
        THEN  returns ELEMENT_STATE_ELEMENT_COMPLETE
        """
        mc = _mc(element_data_status={"SUBCHASIS": "completed"})
        assert _get_element_state(mc, "SUBCHASIS") == ELEMENT_STATE_ELEMENT_COMPLETE

    def test_legacy_fallback_pending_data_maps_to_data_collection(self):
        """
        GIVEN element_states is absent (legacy checkpoint)
        AND   element_data_status["ESCAPE"] == "pending_data"
        WHEN  _get_element_state is called
        THEN  returns ELEMENT_STATE_DATA_COLLECTION
        """
        mc = _mc(element_data_status={"ESCAPE": "pending_data"})
        assert _get_element_state(mc, "ESCAPE") == ELEMENT_STATE_DATA_COLLECTION

    def test_legacy_fallback_current_element_in_data_phase(self):
        """
        GIVEN element_states is absent
        AND   element_data_status has no entry for element (treated as pending_photos)
        AND   the element IS the current element (matching element_codes[current_element_index])
        AND   element_phase == "data"
        WHEN  _get_element_state is called
        THEN  returns ELEMENT_STATE_DATA_COLLECTION
        """
        mc = _mc(
            element_codes=["MANILLAR", "SUSPENSION"],
            current_element_index=1,
            element_phase="data",
            element_data_status={"MANILLAR": "completed"},
        )
        assert _get_element_state(mc, "SUSPENSION") == ELEMENT_STATE_DATA_COLLECTION

    def test_legacy_fallback_current_element_in_photos_phase(self):
        """
        GIVEN element_states is absent
        AND   element_codes[current_element_index] == "MANILLAR"
        AND   element_phase == "photos"
        WHEN  _get_element_state is called for "MANILLAR"
        THEN  returns ELEMENT_STATE_AWAITING_PHOTOS
        """
        mc = _mc(
            element_codes=["MANILLAR"],
            current_element_index=0,
            element_phase="photos",
        )
        assert _get_element_state(mc, "MANILLAR") == ELEMENT_STATE_AWAITING_PHOTOS

    def test_legacy_fallback_non_current_element_defaults_to_awaiting_photos(self):
        """
        GIVEN element_states is absent
        AND   element_data_status has no entry for "ESCAPE" (non-current element)
        WHEN  _get_element_state is called for "ESCAPE"
        THEN  returns ELEMENT_STATE_AWAITING_PHOTOS (default)
        """
        mc = _mc(
            element_codes=["MANILLAR", "ESCAPE"],
            current_element_index=0,
            element_phase="photos",
            element_data_status={},
        )
        assert _get_element_state(mc, "ESCAPE") == ELEMENT_STATE_AWAITING_PHOTOS

    def test_completely_empty_mode_context_defaults_to_awaiting_photos(self):
        """
        GIVEN mode_context is empty (fresh start, no legacy data)
        WHEN  _get_element_state is called
        THEN  returns ELEMENT_STATE_AWAITING_PHOTOS (safest default)
        """
        mc: dict[str, Any] = {}
        assert _get_element_state(mc, "ESCAPE") == ELEMENT_STATE_AWAITING_PHOTOS

    def test_element_states_entry_with_invalid_state_triggers_legacy_fallback(self):
        """
        GIVEN element_states["ELEM"]["state"] is an unrecognized string (data corruption)
        WHEN  _get_element_state is called
        THEN  falls back to legacy derivation (returns ELEMENT_STATE_AWAITING_PHOTOS
              because element_data_status is also absent)
        """
        mc = _mc(element_states={"ELEM": {"state": "INVALID_STATE", "photos_count": 0}})
        # Invalid state in element_states → should NOT return the invalid value
        result = _get_element_state(mc, "ELEM")
        assert result in ELEMENT_STATES, (
            f"Expected a valid ELEMENT_STATE_* constant, got: {result!r}"
        )


# ===========================================================================
# TestSetElementState
# ===========================================================================

class TestSetElementState:
    """Unit tests for _set_element_state()."""

    def test_creates_element_states_dict_when_absent(self):
        """
        GIVEN mode_context has no element_states key
        WHEN  _set_element_state is called
        THEN  mode_context["element_states"] is created and the entry is stored
        """
        mc: dict[str, Any] = {}
        _set_element_state(mc, "ESCAPE", ELEMENT_STATE_PHOTOS_RECEIVED)
        assert "element_states" in mc
        assert mc["element_states"]["ESCAPE"]["state"] == ELEMENT_STATE_PHOTOS_RECEIVED

    def test_default_photos_count_is_zero(self):
        """
        GIVEN mode_context has no element_states
        WHEN  _set_element_state is called without photos_count
        THEN  entry["photos_count"] defaults to 0
        """
        mc: dict[str, Any] = {}
        _set_element_state(mc, "ESCAPE", ELEMENT_STATE_AWAITING_PHOTOS)
        assert mc["element_states"]["ESCAPE"]["photos_count"] == 0

    def test_default_data_complete_is_false(self):
        """
        GIVEN mode_context has no element_states
        WHEN  _set_element_state is called without data_complete
        THEN  entry["data_complete"] defaults to False
        """
        mc: dict[str, Any] = {}
        _set_element_state(mc, "ESCAPE", ELEMENT_STATE_AWAITING_PHOTOS)
        assert mc["element_states"]["ESCAPE"]["data_complete"] is False

    def test_explicit_photos_count_is_stored(self):
        """
        GIVEN photos_count=7 is passed
        WHEN  _set_element_state is called
        THEN  entry["photos_count"] == 7
        """
        mc: dict[str, Any] = {}
        _set_element_state(mc, "ESCAPE", ELEMENT_STATE_PHOTOS_RECEIVED, photos_count=7)
        assert mc["element_states"]["ESCAPE"]["photos_count"] == 7

    def test_explicit_data_complete_true_is_stored(self):
        """
        GIVEN data_complete=True is passed
        WHEN  _set_element_state is called
        THEN  entry["data_complete"] is True
        """
        mc: dict[str, Any] = {}
        _set_element_state(mc, "ESCAPE", ELEMENT_STATE_ELEMENT_COMPLETE, data_complete=True)
        assert mc["element_states"]["ESCAPE"]["data_complete"] is True

    def test_partial_update_preserves_photos_count_when_omitted(self):
        """
        GIVEN an existing entry with photos_count=5
        WHEN  _set_element_state is called WITHOUT photos_count
        THEN  photos_count remains 5 (not reset to 0)
        """
        mc = _mc(element_states={"ESCAPE": _entry(ELEMENT_STATE_PHOTOS_RECEIVED, photos_count=5)})
        _set_element_state(mc, "ESCAPE", ELEMENT_STATE_CONFIRMING_PHOTOS)
        assert mc["element_states"]["ESCAPE"]["photos_count"] == 5

    def test_partial_update_preserves_data_complete_when_omitted(self):
        """
        GIVEN an existing entry with data_complete=True
        WHEN  _set_element_state is called WITHOUT data_complete
        THEN  data_complete remains True (not reset to False)
        """
        mc = _mc(element_states={
            "ESCAPE": _entry(ELEMENT_STATE_DATA_COLLECTION, data_complete=True)
        })
        _set_element_state(mc, "ESCAPE", ELEMENT_STATE_ELEMENT_COMPLETE)
        assert mc["element_states"]["ESCAPE"]["data_complete"] is True

    def test_state_transitions_overwrite_previous_state(self):
        """
        GIVEN an existing entry with state == awaiting_photos
        WHEN  _set_element_state is called with state == photos_confirmed
        THEN  entry["state"] == "photos_confirmed"
        """
        mc = _mc(element_states={"ESCAPE": _entry(ELEMENT_STATE_AWAITING_PHOTOS)})
        _set_element_state(mc, "ESCAPE", ELEMENT_STATE_PHOTOS_CONFIRMED)
        assert mc["element_states"]["ESCAPE"]["state"] == ELEMENT_STATE_PHOTOS_CONFIRMED

    def test_invalid_state_is_rejected_and_does_not_mutate(self):
        """
        GIVEN state is not one of the ELEMENT_STATE_* constants
        WHEN  _set_element_state is called
        THEN  mode_context["element_states"] is NOT modified
              (defensive: invalid state is logged and silently ignored)
        """
        mc = _mc(element_states={"ESCAPE": _entry(ELEMENT_STATE_AWAITING_PHOTOS)})
        original_state = mc["element_states"]["ESCAPE"]["state"]
        _set_element_state(mc, "ESCAPE", "NOT_A_REAL_STATE")
        assert mc["element_states"]["ESCAPE"]["state"] == original_state

    def test_multiple_elements_stored_independently(self):
        """
        GIVEN two elements written in sequence
        WHEN  _set_element_state is called for each
        THEN  both entries co-exist independently
        """
        mc: dict[str, Any] = {}
        _set_element_state(mc, "ESCAPE", ELEMENT_STATE_ELEMENT_COMPLETE, data_complete=True)
        _set_element_state(mc, "SUSPENSION", ELEMENT_STATE_AWAITING_PHOTOS)
        assert mc["element_states"]["ESCAPE"]["state"] == ELEMENT_STATE_ELEMENT_COMPLETE
        assert mc["element_states"]["SUSPENSION"]["state"] == ELEMENT_STATE_AWAITING_PHOTOS
        assert mc["element_states"]["ESCAPE"]["data_complete"] is True
        assert mc["element_states"]["SUSPENSION"]["data_complete"] is False

    @pytest.mark.parametrize("state", list(ELEMENT_STATES))
    def test_all_valid_states_accepted(self, state: str):
        """
        GIVEN each of the 7 ELEMENT_STATE_* strings
        WHEN  _set_element_state is called
        THEN  entry["state"] equals that string (all states accepted)
        """
        mc: dict[str, Any] = {}
        _set_element_state(mc, "ELEM", state)
        assert mc["element_states"]["ELEM"]["state"] == state


# ===========================================================================
# TestInitializeElementStates
# ===========================================================================

class TestInitializeElementStates:
    """Unit tests for _initialize_element_states()."""

    def test_initializes_all_elements_to_awaiting_photos_when_no_legacy(self):
        """
        GIVEN mode_context has no element_data_status (fresh start)
        AND   element_codes = ["ESCAPE", "MANILLAR"]
        WHEN  _initialize_element_states is called
        THEN  both elements get state == ELEMENT_STATE_AWAITING_PHOTOS
        """
        mc: dict[str, Any] = {}
        _initialize_element_states(mc, ["ESCAPE", "MANILLAR"])
        assert mc["element_states"]["ESCAPE"]["state"] == ELEMENT_STATE_AWAITING_PHOTOS
        assert mc["element_states"]["MANILLAR"]["state"] == ELEMENT_STATE_AWAITING_PHOTOS

    def test_idempotent_does_not_overwrite_existing_entries(self):
        """
        GIVEN "ESCAPE" is already initialized with state == "photos_confirmed"
        WHEN  _initialize_element_states is called again
        THEN  "ESCAPE" state is preserved (not reset)
        """
        mc = _mc(element_states={
            "ESCAPE": _entry(ELEMENT_STATE_PHOTOS_CONFIRMED, photos_count=3)
        })
        _initialize_element_states(mc, ["ESCAPE", "MANILLAR"])
        # ESCAPE must be preserved
        assert mc["element_states"]["ESCAPE"]["state"] == ELEMENT_STATE_PHOTOS_CONFIRMED
        assert mc["element_states"]["ESCAPE"]["photos_count"] == 3
        # MANILLAR was new → gets default
        assert mc["element_states"]["MANILLAR"]["state"] == ELEMENT_STATE_AWAITING_PHOTOS

    def test_derives_element_complete_from_legacy_completed_status(self):
        """
        GIVEN element_data_status["ESCAPE"] == "completed"
        WHEN  _initialize_element_states is called
        THEN  ESCAPE is initialized to ELEMENT_STATE_ELEMENT_COMPLETE
        AND   data_complete is True
        """
        mc = _mc(element_data_status={"ESCAPE": "completed"})
        _initialize_element_states(mc, ["ESCAPE", "MANILLAR"])
        assert mc["element_states"]["ESCAPE"]["state"] == ELEMENT_STATE_ELEMENT_COMPLETE
        assert mc["element_states"]["ESCAPE"]["data_complete"] is True

    def test_derives_data_collection_from_legacy_pending_data_status(self):
        """
        GIVEN element_data_status["ESCAPE"] == "pending_data"
        WHEN  _initialize_element_states is called
        THEN  ESCAPE is initialized to ELEMENT_STATE_DATA_COLLECTION
        AND   data_complete is False
        """
        mc = _mc(element_data_status={"ESCAPE": "pending_data"})
        _initialize_element_states(mc, ["ESCAPE"])
        assert mc["element_states"]["ESCAPE"]["state"] == ELEMENT_STATE_DATA_COLLECTION
        assert mc["element_states"]["ESCAPE"]["data_complete"] is False

    def test_missing_legacy_status_defaults_to_awaiting_photos(self):
        """
        GIVEN element_data_status exists but has no entry for "MANILLAR"
        WHEN  _initialize_element_states is called
        THEN  MANILLAR defaults to ELEMENT_STATE_AWAITING_PHOTOS
        """
        mc = _mc(element_data_status={"ESCAPE": "completed"})
        _initialize_element_states(mc, ["ESCAPE", "MANILLAR"])
        assert mc["element_states"]["MANILLAR"]["state"] == ELEMENT_STATE_AWAITING_PHOTOS

    def test_empty_element_codes_is_a_noop(self):
        """
        GIVEN element_codes is empty list
        WHEN  _initialize_element_states is called
        THEN  mode_context is unchanged (no element_states key created)
        """
        mc: dict[str, Any] = {}
        _initialize_element_states(mc, [])
        assert "element_states" not in mc

    def test_creates_element_states_dict_when_absent(self):
        """
        GIVEN mode_context has no element_states key
        WHEN  _initialize_element_states is called
        THEN  element_states dict is created
        """
        mc: dict[str, Any] = {}
        _initialize_element_states(mc, ["ESCAPE"])
        assert "element_states" in mc
        assert isinstance(mc["element_states"], dict)

    def test_recovery_path_partial_completion(self):
        """
        Integration: Simulates an agent re-entry after a crash mid-collection.

        GIVEN element_data_status shows ESCAPE=completed, SUSPENSION=pending_data,
              MANILLAR has no entry (still pending_photos)
        AND   element_states already has a valid entry for ESCAPE (from before crash)
        WHEN  _initialize_element_states is called
        THEN  ESCAPE is preserved, SUSPENSION is set to data_collection,
              MANILLAR defaults to awaiting_photos
        """
        mc = _mc(
            element_data_status={
                "ESCAPE": "completed",
                "SUSPENSION": "pending_data",
            },
            element_states={
                "ESCAPE": _entry(ELEMENT_STATE_ELEMENT_COMPLETE, data_complete=True),
            },
        )
        _initialize_element_states(mc, ["ESCAPE", "SUSPENSION", "MANILLAR"])

        # ESCAPE: already present → preserved
        assert mc["element_states"]["ESCAPE"]["state"] == ELEMENT_STATE_ELEMENT_COMPLETE
        assert mc["element_states"]["ESCAPE"]["data_complete"] is True

        # SUSPENSION: not in element_states → derived from legacy
        assert mc["element_states"]["SUSPENSION"]["state"] == ELEMENT_STATE_DATA_COLLECTION

        # MANILLAR: not in element_states, not in legacy → default
        assert mc["element_states"]["MANILLAR"]["state"] == ELEMENT_STATE_AWAITING_PHOTOS

    def test_all_elements_get_photos_count_initialized_to_zero(self):
        """
        GIVEN a fresh mode_context with no element_states
        WHEN  _initialize_element_states is called for two elements
        THEN  photos_count is 0 for both (never None)
        """
        mc: dict[str, Any] = {}
        _initialize_element_states(mc, ["ESCAPE", "MANILLAR"])
        for code in ["ESCAPE", "MANILLAR"]:
            assert mc["element_states"][code]["photos_count"] == 0


# ===========================================================================
# TestInjectStepPrefix (TASK-06)
# ===========================================================================

class TestInjectStepPrefix:
    """Unit tests for _inject_step_prefix()."""

    # ------------------------------------------------------------------
    # Known sub-modes → correct prefix
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("sub_mode,expected_prefix", [
        ("collect_element_data", "📍 Paso 1/6 — Documentación de elementos"),
        ("collect_base_docs",    "📍 Paso 2/6 — Documentación base"),
        ("collect_personal",     "📍 Paso 3/6 — Datos personales"),
        ("collect_vehicle",      "📍 Paso 4/6 — Datos del vehículo"),
        ("collect_workshop",     "📍 Paso 5/6 — Certificado del taller"),
        ("review_summary",       "📍 Paso 6/6 — Revisión final"),
    ])
    def test_prepends_correct_prefix_for_each_sub_mode(self, sub_mode: str, expected_prefix: str):
        """
        GIVEN a valid sub_mode with a registered prefix
        WHEN  _inject_step_prefix is called with a plain message
        THEN  the result starts with the correct prefix string
        """
        msg = "Por favor, envía las fotos del elemento."
        result = _inject_step_prefix(msg, sub_mode)
        assert result.startswith(expected_prefix), (
            f"Expected prefix '{expected_prefix}' for sub_mode='{sub_mode}'. Got: {result!r}"
        )

    def test_prefix_and_message_separated_by_double_newline(self):
        """
        GIVEN a valid sub_mode
        WHEN  _inject_step_prefix is called
        THEN  prefix and message are separated by a blank line (\\n\\n)
        """
        msg = "Aquí va tu mensaje."
        result = _inject_step_prefix(msg, "collect_personal")
        prefix = EXPEDIENTE_STEP_PREFIX["collect_personal"]
        assert result == f"{prefix}\n\n{msg}"

    # ------------------------------------------------------------------
    # Idempotency guard
    # ------------------------------------------------------------------

    def test_already_prefixed_message_is_returned_unchanged(self):
        """
        GIVEN a message that already starts with '📍 Paso'
        WHEN  _inject_step_prefix is called
        THEN  the message is returned unchanged (no double prefix)
        """
        prefixed = "📍 Paso 3/6 — Datos personales\n\nNecesito tu nombre completo."
        result = _inject_step_prefix(prefixed, "collect_personal")
        assert result == prefixed

    def test_idempotency_different_sub_mode_does_not_double_prefix(self):
        """
        GIVEN a message already prefixed with Paso 1/6
        WHEN  _inject_step_prefix is called with sub_mode="collect_personal"
        THEN  the original message is returned unchanged (idempotency wins)
        """
        msg = "📍 Paso 1/6 — Documentación de elementos\n\nEnvía las fotos."
        result = _inject_step_prefix(msg, "collect_personal")
        assert result == msg

    # ------------------------------------------------------------------
    # Unknown / empty sub_mode
    # ------------------------------------------------------------------

    def test_unknown_sub_mode_returns_message_unchanged(self):
        """
        GIVEN sub_mode is not in EXPEDIENTE_STEP_PREFIX
        WHEN  _inject_step_prefix is called
        THEN  message is returned unchanged (no prefix appended)
        """
        msg = "Mensaje sin contexto de sub-modo."
        result = _inject_step_prefix(msg, "unknown_sub_mode")
        assert result == msg

    def test_empty_sub_mode_returns_message_unchanged(self):
        """
        GIVEN sub_mode is an empty string
        WHEN  _inject_step_prefix is called
        THEN  message is returned unchanged
        """
        msg = "Mensaje de prueba."
        result = _inject_step_prefix(msg, "")
        assert result == msg

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_empty_message_returns_empty_string(self):
        """
        GIVEN message is an empty string
        WHEN  _inject_step_prefix is called with a valid sub_mode
        THEN  returns the empty string unchanged
        """
        result = _inject_step_prefix("", "collect_personal")
        assert result == ""

    def test_multiline_message_gets_prefix(self):
        """
        GIVEN a multi-line message
        WHEN  _inject_step_prefix is called
        THEN  prefix is prepended correctly (body lines are preserved)
        """
        msg = "Necesito:\n- Tu nombre\n- Tu DNI\n- Tu email"
        result = _inject_step_prefix(msg, "collect_personal")
        expected_prefix = EXPEDIENTE_STEP_PREFIX["collect_personal"]
        assert result.startswith(expected_prefix)
        assert "Necesito:" in result
        assert "- Tu nombre" in result

    def test_prefix_dict_has_exactly_six_entries(self):
        """
        EXPEDIENTE_STEP_PREFIX must have exactly 6 entries — one per step.
        This test documents the contract and protects against accidental additions/removals.
        """
        assert len(EXPEDIENTE_STEP_PREFIX) == 6, (
            f"Expected exactly 6 sub-mode prefixes in EXPEDIENTE_STEP_PREFIX. "
            f"Got {len(EXPEDIENTE_STEP_PREFIX)}: {list(EXPEDIENTE_STEP_PREFIX.keys())}"
        )

    @pytest.mark.parametrize("sub_mode", [
        "collect_element_data",
        "collect_base_docs",
        "collect_personal",
        "collect_vehicle",
        "collect_workshop",
        "review_summary",
    ])
    def test_all_six_sub_modes_have_registered_prefix(self, sub_mode: str):
        """
        All 6 EXPEDIENTE sub-modes must have a non-empty prefix registered
        in EXPEDIENTE_STEP_PREFIX (prevents silent no-op on new sub-modes).
        """
        prefix = EXPEDIENTE_STEP_PREFIX.get(sub_mode, "")
        assert prefix, f"Sub-mode '{sub_mode}' has no entry in EXPEDIENTE_STEP_PREFIX"
        assert "📍 Paso" in prefix, (
            f"Prefix for '{sub_mode}' must contain '📍 Paso'. Got: {prefix!r}"
        )


# ===========================================================================
# TestElementStateConstants
# ===========================================================================

class TestElementStateConstants:
    """Sanity checks for the ELEMENT_STATES frozenset and constants."""

    def test_element_states_frozenset_has_seven_values(self):
        """There must be exactly 7 states in ELEMENT_STATES."""
        assert len(ELEMENT_STATES) == 7

    @pytest.mark.parametrize("const,value", [
        (ELEMENT_STATE_AWAITING_PHOTOS,   "awaiting_photos"),
        (ELEMENT_STATE_PHOTOS_RECEIVED,   "photos_received"),
        (ELEMENT_STATE_CONFIRMING_PHOTOS, "confirming_photos"),
        (ELEMENT_STATE_RETRY_PHOTOS,      "retry_photos"),
        (ELEMENT_STATE_PHOTOS_CONFIRMED,  "photos_confirmed"),
        (ELEMENT_STATE_DATA_COLLECTION,   "data_collection"),
        (ELEMENT_STATE_ELEMENT_COMPLETE,  "element_complete"),
    ])
    def test_constant_has_expected_string_value(self, const: str, value: str):
        """Each ELEMENT_STATE_* constant must equal its documented string value."""
        assert const == value, (
            f"Constant mismatch: expected {value!r}, got {const!r}. "
            "Update openspec docs if this was intentional."
        )

    def test_all_constants_are_in_element_states_frozenset(self):
        """Every ELEMENT_STATE_* constant must appear in ELEMENT_STATES."""
        for const in [
            ELEMENT_STATE_AWAITING_PHOTOS,
            ELEMENT_STATE_PHOTOS_RECEIVED,
            ELEMENT_STATE_CONFIRMING_PHOTOS,
            ELEMENT_STATE_RETRY_PHOTOS,
            ELEMENT_STATE_PHOTOS_CONFIRMED,
            ELEMENT_STATE_DATA_COLLECTION,
            ELEMENT_STATE_ELEMENT_COMPLETE,
        ]:
            assert const in ELEMENT_STATES, (
                f"Constant {const!r} is not in ELEMENT_STATES frozenset"
            )
