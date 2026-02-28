"""Redis cleanup executor for conversation reset pipeline."""

from __future__ import annotations

import logging
from typing import Any

from api.models.conversation_reset import ResetDomainResult
from api.services.conversation_reset_coordinator import ResetExecutionContext
from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class ConversationResetRedisExecutor:
    """Best-effort Redis cleanup for conversation-scoped key families."""

    domain = "redis"

    def __init__(self, redis_client: Any | None = None) -> None:
        self._redis = redis_client

    async def execute(self, context: ResetExecutionContext) -> ResetDomainResult:
        redis = self._redis or get_redis_client()
        conversation_id = context.conversation_id

        pattern_families = {
            "checkpoint": f"checkpoint:{conversation_id}:*",
            "checkpoint_write": f"checkpoint_write:{conversation_id}:*",
            "write_keys_zset": f"write_keys_zset:{conversation_id}:*",
            "checkpoint_latest": f"checkpoint_latest:{conversation_id}:*",
        }
        exact_families = {
            "image_batch": f"image_batch:{conversation_id}",
            "image_batch_final": f"image_batch_final:{conversation_id}",
        }

        deleted_total = 0
        family_counts: dict[str, int] = {}
        errors: dict[str, str] = {}

        for family_name, pattern in pattern_families.items():
            family_deleted = 0
            cursor = 0
            try:
                while True:
                    cursor, keys = await redis.scan(cursor, match=pattern, count=200)
                    if keys:
                        await redis.delete(*keys)
                        family_deleted += len(keys)
                    if cursor == 0:
                        break
            except Exception as exc:
                errors[family_name] = str(exc)

            family_counts[family_name] = family_deleted
            deleted_total += family_deleted

        for family_name, key in exact_families.items():
            try:
                deleted = await redis.delete(key)
                family_counts[family_name] = int(deleted or 0)
                deleted_total += int(deleted or 0)
            except Exception as exc:
                family_counts[family_name] = 0
                errors[family_name] = str(exc)

        if errors and deleted_total == 0:
            return ResetDomainResult(
                domain=self.domain,
                status="failed",
                details={**family_counts, "deleted_keys_total": deleted_total},
                error="; ".join(f"{key}={value}" for key, value in errors.items()),
            )

        if errors:
            logger.warning(
                "conversation_reset_redis_partial",
                extra={
                    "conversation_id": conversation_id,
                    "deleted_keys_total": deleted_total,
                    "errors": errors,
                },
            )
            return ResetDomainResult(
                domain=self.domain,
                status="partial",
                details={**family_counts, "deleted_keys_total": deleted_total},
                error="; ".join(f"{key}={value}" for key, value in errors.items()),
            )

        return ResetDomainResult(
            domain=self.domain,
            status="success",
            details={**family_counts, "deleted_keys_total": deleted_total},
        )
