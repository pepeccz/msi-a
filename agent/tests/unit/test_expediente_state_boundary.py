"""
Unit tests for retry_state threading through the expediente subgraph boundary.

Ola 1 TDD:
  1.1 — parent_to_expediente copies retry_state from parent ConversationState
  1.5 — round-trip: parent → mutate → expediente_to_parent_updates preserves it
  1.6 — exit_reason propagates from ExpedienteState to parent updates
  1.7 — sentinel keys _fallback_triggered + escalation_reason propagate to parent
"""
from __future__ import annotations

from agent.modes.expediente_state import parent_to_expediente, expediente_to_parent_updates


# ---------------------------------------------------------------------------
# Task 1.1 — retry_state injected into ExpedienteState from parent
# ---------------------------------------------------------------------------

class TestParentToExpediente:
    """parent_to_expediente must thread retry_state from parent into ExpedienteState."""

    def test_retry_state_copied_into_expediente(self):
        """Seed parent with retry_count=2 — ExpedienteState must carry it."""
        parent_state = {
            "conversation_id": "conv-001",
            "user_id": "user-001",
            "user_phone": "+34600000001",
            "user_message": "Hola",
            "mode_context": {},
            "retry_state": {"retry_count": 2, "consecutive_errors": 1},
        }
        exp = parent_to_expediente(parent_state)
        assert exp.get("retry_state") is not None
        assert exp["retry_state"]["retry_count"] == 2

    def test_retry_state_defaults_to_empty_when_missing(self):
        """If parent has no retry_state, ExpedienteState gets create_empty_retry_state()."""
        parent_state = {
            "conversation_id": "conv-002",
            "user_id": None,
            "user_phone": "+34600000002",
            "user_message": "",
            "mode_context": {},
            # no retry_state key
        }
        exp = parent_to_expediente(parent_state)
        assert exp.get("retry_state") is not None
        assert exp["retry_state"].get("retry_count", 0) == 0

    def test_retry_state_none_defaults_to_empty(self):
        """If parent retry_state is None, ExpedienteState gets empty state."""
        parent_state = {
            "conversation_id": "conv-003",
            "user_id": None,
            "user_phone": "+34600000003",
            "user_message": "",
            "mode_context": {},
            "retry_state": None,
        }
        exp = parent_to_expediente(parent_state)
        assert exp.get("retry_state") is not None
        assert exp["retry_state"].get("retry_count", 0) == 0


# ---------------------------------------------------------------------------
# Task 1.5 — round-trip: retry_state preserved through write-back
# ---------------------------------------------------------------------------

class TestExpedienteToParentUpdates:
    """expediente_to_parent_updates must write retry_state back at top level (not mode_context)."""

    def test_round_trip_preserves_retry_count(self):
        """Mutate retry_count inside ExpedienteState and verify write-back."""
        parent_state = {
            "conversation_id": "conv-010",
            "user_id": "user-010",
            "user_phone": "+34600000010",
            "user_message": "test",
            "mode_context": {},
            "retry_state": {"retry_count": 1, "consecutive_errors": 1},
        }
        exp = parent_to_expediente(parent_state)

        # Simulate sub-node mutating retry_state
        exp["retry_state"] = {"retry_count": 3, "consecutive_errors": 3}

        updates = expediente_to_parent_updates(exp)

        assert "retry_state" in updates, "retry_state must be at parent top level"
        assert updates["retry_state"]["retry_count"] == 3

    def test_retry_state_not_inside_mode_context(self):
        """retry_state must NOT be nested inside mode_context — it's a parent top-level key."""
        parent_state = {
            "conversation_id": "conv-011",
            "user_id": None,
            "user_phone": "+34600000011",
            "user_message": "test",
            "mode_context": {},
            "retry_state": {"retry_count": 2, "consecutive_errors": 2},
        }
        exp = parent_to_expediente(parent_state)
        exp["retry_state"] = {"retry_count": 2, "consecutive_errors": 2}

        updates = expediente_to_parent_updates(exp)

        mode_ctx = updates.get("mode_context", {})
        assert "retry_state" not in mode_ctx, (
            "retry_state must be at top level, NOT inside mode_context"
        )

    def test_consecutive_errors_preserved_in_round_trip(self):
        """consecutive_errors also round-trips correctly."""
        parent_state = {
            "conversation_id": "conv-012",
            "user_id": None,
            "user_phone": "+34600000012",
            "user_message": "",
            "mode_context": {},
            "retry_state": {"retry_count": 0, "consecutive_errors": 0},
        }
        exp = parent_to_expediente(parent_state)
        exp["retry_state"] = {"retry_count": 1, "consecutive_errors": 1}

        updates = expediente_to_parent_updates(exp)

        assert updates["retry_state"]["consecutive_errors"] == 1


# ---------------------------------------------------------------------------
# Task 1.6 — exit_reason propagates to parent updates
# ---------------------------------------------------------------------------

class TestExitReason:
    """exit_reason must propagate from ExpedienteState to parent updates (top level)."""

    def test_exit_reason_max_iterations_propagates(self):
        """exit_reason='max_iterations' written by sub-node arrives in parent updates."""
        parent_state = {
            "conversation_id": "conv-020",
            "user_id": None,
            "user_phone": "+34600000020",
            "user_message": "",
            "mode_context": {},
        }
        exp = parent_to_expediente(parent_state)
        exp["exit_reason"] = "max_iterations"
        exp["ai_response"] = ""

        updates = expediente_to_parent_updates(exp)

        assert updates.get("exit_reason") == "max_iterations"

    def test_exit_reason_not_in_mode_context(self):
        """exit_reason must NOT leak into mode_context."""
        parent_state = {
            "conversation_id": "conv-021",
            "user_id": None,
            "user_phone": "+34600000021",
            "user_message": "",
            "mode_context": {},
        }
        exp = parent_to_expediente(parent_state)
        exp["exit_reason"] = "escalated"

        updates = expediente_to_parent_updates(exp)

        assert "exit_reason" not in updates.get("mode_context", {})


# ---------------------------------------------------------------------------
# Task 1.7 — sentinel keys _fallback_triggered + escalation_reason propagate
# ---------------------------------------------------------------------------

class TestSentinelKeys:
    """Boundary-only sentinel keys must propagate to top-level parent updates."""

    def test_fallback_triggered_propagates_to_parent_updates(self):
        """_fallback_triggered=True written by sub-node arrives in parent updates."""
        parent_state = {
            "conversation_id": "conv-030",
            "user_id": None,
            "user_phone": "+34600000030",
            "user_message": "",
            "mode_context": {},
        }
        exp = parent_to_expediente(parent_state)
        exp["_fallback_triggered"] = True
        exp["escalation_reason"] = "expediente_retry_limit_3"

        updates = expediente_to_parent_updates(exp)

        assert updates.get("_fallback_triggered") is True
        assert updates.get("escalation_reason") == "expediente_retry_limit_3"

    def test_sentinel_keys_not_in_mode_context(self):
        """Sentinel keys must NOT leak into mode_context."""
        parent_state = {
            "conversation_id": "conv-031",
            "user_id": None,
            "user_phone": "+34600000031",
            "user_message": "",
            "mode_context": {},
        }
        exp = parent_to_expediente(parent_state)
        exp["_fallback_triggered"] = True
        exp["escalation_reason"] = "expediente_retry_limit_3"

        updates = expediente_to_parent_updates(exp)

        mc = updates.get("mode_context", {})
        assert "_fallback_triggered" not in mc
        assert "escalation_reason" not in mc
