"""
MSI Automotive - Redis checkpointer for LangGraph state persistence.

This module provides a singleton Redis checkpointer for LangGraph StateGraph.
The checkpointer enables crash recovery by persisting conversation state to Redis
after each node execution.

ModeAwareTTLSaver extends AsyncRedisSaver to apply per-conversation-mode TTLs:
- CONSULTA_MODE:    60 min  (1h)  — short educational queries
- PRESUPUESTO_MODE: 240 min (4h)  — active pricing sessions
- EXPEDIENTE_MODE:  10080 min (7d) — formal case collection
- ESCALATION:       120 min (2h)  — human handoff sessions
- _default:         1440 min (24h) — fallback for unknown/no mode
"""

import logging
from typing import Any

import structlog
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from redis.asyncio import Redis

from shared.config import get_settings

logger = logging.getLogger(__name__)
_structlog = structlog.get_logger(__name__)

# Global flag to track if Redis indexes have been initialized
_redis_indexes_initialized = False
# Module-level singleton: set after initialize_redis_indexes() succeeds
_initialized_checkpointer: BaseCheckpointSaver | None = None


async def initialize_redis_indexes(checkpointer: AsyncRedisSaver) -> None:
    """
    Initialize Redis indexes for LangGraph checkpointer.

    This function calls setup() on the AsyncRedisSaver to create necessary
    RedisSearch indexes that are required for checkpoint persistence.

    Args:
        checkpointer: AsyncRedisSaver instance to initialize

    Raises:
        Exception: If index creation fails
    """
    global _redis_indexes_initialized, _initialized_checkpointer

    if _redis_indexes_initialized:
        logger.debug("Redis indexes already initialized, skipping")
        return

    try:
        logger.info("Initializing Redis indexes for LangGraph checkpointer...")
        await checkpointer.setup()
        _redis_indexes_initialized = True
        _initialized_checkpointer = checkpointer
        logger.info("Redis indexes initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Redis indexes: {e}", exc_info=True)
        raise


class ModeAwareTTLSaver(AsyncRedisSaver):
    """AsyncRedisSaver subclass that applies per-conversation-mode TTL on each checkpoint write.

    After every successful aput() call, this class reads `current_mode` from the
    checkpoint's `channel_values` and applies the corresponding TTL (in seconds) to
    all Redis keys matching the thread_id pattern.

    TTL is applied as a best-effort operation — any failure is logged as WARNING and
    the checkpoint result is returned unchanged. This ensures TTL logic never blocks
    checkpoint writes.

    The Redis connection attribute `self._redis` is inherited from BaseRedisSaver
    (set by AsyncRedisSaver.configure_client()).
    """

    def __init__(self, ttl_by_mode: dict[str, int], **kwargs: Any) -> None:
        """Initialize ModeAwareTTLSaver.

        Args:
            ttl_by_mode: Mapping of mode name → TTL in minutes.
                         Must include a "_default" key as fallback.
                         Example: {"CONSULTA_MODE": 60, "_default": 1440}
            **kwargs: Forwarded to AsyncRedisSaver (redis_client, ttl, etc.)
        """
        super().__init__(**kwargs)
        self._ttl_by_mode = ttl_by_mode

    async def aput(
        self,
        config: Any,
        checkpoint: Any,
        metadata: Any,
        new_versions: Any,
        **kwargs: Any,
    ) -> Any:
        """Store checkpoint and apply per-mode TTL to all thread keys.

        Calls super().aput() first to persist the checkpoint, then applies
        the mode-specific TTL. Any error in TTL application is swallowed and
        logged as a WARNING to avoid blocking checkpoint writes.

        Args:
            config: LangGraph RunnableConfig with configurable.thread_id
            checkpoint: LangGraph Checkpoint dict with channel_values
            metadata: CheckpointMetadata
            new_versions: ChannelVersions
            **kwargs: Additional kwargs forwarded to parent (e.g. stream_mode)

        Returns:
            Updated RunnableConfig (from super().aput())
        """
        result = await super().aput(
            config, checkpoint, metadata, new_versions, **kwargs
        )

        try:
            # Extract conversation mode from checkpoint channel values
            mode = checkpoint.get("channel_values", {}).get("current_mode", "")

            # Look up mode-specific TTL, falling back to default
            ttl_minutes = self._ttl_by_mode.get(mode) or self._ttl_by_mode.get(
                "_default", 1440
            )
            ttl_seconds = ttl_minutes * 60

            # Extract thread_id to build the key pattern
            thread_id = config.get("configurable", {}).get("thread_id", "")

            if thread_id and ttl_seconds > 0:
                # Apply TTL to all Redis keys associated with this thread
                # Pattern matches checkpoint keys: checkpoint:{thread_id}:*, checkpoint_write:{thread_id}:*, etc.
                pattern = f"*{thread_id}*"
                keys = [key async for key in self._redis.scan_iter(match=pattern)]
                if keys:
                    pipe = self._redis.pipeline()
                    for key in keys:
                        pipe.expire(key, ttl_seconds)
                    await pipe.execute()
                    _structlog.debug(
                        "checkpoint_ttl_applied",
                        thread_id=thread_id,
                        mode=mode or "_default",
                        ttl_minutes=ttl_minutes,
                        keys_updated=len(keys),
                    )

        except Exception as e:
            # Never let TTL logic block checkpoint writes
            _structlog.warning(
                "checkpoint_ttl_apply_failed",
                error=str(e),
                thread_id=config.get("configurable", {}).get("thread_id", "unknown"),
            )

        return result


def get_redis_checkpointer() -> BaseCheckpointSaver[Any]:
    """
    Get Redis checkpointer instance with per-mode TTL support.

    This function creates a ModeAwareTTLSaver instance for LangGraph state persistence.
    Checkpoints are automatically expired according to the conversation mode:
    - CONSULTA_MODE:    60 min  (1h)
    - PRESUPUESTO_MODE: 240 min (4h)
    - EXPEDIENTE_MODE:  10080 min (7d)
    - ESCALATION:       120 min (2h)
    - default:          1440 min (24h)

    Returns:
        ModeAwareTTLSaver instance configured with REDIS_URL and per-mode TTLs

    Note:
        - Checkpoints are automatically saved after each node execution
        - Crash recovery: Invoke graph with same thread_id to resume
        - Redis key pattern: checkpoint:{thread_id}:{checkpoint_ns}:{checkpoint_id}
        - TTL: mode-dependent (see above), default 24h, configured via env vars
        - IMPORTANT: Call initialize_redis_indexes() before first use
        - TTL unit: minutes (as required by AsyncRedisSaver.ttl["default_ttl"])
    """
    settings = get_settings()
    redis_url = settings.REDIS_URL

    logger.info(f"Creating Redis checkpointer with URL: {redis_url}")

    # Build connection kwargs (decode_responses=False for binary checkpoint data)
    conn_kwargs: dict[str, Any] = {"decode_responses": False}
    if settings.REDIS_PASSWORD:
        conn_kwargs["password"] = settings.REDIS_PASSWORD
        logger.info("Redis checkpointer: using password authentication")

    # Create Redis async client
    redis_client = Redis.from_url(redis_url, **conn_kwargs)

    # Build per-mode TTL mapping from settings (values in minutes)
    ttl_by_mode: dict[str, int] = {
        "CONSULTA_MODE": settings.CHECKPOINT_TTL_CONSULTA_MINUTES,
        "PRESUPUESTO_MODE": settings.CHECKPOINT_TTL_PRESUPUESTO_MINUTES,
        "EXPEDIENTE_MODE": settings.CHECKPOINT_TTL_EXPEDIENTE_MINUTES,
        "ESCALATION": settings.CHECKPOINT_TTL_ESCALATION_MINUTES,
        "_default": settings.CHECKPOINT_TTL_DEFAULT_MINUTES,
    }

    # Create ModeAwareTTLSaver with default TTL for initial writes
    # (before first aput, mode is unknown — default_ttl covers this)
    checkpointer = ModeAwareTTLSaver(
        redis_client=redis_client,
        ttl={"default_ttl": settings.CHECKPOINT_TTL_DEFAULT_MINUTES},  # minutes
        ttl_by_mode=ttl_by_mode,
    )

    logger.info(
        "Redis checkpointer created with per-mode TTLs",
        extra={
            "default_ttl_minutes": settings.CHECKPOINT_TTL_DEFAULT_MINUTES,
            "consulta_ttl_minutes": settings.CHECKPOINT_TTL_CONSULTA_MINUTES,
            "presupuesto_ttl_minutes": settings.CHECKPOINT_TTL_PRESUPUESTO_MINUTES,
            "expediente_ttl_minutes": settings.CHECKPOINT_TTL_EXPEDIENTE_MINUTES,
            "escalation_ttl_minutes": settings.CHECKPOINT_TTL_ESCALATION_MINUTES,
        },
    )

    return checkpointer


def get_initialized_checkpointer() -> BaseCheckpointSaver[Any] | None:
    """Return the checkpointer instance that has had setup() called.

    Returns None if initialize_redis_indexes() has not been called yet.
    Callers that need a checkpoint reader (e.g. image assignment) MUST
    use this instead of get_redis_checkpointer() to avoid the
    'No such index checkpoint_write' error.
    """
    return _initialized_checkpointer
