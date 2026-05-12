"""
Attachment download worker — async background task running inside the API process.

Consumes the ``attachment_downloads`` Redis Stream, downloads inbound image
attachments from Chatwoot (SSRF-safe, validated), writes them to disk, and
creates MessageAttachment rows in the database.

Architecture:
  - Consumer group: ``attachment_workers``
  - Stream: ``attachment_downloads``
  - DLQ: ``attachment_downloads:dlq``
  - Started in api/main.py lifespan via asyncio.create_task(run())
  - Stopped via shutdown() on lifespan teardown

Retry logic:
  - Up to 3 delivery attempts per message (Redis PEL tracks delivery count).
  - After 3 failures: move to DLQ, ACK original, log ERROR.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import structlog

from api.services.conversation_image_service import get_conversation_image_service
from database.connection import get_async_session
from shared.redis_client import (
    add_to_stream,
    create_consumer_group,
    get_redis_client,
    read_from_stream,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STREAM_NAME = "attachment_downloads"
CONSUMER_GROUP = "attachment_workers"
CONSUMER_NAME = "attachment_worker_0"
DLQ_STREAM = "attachment_downloads:dlq"
MAX_DELIVERY_COUNT = 3
BLOCK_MS = 5000  # block up to 5s waiting for messages

_shutdown_event: asyncio.Event | None = None


# ---------------------------------------------------------------------------
# Public lifecycle API
# ---------------------------------------------------------------------------


async def run() -> None:
    """
    Start the attachment download worker consume loop.

    Call from api/main.py startup event via asyncio.create_task(run()).
    """
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    logger.info("attachment_download_worker_started")

    redis = get_redis_client()

    # Ensure consumer group exists (idempotent — BUSYGROUP silently ignored)
    await create_consumer_group(STREAM_NAME, CONSUMER_GROUP, start_id="$")

    while not _shutdown_event.is_set():
        try:
            messages = await read_from_stream(
                stream=STREAM_NAME,
                group=CONSUMER_GROUP,
                consumer=CONSUMER_NAME,
                count=10,
                block_ms=BLOCK_MS,
            )

            if not messages:
                # Nothing to process — loop back
                continue

            for msg_id, data in messages:
                # Check PEL delivery count to decide whether to process or DLQ
                delivery_count = await _get_delivery_count(redis, msg_id)

                if delivery_count > MAX_DELIVERY_COUNT:
                    await _handle_dlq(
                        redis=redis,
                        msg_id=msg_id,
                        data=data,
                        stream_name=STREAM_NAME,
                        consumer_group=CONSUMER_GROUP,
                        dlq_stream=DLQ_STREAM,
                        error=f"Exceeded max delivery count ({MAX_DELIVERY_COUNT})",
                    )
                    continue

                try:
                    await _process_one_message(
                        redis=redis,
                        msg_id=msg_id,
                        data=data,
                        stream_name=STREAM_NAME,
                        consumer_group=CONSUMER_GROUP,
                        dlq_stream=DLQ_STREAM,
                    )
                except Exception as exc:
                    if delivery_count >= MAX_DELIVERY_COUNT:
                        await _handle_dlq(
                            redis=redis,
                            msg_id=msg_id,
                            data=data,
                            stream_name=STREAM_NAME,
                            consumer_group=CONSUMER_GROUP,
                            dlq_stream=DLQ_STREAM,
                            error=str(exc),
                        )
                    else:
                        # Leave in PEL for redelivery (exponential backoff via consumer group)
                        logger.warning(
                            "attachment_download_attempt_failed",
                            msg_id=msg_id,
                            delivery_count=delivery_count,
                            error=str(exc),
                        )

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error(
                "attachment_download_worker_loop_error",
                error=str(exc),
                exc_info=True,
            )
            # Brief pause to avoid tight error loop
            await asyncio.sleep(1)

    logger.info("attachment_download_worker_stopped")


async def shutdown() -> None:
    """Signal the worker loop to stop gracefully."""
    global _shutdown_event
    if _shutdown_event is None:
        _shutdown_event = asyncio.Event()
    _shutdown_event.set()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_delivery_count(redis: Any, msg_id: str) -> int:
    """
    Return the number of times this message has been delivered from the PEL.

    Uses XPENDING to query the pending entry list.
    Returns 1 if the message is not found in XPENDING (first delivery).
    """
    try:
        # XPENDING STREAM GROUP - + COUNT to get all pending entries
        entries = await redis.xpending_range(
            STREAM_NAME,
            CONSUMER_GROUP,
            min=msg_id,
            max=msg_id,
            count=1,
        )
        if entries:
            return entries[0].get("times_delivered", 1)
        return 1
    except Exception:
        return 1


async def _process_one_message(
    redis: Any,
    msg_id: str,
    data: dict[str, Any],
    stream_name: str,
    consumer_group: str,
    dlq_stream: str,
) -> None:
    """
    Parse payload, call ConversationImageService, ACK on success.

    Raises on any processing error so the caller can decide retry vs DLQ.
    """
    # `data` is already the parsed payload — read_from_stream() does json.loads internally.
    conversation_id = uuid.UUID(data["conversation_id"])
    message_id = uuid.UUID(data["message_id"])
    attachments: list[dict] = data.get("attachments", [])

    service = get_conversation_image_service()

    async with get_async_session() as session:
        try:
            rows = await service.download_and_persist_inbound(
                session=session,
                conversation_id=conversation_id,
                message_id=message_id,
                chatwoot_attachments=attachments,
            )
            await session.commit()
            logger.info(
                "attachment_download_completed",
                msg_id=msg_id,
                message_id=str(message_id),
                rows_created=len(rows),
            )
        except Exception:
            await session.rollback()
            raise

    # ACK only after successful DB commit
    await redis.xack(stream_name, consumer_group, msg_id)


async def _handle_dlq(
    redis: Any,
    msg_id: str,
    data: dict[str, Any],
    stream_name: str,
    consumer_group: str,
    dlq_stream: str,
    error: str,
) -> None:
    """
    Move a failed message to the DLQ and ACK it from the original stream.

    The DLQ entry contains the original payload plus the error string and
    the original message ID for traceability.
    """
    logger.error(
        "attachment_download_moved_to_dlq",
        original_msg_id=msg_id,
        error=error,
    )

    dlq_entry = {
        "original_msg_id": msg_id,
        "error": error,
        "data": json.dumps(data),
    }

    await redis.xadd(dlq_stream, dlq_entry)
    # ACK from original stream so it stops being re-delivered
    await redis.xack(stream_name, consumer_group, msg_id)
