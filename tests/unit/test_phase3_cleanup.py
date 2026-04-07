"""
Phase 3 structural-cleanup RED tests.

These tests assert the DESIRED post-cleanup state.  They are written FIRST
(TDD RED phase) and will fail until the corresponding Phase 2 deletions are
applied.

Tests cover:
  1.1  expediente_guardrails.py does NOT exist on disk.
  1.2  BaseModeNode has no _validate_response_constraints attribute.
  1.3  agent.modes.submodos._shared is importable AND CertaintyEnvelope /
       ClaimClass are NOT in its namespace.
  1.4  agent.modes.generic_loop module has no _apply_internal_flags function.
  1.5  _apply_state_updates handles three payload shapes correctly:
       _internal_flags only, _state_update only, both combined.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# 1.1 — expediente_guardrails.py must NOT exist on disk
# ---------------------------------------------------------------------------


class TestGuardrailsFileDeletion:
    """Task 1.1: expediente_guardrails.py must be absent after Phase 2."""

    def test_guardrails_file_absent(self) -> None:
        """The file agent/modes/expediente_guardrails.py must not exist on disk."""
        # Locate the project root relative to this test file
        project_root = Path(__file__).resolve().parents[2]
        guardrails_path = project_root / "agent" / "modes" / "expediente_guardrails.py"

        assert not guardrails_path.exists(), (
            f"expediente_guardrails.py still exists at {guardrails_path}. "
            "Delete the file entirely as part of Phase 2 task 2.1."
        )


# ---------------------------------------------------------------------------
# 1.2 — BaseModeNode must NOT have _validate_response_constraints
# ---------------------------------------------------------------------------


class TestBaseModeNodeMethodDeletion:
    """Task 1.2: _validate_response_constraints must be removed from BaseModeNode."""

    def test_validate_response_constraints_absent(self) -> None:
        """hasattr(BaseModeNode, '_validate_response_constraints') must be False."""
        from agent.modes.base_mode import BaseModeNode

        assert not hasattr(BaseModeNode, "_validate_response_constraints"), (
            "BaseModeNode still has '_validate_response_constraints'. "
            "Delete the method (lines 647-743 approximately) as Phase 2 task 2.4."
        )


# ---------------------------------------------------------------------------
# 1.3 — _shared importable; CertaintyEnvelope / ClaimClass NOT in namespace
# ---------------------------------------------------------------------------


class TestSharedModuleCleanup:
    """Task 1.3: agent.modes.submodos._shared must import cleanly without guardrail symbols."""

    def test_shared_imports_without_error(self) -> None:
        """Importing agent.modes.submodos._shared must not raise ImportError."""
        try:
            importlib.import_module("agent.modes.submodos._shared")
        except ImportError as exc:
            pytest.fail(
                f"agent.modes.submodos._shared raised ImportError after guardrail cleanup: {exc}"
            )

    def test_certainty_envelope_not_in_shared_namespace(self) -> None:
        """CertaintyEnvelope must NOT be importable from agent.modes.submodos._shared."""
        mod = importlib.import_module("agent.modes.submodos._shared")
        assert not hasattr(mod, "CertaintyEnvelope"), (
            "CertaintyEnvelope is still present in _shared namespace. "
            "Remove the guardrail import block (lines 46-51) as Phase 2 task 2.3."
        )

    def test_claim_class_not_in_shared_namespace(self) -> None:
        """ClaimClass must NOT be importable from agent.modes.submodos._shared."""
        mod = importlib.import_module("agent.modes.submodos._shared")
        assert not hasattr(mod, "ClaimClass"), (
            "ClaimClass is still present in _shared namespace. "
            "Remove the guardrail import block (lines 46-51) as Phase 2 task 2.3."
        )


# ---------------------------------------------------------------------------
# 1.4 — generic_loop must NOT have _apply_internal_flags
# ---------------------------------------------------------------------------


class TestGenericLoopInlining:
    """Task 1.4: _apply_internal_flags must be inlined into _apply_state_updates and deleted."""

    def test_apply_internal_flags_absent_from_module(self) -> None:
        """_apply_internal_flags must NOT appear in dir(generic_loop module)."""
        import agent.modes.generic_loop as gl_module

        assert "_apply_internal_flags" not in dir(gl_module), (
            "_apply_internal_flags still exists as a top-level name in generic_loop. "
            "Inline its body into _apply_state_updates and delete the function "
            "as Phase 2 task 2.5."
        )


# ---------------------------------------------------------------------------
# 1.5 — _apply_state_updates handles three payload shapes
# ---------------------------------------------------------------------------


class TestApplyStateUpdatesContract:
    """
    Task 1.5: _apply_state_updates must handle three distinct payload shapes.

    After Phase 2 task 2.5 inlines _apply_internal_flags, the function must
    still handle ALL three shapes correctly with no separate helper required.

    Parametrized cases:
      A — _internal_flags only  (legacy channel)
      B — _state_update only    (new canonical channel)
      C — both present          (_state_update takes precedence)
    """

    @pytest.mark.parametrize(
        "result_dict, expected_updates",
        [
            pytest.param(
                # Case A: legacy _internal_flags only
                {
                    "success": True,
                    "_internal_flags": {
                        "precio_comunicado": True,
                        "imagenes_enviadas": False,
                    },
                },
                {
                    "precio_comunicado": True,
                    "imagenes_enviadas": False,
                },
                id="internal_flags_only",
            ),
            pytest.param(
                # Case B: new _state_update channel only
                {
                    "success": True,
                    "_state_update": {
                        "precio_comunicado": True,
                        "tarifa_calculada": 450.0,
                    },
                },
                {
                    "precio_comunicado": True,
                    "tarifa_calculada": 450.0,
                },
                id="state_update_only",
            ),
            pytest.param(
                # Case C: both present — _state_update takes precedence
                {
                    "success": True,
                    "_state_update": {"precio_comunicado": True},
                    "_internal_flags": {
                        "precio_comunicado": False,
                        "imagenes_enviadas": True,
                    },
                },
                # _state_update wins; _internal_flags is NOT merged
                {
                    "precio_comunicado": True,
                },
                id="both_present_state_update_wins",
            ),
        ],
    )
    def test_apply_state_updates_parametrized(
        self, result_dict: dict, expected_updates: dict
    ) -> None:
        """
        _apply_state_updates must merge the correct channel into context_updates.

        After inlining, there is no _apply_internal_flags call — the logic is
        handled entirely within _apply_state_updates itself.
        """
        from agent.modes.generic_loop import _apply_state_updates

        context_updates: dict = {}
        _apply_state_updates(context_updates, result_dict)

        for key, expected_value in expected_updates.items():
            assert context_updates.get(key) == expected_value, (
                f"Expected context_updates[{key!r}] == {expected_value!r}, "
                f"got {context_updates.get(key)!r}. "
                "Check _apply_state_updates implementation in generic_loop.py."
            )

    def test_apply_state_updates_transition_to_preserved(self) -> None:
        """_transition_to inside _state_update must surface as a top-level key."""
        from agent.modes.generic_loop import _apply_state_updates

        context_updates: dict = {}
        _apply_state_updates(
            context_updates,
            {"_state_update": {"_transition_to": "EXPEDIENTE_MODE", "some_flag": True}},
        )

        assert context_updates.get("_transition_to") == "EXPEDIENTE_MODE"
        assert context_updates.get("some_flag") is True

    def test_apply_state_updates_noop_on_empty_result(self) -> None:
        """_apply_state_updates must not raise or mutate context when result has no channels."""
        from agent.modes.generic_loop import _apply_state_updates

        context_updates: dict = {}
        _apply_state_updates(context_updates, {"success": True, "data": "something"})

        # Must remain empty — no channels to merge
        assert context_updates == {}, (
            f"context_updates should be empty but got {context_updates!r}"
        )
