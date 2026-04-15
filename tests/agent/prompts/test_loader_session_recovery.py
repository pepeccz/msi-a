"""
Unit tests for session recovery module loading condition in assemble_system_prompt().

RECOV-01: The session recovery module (core/11_session_recovery.md) must be
included when EITHER pending_recovery_case OR pending_abandoned_case is set in
mode_context, unless recovery_acknowledged=True.

All tests are pure unit tests — no DB, no Redis, no LLM, no I/O.
"""

from unittest.mock import patch

import pytest

import agent.prompts.loader as loader_module
from agent.prompts.loader import assemble_system_prompt

RECOVERY_SENTINEL = "__SESSION_RECOVERY_SENTINEL__"
OTHER_MODULE_CONTENT = "other-module-content"


def _make_load_module_mock(sentinel: str = RECOVERY_SENTINEL):
    """Return a side_effect function for _load_module.

    Returns the sentinel string only for the session recovery module,
    and a short placeholder for everything else (to avoid disk reads).
    """

    def _mock(relative_path: str) -> str:
        if relative_path == "core/11_session_recovery.md":
            return sentinel
        return OTHER_MODULE_CONTENT

    return _mock


class TestSessionRecoveryLoaderCondition:
    """assemble_system_prompt() includes session recovery module conditionally."""

    def test_pending_recovery_case_loads_module(self):
        """pending_recovery_case=True (no acknowledged) → recovery module included."""
        with patch.object(
            loader_module,
            "_load_module",
            side_effect=_make_load_module_mock(),
        ):
            result = assemble_system_prompt(
                mode="PRE_EXPEDIENTE_MODE",
                mode_context={"pending_recovery_case": True},
            )
        assert RECOVERY_SENTINEL in result

    def test_pending_abandoned_case_loads_module(self):
        """pending_abandoned_case=True (no acknowledged) → recovery module included."""
        with patch.object(
            loader_module,
            "_load_module",
            side_effect=_make_load_module_mock(),
        ):
            result = assemble_system_prompt(
                mode="PRE_EXPEDIENTE_MODE",
                mode_context={"pending_abandoned_case": True},
            )
        assert RECOVERY_SENTINEL in result

    def test_both_flags_set_loads_module_exactly_once(self):
        """Both pending_recovery_case and pending_abandoned_case set → module included exactly once."""
        call_count = {"n": 0}
        original_mock = _make_load_module_mock()

        def counting_mock(relative_path: str) -> str:
            if relative_path == "core/11_session_recovery.md":
                call_count["n"] += 1
            return original_mock(relative_path)

        with patch.object(
            loader_module,
            "_load_module",
            side_effect=counting_mock,
        ):
            result = assemble_system_prompt(
                mode="PRE_EXPEDIENTE_MODE",
                mode_context={
                    "pending_recovery_case": True,
                    "pending_abandoned_case": True,
                },
            )

        assert RECOVERY_SENTINEL in result
        assert call_count["n"] == 1, (
            f"11_session_recovery.md was loaded {call_count['n']} times, expected exactly 1"
        )

    def test_recovery_acknowledged_blocks_loading(self):
        """recovery_acknowledged=True → recovery module NOT included, regardless of pending flags."""
        with patch.object(
            loader_module,
            "_load_module",
            side_effect=_make_load_module_mock(),
        ):
            result = assemble_system_prompt(
                mode="PRE_EXPEDIENTE_MODE",
                mode_context={
                    "pending_recovery_case": True,
                    "pending_abandoned_case": True,
                    "recovery_acknowledged": True,
                },
            )
        assert RECOVERY_SENTINEL not in result

    def test_neither_flag_set_does_not_load_module(self):
        """Neither flag set → recovery module NOT included."""
        with patch.object(
            loader_module,
            "_load_module",
            side_effect=_make_load_module_mock(),
        ):
            result = assemble_system_prompt(
                mode="PRE_EXPEDIENTE_MODE",
                mode_context={"precio_comunicado": False},
            )
        assert RECOVERY_SENTINEL not in result

    def test_no_mode_context_does_not_load_module(self):
        """mode_context=None → recovery module NOT included."""
        with patch.object(
            loader_module,
            "_load_module",
            side_effect=_make_load_module_mock(),
        ):
            result = assemble_system_prompt(
                mode="PRE_EXPEDIENTE_MODE",
                mode_context=None,
            )
        assert RECOVERY_SENTINEL not in result
