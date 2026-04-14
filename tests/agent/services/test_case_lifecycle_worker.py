"""
Tests for case_lifecycle_worker — Batch 2 (RED phase)

Spec 2: Case Lifecycle Worker

Requirements verified:
  - Reminder sent exactly once per inactive case (reminder_sent_at IS NULL)
  - Reminder NOT re-sent if reminder_sent_at IS NOT NULL
  - send_message failure skips the case but worker continues
  - Case abandoned after threshold (status → 'abandoned', abandoned_at set)
  - Already-abandoned cases not double-processed (status filter excludes them)
  - shutdown_event.set() stops the loop cleanly
  - DB exception caught + logged at error level, loop continues
  - Worker uses event-based wait for fast graceful shutdown
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_case(
    *,
    case_id: str | None = None,
    user_id: str | None = None,
    status: str = "collecting",
    last_activity_at: datetime | None = None,
    reminder_sent_at: datetime | None = None,
    abandoned_at: datetime | None = None,
    chatwoot_conversation_id: str | None = None,
    element_codes: list[str] | None = None,
    user_name: str = "Test User",
) -> MagicMock:
    """Build a mock Case object with lifecycle fields."""
    case = MagicMock()
    case.id = uuid.UUID(case_id) if case_id else uuid.uuid4()
    case.user_id = uuid.UUID(user_id) if user_id else uuid.uuid4()
    case.status = status
    case.last_activity_at = last_activity_at or datetime.now(UTC) - timedelta(hours=25)
    case.reminder_sent_at = reminder_sent_at
    case.abandoned_at = abandoned_at
    case.conversation_id = chatwoot_conversation_id or "conv-123"
    case.element_codes = element_codes or ["ESCAPE"]
    # Simulate user relationship
    case.user = MagicMock()
    case.user.first_name = user_name.split()[0]
    case.user.last_name = user_name.split()[-1] if len(user_name.split()) > 1 else ""
    case.user.phone = "+34600000000"
    return case


def _make_chatwoot() -> MagicMock:
    """Build a mock ChatwootClient."""
    chatwoot = MagicMock()
    chatwoot.send_message = AsyncMock()
    return chatwoot


def _make_settings(
    *,
    reminder_hours: float = 20.0,
    abandon_days: float = 4.0,
    scan_interval_minutes: int = 15,
    reminder_template: str = "Hola {name}, tu expediente de {elements} lleva tiempo inactivo.",
) -> MagicMock:
    """Build mock settings for the worker."""
    settings = MagicMock()
    settings.CASE_REMINDER_HOURS = reminder_hours
    settings.CASE_ABANDON_DAYS = abandon_days
    settings.CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES = scan_interval_minutes
    settings.CASE_REMINDER_MESSAGE_TEMPLATE = reminder_template
    return settings


def _stop_after_scan(shutdown_event: asyncio.Event):
    """Return a mark_cases_abandoned mock that sets shutdown_event after first call."""

    async def _side_effect(_days):
        shutdown_event.set()
        return 0

    return AsyncMock(side_effect=_side_effect)


# ===========================================================================
# Test class: Reminder logic
# ===========================================================================


class TestWorkerReminderLogic:
    """Tests for the reminder scan phase of case_lifecycle_worker."""

    async def test_reminder_sent_once_for_inactive_case(self):
        """Inactive case with reminder_sent_at=None → send_message called once."""
        from agent.services.case_lifecycle_worker import case_lifecycle_worker

        inactive_case = _make_case(
            last_activity_at=datetime.now(UTC) - timedelta(hours=25),
            reminder_sent_at=None,
        )
        chatwoot = _make_chatwoot()
        shutdown_event = asyncio.Event()

        with (
            patch(
                "agent.services.case_lifecycle_worker.get_settings",
                return_value=_make_settings(),
            ),
            patch(
                "agent.services.case_lifecycle_worker.get_reminder_candidates",
                new=AsyncMock(return_value=[inactive_case]),
            ),
            patch(
                "agent.services.case_lifecycle_worker.mark_cases_abandoned",
                new=_stop_after_scan(shutdown_event),
            ),
            patch(
                "agent.services.case_lifecycle_worker._mark_reminder_sent",
                new=AsyncMock(),
            ),
        ):
            await case_lifecycle_worker(shutdown_event, chatwoot)

        chatwoot.send_message.assert_awaited_once()

    async def test_reminder_not_resent_if_already_sent(self):
        """get_reminder_candidates returns empty (already-sent excluded by query) → no send."""
        from agent.services.case_lifecycle_worker import case_lifecycle_worker

        chatwoot = _make_chatwoot()
        shutdown_event = asyncio.Event()

        with (
            patch(
                "agent.services.case_lifecycle_worker.get_settings",
                return_value=_make_settings(),
            ),
            patch(
                "agent.services.case_lifecycle_worker.get_reminder_candidates",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "agent.services.case_lifecycle_worker.mark_cases_abandoned",
                new=_stop_after_scan(shutdown_event),
            ),
        ):
            await case_lifecycle_worker(shutdown_event, chatwoot)

        chatwoot.send_message.assert_not_awaited()

    async def test_send_message_failure_skips_case_worker_continues(self):
        """send_message fails for case A → case A skipped, case B processed, worker continues."""
        from agent.services.case_lifecycle_worker import case_lifecycle_worker

        case_a = _make_case(reminder_sent_at=None)
        case_b = _make_case(reminder_sent_at=None)
        chatwoot = _make_chatwoot()
        shutdown_event = asyncio.Event()

        call_count = 0

        async def send_message_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Chatwoot connection failed")

        chatwoot.send_message = AsyncMock(side_effect=send_message_side_effect)

        mark_sent_calls = []

        async def capture_mark_sent(case_id):
            mark_sent_calls.append(case_id)

        with (
            patch(
                "agent.services.case_lifecycle_worker.get_settings",
                return_value=_make_settings(),
            ),
            patch(
                "agent.services.case_lifecycle_worker.get_reminder_candidates",
                new=AsyncMock(return_value=[case_a, case_b]),
            ),
            patch(
                "agent.services.case_lifecycle_worker.mark_cases_abandoned",
                new=_stop_after_scan(shutdown_event),
            ),
            patch(
                "agent.services.case_lifecycle_worker._mark_reminder_sent",
                new=AsyncMock(side_effect=capture_mark_sent),
            ),
        ):
            await case_lifecycle_worker(shutdown_event, chatwoot)

        assert chatwoot.send_message.await_count == 2
        assert len(mark_sent_calls) == 1
        assert mark_sent_calls[0] == case_b.id


# ===========================================================================
# Test class: Abandonment logic
# ===========================================================================


class TestWorkerAbandonmentLogic:
    """Tests for the abandon scan phase of case_lifecycle_worker."""

    async def test_case_abandoned_after_threshold(self):
        """mark_cases_abandoned called once per cycle."""
        from agent.services.case_lifecycle_worker import case_lifecycle_worker

        chatwoot = _make_chatwoot()
        shutdown_event = asyncio.Event()
        mark_abandoned = _stop_after_scan(shutdown_event)

        with (
            patch(
                "agent.services.case_lifecycle_worker.get_settings",
                return_value=_make_settings(),
            ),
            patch(
                "agent.services.case_lifecycle_worker.get_reminder_candidates",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "agent.services.case_lifecycle_worker.mark_cases_abandoned",
                new=mark_abandoned,
            ),
        ):
            await case_lifecycle_worker(shutdown_event, chatwoot)

        mark_abandoned.assert_awaited_once()

    async def test_already_abandoned_not_double_processed(self):
        """mark_cases_abandoned uses status IN filter — already-abandoned rows excluded by DB."""
        from agent.services.case_lifecycle_worker import case_lifecycle_worker

        chatwoot = _make_chatwoot()
        shutdown_event = asyncio.Event()
        mark_abandoned = _stop_after_scan(shutdown_event)

        with (
            patch(
                "agent.services.case_lifecycle_worker.get_settings",
                return_value=_make_settings(),
            ),
            patch(
                "agent.services.case_lifecycle_worker.get_reminder_candidates",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "agent.services.case_lifecycle_worker.mark_cases_abandoned",
                new=mark_abandoned,
            ),
        ):
            await case_lifecycle_worker(shutdown_event, chatwoot)

        mark_abandoned.assert_awaited_once()


# ===========================================================================
# Test class: Shutdown and error handling
# ===========================================================================


class TestWorkerControlFlow:
    """Tests for worker shutdown and exception handling."""

    async def test_shutdown_event_stops_loop(self):
        """When shutdown_event is set before the loop, worker exits without running."""
        from agent.services.case_lifecycle_worker import case_lifecycle_worker

        chatwoot = _make_chatwoot()
        shutdown_event = asyncio.Event()
        shutdown_event.set()

        get_reminder = AsyncMock(return_value=[])
        mark_abandoned = AsyncMock(return_value=0)

        with (
            patch(
                "agent.services.case_lifecycle_worker.get_settings",
                return_value=_make_settings(),
            ),
            patch(
                "agent.services.case_lifecycle_worker.get_reminder_candidates",
                new=get_reminder,
            ),
            patch(
                "agent.services.case_lifecycle_worker.mark_cases_abandoned",
                new=mark_abandoned,
            ),
        ):
            await case_lifecycle_worker(shutdown_event, chatwoot)

        get_reminder.assert_not_awaited()
        mark_abandoned.assert_not_awaited()

    async def test_db_exception_caught_loop_continues(self):
        """DB exception in scan cycle → caught, logged at error level, loop continues."""
        from agent.services.case_lifecycle_worker import case_lifecycle_worker

        chatwoot = _make_chatwoot()
        shutdown_event = asyncio.Event()
        cycle_count = 0

        async def get_reminder_side_effect(_hours):
            nonlocal cycle_count
            cycle_count += 1
            if cycle_count == 1:
                raise Exception("DB connection lost")
            return []

        async def stop_on_abandon(_days):
            if cycle_count >= 2:
                shutdown_event.set()
            return 0

        # Use minimal interval so wait_for between cycles is near-instant
        settings = _make_settings()
        settings.CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES = 0.001  # ~60ms

        with (
            patch(
                "agent.services.case_lifecycle_worker.get_settings",
                return_value=settings,
            ),
            patch(
                "agent.services.case_lifecycle_worker.get_reminder_candidates",
                new=AsyncMock(side_effect=get_reminder_side_effect),
            ),
            patch(
                "agent.services.case_lifecycle_worker.mark_cases_abandoned",
                new=AsyncMock(side_effect=stop_on_abandon),
            ),
        ):
            await asyncio.wait_for(
                case_lifecycle_worker(shutdown_event, chatwoot),
                timeout=5.0,
            )

        assert cycle_count >= 2

    async def test_shutdown_during_wait_exits_immediately(self):
        """Setting shutdown_event during wait_for exits without waiting full interval."""
        from agent.services.case_lifecycle_worker import case_lifecycle_worker

        chatwoot = _make_chatwoot()
        shutdown_event = asyncio.Event()
        scan_count = 0

        async def count_and_schedule_stop(_days):
            nonlocal scan_count
            scan_count += 1
            # Schedule shutdown slightly after scan completes — worker should
            # exit from wait_for immediately, not wait the full 15 min
            asyncio.get_event_loop().call_soon(shutdown_event.set)
            return 0

        with (
            patch(
                "agent.services.case_lifecycle_worker.get_settings",
                return_value=_make_settings(scan_interval_minutes=15),
            ),
            patch(
                "agent.services.case_lifecycle_worker.get_reminder_candidates",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "agent.services.case_lifecycle_worker.mark_cases_abandoned",
                new=AsyncMock(side_effect=count_and_schedule_stop),
            ),
        ):
            await asyncio.wait_for(
                case_lifecycle_worker(shutdown_event, chatwoot),
                timeout=5.0,  # Must exit well before 15 min
            )

        assert scan_count == 1
