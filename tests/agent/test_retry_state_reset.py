"""
Tests for _reset_validation_retry_state helper.

Task 5.1 — fix-category-routing-and-retry-contamination

Coverage:
- Resets retry_count → 0
- Preserves consecutive_errors
- Clears last_validation_context, last_error_type, last_error_message
- Is a no-op on already-clean state
"""

import pytest

from agent.modes.presupuesto_mode import _reset_validation_retry_state


# =============================================================================
# TESTS
# =============================================================================

class TestResetValidationRetryState:
    """Tests for _reset_validation_retry_state helper (Task 5.1)."""

    def test_reset_clears_retry_count(self):
        """retry_count must be set to 0 after reset."""
        state = {
            "retry_count": 3,
            "consecutive_errors": 2,
            "last_validation_context": {"x": 1},
            "last_error_type": "foo",
            "last_error_message": "bar",
            "first_error_at": "2026-01-01",
            "last_retry_at": "2026-01-01",
        }
        result = _reset_validation_retry_state(state)
        assert result["retry_count"] == 0

    def test_reset_preserves_consecutive_errors(self):
        """consecutive_errors must be preserved (drives outer escalation)."""
        state = {
            "retry_count": 3,
            "consecutive_errors": 5,
            "last_validation_context": {"x": 1},
            "last_error_type": "foo",
            "last_error_message": "bar",
            "first_error_at": "2026-01-01",
            "last_retry_at": "2026-01-01",
        }
        result = _reset_validation_retry_state(state)
        assert result["consecutive_errors"] == 5

    def test_reset_clears_validation_context(self):
        """last_validation_context, last_error_type, and last_error_message must be None."""
        state = {
            "retry_count": 1,
            "consecutive_errors": 0,
            "last_validation_context": {"tool": "foo", "errors": ["err"]},
            "last_error_type": "validation",
            "last_error_message": "bad input",
            "first_error_at": "2026-01-01",
            "last_retry_at": "2026-01-01",
        }
        result = _reset_validation_retry_state(state)
        assert result["last_validation_context"] is None
        assert result["last_error_type"] is None
        assert result["last_error_message"] is None

    def test_reset_on_clean_state_is_noop(self):
        """Calling reset on an already-clean state returns identical values."""
        state = {
            "retry_count": 0,
            "consecutive_errors": 0,
            "last_validation_context": None,
            "last_error_type": None,
            "last_error_message": None,
            "first_error_at": None,
            "last_retry_at": None,
        }
        result = _reset_validation_retry_state(state)
        assert result["retry_count"] == 0
        assert result["consecutive_errors"] == 0
        assert result["last_validation_context"] is None
        assert result["last_error_type"] is None
        assert result["last_error_message"] is None

    def test_reset_preserves_timestamp_fields(self):
        """first_error_at and last_retry_at are preserved (not wiped)."""
        state = {
            "retry_count": 2,
            "consecutive_errors": 1,
            "last_validation_context": {"tool": "x"},
            "last_error_type": "validation",
            "last_error_message": "err",
            "first_error_at": "2026-01-15T10:00:00",
            "last_retry_at": "2026-01-15T10:05:00",
        }
        result = _reset_validation_retry_state(state)
        # Timestamps survive the reset (they chronicle when errors occurred)
        assert result["first_error_at"] == "2026-01-15T10:00:00"
        assert result["last_retry_at"] == "2026-01-15T10:05:00"

    def test_reset_returns_new_dict(self):
        """Result must be a new dict, not a mutation of the original."""
        state = {
            "retry_count": 3,
            "consecutive_errors": 1,
            "last_validation_context": {"tool": "x"},
            "last_error_type": "validation",
            "last_error_message": "err",
            "first_error_at": None,
            "last_retry_at": None,
        }
        result = _reset_validation_retry_state(state)
        # Original must be untouched
        assert state["retry_count"] == 3
        assert result["retry_count"] == 0
        assert result is not state

    def test_reset_high_consecutive_errors_preserved(self):
        """High consecutive_errors count is preserved for escalation logic."""
        state = {
            "retry_count": 10,
            "consecutive_errors": 99,
            "last_validation_context": {"errors": ["a", "b"]},
            "last_error_type": "tool_call_failed",
            "last_error_message": "tool blew up",
            "first_error_at": "2026-01-01",
            "last_retry_at": "2026-02-01",
        }
        result = _reset_validation_retry_state(state)
        assert result["consecutive_errors"] == 99
        assert result["retry_count"] == 0
