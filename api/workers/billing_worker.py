"""Billing worker — scheduled invoice generation and overdue checking."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog

logger = structlog.get_logger(__name__)

_shutdown_event: asyncio.Event | None = None


async def run() -> None:
    """Start the billing worker loops. Call from startup event."""
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    logger.info("billing_worker_started")

    await asyncio.gather(
        _monthly_invoice_loop(),
        _overdue_check_loop(),
        return_exceptions=True,
    )

    logger.info("billing_worker_stopped")


async def shutdown() -> None:
    """Signal the worker to stop gracefully."""
    if _shutdown_event:
        _shutdown_event.set()


async def _monthly_invoice_loop() -> None:
    """Generate invoice for previous month on the 1st at 02:00 UTC."""
    while _shutdown_event and not _shutdown_event.is_set():
        try:
            seconds = _seconds_until(target_hour=2, target_minute=0, target_day=1)
            logger.debug("billing_worker_invoice_next_run", seconds=seconds)

            try:
                await asyncio.wait_for(_shutdown_event.wait(), timeout=seconds)
                return  # Shutdown was requested
            except asyncio.TimeoutError:
                pass  # Time to run

            # Calculate previous month
            now = datetime.now(timezone.utc)
            if now.month == 1:
                prev_year, prev_month = now.year - 1, 12
            else:
                prev_year, prev_month = now.year, now.month - 1

            logger.info(
                "billing_worker_generating_invoice",
                year=prev_year,
                month=prev_month,
            )

            from database.connection import get_async_session
            from api.services.billing_service import BillingService  # noqa: PLC0415

            async with get_async_session() as session:
                service = BillingService()
                await service.generate_invoice(session, prev_year, prev_month)

            logger.info(
                "billing_worker_invoice_generated",
                year=prev_year,
                month=prev_month,
            )

        except asyncio.CancelledError:
            return

        except Exception as e:
            # HTTPException(409) = already exists → expected, log at INFO not ERROR
            status_code = getattr(e, "status_code", None)
            if status_code == 409:
                logger.info(
                    "billing_worker_invoice_skipped",
                    reason="already_exists",
                )
            else:
                logger.error(
                    "billing_worker_invoice_error",
                    error=str(e),
                    exc_info=True,
                )


async def _overdue_check_loop() -> None:
    """Check for overdue invoices daily at 03:00 UTC."""
    while _shutdown_event and not _shutdown_event.is_set():
        try:
            seconds = _seconds_until(target_hour=3, target_minute=0)
            logger.debug("billing_worker_overdue_next_run", seconds=seconds)

            try:
                await asyncio.wait_for(_shutdown_event.wait(), timeout=seconds)
                return  # Shutdown was requested
            except asyncio.TimeoutError:
                pass  # Time to run

            from database.connection import get_async_session
            from api.services.billing_service import BillingService  # noqa: PLC0415

            async with get_async_session() as session:
                service = BillingService()
                count = await service.check_overdue(session)

            logger.info("billing_worker_overdue_check", overdue_count=count)

        except asyncio.CancelledError:
            return

        except Exception:
            logger.error("billing_worker_overdue_error", exc_info=True)


def _seconds_until(
    target_hour: int,
    target_minute: int,
    target_day: int | None = None,
) -> float:
    """Calculate seconds from now until the next occurrence of the target time.

    Args:
        target_hour: UTC hour (0-23) to target.
        target_minute: UTC minute (0-59) to target.
        target_day: If given, calculates until day N of next month that hasn't
                    passed yet. If None, calculates the next daily occurrence.

    Returns:
        Positive float — seconds until the next fire time.
    """
    now = datetime.now(timezone.utc)

    if target_day is not None:
        # Monthly: next occurrence of day N at HH:MM
        year, month = now.year, now.month

        # Has the target already passed this month?
        if now.day > target_day or (
            now.day == target_day and now.hour >= target_hour
        ):
            month += 1
            if month > 12:
                month = 1
                year += 1

        target = now.replace(
            year=year,
            month=month,
            day=target_day,
            hour=target_hour,
            minute=target_minute,
            second=0,
            microsecond=0,
        )
    else:
        # Daily: next occurrence of HH:MM
        target = now.replace(
            hour=target_hour,
            minute=target_minute,
            second=0,
            microsecond=0,
        )
        if target <= now:
            target += timedelta(days=1)

    return (target - now).total_seconds()
