"""Tests for ADR-006 case_collection merge semantics.

Validates that the inline {**existing, **updates} merge pattern properly
ACCUMULATES chained calls instead of overwriting, which was the root cause
of state propagation bugs where transition + subsequent update lost fields.

Bug context:
    step1 = {**existing, "step": "collect_base_docs"}        # sets step
    step2 = {**step1_cc, "element_data_status": {...}}        # adds status
    # Before fix: step2 LOST "step" (overwrite)
    # After fix:  step2 KEEPS "step" (merge)

These tests verify the inline merge pattern used across case_tools.py and
element_data_tools.py.
"""

import pytest
from copy import deepcopy

from agent.utils.expediente_types import CollectionStep


# ---------------------------------------------------------------------------
# Helpers — replicate the inline merge pattern used in production code
# ---------------------------------------------------------------------------

def _update_case_fsm_state(fsm_state: dict | None, updates: dict) -> dict:
    """Inline merge pattern from case_tools / element_data_tools.

    Mirrors the ADR-006 merge semantics:
        existing = fsm_state.get("case_collection", {}) if isinstance(fsm_state, dict) else {}
        return {"case_collection": {**existing, **updates}}
    """
    existing = fsm_state.get("case_collection", {}) if isinstance(fsm_state, dict) else {}
    return {"case_collection": {**existing, **updates}}


def _transition_to(fsm_state: dict | None, target: CollectionStep) -> dict:
    """Inline transition pattern — just sets step via merge."""
    return _update_case_fsm_state(fsm_state, {"step": target.value})


class TestInlineMergeSemantics:
    """Test that the inline {**existing, **updates} pattern properly merges chained calls."""

    def test_single_call_wraps_in_case_collection(self):
        """Single call wraps updates in case_collection key."""
        result = _update_case_fsm_state(None, {"element_phase": "data"})
        assert result == {"case_collection": {"element_phase": "data"}}

    def test_single_call_with_none_fsm_state(self):
        """Works with None as fsm_state."""
        result = _update_case_fsm_state(None, {"step": "collect_base_docs"})
        assert result["case_collection"]["step"] == "collect_base_docs"

    def test_single_call_with_empty_dict(self):
        """Works with empty dict as fsm_state."""
        result = _update_case_fsm_state({}, {"step": "collect_base_docs"})
        assert result["case_collection"]["step"] == "collect_base_docs"

    def test_chained_calls_accumulate(self):
        """Chained calls accumulate fields, not overwrite."""
        step1 = _update_case_fsm_state(None, {"step": "collect_base_docs"})
        step2 = _update_case_fsm_state(step1, {"element_data_status": {"SUBCHASIS": "complete"}})

        case_coll = step2["case_collection"]
        assert "step" in case_coll, "step from first call must survive"
        assert "element_data_status" in case_coll, "new field must be added"
        assert case_coll["step"] == "collect_base_docs"
        assert case_coll["element_data_status"] == {"SUBCHASIS": "complete"}

    def test_triple_chain_accumulates(self):
        """Three chained calls all accumulate."""
        step1 = _update_case_fsm_state(None, {"step": "collect_personal"})
        step2 = _update_case_fsm_state(step1, {"personal_data": {"name": "Juan"}})
        step3 = _update_case_fsm_state(step2, {"personal_complete": True})

        case_coll = step3["case_collection"]
        assert case_coll["step"] == "collect_personal"
        assert case_coll["personal_data"] == {"name": "Juan"}
        assert case_coll["personal_complete"] is True

    def test_later_call_overrides_same_key(self):
        """Later call overrides the same key (update semantics)."""
        step1 = _update_case_fsm_state(None, {"element_phase": "photos"})
        step2 = _update_case_fsm_state(step1, {"element_phase": "data"})

        assert step2["case_collection"]["element_phase"] == "data"

    def test_does_not_mutate_input(self):
        """Input fsm_state is not mutated."""
        step1 = _update_case_fsm_state(None, {"step": "collect_base_docs"})
        original_keys = set(step1["case_collection"].keys())

        _update_case_fsm_state(step1, {"new_field": "value"})

        assert set(step1["case_collection"].keys()) == original_keys

    def test_transition_then_update_preserves_step(self):
        """Simulates the real-world pattern: transition + update."""
        step1 = _update_case_fsm_state(None, {"step": "collect_base_docs"})
        step2 = _update_case_fsm_state(step1, {"element_data_status": {"ESC": "done"}})

        case_coll = step2["case_collection"]
        assert case_coll["step"] == "collect_base_docs", "transition step must survive"
        assert case_coll["element_data_status"] == {"ESC": "done"}, "status must be added"


class TestTransitionMerge:
    """Test that the inline transition pattern integrates with merge semantics."""

    def test_transition_returns_case_collection(self):
        """Transition wraps step in case_collection."""
        result = _transition_to(None, CollectionStep.COLLECT_BASE_DOCS)
        assert result == {"case_collection": {"step": "collect_base_docs"}}

    def test_transition_then_update_preserves_both(self):
        """Real-world pattern: transition + update."""
        step1 = _transition_to(None, CollectionStep.COLLECT_BASE_DOCS)
        step2 = _update_case_fsm_state(step1, {"element_data_status": {"SUB": "complete"}})

        case_coll = step2["case_collection"]
        assert case_coll["step"] == "collect_base_docs"
        assert case_coll["element_data_status"] == {"SUB": "complete"}

    def test_chained_transitions_override_step(self):
        """Two transitions: second step overrides first."""
        step1 = _transition_to(None, CollectionStep.COLLECT_BASE_DOCS)
        step2 = _transition_to(step1, CollectionStep.COLLECT_PERSONAL)

        assert step2["case_collection"]["step"] == "collect_personal"

    def test_transition_preserves_non_step_fields(self):
        """Transition preserves fields other than step from previous state."""
        step1 = _update_case_fsm_state(None, {
            "step": "collect_element_data",
            "element_data_status": {"ESC": "complete"},
            "personal_data": {"name": "Juan"},
        })
        step2 = _transition_to(step1, CollectionStep.COLLECT_BASE_DOCS)

        case_coll = step2["case_collection"]
        assert case_coll["step"] == "collect_base_docs"
        assert case_coll["element_data_status"] == {"ESC": "complete"}
        assert case_coll["personal_data"] == {"name": "Juan"}


class TestMergeEdgeCases:
    """Edge cases for the inline merge pattern."""

    def test_fsm_state_without_case_collection_key(self):
        """fsm_state dict without case_collection key starts fresh."""
        result = _update_case_fsm_state({"other_key": "value"}, {"step": "idle"})
        assert result == {"case_collection": {"step": "idle"}}

    def test_empty_updates_dict(self):
        """Empty updates dict returns existing state unchanged."""
        step1 = _update_case_fsm_state(None, {"step": "collect_personal"})
        step2 = _update_case_fsm_state(step1, {})

        assert step2["case_collection"] == {"step": "collect_personal"}

    def test_nested_dict_update_replaces_not_deep_merges(self):
        """Nested dicts are replaced, not deep-merged (dict.update semantics)."""
        step1 = _update_case_fsm_state(None, {
            "element_data_status": {"ESC": "complete", "SUB": "pending"},
        })
        step2 = _update_case_fsm_state(step1, {
            "element_data_status": {"ESC": "complete", "SUB": "complete", "TOLDO": "pending"},
        })

        status = step2["case_collection"]["element_data_status"]
        assert status == {"ESC": "complete", "SUB": "complete", "TOLDO": "pending"}

    def test_multiple_fields_in_single_update(self):
        """Multiple fields in a single update call."""
        result = _update_case_fsm_state(None, {
            "step": "collect_element_data",
            "element_phase": "photos",
            "current_element_index": 0,
            "element_codes": ["ESC", "SUB"],
        })

        case_coll = result["case_collection"]
        assert case_coll["step"] == "collect_element_data"
        assert case_coll["element_phase"] == "photos"
        assert case_coll["current_element_index"] == 0
        assert case_coll["element_codes"] == ["ESC", "SUB"]

    def test_boolean_fields_preserved(self):
        """Boolean fields are correctly preserved across chains."""
        step1 = _update_case_fsm_state(None, {"base_docs_received": False})
        step2 = _update_case_fsm_state(step1, {"step": "collect_base_docs"})
        step3 = _update_case_fsm_state(step2, {"base_docs_received": True})

        case_coll = step3["case_collection"]
        assert case_coll["base_docs_received"] is True
        assert case_coll["step"] == "collect_base_docs"

    def test_none_values_preserved(self):
        """None values are preserved in updates (not stripped)."""
        step1 = _update_case_fsm_state(None, {"case_id": "abc-123"})
        step2 = _update_case_fsm_state(step1, {"taller_propio": None})

        case_coll = step2["case_collection"]
        assert case_coll["case_id"] == "abc-123"
        assert "taller_propio" in case_coll
        assert case_coll["taller_propio"] is None
