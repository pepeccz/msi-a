"""
MSI Automotive - LLM Metrics Persistence Service.

Background task that periodically flushes LLMRouter._metrics_buffer
to the llm_usage_metrics PostgreSQL table.
"""

import asyncio
import logging
import uuid
from datetime import datetime, UTC
from decimal import Decimal

from database.connection import get_async_session
from database.models import LLMUsageMetric
from shared.config import get_settings
from shared.llm_router import get_llm_router, LLMMetrics

logger = logging.getLogger(__name__)

# Flush interval in seconds
FLUSH_INTERVAL_SECONDS = 30


def _estimate_cost(metrics: LLMMetrics) -> Decimal | None:
    """Estimate cost for cloud-only calls using configured pricing."""
    if metrics.provider.value != "openrouter":
        return None

    input_tokens = metrics.input_tokens or 0
    output_tokens = metrics.output_tokens or 0

    settings = get_settings()
    input_cost_per_token = settings.TOKEN_PRICE_INPUT / Decimal("1000000")
    output_cost_per_token = settings.TOKEN_PRICE_OUTPUT / Decimal("1000000")

    cost = (
        Decimal(str(input_tokens)) * input_cost_per_token
        + Decimal(str(output_tokens)) * output_cost_per_token
    )
    return cost if cost > 0 else None


async def persist_metrics_batch(metrics_list: list[LLMMetrics]) -> int:
    """
    Persist a batch of LLM metrics to PostgreSQL.

    Args:
        metrics_list: List of LLMMetrics dataclass instances

    Returns:
        Number of metrics successfully persisted
    """
    if not metrics_list:
        return 0

    persisted = 0

    try:
        async with get_async_session() as session:
            for m in metrics_list:
                record = LLMUsageMetric(
                    id=uuid.uuid4(),
                    task_type=m.task_type.value,
                    tier=m.tier.value,
                    provider=m.provider.value,
                    model=m.model,
                    latency_ms=m.latency_ms,
                    input_tokens=m.input_tokens,
                    output_tokens=m.output_tokens,
                    success=m.success,
                    error=m.error[:1000] if m.error else None,
                    fallback_used=m.fallback_used,
                    original_tier=m.original_tier.value if m.original_tier else None,
                    estimated_cost_usd=_estimate_cost(m),
                    created_at=datetime.now(UTC),
                )
                session.add(record)
                persisted += 1

            await session.commit()

        logger.info(
            f"Flushed {persisted} LLM metrics to database",
            extra={"metrics_count": persisted},
        )

    except Exception as e:
        logger.error(
            f"Failed to persist LLM metrics batch: {e}",
            exc_info=True,
        )

    return persisted


async def metrics_flush_loop(shutdown_event: asyncio.Event) -> None:
    """
    Background loop that flushes LLM metrics buffer every FLUSH_INTERVAL_SECONDS.

    Args:
        shutdown_event: Event that signals shutdown
    """
    logger.info(
        f"LLM metrics flush loop started (interval={FLUSH_INTERVAL_SECONDS}s)"
    )

    router = get_llm_router()

    while not shutdown_event.is_set():
        try:
            await asyncio.sleep(FLUSH_INTERVAL_SECONDS)

            # Drain buffer (atomic: get_pending_metrics copies + clears)
            pending = router.get_pending_metrics()
            if pending:
                await persist_metrics_batch(pending)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(
                f"Error in metrics flush loop: {e}",
                exc_info=True,
            )

    # Final flush on shutdown
    try:
        pending = router.get_pending_metrics()
        if pending:
            await persist_metrics_batch(pending)
            logger.info(f"Final flush: persisted {len(pending)} metrics on shutdown")
    except Exception as e:
        logger.error(f"Error in final metrics flush: {e}")

    logger.info("LLM metrics flush loop stopped")
