"""
Unit tests for P0 Fix 1 — Tombstone `_transition_to` in presupuesto_mode.py.

Verifies that after pop()ing _transition_to and assigning None (tombstone),
merge_dicts() cannot resurrect the old value from the checkpoint on subsequent
turns.

No DB or Redis required — tests only the merge_dicts reducer.
"""

import pytest
from agent.state.conversation_state import merge_dicts


# ---------------------------------------------------------------------------
# Helper: simulate what presupuesto_mode._process_message() does when
# transition_target is consumed.
# ---------------------------------------------------------------------------


def apply_tombstone(updated_context: dict) -> dict:
    """
    Simulates the tombstone pattern now present in presupuesto_mode.py:

        transition_target = updated_context.pop("_transition_to", None)
        updated_context["_transition_to"] = None  # TOMBSTONE

    Returns the updated_context with the tombstone applied.
    """
    _target = updated_context.pop("_transition_to", None)  # noqa: F841 — consumed
    updated_context["_transition_to"] = None  # TOMBSTONE
    return updated_context


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTombstonePreventResurrection:
    """
    Simulates a 3-turn merge cycle using merge_dicts (same as LangGraph reducer).

    Turn N  : checkpoint has _transition_to = "EVALUACION_GATEWAY"
    Turn N+1: node pops + tombstones → update has _transition_to = None
    Turn N+2: node returns empty update {} → merge_dicts must NOT resurrect
    """

    def test_tombstone_null_after_turn_n1_merge(self):
        """
        After turn N+1: merge_dicts({...with non-None _transition_to}, {_transition_to: None})
        should produce _transition_to = None, not "EVALUACION_GATEWAY".
        """
        # Turn N checkpoint (what Redis has persisted)
        checkpoint_context = {
            "_transition_to": "EVALUACION_GATEWAY",
            "other": "keep",
        }

        # Turn N+1: code pops _transition_to, assigns None (tombstone)
        turn_n1_update = {"_transition_to": "EVALUACION_GATEWAY", "other": "keep"}
        apply_tombstone(turn_n1_update)
        # After apply_tombstone: turn_n1_update["_transition_to"] is None

        result_n1 = merge_dicts(checkpoint_context, turn_n1_update)

        assert result_n1["_transition_to"] is None, (
            f"Expected None after tombstone merge, got {result_n1['_transition_to']!r}"
        )

    def test_no_resurrection_on_turn_n2(self):
        """
        Turn N+2: empty update {} must NOT resurrect _transition_to from the
        N+1 checkpoint (which now has _transition_to = None).
        """
        # Turn N+1 result becomes the new checkpoint
        checkpoint_n1 = {
            "_transition_to": None,  # Tombstoned from N+1
            "other": "keep",
        }

        # Turn N+2: node returns no update for _transition_to
        turn_n2_update: dict = {}

        result_n2 = merge_dicts(checkpoint_n1, turn_n2_update)

        assert result_n2["_transition_to"] is None, (
            f"_transition_to was resurrected on turn N+2: {result_n2['_transition_to']!r}"
        )

    def test_other_keys_survive_unchanged(self):
        """
        Keys unrelated to _transition_to must survive the tombstone merge
        without modification.
        """
        checkpoint_context = {
            "_transition_to": "EVALUACION_GATEWAY",
            "other": "keep",
            "element_codes": ["ESCAPE"],
            "categoria_slug": "motos-part",
        }

        turn_n1_update = dict(checkpoint_context)
        apply_tombstone(turn_n1_update)

        result_n1 = merge_dicts(checkpoint_context, turn_n1_update)

        assert result_n1["other"] == "keep"
        assert result_n1["element_codes"] == ["ESCAPE"]
        assert result_n1["categoria_slug"] == "motos-part"

    def test_pop_alone_would_resurrect(self):
        """
        Demonstrates the OLD (broken) behaviour: pop() alone without tombstone
        allows resurrection on the next merge. This test documents WHY the fix
        is necessary.
        """
        checkpoint_context = {
            "_transition_to": "EVALUACION_GATEWAY",
            "other": "keep",
        }

        # BUG: only pop, no tombstone assignment
        buggy_update = dict(checkpoint_context)
        buggy_update.pop("_transition_to", None)  # key is now absent from buggy_update

        result_buggy = merge_dicts(checkpoint_context, buggy_update)

        # Without tombstone, value is PRESERVED from checkpoint — this is the bug
        assert result_buggy["_transition_to"] == "EVALUACION_GATEWAY", (
            "Expected resurrection to occur in bug scenario"
        )

    def test_full_three_turn_cycle(self):
        """
        End-to-end simulation of the three-turn merge cycle verifying both
        the immediate tombstone effect and no subsequent resurrection.
        """
        # Turn N: checkpoint has pending transition
        checkpoint_n = {
            "_transition_to": "EVALUACION_GATEWAY",
            "other": "keep",
        }

        # Turn N+1: LLM consumes the transition → apply tombstone
        update_n1 = dict(checkpoint_n)
        apply_tombstone(update_n1)

        result_n1 = merge_dicts(checkpoint_n, update_n1)

        # Assert: transition consumed and tombstoned
        assert result_n1["_transition_to"] is None, (
            f"Turn N+1: expected None, got {result_n1['_transition_to']!r}"
        )

        # Turn N+2: empty update from node (no transition signal)
        result_n2 = merge_dicts(result_n1, {})

        # Assert: no resurrection
        assert result_n2["_transition_to"] is None, (
            f"Turn N+2: _transition_to resurrected to {result_n2['_transition_to']!r}"
        )

        # Assert: unrelated key survived all turns
        assert result_n2["other"] == "keep"
