"""
Guard: dead code in agent.modes.expediente_mode must be removed by Batch B.

This test is expected to FAIL until Batch B deletes:
  - _process_message method
  - _build_tool_loop_fn method
  - _HANDLERS dispatch table
  - canonicalize_transition import

The guard also asserts that _guard_photo_completion_intent is PRESERVED
(it must remain importable after the dead-code removal).

Requirements: R3.1 — _process_message removed
              R3.2 — _build_tool_loop_fn removed
              R3.3 — _HANDLERS dispatch table removed
              R3.4 — canonicalize_transition import removed
              R3.5 — _guard_photo_completion_intent preserved (must stay TRUE)
"""

from __future__ import annotations

import importlib
import sys

import pytest

from agent.modes.expediente_mode import ExpedienteModeNode


@pytest.fixture(scope="module")
def expediente_mode_module():
    """Return the expediente_mode module object for namespace inspection."""
    return sys.modules.get(
        "agent.modes.expediente_mode",
        importlib.import_module("agent.modes.expediente_mode"),
    )


class TestDeadCodeRemoved:
    """Batch B must delete these methods/attributes from ExpedienteModeNode."""

    def test_process_message_not_present(self) -> None:
        """
        _process_message is dead code: the live path runs through
        expediente_subgraph_node, not through this method.
        """
        assert not hasattr(ExpedienteModeNode, "_process_message"), (
            "ExpedienteModeNode._process_message still exists. "
            "Remove it in Batch B — the live path is expediente_subgraph_node."
        )

    def test_build_tool_loop_fn_not_present(self) -> None:
        """
        _build_tool_loop_fn (and its nested _tool_loop_adapter / _run_with_tool_loop)
        are dead code referenced only by the deleted _process_message.
        """
        assert not hasattr(ExpedienteModeNode, "_build_tool_loop_fn"), (
            "ExpedienteModeNode._build_tool_loop_fn still exists. "
            "Remove it in Batch B along with _process_message."
        )

    def test_handlers_dispatch_table_not_present(
        self, expediente_mode_module
    ) -> None:
        """
        _HANDLERS is a module-level dispatch table used only by _process_message.
        Once _process_message is removed, _HANDLERS has no live consumer.

        Note: _HANDLERS is defined at module scope (line 97), NOT as a class
        attribute — so we check the module namespace, not the class.
        """
        assert not hasattr(expediente_mode_module, "_HANDLERS"), (
            "agent.modes.expediente_mode._HANDLERS (module-level dispatch table) "
            "still exists. Remove it in Batch B — it was only consumed by the "
            "dead _process_message method."
        )

    def test_canonicalize_transition_not_in_module_namespace(
        self, expediente_mode_module
    ) -> None:
        """
        canonicalize_transition was imported but never used by the live path.
        The import line must be removed from agent/modes/expediente_mode.py.
        """
        assert not hasattr(expediente_mode_module, "canonicalize_transition"), (
            "canonicalize_transition is still in the agent.modes.expediente_mode "
            "namespace. Remove the import at line 58 in Batch B."
        )


class TestLiveCodePreserved:
    """These must survive Batch B untouched."""

    def test_guard_photo_completion_intent_preserved(self) -> None:
        """
        _guard_photo_completion_intent is the LIVE guard imported by
        tests/test_expediente_photo_confirmation_guard.py. It must never be removed.
        """
        assert hasattr(ExpedienteModeNode, "_guard_photo_completion_intent"), (
            "ExpedienteModeNode._guard_photo_completion_intent is missing. "
            "This method must be preserved — it is part of the live photo guard."
        )
