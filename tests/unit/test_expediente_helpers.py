"""
Unit tests for agent/services/expediente_helpers.py

Tests each public helper function and the shared constants.
No database, Redis, or LLM access — the only dependency is the
ContextVar from agent.state.helpers, which we control via
set_current_state / clear_current_state.
"""

from __future__ import annotations

import pytest

from agent.utils.expediente_types import (
    CaseCollectionState,
    CollectionStep,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_context():
    """Clear the shared ContextVar before and after each test."""
    from agent.state.helpers import clear_current_state

    clear_current_state()
    yield
    clear_current_state()


def _set_state(state: dict) -> None:
    from agent.state.helpers import set_current_state

    set_current_state(state)


def _make_expediente_state(
    sub_mode: str = CollectionStep.IDLE.value,
    case_id: str | None = None,
    element_codes: list[str] | None = None,
    **extra_mode_context,
) -> dict:
    """Build a minimal ConversationState dict for EXPEDIENTE_MODE."""
    return {
        "current_mode": "EXPEDIENTE_MODE",
        "conversation_id": "test-conv-001",
        "mode_context": {
            "expediente_sub_mode": sub_mode,
            "case_id": case_id,
            "element_codes": element_codes or [],
            **extra_mode_context,
        },
    }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_initial_case_state_step_is_idle(self):
        from agent.services.expediente_helpers import INITIAL_CASE_STATE

        assert INITIAL_CASE_STATE["step"] == CollectionStep.IDLE.value

    def test_step_prompts_covers_all_active_steps(self):
        from agent.services.expediente_helpers import STEP_PROMPTS

        expected = {
            CollectionStep.COLLECT_ELEMENT_DATA,
            CollectionStep.COLLECT_BASE_DOCS,
            CollectionStep.COLLECT_PERSONAL,
            CollectionStep.COLLECT_VEHICLE,
            CollectionStep.COLLECT_WORKSHOP,
            CollectionStep.REVIEW_SUMMARY,
            CollectionStep.COMPLETED,
        }
        assert expected == set(STEP_PROMPTS.keys())

    def test_valid_transitions_all_steps_have_entry(self):
        from agent.services.expediente_helpers import VALID_TRANSITIONS

        # Every CollectionStep should appear as a key (even if value is [])
        for step in CollectionStep:
            assert step in VALID_TRANSITIONS, f"{step} missing from VALID_TRANSITIONS"

    def test_valid_transitions_completed_has_no_successors(self):
        from agent.services.expediente_helpers import VALID_TRANSITIONS

        assert VALID_TRANSITIONS[CollectionStep.COMPLETED] == []


# ---------------------------------------------------------------------------
# get_mode_context
# ---------------------------------------------------------------------------


class TestGetModeContext:
    def test_returns_initial_when_no_state(self):
        from agent.services.expediente_helpers import INITIAL_CASE_STATE, get_mode_context

        mc = get_mode_context()
        assert mc["step"] == CollectionStep.IDLE.value

    def test_returns_initial_when_wrong_mode(self):
        from agent.services.expediente_helpers import get_mode_context

        _set_state({"current_mode": "PRESUPUESTO_MODE", "mode_context": {}})
        mc = get_mode_context()
        assert mc["step"] == CollectionStep.IDLE.value

    def test_reads_sub_mode_from_mode_context(self):
        from agent.services.expediente_helpers import get_mode_context

        _set_state(
            _make_expediente_state(
                sub_mode=CollectionStep.COLLECT_PERSONAL.value,
                case_id="abc-123",
            )
        )
        mc = get_mode_context()
        assert mc["step"] == CollectionStep.COLLECT_PERSONAL.value
        assert mc["case_id"] == "abc-123"

    def test_defaults_element_phase_to_photos(self):
        from agent.services.expediente_helpers import get_mode_context

        _set_state(_make_expediente_state())
        mc = get_mode_context()
        assert mc["element_phase"] == "photos"

    def test_reads_element_codes(self):
        from agent.services.expediente_helpers import get_mode_context

        _set_state(_make_expediente_state(element_codes=["ESCAPE", "MANILLAR"]))
        mc = get_mode_context()
        assert mc["element_codes"] == ["ESCAPE", "MANILLAR"]


# ---------------------------------------------------------------------------
# get_current_step
# ---------------------------------------------------------------------------


class TestGetCurrentStep:
    def test_idle_when_no_state(self):
        from agent.services.expediente_helpers import get_current_step

        assert get_current_step() == CollectionStep.IDLE

    def test_reflects_mode_context_step(self):
        from agent.services.expediente_helpers import get_current_step

        _set_state(
            _make_expediente_state(sub_mode=CollectionStep.COLLECT_VEHICLE.value)
        )
        assert get_current_step() == CollectionStep.COLLECT_VEHICLE

    def test_invalid_step_value_falls_back_to_idle(self):
        from agent.services.expediente_helpers import get_current_step

        _set_state(
            {
                "current_mode": "EXPEDIENTE_MODE",
                "mode_context": {"expediente_sub_mode": "NONEXISTENT_STEP"},
            }
        )
        assert get_current_step() == CollectionStep.IDLE


# ---------------------------------------------------------------------------
# build_case_update
# ---------------------------------------------------------------------------


class TestBuildCaseUpdate:
    def test_creates_case_collection_key(self):
        from agent.services.expediente_helpers import build_case_update

        result = build_case_update(None, {"step": "collect_personal"})
        assert "case_collection" in result
        assert result["case_collection"]["step"] == "collect_personal"

    def test_merges_with_existing_case_collection(self):
        from agent.services.expediente_helpers import build_case_update

        existing = {"case_collection": {"step": "idle", "case_id": "orig-id"}}
        result = build_case_update(existing, {"step": "collect_personal"})
        # case_id should be preserved; step should be updated
        assert result["case_collection"]["case_id"] == "orig-id"
        assert result["case_collection"]["step"] == "collect_personal"

    def test_accumulates_on_chained_calls(self):
        from agent.services.expediente_helpers import build_case_update

        state: dict = {}
        state = build_case_update(state, {"a": 1})
        state = build_case_update(state, {"b": 2})
        assert state["case_collection"]["a"] == 1
        assert state["case_collection"]["b"] == 2

    def test_none_fsm_state_treated_as_empty(self):
        from agent.services.expediente_helpers import build_case_update

        result = build_case_update(None, {"key": "value"})
        assert result["case_collection"]["key"] == "value"


# ---------------------------------------------------------------------------
# set_collection_step
# ---------------------------------------------------------------------------


class TestSetCollectionStep:
    def test_creates_step_entry(self):
        from agent.services.expediente_helpers import set_collection_step

        result = set_collection_step(None, CollectionStep.COLLECT_PERSONAL)
        assert result["case_collection"]["step"] == CollectionStep.COLLECT_PERSONAL.value

    def test_preserves_other_keys(self):
        from agent.services.expediente_helpers import set_collection_step

        existing = {"case_collection": {"case_id": "xyz", "step": "idle"}}
        result = set_collection_step(existing, CollectionStep.COLLECT_VEHICLE)
        assert result["case_collection"]["case_id"] == "xyz"
        assert result["case_collection"]["step"] == CollectionStep.COLLECT_VEHICLE.value


# ---------------------------------------------------------------------------
# can_transition_to
# ---------------------------------------------------------------------------


class TestCanTransitionTo:
    def test_idle_to_collect_element_data_is_valid(self):
        from agent.services.expediente_helpers import can_transition_to

        assert can_transition_to(CollectionStep.IDLE, CollectionStep.COLLECT_ELEMENT_DATA)

    def test_idle_to_collect_personal_is_invalid(self):
        from agent.services.expediente_helpers import can_transition_to

        assert not can_transition_to(CollectionStep.IDLE, CollectionStep.COLLECT_PERSONAL)

    def test_any_step_to_idle_is_always_valid(self):
        """Idle represents a cancel/reset — always allowed."""
        from agent.services.expediente_helpers import can_transition_to

        for step in CollectionStep:
            assert can_transition_to(step, CollectionStep.IDLE), (
                f"Transition {step} → IDLE should always be valid"
            )

    def test_completed_has_no_valid_forward_transitions(self):
        from agent.services.expediente_helpers import can_transition_to

        for step in CollectionStep:
            if step == CollectionStep.IDLE:
                continue  # IDLE is always valid
            assert not can_transition_to(CollectionStep.COMPLETED, step), (
                f"COMPLETED → {step} should not be valid"
            )

    def test_review_summary_can_go_back_to_personal(self):
        from agent.services.expediente_helpers import can_transition_to

        assert can_transition_to(
            CollectionStep.REVIEW_SUMMARY, CollectionStep.COLLECT_PERSONAL
        )


# ---------------------------------------------------------------------------
# is_collection_active
# ---------------------------------------------------------------------------


class TestIsCollectionActive:
    def test_idle_is_not_active(self):
        from agent.services.expediente_helpers import is_collection_active

        _set_state(_make_expediente_state(sub_mode=CollectionStep.IDLE.value))
        assert not is_collection_active()

    def test_completed_is_not_active(self):
        from agent.services.expediente_helpers import is_collection_active

        _set_state(_make_expediente_state(sub_mode=CollectionStep.COMPLETED.value))
        assert not is_collection_active()

    def test_collect_personal_is_active(self):
        from agent.services.expediente_helpers import is_collection_active

        _set_state(_make_expediente_state(sub_mode=CollectionStep.COLLECT_PERSONAL.value))
        assert is_collection_active()

    def test_collect_element_data_is_active(self):
        from agent.services.expediente_helpers import is_collection_active

        _set_state(_make_expediente_state(sub_mode=CollectionStep.COLLECT_ELEMENT_DATA.value))
        assert is_collection_active()


# ---------------------------------------------------------------------------
# reset_case_collection
# ---------------------------------------------------------------------------


class TestResetCaseCollection:
    def test_resets_to_idle_step(self):
        from agent.services.expediente_helpers import (
            INITIAL_CASE_STATE,
            reset_case_collection,
        )

        existing = {"case_collection": {"step": "collect_personal", "case_id": "x"}}
        result = reset_case_collection(existing)
        assert result["case_collection"]["step"] == CollectionStep.IDLE.value

    def test_none_input_creates_clean_dict(self):
        from agent.services.expediente_helpers import reset_case_collection

        result = reset_case_collection(None)
        assert "case_collection" in result
        assert result["case_collection"]["step"] == CollectionStep.IDLE.value

    def test_preserves_other_fsm_keys(self):
        """Keys outside case_collection should be untouched."""
        from agent.services.expediente_helpers import reset_case_collection

        existing = {"other_key": 42, "case_collection": {"step": "collect_vehicle"}}
        result = reset_case_collection(existing)
        assert result["other_key"] == 42

    def test_reset_does_not_mutate_input(self):
        from agent.services.expediente_helpers import reset_case_collection

        existing = {"case_collection": {"step": "collect_vehicle"}}
        original_step = existing["case_collection"]["step"]
        reset_case_collection(existing)
        # Original dict must not be mutated
        assert existing["case_collection"]["step"] == original_step


# ---------------------------------------------------------------------------
# Backward-compat aliases
# ---------------------------------------------------------------------------


class TestBackwardCompatAliases:
    """The private aliases must point to the same functions as the public API."""

    def test_get_mode_context_alias(self):
        from agent.services.expediente_helpers import (
            _get_mode_context,
            get_mode_context,
        )

        assert _get_mode_context is get_mode_context

    def test_get_current_step_alias(self):
        from agent.services.expediente_helpers import (
            _get_current_step_from_context,
            get_current_step,
        )

        assert _get_current_step_from_context is get_current_step

    def test_build_case_update_alias(self):
        from agent.services.expediente_helpers import (
            _build_case_update,
            build_case_update,
        )

        assert _build_case_update is build_case_update

    def test_set_collection_step_alias(self):
        from agent.services.expediente_helpers import (
            _set_collection_step,
            set_collection_step,
        )

        assert _set_collection_step is set_collection_step

    def test_constants_aliases(self):
        from agent.services.expediente_helpers import (
            INITIAL_CASE_STATE,
            STEP_PROMPTS,
            VALID_TRANSITIONS,
            _INITIAL_CASE_STATE,
            _STEP_PROMPTS,
            _VALID_TRANSITIONS,
        )

        assert _INITIAL_CASE_STATE is INITIAL_CASE_STATE
        assert _STEP_PROMPTS is STEP_PROMPTS
        assert _VALID_TRANSITIONS is VALID_TRANSITIONS
