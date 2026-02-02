"""
MSI Automotive - Token Usage Tracking Service.

Provides atomic token usage recording for LLM calls.
Uses PostgreSQL UPSERT pattern to aggregate monthly totals.
"""

import logging
import uuid
from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from database.connection import get_async_session
from database.models import TokenUsage

logger = logging.getLogger(__name__)


async def record_token_usage(input_tokens: int, output_tokens: int) -> None:
    """
    Record token usage for the current month.

    Uses atomic UPSERT to increment counters. If a record for the current
    year/month exists, it increments the values. Otherwise, creates a new record.

    Args:
        input_tokens: Number of input/prompt tokens used
        output_tokens: Number of output/completion tokens used
    """
    if input_tokens <= 0 and output_tokens <= 0:
        return

    now = datetime.now(UTC)
    year = now.year
    month = now.month

    try:
        async with get_async_session() as session:
            # PostgreSQL UPSERT with increment
            stmt = insert(TokenUsage).values(
                id=uuid.uuid4(),
                year=year,
                month=month,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_requests=1,
                created_at=now,
                updated_at=now,
            )

            # On conflict, increment existing values
            stmt = stmt.on_conflict_do_update(
                constraint="uq_token_usage_year_month",
                set_={
                    "input_tokens": TokenUsage.input_tokens + input_tokens,
                    "output_tokens": TokenUsage.output_tokens + output_tokens,
                    "total_requests": TokenUsage.total_requests + 1,
                    "updated_at": now,
                },
            )

            await session.execute(stmt)
            await session.commit()

            logger.debug(
                f"Recorded token usage | year={year} month={month} "
                f"input={input_tokens} output={output_tokens}"
            )

    except Exception as e:
        # Log but don't raise - token tracking should not break the agent
        logger.error(f"Failed to record token usage: {e}")


async def get_current_month_usage() -> dict | None:
    """
    Get token usage for the current month.

    Returns:
        Dict with usage data or None if no data exists.
    """
    now = datetime.now(UTC)

    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(TokenUsage).where(
                    TokenUsage.year == now.year,
                    TokenUsage.month == now.month,
                )
            )
            usage = result.scalar_one_or_none()

            if usage:
                return {
                    "year": usage.year,
                    "month": usage.month,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.input_tokens + usage.output_tokens,
                    "total_requests": usage.total_requests,
                }
            return None

    except Exception as e:
        logger.error(f"Failed to get current month usage: {e}")
        return None
