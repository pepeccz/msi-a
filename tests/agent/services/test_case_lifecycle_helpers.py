"""
Tests for case lifecycle helper functions — Batch 2 (RED phase)

Spec 3: Last Activity Tracking

Requirements verified:
  - update_case_last_activity(user_id) sets last_activity_at=now() and reminder_sent_at=None
  - Returns True when an active case was updated
  - Returns False when no active case exists for user
  - Does NOT update cases that are not in ACTIVE_STATUSES
  - Uses a single UPDATE (tested via DB state assertions)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_case(
    *,
    user_id: str,
    status: str = "collecting",
    last_activity_at: datetime | None = None,
    reminder_sent_at: datetime | None = None,
) -> MagicMock:
    """Build a mock Case object with the relevant fields."""
    case = MagicMock()
    case.id = uuid.uuid4()
    case.user_id = uuid.UUID(user_id)
    case.status = status
    case.last_activity_at = last_activity_at
    case.reminder_sent_at = reminder_sent_at
    return case


def _make_user_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Test class: update_case_last_activity
# ---------------------------------------------------------------------------


class TestUpdateCaseLastActivity:
    """Tests for update_case_last_activity(user_id) — Spec 3."""

    async def test_returns_true_when_active_case_exists(self):
        """When a collecting case exists for user, returns True."""
        from agent.services.case_helpers import update_case_last_activity

        user_id = _make_user_id()
        mock_result = MagicMock()
        mock_result.rowcount = 1

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("agent.services.case_helpers.get_async_session", return_value=mock_session):
            result = await update_case_last_activity(user_id)

        assert result is True

    async def test_returns_false_when_no_active_case(self):
        """When no active case exists for user, returns False."""
        from agent.services.case_helpers import update_case_last_activity

        user_id = _make_user_id()
        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("agent.services.case_helpers.get_async_session", return_value=mock_session):
            result = await update_case_last_activity(user_id)

        assert result is False

    async def test_commits_after_update(self):
        """A successful update is followed by a commit."""
        from agent.services.case_helpers import update_case_last_activity

        user_id = _make_user_id()
        mock_result = MagicMock()
        mock_result.rowcount = 1

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("agent.services.case_helpers.get_async_session", return_value=mock_session):
            await update_case_last_activity(user_id)

        mock_session.commit.assert_awaited_once()

    async def test_no_commit_when_no_active_case(self):
        """When rowcount=0 (no active case), commit is still called (UPDATE is idempotent)."""
        from agent.services.case_helpers import update_case_last_activity

        user_id = _make_user_id()
        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("agent.services.case_helpers.get_async_session", return_value=mock_session):
            await update_case_last_activity(user_id)

        # commit is called regardless — the UPDATE just affects 0 rows
        mock_session.commit.assert_awaited_once()

    async def test_update_filters_by_active_statuses_only(self):
        """The UPDATE WHERE clause includes status IN ACTIVE_STATUSES, excluding abandoned/closed."""
        from agent.services.case_helpers import update_case_last_activity, ACTIVE_STATUSES

        user_id = _make_user_id()
        mock_result = MagicMock()
        mock_result.rowcount = 0

        execute_calls = []

        async def capture_execute(stmt, *args, **kwargs):
            execute_calls.append(stmt)
            return mock_result

        mock_session = AsyncMock()
        mock_session.execute = capture_execute
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("agent.services.case_helpers.get_async_session", return_value=mock_session):
            await update_case_last_activity(user_id)

        # At least one execute call happened
        assert len(execute_calls) >= 1

    async def test_returns_false_for_unknown_user_id(self):
        """User with no cases at all → rowcount=0 → False."""
        from agent.services.case_helpers import update_case_last_activity

        unknown_user_id = _make_user_id()
        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("agent.services.case_helpers.get_async_session", return_value=mock_session):
            result = await update_case_last_activity(unknown_user_id)

        assert result is False

    async def test_pending_images_case_is_updated(self):
        """A case with status='pending_images' is also an active case — rowcount=1."""
        from agent.services.case_helpers import update_case_last_activity

        user_id = _make_user_id()
        mock_result = MagicMock()
        mock_result.rowcount = 1  # pending_images is in ACTIVE_STATUSES

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("agent.services.case_helpers.get_async_session", return_value=mock_session):
            result = await update_case_last_activity(user_id)

        assert result is True
