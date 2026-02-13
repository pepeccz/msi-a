"""Tests for FSM compat layer merge semantics.

Validates that update_case_fsm_state() properly MERGES chained calls
instead of overwriting, which was the root cause of state propagation
bugs where transition_to() + subsequent update lost the "step" field.

Bug context:
    step1 = transition_to(state, COLLECT_BASE_DOCS)      # sets step
    step2 = update_case_fsm_state(step1, {"element_data_status": {...}})
    # Before fix: step2 LOST "step" (overwrite)
    # After fix:  step2 KEEPS "step" (merge)
"""

import pytest
from copy import deepcopy

from agent.utils.fsm_compat import (
    update_case_fsm_state,
    transition_to,
    CollectionStep,
)


class TestUpdateCaseFSMStateMerge:
    """Test that update_case_fsm_state properly merges chained calls."""

    def test_single_call_wraps_in_case_collection(self):
        """Single call wraps updates in case_collection key."""
        result = update_case_fsm_state(None, {"element_phase": "data"})
        assert result == {"case_collection": {"element_phase": "data"}}

    def test_single_call_with_none_fsm_state(self):
        """Works with None as fsm_state."""
        result = update_case_fsm_state(None, {"step": "collect_base_docs"})
        assert result["case_collection"]["step"] == "collect_base_docs"

    def test_single_call_with_empty_dict(self):
        """Works with empty dict as fsm_state."""
        result = update_case_fsm_state({}, {"step": "collect_base_docs"})
        assert result["case_collection"]["step"] == "collect_base_docs"

    def test_chained_calls_accumulate(self):
        """Chained calls accumulate fields, not overwrite."""
        step1 = update_case_fsm_state(None, {"step": "collect_base_docs"})
        step2 = update_case_fsm_state(step1, {"element_data_status": {"SUBCHASIS": "complete"}})

        case_coll = step2["case_collection"]
        assert "step" in case_coll, "step from first call must survive"
        assert "element_data_status" in case_coll, "new field must be added"
        assert case_coll["step"] == "collect_base_docs"
        assert case_coll["element_data_status"] == {"SUBCHASIS": "complete"}

    def test_triple_chain_accumulates(self):
        """Three chained calls all accumulate."""
        step1 = update_case_fsm_state(None, {"step": "collect_personal"})
        step2 = update_case_fsm_state(step1, {"personal_data": {"name": "Juan"}})
        step3 = update_case_fsm_state(step2, {"personal_complete": True})

        case_coll = step3["case_collection"]
        assert case_coll["step"] == "collect_personal"
        assert case_coll["personal_data"] == {"name": "Juan"}
        assert case_coll["personal_complete"] is True

    def test_later_call_overrides_same_key(self):
        """Later call overrides the same key (update semantics)."""
        step1 = update_case_fsm_state(None, {"element_phase": "photos"})
        step2 = update_case_fsm_state(step1, {"element_phase": "data"})

        assert step2["case_collection"]["element_phase"] == "data"

    def test_does_not_mutate_input(self):
        """Input fsm_state is not mutated."""
        step1 = update_case_fsm_state(None, {"step": "collect_base_docs"})
        original_keys = set(step1["case_collection"].keys())

        update_case_fsm_state(step1, {"new_field": "value"})

        assert set(step1["case_collection"].keys()) == original_keys

    def test_transition_to_then_update_preserves_step(self):
        """Simulates the real-world pattern: transition_to + update."""
        # This simulates what transition_to returns
        step1 = update_case_fsm_state(None, {"step": "collect_base_docs"})
        # Then another update adds element_data_status
        step2 = update_case_fsm_state(step1, {"element_data_status": {"ESC": "done"}})

        case_coll = step2["case_collection"]
        assert case_coll["step"] == "collect_base_docs", "transition step must survive"
        assert case_coll["element_data_status"] == {"ESC": "done"}, "status must be added"


class TestTransitionToMerge:
    """Test that transition_to() integrates with merge semantics."""

    def test_transition_to_returns_case_collection(self):
        """transition_to wraps step in case_collection."""
        result = transition_to(None, CollectionStep.COLLECT_BASE_DOCS)
        assert result == {"case_collection": {"step": "collect_base_docs"}}

    def test_transition_to_then_update_preserves_both(self):
        """Real-world pattern: transition_to + update_case_fsm_state."""
        step1 = transition_to(None, CollectionStep.COLLECT_BASE_DOCS)
        step2 = update_case_fsm_state(step1, {"element_data_status": {"SUB": "complete"}})

        case_coll = step2["case_collection"]
        assert case_coll["step"] == "collect_base_docs"
        assert case_coll["element_data_status"] == {"SUB": "complete"}

    def test_transition_to_chained_transitions_override_step(self):
        """Two transitions: second step overrides first."""
        step1 = transition_to(None, CollectionStep.COLLECT_BASE_DOCS)
        step2 = transition_to(step1, CollectionStep.COLLECT_PERSONAL)

        assert step2["case_collection"]["step"] == "collect_personal"

    def test_transition_to_preserves_non_step_fields(self):
        """transition_to preserves fields other than step from previous state."""
        step1 = update_case_fsm_state(None, {
            "step": "collect_element_data",
            "element_data_status": {"ESC": "complete"},
            "personal_data": {"name": "Juan"},
        })
        step2 = transition_to(step1, CollectionStep.COLLECT_BASE_DOCS)

        case_coll = step2["case_collection"]
        assert case_coll["step"] == "collect_base_docs"
        assert case_coll["element_data_status"] == {"ESC": "complete"}
        assert case_coll["personal_data"] == {"name": "Juan"}


class TestUpdateCaseFSMStateEdgeCases:
    """Edge cases for update_case_fsm_state."""

    def test_fsm_state_without_case_collection_key(self):
        """fsm_state dict without case_collection key starts fresh."""
        result = update_case_fsm_state({"other_key": "value"}, {"step": "idle"})
        assert result == {"case_collection": {"step": "idle"}}

    def test_empty_updates_dict(self):
        """Empty updates dict returns existing state unchanged."""
        step1 = update_case_fsm_state(None, {"step": "collect_personal"})
        step2 = update_case_fsm_state(step1, {})

        assert step2["case_collection"] == {"step": "collect_personal"}

    def test_nested_dict_update_replaces_not_deep_merges(self):
        """Nested dicts are replaced, not deep-merged (dict.update semantics)."""
        step1 = update_case_fsm_state(None, {
            "element_data_status": {"ESC": "complete", "SUB": "pending"},
        })
        step2 = update_case_fsm_state(step1, {
            "element_data_status": {"ESC": "complete", "SUB": "complete", "TOLDO": "pending"},
        })

        status = step2["case_collection"]["element_data_status"]
        assert status == {"ESC": "complete", "SUB": "complete", "TOLDO": "pending"}

    def test_multiple_fields_in_single_update(self):
        """Multiple fields in a single update call."""
        result = update_case_fsm_state(None, {
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
        step1 = update_case_fsm_state(None, {"base_docs_received": False})
        step2 = update_case_fsm_state(step1, {"step": "collect_base_docs"})
        step3 = update_case_fsm_state(step2, {"base_docs_received": True})

        case_coll = step3["case_collection"]
        assert case_coll["base_docs_received"] is True
        assert case_coll["step"] == "collect_base_docs"

    def test_none_values_preserved(self):
        """None values are preserved in updates (not stripped)."""
        step1 = update_case_fsm_state(None, {"case_id": "abc-123"})
        step2 = update_case_fsm_state(step1, {"taller_propio": None})

        case_coll = step2["case_collection"]
        assert case_coll["case_id"] == "abc-123"
        assert "taller_propio" in case_coll
        assert case_coll["taller_propio"] is None
