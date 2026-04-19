"""
Unit tests for FallbackHandler EXPEDIENTE_MODE policy.

Ola 2 TDD:
  2.2 — EXPEDIENTE_MODE policy has action_on_limit == ESCALATE_TO_HUMAN and max_retries == 3
  2.3 — should_fallback returns True at retry_count >= 3, False below
"""
from __future__ import annotations

from agent.fallback.fallback_handler import (
    FallbackAction,
    FallbackHandler,
)
from agent.state.conversation_state import RetryStateData


# ---------------------------------------------------------------------------
# Task 2.2 — EXPEDIENTE_MODE policy shape
# ---------------------------------------------------------------------------

class TestExpedienteModePolicy:
    """EXPEDIENTE_MODE policy must have ESCALATE_TO_HUMAN and max_retries=3."""

    def test_action_on_limit_is_escalate_to_human(self):
        """action_on_limit must be ESCALATE_TO_HUMAN (hard hand-off)."""
        handler = FallbackHandler()
        policy = handler.get_policy("EXPEDIENTE_MODE")
        assert policy.action_on_limit == FallbackAction.ESCALATE_TO_HUMAN

    def test_max_retries_is_3(self):
        """max_retries must be 3 for EXPEDIENTE_MODE."""
        handler = FallbackHandler()
        policy = handler.get_policy("EXPEDIENTE_MODE")
        assert policy.max_retries == 3

    def test_msg_limit_is_spanish_and_non_empty(self):
        """msg_limit must be set and non-empty (Spanish hand-off message)."""
        handler = FallbackHandler()
        policy = handler.get_policy("EXPEDIENTE_MODE")
        assert policy.msg_limit is not None
        assert len(policy.msg_limit.strip()) > 0

    def test_msg_retry_1_is_non_empty(self):
        """msg_retry_1 must be defined for EXPEDIENTE_MODE."""
        handler = FallbackHandler()
        policy = handler.get_policy("EXPEDIENTE_MODE")
        assert policy.msg_retry_1 is not None
        assert len(policy.msg_retry_1.strip()) > 0


# ---------------------------------------------------------------------------
# Task 2.3 — should_fallback decision logic
# ---------------------------------------------------------------------------

class TestShouldFallbackExpediente:
    """should_fallback must fire at retry_count >= max_retries (3)."""

    def setup_method(self):
        self.handler = FallbackHandler()
        self.policy = self.handler.get_policy("EXPEDIENTE_MODE")

    def test_should_fallback_true_at_limit(self):
        """retry_count == 3 → should_fallback is True."""
        retry_state = RetryStateData(retry_count=3, consecutive_errors=3)
        assert self.handler.should_fallback(retry_state, self.policy) is True

    def test_should_fallback_true_above_limit(self):
        """retry_count > 3 → should_fallback is True."""
        retry_state = RetryStateData(retry_count=5, consecutive_errors=5)
        assert self.handler.should_fallback(retry_state, self.policy) is True

    def test_should_fallback_false_below_limit(self):
        """retry_count == 2 → should_fallback is False (one more chance)."""
        retry_state = RetryStateData(retry_count=2, consecutive_errors=2)
        assert self.handler.should_fallback(retry_state, self.policy) is False

    def test_should_fallback_false_at_zero(self):
        """retry_count == 0 → should_fallback is False."""
        retry_state = RetryStateData(retry_count=0, consecutive_errors=0)
        assert self.handler.should_fallback(retry_state, self.policy) is False

    def test_should_fallback_false_at_one(self):
        """retry_count == 1 → should_fallback is False."""
        retry_state = RetryStateData(retry_count=1, consecutive_errors=1)
        assert self.handler.should_fallback(retry_state, self.policy) is False
