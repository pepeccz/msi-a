"""
Unit tests for tombstone protocol in mode_context cleanup.

Background
----------
`merge_dicts()` in `conversation_state.py` implements a shallow merge:

    {**current, **update}

This means keys present in `current` (the checkpoint) that are ABSENT from
`update` survive unchanged — they are NOT deleted.

When a mode pops a key to consume it for the current turn, the pop only
removes it from the in-memory dict.  On the NEXT turn, `merge_dicts` reads
the checkpoint (`current`) and the key reappears — it "resurrects".

The tombstone protocol fixes this: after every `pop()`, assign `None` (or the
zero value for booleans) to the same key so the `update` dict explicitly
carries a `None` entry that overwrites the checkpoint value.

These tests verify:
1. Without tombstone → key resurrects on the next turn merge.
2. With tombstone    → key stays None / False after the merge.
3. Survivor keys     → unrelated keys are never affected.
4. Boolean sentinel  → `_guard_photo_fired_this_turn` uses False, not None.
"""

from __future__ import annotations

import sys
import types

# Stub optional heavy dependencies so imports don't fail in unit context
sys.modules.setdefault("phonenumbers", types.ModuleType("phonenumbers"))

import pytest

from agent.state.conversation_state import merge_dicts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simulate_turn_output(
    checkpoint: dict,
    pop_key: str,
    *,
    add_tombstone: bool,
    tombstone_value: object = None,
    survivor_key: str = "other_key",
    survivor_value: object = "keep_me",
) -> dict:
    """
    Simulate what a mode node does each turn:

    1.  Start from a copy of the checkpoint (as the mode receives it).
    2.  Pop the cleanup key (consume it for this turn).
    3.  Optionally assign the tombstone value.
    4.  Ensure a survivor key is present to prove unrelated keys survive.
    5.  Run through merge_dicts to produce the next checkpoint.
    """
    updated_context = dict(checkpoint)  # shallow copy — same as mode code
    updated_context.pop(pop_key, None)
    if add_tombstone:
        updated_context[pop_key] = tombstone_value

    # Survivor key always present in both turns (unchanged)
    updated_context.setdefault(survivor_key, survivor_value)

    return merge_dicts(current=checkpoint, update=updated_context)


# ---------------------------------------------------------------------------
# B3 — Core tombstone tests
# ---------------------------------------------------------------------------


class TestTombstoneSemantics:
    """Verify tombstone protocol prevents key resurrection across turns."""

    SURVIVOR_KEY = "other_key"
    SURVIVOR_VALUE = "keep_me"

    # ---- expediente_transition_marker -----------------------------------

    def test_expediente_transition_marker_without_tombstone_resurrects(self) -> None:
        """Control test: pop() alone causes resurrection on turn N+2."""
        # Turn N checkpoint — marker has a value
        turn_n_context: dict = {
            "expediente_transition_marker": "some_value",
            self.SURVIVOR_KEY: self.SURVIVOR_VALUE,
        }

        # Turn N+1: pop WITHOUT tombstone
        turn_n1_result = _simulate_turn_output(
            turn_n_context,
            pop_key="expediente_transition_marker",
            add_tombstone=False,
        )
        # After the pop the key is absent from the update dict but the
        # checkpoint still has it — merge_dicts resurrects it.
        assert turn_n1_result["expediente_transition_marker"] == "some_value", (
            "Without tombstone, merge_dicts resurrects the key from the checkpoint"
        )

    def test_expediente_transition_marker_with_tombstone_stays_none(self) -> None:
        """Turn N sets marker → Turn N+1 pops + tombstones → key is None."""
        # Turn N checkpoint
        turn_n_context: dict = {
            "expediente_transition_marker": "some_value",
            self.SURVIVOR_KEY: self.SURVIVOR_VALUE,
        }

        # Turn N+1: pop WITH tombstone
        turn_n1_result = _simulate_turn_output(
            turn_n_context,
            pop_key="expediente_transition_marker",
            add_tombstone=True,
            tombstone_value=None,
        )

        assert turn_n1_result["expediente_transition_marker"] is None, (
            "With tombstone, merge_dicts stores None — key does not resurrect"
        )

    def test_expediente_transition_marker_not_resurrected_on_turn_n2(self) -> None:
        """Turn N+2 with empty update — tombstoned None persists."""
        # Turn N checkpoint
        turn_n_context: dict = {
            "expediente_transition_marker": "some_value",
            self.SURVIVOR_KEY: self.SURVIVOR_VALUE,
        }

        # Turn N+1: pop + tombstone
        turn_n1_result = _simulate_turn_output(
            turn_n_context,
            pop_key="expediente_transition_marker",
            add_tombstone=True,
            tombstone_value=None,
        )

        # Turn N+2: nothing updates the key (empty update mirrors no-change turns)
        turn_n2_result = merge_dicts(
            current=turn_n1_result,
            update={self.SURVIVOR_KEY: self.SURVIVOR_VALUE},
        )

        assert turn_n2_result["expediente_transition_marker"] is None, (
            "Tombstoned None must persist to turn N+2; must not re-read old checkpoint value"
        )

    def test_survivor_key_always_preserved(self) -> None:
        """Keys unrelated to the cleanup must survive all turns intact."""
        turn_n_context: dict = {
            "expediente_transition_marker": "some_value",
            self.SURVIVOR_KEY: self.SURVIVOR_VALUE,
        }

        turn_n1_result = _simulate_turn_output(
            turn_n_context,
            pop_key="expediente_transition_marker",
            add_tombstone=True,
        )

        assert turn_n1_result[self.SURVIVOR_KEY] == self.SURVIVOR_VALUE

        turn_n2_result = merge_dicts(
            current=turn_n1_result,
            update={self.SURVIVOR_KEY: self.SURVIVOR_VALUE},
        )
        assert turn_n2_result[self.SURVIVOR_KEY] == self.SURVIVOR_VALUE

    # ---- just_transitioned_from ----------------------------------------

    def test_just_transitioned_from_tombstone(self) -> None:
        """just_transitioned_from follows the same tombstone pattern."""
        turn_n_context: dict = {
            "just_transitioned_from": "collect_personal",
            self.SURVIVOR_KEY: self.SURVIVOR_VALUE,
        }

        turn_n1_result = _simulate_turn_output(
            turn_n_context,
            pop_key="just_transitioned_from",
            add_tombstone=True,
        )

        assert turn_n1_result["just_transitioned_from"] is None

        # Turn N+2 — must not resurrect
        turn_n2_result = merge_dicts(
            current=turn_n1_result,
            update={self.SURVIVOR_KEY: self.SURVIVOR_VALUE},
        )
        assert turn_n2_result["just_transitioned_from"] is None

    # ---- _guard_photo_fired_this_turn (boolean sentinel) ----------------

    def test_guard_photo_fired_tombstone_uses_false(self) -> None:
        """
        _guard_photo_fired_this_turn uses False (not None) as its tombstone.
        Verify False persists and does not resurrect as True.
        """
        turn_n_context: dict = {
            "_guard_photo_fired_this_turn": True,
            self.SURVIVOR_KEY: self.SURVIVOR_VALUE,
        }

        # Simulate the mode code: pop + assign False
        updated_context = dict(turn_n_context)
        _fired = updated_context.pop("_guard_photo_fired_this_turn", False)
        updated_context["_guard_photo_fired_this_turn"] = False  # TOMBSTONE

        assert _fired is True  # Verify we got the value

        turn_n1_result = merge_dicts(current=turn_n_context, update=updated_context)

        assert turn_n1_result["_guard_photo_fired_this_turn"] is False

        # Turn N+2 — must still be False, not True
        turn_n2_result = merge_dicts(
            current=turn_n1_result,
            update={self.SURVIVOR_KEY: self.SURVIVOR_VALUE},
        )
        assert turn_n2_result["_guard_photo_fired_this_turn"] is False

    # ---- expediente_intro_message ----------------------------------------

    def test_expediente_intro_message_tombstone(self) -> None:
        """expediente_intro_message must not reappear after being consumed."""
        turn_n_context: dict = {
            "expediente_intro_message": "Bienvenido al expediente...",
            self.SURVIVOR_KEY: self.SURVIVOR_VALUE,
        }

        turn_n1_result = _simulate_turn_output(
            turn_n_context,
            pop_key="expediente_intro_message",
            add_tombstone=True,
        )

        assert turn_n1_result["expediente_intro_message"] is None

        turn_n2_result = merge_dicts(
            current=turn_n1_result,
            update={self.SURVIVOR_KEY: self.SURVIVOR_VALUE},
        )
        assert turn_n2_result["expediente_intro_message"] is None

    # ---- _tarifa_actual (presupuesto_mode) --------------------------------

    def test_tarifa_actual_tombstone(self) -> None:
        """_tarifa_actual in presupuesto_mode must not resurrect from checkpoint."""
        turn_n_context: dict = {
            "_tarifa_actual": {"precio": 410.0, "elementos": ["ESCAPE"]},
            self.SURVIVOR_KEY: self.SURVIVOR_VALUE,
        }

        # Simulate presupuesto_mode code path
        updated_context = dict(turn_n_context)
        if updated_context.get("_tarifa_actual"):
            updated_context.pop("_tarifa_actual")
            updated_context["_tarifa_actual"] = None  # TOMBSTONE

        turn_n1_result = merge_dicts(current=turn_n_context, update=updated_context)

        assert turn_n1_result["_tarifa_actual"] is None

        # Turn N+2 — must not resurrect
        turn_n2_result = merge_dicts(
            current=turn_n1_result,
            update={self.SURVIVOR_KEY: self.SURVIVOR_VALUE},
        )
        assert turn_n2_result["_tarifa_actual"] is None


# ---------------------------------------------------------------------------
# Baseline / sanity tests for merge_dicts itself
# ---------------------------------------------------------------------------


class TestMergeDictsBaseline:
    """Verify merge_dicts core behaviour so tombstone tests are grounded."""

    def test_absent_key_in_update_preserves_checkpoint_value(self) -> None:
        """This is the root-cause: absent key in update → checkpoint value survives."""
        current = {"a": "old_value", "b": "keep"}
        update = {"b": "new_b"}  # "a" is absent
        result = merge_dicts(current=current, update=update)
        assert result["a"] == "old_value"  # survived

    def test_none_value_in_update_overwrites_checkpoint_value(self) -> None:
        """Tombstone semantics: None in update → None in result (NOT old value)."""
        current = {"a": "old_value", "b": "keep"}
        update = {"a": None, "b": "new_b"}  # explicit None
        result = merge_dicts(current=current, update=update)
        assert result["a"] is None  # tombstoned

    def test_none_update_returns_current(self) -> None:
        current = {"a": 1}
        result = merge_dicts(current=current, update=None)
        assert result == current

    def test_none_current_returns_update(self) -> None:
        update = {"a": 1}
        result = merge_dicts(current=None, update=update)
        assert result == update

    def test_both_none_returns_empty(self) -> None:
        result = merge_dicts(current=None, update=None)
        assert result == {}
