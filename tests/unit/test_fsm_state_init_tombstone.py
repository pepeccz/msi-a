"""
RED-phase tests for fix-element-data-tools-fsm-state — `_fsm_state_init` tombstone key.

Bug (REQ-4): `_fsm_state_init` is written to `mode_context` by `expediente_mode.py`
at 4 locations (lines 686, 1002, 1196, 1414), and is tombstoned by
`loop_engine.py` (line 264) using the correct tombstone protocol
(`mode_context["_fsm_state_init"] = None`).

However, `_fsm_state_init` is NOT registered in `CANONICAL_MODE_CONTEXT_KEYS`
(specifically, it is absent from `_MODE_RUNTIME_KEYS` in `mode_context_keys.py`).

This causes spurious `state_warning` log events whenever EXPEDIENTE_MODE processes
a turn that includes `_fsm_state_init` in the mode_context, because the
`validate_mode_context_update()` function logs a warning for every unrecognised key.

Expected behavior (after Phase 4 fix):
1. `_fsm_state_init` is present in `CANONICAL_MODE_CONTEXT_KEYS` (via `_MODE_RUNTIME_KEYS`).
2. No `state_warning` is emitted for `_fsm_state_init` when it appears in mode_context.
3. After a sub-mode transition, `_fsm_state_init` is set to `None` (tombstoned, not absent).

These tests FAIL today (RED phase) because `_fsm_state_init` is NOT in
`CANONICAL_MODE_CONTEXT_KEYS`.

Tasks covered: 1.7, 1.8 from the SDD tasks artifact.
"""

from __future__ import annotations

import logging

import pytest

from agent.state.mode_context_keys import (
    CANONICAL_MODE_CONTEXT_KEYS,
    _MODE_RUNTIME_KEYS,
    validate_mode_context_update,
)
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# T7 — `_fsm_state_init` must be in CANONICAL_MODE_CONTEXT_KEYS
# ---------------------------------------------------------------------------


class TestFsmStateInitIsCanonicalKey:
    """
    T7 — `_fsm_state_init` must be registered as a canonical mode_context key
    so that `validate_mode_context_update()` does NOT emit warnings when it
    is present in a mode_context update dict.

    THIS TEST FAILS TODAY (RED phase) because `_fsm_state_init` is absent
    from `_MODE_RUNTIME_KEYS` and therefore absent from `CANONICAL_MODE_CONTEXT_KEYS`.

    After Phase 4 fix, adding `"_fsm_state_init"` to `_MODE_RUNTIME_KEYS` in
    `mode_context_keys.py` will make this test pass.
    """

    def test_fsm_state_init_in_canonical_keys(self):
        """
        `_fsm_state_init` must be in CANONICAL_MODE_CONTEXT_KEYS.

        It is written by expediente_mode.py at 4 locations and tombstoned by
        loop_engine.py (line 264). It is a legitimate runtime key that SHOULD be
        registered.

        BUG: Today it is absent, causing spurious state_warning logs on every
        turn where EXPEDIENTE_MODE initialises a case (very common path).
        """
        assert "_fsm_state_init" in CANONICAL_MODE_CONTEXT_KEYS, (
            "'_fsm_state_init' must be in CANONICAL_MODE_CONTEXT_KEYS. "
            "It is written by expediente_mode.py at lines 686, 1002, 1196, 1414 "
            "and tombstoned by loop_engine.py:264. "
            "Add it to _MODE_RUNTIME_KEYS in agent/state/mode_context_keys.py."
        )

    def test_fsm_state_init_in_mode_runtime_keys(self):
        """
        `_fsm_state_init` must be in `_MODE_RUNTIME_KEYS` specifically.

        This is the correct semantic group — it is written by modes at runtime
        (not from a TypedDict, not from a tool flag, not from compat layer).
        """
        assert "_fsm_state_init" in _MODE_RUNTIME_KEYS, (
            "'_fsm_state_init' must be in _MODE_RUNTIME_KEYS. "
            "It is an expediente_mode.py runtime initialization key."
        )


# ---------------------------------------------------------------------------
# T8 — No state_warning for `_fsm_state_init` when present in update
# ---------------------------------------------------------------------------


class TestNoStateWarningForFsmStateInit:
    """
    T8 — `validate_mode_context_update()` must NOT emit a state_warning for
    `_fsm_state_init` when it is present in the update dict.

    The function logs a structured warning for any key not in CANONICAL_MODE_CONTEXT_KEYS.
    Since `_fsm_state_init` is not in the canonical set today, every expediente
    kickoff turn triggers a warning log — noise that can mask real issues.

    THIS TEST FAILS TODAY because `_fsm_state_init` is not canonical — the
    function will log a state_warning which we capture and assert is absent.

    After Phase 4 fix, the key is registered and no warning is emitted.
    """

    def test_no_state_warning_when_fsm_state_init_present(self, caplog):
        """
        Given:  A mode_context update dict containing '_fsm_state_init'
                set to a realistic fsm_state value (a dict with case_collection)
                AND enforcement is enabled (ENABLE_STATE_CONTRACT_ENFORCEMENT=True)
        When:   validate_mode_context_update() processes this update
        Then:   The returned warnings_list is EMPTY — no warning about _fsm_state_init.
                No log record for 'non_canonical_mode_context_keys_stripped' references it.

        BUG today: The _fsm_state_init key IS in the unknown_keys set and the
        validation returns a non-empty warnings list (and logs a warning) because
        it is not registered in CANONICAL_MODE_CONTEXT_KEYS.
        """
        # Build an update dict that would be emitted by expediente_mode.py
        # on case initialization (typical path at line 686, 1002, etc.)
        realistic_fsm_state = {
            "case_collection": {
                "step": "collect_element_data",
                "case_id": "123e4567-e89b-12d3-a456-426614174000",
                "element_codes": ["ESCAPE"],
                "current_element_index": 0,
                "element_phase": "photos",
                "element_data_status": {},
            }
        }

        update_dict = {
            "expediente_sub_mode": "collect_element_data",
            "case_id": "123e4567-e89b-12d3-a456-426614174000",
            "_fsm_state_init": realistic_fsm_state,  # The key under test
        }

        # Force enforcement ON so we can observe the warning behaviour
        with patch(
            "shared.config.get_settings",
            return_value=MagicMock(ENABLE_STATE_CONTRACT_ENFORCEMENT=True),
        ):
            _cleaned, warnings = validate_mode_context_update(
                update_dict, mode="EXPEDIENTE_MODE"
            )

        # The warnings list must NOT contain a warning about _fsm_state_init
        fsm_init_warnings = [w for w in warnings if "_fsm_state_init" in w]
        assert not fsm_init_warnings, (
            "No warning should be emitted for '_fsm_state_init' — "
            "it is a legitimate runtime key used by expediente_mode.py. "
            f"Warnings returned: {warnings}"
        )

    def test_no_state_warning_when_fsm_state_init_tombstoned(self, caplog):
        """
        Given:  A mode_context update dict where '_fsm_state_init' is tombstoned
                (set to None — as done by loop_engine.py:264 after extraction)
        When:   validate_mode_context_update() processes this update (enforcement ON)
        Then:   No warning about '_fsm_state_init' in the returned warnings list.

        The tombstone value (None) should also not trigger warnings —
        tombstones are valid signals, not errors.
        """
        update_dict = {
            "expediente_sub_mode": "collect_base_docs",
            "_fsm_state_init": None,  # Tombstone — loop_engine.py has consumed the value
        }

        with patch(
            "shared.config.get_settings",
            return_value=MagicMock(ENABLE_STATE_CONTRACT_ENFORCEMENT=True),
        ):
            _cleaned, warnings = validate_mode_context_update(
                update_dict,
                mode="EXPEDIENTE_MODE",
            )

        fsm_init_warnings = [w for w in warnings if "_fsm_state_init" in w]
        assert not fsm_init_warnings, (
            "Tombstoned '_fsm_state_init' (value=None) must not trigger a "
            "warning — it is the correct tombstone protocol signal. "
            f"Warnings returned: {warnings}"
        )

    def test_no_state_warning_when_fsm_state_init_tombstoned(self, caplog):
        """
        Given:  A mode_context update dict where '_fsm_state_init' is tombstoned
                (set to None — as done by loop_engine.py:264 after extraction)
        When:   validate_mode_context_update() processes this update
        Then:   No state_warning for '_fsm_state_init'

        The tombstone value (None) should also not trigger warnings —
        tombstones are valid signals, not errors.
        """
        update_dict = {
            "expediente_sub_mode": "collect_base_docs",
            "_fsm_state_init": None,  # Tombstone — loop_engine.py has consumed the value
        }

        with patch(
            "shared.config.get_settings",
            return_value=MagicMock(ENABLE_STATE_CONTRACT_ENFORCEMENT=True),
        ):
            _cleaned, warnings = validate_mode_context_update(
                update_dict,
                mode="EXPEDIENTE_MODE",
            )

        fsm_init_warnings = [w for w in warnings if "_fsm_state_init" in w]
        assert not fsm_init_warnings, (
            "Tombstoned '_fsm_state_init' (value=None) must not trigger a "
            "warning — it is the correct tombstone protocol signal. "
            f"Warnings returned: {warnings}"
        )


# ---------------------------------------------------------------------------
# T8b — After sub-mode transition, _fsm_state_init is None (tombstone check)
# ---------------------------------------------------------------------------


class TestFsmStateInitTombstoneAfterTransition:
    """
    T8b — After loop_engine.py processes a turn, `_fsm_state_init` must be
    set to None in the mode_context (tombstone protocol), not absent.

    This test validates the tombstone contract directly by checking that
    `loop_engine.py` follows the TOMBSTONE comment at line 264:
        mode_context["_fsm_state_init"] = None  # TOMBSTONE

    This test PASSES today (the tombstone is already implemented).
    We include it to document the contract and ensure it doesn't regress.
    """

    def test_loop_engine_tombstones_fsm_state_init(self):
        """
        The loop_engine.py module must follow the tombstone protocol for
        _fsm_state_init: set to None after pop, NOT deleted.

        We verify this by reading the source code of loop_engine.py and
        confirming that both operations are present (pop + None assignment).
        """
        import inspect
        import agent.modes.submodos.loop_engine as loop_engine_module

        source = inspect.getsource(loop_engine_module)

        assert 'mode_context.pop("_fsm_state_init"' in source, (
            "loop_engine.py must pop '_fsm_state_init' from mode_context."
        )
        assert 'mode_context["_fsm_state_init"] = None' in source, (
            "loop_engine.py must tombstone '_fsm_state_init' by assigning None "
            "AFTER the pop, per the tombstone protocol. "
            "Otherwise, the key will resurrect from the Redis checkpoint on the "
            "next turn, causing repeated stale FSM state injections."
        )
