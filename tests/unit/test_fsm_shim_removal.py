"""
Phase 3 — FSM shim removal tests.

Sub-step 3a (T-21/T-22): Fix get_mode_context() ContextVar trap
Sub-step 3b (T-23/T-24): Update 8 case tools to not use fsm_state
Sub-step 3c (T-25/T-26): Update case_service to return flat _state_update
Sub-step 3d (T-27/T-28): Remove _fsm_state_init from codebase
Sub-step 3e (T-29/T-32): Retire ExpedienteModeNode bridge
"""

from __future__ import annotations

import pytest

from agent.utils.expediente_types import CaseCollectionState, CollectionStep


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


def _make_mode_context(
    sub_mode: str = CollectionStep.IDLE.value,
    case_id: str | None = None,
    element_codes: list[str] | None = None,
    **extra,
) -> dict:
    return {
        "expediente_sub_mode": sub_mode,
        "case_id": case_id,
        "element_codes": element_codes or [],
        **extra,
    }


# ===========================================================================
# Sub-step 3a: Fix get_mode_context() ContextVar trap
# ===========================================================================


class TestGetModeContextWithExplicitDict:
    """T-21: get_mode_context(mode_context=...) bypasses ContextVar."""

    def test_get_mode_context_with_explicit_dict(self):
        """Pass mode_context dict, returns correct CaseCollectionState WITHOUT touching ContextVar."""
        from agent.services.expediente_helpers import get_mode_context

        mc = _make_mode_context(
            sub_mode=CollectionStep.COLLECT_PERSONAL.value,
            case_id="case-abc-123",
            element_codes=["ESCAPE"],
        )
        result = get_mode_context(mode_context=mc)

        assert result["step"] == CollectionStep.COLLECT_PERSONAL.value
        assert result["case_id"] == "case-abc-123"
        assert result["element_codes"] == ["ESCAPE"]

    def test_get_mode_context_legacy_path_unchanged(self):
        """No-arg call still reads ContextVar (backward compat)."""
        from agent.services.expediente_helpers import get_mode_context
        from agent.state.helpers import set_current_state

        set_current_state(
            {
                "current_mode": "EXPEDIENTE_MODE",
                "conversation_id": "test-conv",
                "mode_context": _make_mode_context(
                    sub_mode=CollectionStep.COLLECT_VEHICLE.value,
                    case_id="cv-456",
                ),
            }
        )
        result = get_mode_context()
        assert result["step"] == CollectionStep.COLLECT_VEHICLE.value
        assert result["case_id"] == "cv-456"

    def test_get_mode_context_no_contextvar_no_arg(self):
        """No ContextVar, no arg → returns INITIAL_CASE_STATE."""
        from agent.services.expediente_helpers import (
            INITIAL_CASE_STATE,
            get_mode_context,
        )

        result = get_mode_context()
        assert result["step"] == INITIAL_CASE_STATE["step"]

    def test_is_collection_active_with_mode_context(self):
        """is_collection_active(mode_context=...) returns True when case_id present and step active."""
        from agent.services.expediente_helpers import is_collection_active

        mc = _make_mode_context(
            sub_mode=CollectionStep.COLLECT_PERSONAL.value,
            case_id="active-case-001",
        )
        assert is_collection_active(mode_context=mc)

    def test_is_collection_active_empty_mode_context(self):
        """is_collection_active(mode_context={}) returns False (IDLE step)."""
        from agent.services.expediente_helpers import is_collection_active

        # Empty dict → defaults to IDLE step → not active
        assert not is_collection_active(mode_context={})


# ===========================================================================
# Sub-step 3b: Update 8 case tools
# ===========================================================================


class TestCaseToolsNoFsmState:
    """T-23: Case tools work without fsm_state in state dict."""

    def _make_state_without_fsm(
        self,
        sub_mode: str = CollectionStep.COLLECT_PERSONAL.value,
        case_id: str = "case-no-fsm-001",
    ) -> dict:
        """Build a ConversationState dict WITHOUT a 'fsm_state' key."""
        return {
            "current_mode": "EXPEDIENTE_MODE",
            "conversation_id": "conv-no-fsm-001",
            "user_id": "user-001",
            "client_type": "particular",
            "mode_context": _make_mode_context(
                sub_mode=sub_mode,
                case_id=case_id,
            ),
            # Explicitly NO 'fsm_state' key
        }

    def test_state_has_no_fsm_state_key(self):
        """Sanity check: our test state truly has no fsm_state key."""
        state = self._make_state_without_fsm()
        assert "fsm_state" not in state

    def test_case_tools_do_not_pass_fsm_state_to_service(self):
        """
        Verify that case_tools.py does NOT contain 'fsm_state=state.get("fsm_state")'
        after the refactor.

        This is a code-level static check.
        """
        import ast
        import pathlib

        case_tools_path = pathlib.Path(
            "agent/tools/case_tools.py"
        )
        source = case_tools_path.read_text()

        # The old pattern that should NO LONGER appear after T-24
        old_pattern = 'fsm_state=state.get("fsm_state")'
        assert old_pattern not in source, (
            f"Found legacy fsm_state=state.get('fsm_state') in case_tools.py — "
            f"this must be removed in T-24"
        )


# ===========================================================================
# Sub-step 3c: Update case_service to return flat _state_update
# ===========================================================================


class TestCaseServiceFlatStateUpdate:
    """T-25: case_service returns flat _state_update without case_collection_update key."""

    def test_initiate_case_no_longer_has_case_collection_update(self):
        """
        After T-26: initiate_case does NOT return a 'case_collection_update' key.

        We check that the service function signature and implementation no longer
        use 'case_collection_update' as a return key.
        """
        import inspect
        from agent.services import case_service

        source = inspect.getsource(case_service.initiate_case)
        # After T-26 this key should be gone from the return value
        assert "case_collection_update" not in source, (
            "initiate_case still returns 'case_collection_update' key — remove in T-26"
        )

    def test_update_personal_data_no_longer_has_case_collection_update(self):
        """After T-26: update_personal_data does NOT return 'case_collection_update'."""
        import inspect
        from agent.services import case_service

        source = inspect.getsource(case_service.update_personal_data)
        assert "case_collection_update" not in source, (
            "update_personal_data still returns 'case_collection_update' — remove in T-26"
        )

    def test_cancel_case_no_longer_has_case_collection_update(self):
        """After T-26: cancel_case does NOT return 'case_collection_update'."""
        import inspect
        from agent.services import case_service

        source = inspect.getsource(case_service.cancel_case)
        assert "case_collection_update" not in source, (
            "cancel_case still returns 'case_collection_update' — remove in T-26"
        )

    def test_get_case_status_no_transition(self):
        """
        get_case_status is read-only — it should never set expediente_sub_mode
        directly in its return value.
        """
        import inspect
        from agent.services import case_service

        source = inspect.getsource(case_service.get_case_status)
        # get_case_status is a read-only op; it must NOT write expediente_sub_mode
        assert "expediente_sub_mode" not in source, (
            "get_case_status should NOT set expediente_sub_mode — it is read-only"
        )


# ===========================================================================
# Sub-step 3d: Remove _fsm_state_init from codebase
# ===========================================================================


class TestFsmStateInitRemoved:
    """T-27: _fsm_state_init is removed from ExpedienteState and related files."""

    def test_expediente_state_no_fsm_state_init_field(self):
        """ExpedienteState TypedDict no longer has _fsm_state_init field."""
        import inspect
        from agent.modes import expediente_state

        source = inspect.getsource(expediente_state.ExpedienteState)
        assert "_fsm_state_init" not in source, (
            "ExpedienteState still has _fsm_state_init field — remove in T-28"
        )

    def test_fsm_state_init_not_in_expediente_mc_keys(self):
        """_EXPEDIENTE_MC_KEYS frozenset no longer includes '_fsm_state_init'."""
        from agent.modes.expediente_state import _EXPEDIENTE_MC_KEYS

        assert "_fsm_state_init" not in _EXPEDIENTE_MC_KEYS, (
            "_EXPEDIENTE_MC_KEYS still contains '_fsm_state_init' — remove in T-28"
        )

    def test_parent_to_expediente_no_keyerror(self):
        """
        parent_to_expediente works without _fsm_state_init key in parent state.

        This verifies the conversion boundary works correctly after removal.
        """
        from agent.modes.expediente_state import parent_to_expediente

        parent_state = {
            "conversation_id": "test-conv",
            "user_id": "user-001",
            "user_phone": "+34600000000",
            "user_name": "Test User",
            "client_type": "particular",
            "user_message": "Hola",
            "incoming_attachments": [],
            "mode_context": {
                "expediente_sub_mode": "collect_element_data",
                "case_id": "case-001",
                "element_codes": ["ESCAPE"],
            },
        }
        # Should not raise KeyError
        result = parent_to_expediente(parent_state)
        assert isinstance(result, dict)
        assert result.get("case_id") == "case-001"

    def test_fsm_state_not_in_expediente_nodes(self):
        """
        expediente_nodes.py _build_full_state_for_tools does NOT add 'fsm_state' key.

        After T-28, the 'fsm_state' line is removed from that function.
        """
        import inspect
        from agent.modes import expediente_nodes

        source = inspect.getsource(expediente_nodes._build_full_state_for_tools)
        assert '"fsm_state"' not in source, (
            "_build_full_state_for_tools still sets 'fsm_state' key — remove in T-28"
        )


# ===========================================================================
# Sub-step 3e: Retire ExpedienteModeNode bridge
# ===========================================================================


class TestExpedienteModeNodeBridgeRetired:
    """T-29/T-31: ExpedienteModeNode.extract_context_from_tool is no longer used."""

    def test_expediente_guards_does_not_import_ExpedienteModeNode(self):
        """
        expediente_guards.py no longer calls ExpedienteModeNode.extract_context_from_tool.

        Instead it uses _extract_expediente_context from post_tool_hooks.
        """
        import inspect
        from agent.services import expediente_guards

        source = inspect.getsource(expediente_guards)
        assert "ExpedienteModeNode" not in source, (
            "expediente_guards.py still references ExpedienteModeNode — replace in T-30"
        )

    def test_expediente_guards_uses_extract_expediente_context(self):
        """expediente_guards.py uses _extract_expediente_context from post_tool_hooks."""
        import inspect
        from agent.services import expediente_guards

        source = inspect.getsource(expediente_guards)
        assert "_extract_expediente_context" in source, (
            "expediente_guards.py does not use _extract_expediente_context — wire in T-30"
        )

    def test_expediente_mode_node_no_longer_calls_own_extract_context_in_guards(self):
        """
        ExpedienteModeNode._run_with_tool_loop no longer calls
        ExpedienteModeNode.extract_context_from_tool for post-tool context.

        Instead, the post-tool hook (expediente_post_tool_hook) calls
        _extract_expediente_context from post_tool_hooks directly.
        The bridge call in expediente_guards.py must NOT use
        ExpedienteModeNode.extract_context_from_tool.
        """
        import inspect
        from agent.services import expediente_guards

        source = inspect.getsource(expediente_guards)
        # Guards must NOT call ExpedienteModeNode.extract_context_from_tool
        assert "ExpedienteModeNode.extract_context_from_tool" not in source, (
            "expediente_guards still calls ExpedienteModeNode.extract_context_from_tool — "
            "this must be _extract_expediente_context from post_tool_hooks"
        )
