"""
MSI-a — Case lifecycle background worker.

Polls PostgreSQL for inactive cases and:
  - Phase 1 (reminder): Sends a WhatsApp reminder at ~20h of inactivity.
  - Phase 2 (abandon): Marks cases as abandoned at ~4 days of inactivity.

Follows the same structure as ``image_batch_confirmation_worker`` in
``agent/services/image_handling.py``.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from agent.services.case_helpers import (
    get_reminder_candidates,
    mark_cases_abandoned,
)
from database.connection import get_async_session
from database.models import Case
from shared.config import get_settings

if TYPE_CHECKING:
    from shared.chatwoot_client import ChatwootClient

logger = structlog.get_logger(__name__)


async def _mark_reminder_sent(case_id: uuid.UUID) -> None:
    """Set reminder_sent_at=now() for the given case."""
    from sqlalchemy import update

    async with get_async_session() as session:
        await session.execute(
            update(Case)
            .where(Case.id == case_id)
            .values(reminder_sent_at=datetime.now(UTC))
        )
        await session.commit()


async def case_lifecycle_worker(
    shutdown_event: asyncio.Event,
    chatwoot: "ChatwootClient",
) -> None:
    """Background worker: reminders at ~20h, abandonment at ~4d.

    Runs in a loop until ``shutdown_event`` is set.  Reads timing from
    ``get_settings()`` on each iteration so changes take effect without
    restart.

    Error handling:
    - Per-case failures are isolated (one bad case never blocks others).
    - Full-cycle DB exceptions are caught, logged at error level, and the
      loop continues after the configured interval.

    Args:
        shutdown_event: asyncio.Event that signals graceful shutdown.
        chatwoot: ChatwootClient instance used to send reminder messages.
    """
    logger.info("case_lifecycle_worker_started")

    while not shutdown_event.is_set():
        try:
            settings = get_settings()
            reminder_hours = settings.CASE_REMINDER_HOURS
            abandon_days = settings.CASE_ABANDON_DAYS
            interval_seconds = settings.CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES * 60
            template = settings.CASE_REMINDER_MESSAGE_TEMPLATE

            # ── Phase 1: Reminder scan ────────────────────────────────────
            candidates = await get_reminder_candidates(reminder_hours)
            for case in candidates:
                try:
                    user = case.user
                    if user is None:
                        logger.warning(
                            "case_lifecycle_reminder_skipped_no_user",
                            case_id=str(case.id),
                        )
                        continue

                    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Usuario"
                    elements = ", ".join(case.element_codes) if case.element_codes else ""
                    message = template.format(name=name, elements=elements)

                    await chatwoot.send_message(
                        customer_phone=user.phone,
                        message=message,
                    )
                    await _mark_reminder_sent(case.id)
                    logger.info(
                        "case_lifecycle_reminder_sent",
                        case_id=str(case.id),
                        user_id=str(case.user_id),
                    )
                except Exception:
                    logger.error(
                        "case_lifecycle_reminder_failed",
                        case_id=str(case.id),
                        exc_info=True,
                    )

            # ── Phase 2: Abandon scan ─────────────────────────────────────
            abandoned_count = await mark_cases_abandoned(abandon_days)
            if abandoned_count > 0:
                logger.info(
                    "case_lifecycle_abandoned",
                    count=abandoned_count,
                )

        except asyncio.CancelledError:
            logger.info("case_lifecycle_worker_cancelled")
            raise

        except Exception:
            logger.error(
                "case_lifecycle_worker_cycle_error",
                exc_info=True,
            )

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval_seconds)
            break  # Event was set — exit loop
        except asyncio.TimeoutError:
            pass  # Normal: no shutdown requested, continue scanning

    logger.info("case_lifecycle_worker_stopped")
