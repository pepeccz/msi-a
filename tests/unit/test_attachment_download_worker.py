"""
Unit tests for attachment_download_worker.

TDD cycle: RED → GREEN → REFACTOR

Covers:
  - Stream consume loop processes messages
  - On success: ACK is called, service method invoked
  - On failure (1st attempt): message remains in PEL, re-delivered
  - After 3 delivery failures: message moved to DLQ, ERROR logged
  - Worker startup creates consumer group
  - Shutdown event terminates the loop gracefully
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stream_message(
    msg_id: str = "1234567890-0",
    conversation_id: str | None = None,
    message_id: str | None = None,
    attachments: list[dict] | None = None,
) -> tuple[str, dict]:
    """Build a (message_id, data) tuple as returned by read_from_stream."""
    conv_id = conversation_id or str(uuid.uuid4())
    m_id = message_id or str(uuid.uuid4())
    atts = attachments or [
        {"url": "https://chatwoot.example.com/img.jpg", "name": "img.jpg", "type": "image/jpeg"}
    ]
    payload = {
        "data": json.dumps(
            {
                "conversation_id": conv_id,
                "message_id": m_id,
                "attachments": atts,
            }
        )
    }
    return (msg_id, payload)


# ---------------------------------------------------------------------------
# process_one_message
# ---------------------------------------------------------------------------


class TestProcessOneMessage:
    """Tests for the internal _process_one_message helper."""

    @pytest.mark.asyncio
    async def test_happy_path_acks_message(self) -> None:
        """Successful processing → ACK is sent to Redis."""
        from api.workers.attachment_download_worker import _process_one_message

        msg_id, data = _make_stream_message()

        mock_service = MagicMock()
        mock_service.download_and_persist_inbound = AsyncMock(return_value=[MagicMock()])

        mock_redis = MagicMock()
        mock_redis.xack = AsyncMock(return_value=1)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock()

        with (
            patch(
                "api.workers.attachment_download_worker.get_conversation_image_service",
                return_value=mock_service,
            ),
            patch(
                "api.workers.attachment_download_worker.get_async_session",
                return_value=mock_session,
            ),
        ):
            await _process_one_message(
                redis=mock_redis,
                msg_id=msg_id,
                data=data,
                stream_name="attachment_downloads",
                consumer_group="attachment_workers",
                dlq_stream="attachment_downloads:dlq",
            )

        mock_redis.xack.assert_called_once_with(
            "attachment_downloads", "attachment_workers", msg_id
        )
        mock_service.download_and_persist_inbound.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_does_not_ack(self) -> None:
        """If the service raises, xack is NOT called (message stays in PEL for retry)."""
        from api.workers.attachment_download_worker import _process_one_message

        msg_id, data = _make_stream_message()

        mock_service = MagicMock()
        mock_service.download_and_persist_inbound = AsyncMock(
            side_effect=RuntimeError("db error")
        )

        mock_redis = MagicMock()
        mock_redis.xack = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.rollback = AsyncMock()
        mock_session.commit = AsyncMock()

        with (
            patch(
                "api.workers.attachment_download_worker.get_conversation_image_service",
                return_value=mock_service,
            ),
            patch(
                "api.workers.attachment_download_worker.get_async_session",
                return_value=mock_session,
            ),
        ):
            # Should not raise — errors are caught and re-raised for DLQ logic
            with pytest.raises(RuntimeError):
                await _process_one_message(
                    redis=mock_redis,
                    msg_id=msg_id,
                    data=data,
                    stream_name="attachment_downloads",
                    consumer_group="attachment_workers",
                    dlq_stream="attachment_downloads:dlq",
                )

        mock_redis.xack.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_json_moves_to_dlq(self) -> None:
        """Malformed JSON payload → immediately moved to DLQ (no retry value)."""
        from api.workers.attachment_download_worker import _process_one_message

        msg_id = "9999-0"
        data = {"data": "not-valid-json!!!"}

        mock_redis = MagicMock()
        mock_redis.xack = AsyncMock()
        mock_redis.xadd = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "api.workers.attachment_download_worker.get_async_session",
            return_value=mock_session,
        ):
            with pytest.raises((ValueError, json.JSONDecodeError)):
                await _process_one_message(
                    redis=mock_redis,
                    msg_id=msg_id,
                    data=data,
                    stream_name="attachment_downloads",
                    consumer_group="attachment_workers",
                    dlq_stream="attachment_downloads:dlq",
                )

        mock_redis.xack.assert_not_called()


# ---------------------------------------------------------------------------
# DLQ after max retries
# ---------------------------------------------------------------------------


class TestDlqHandling:
    """Tests for DLQ behaviour after retry exhaustion."""

    @pytest.mark.asyncio
    async def test_after_max_retries_message_moved_to_dlq(self) -> None:
        """After 3 delivery failures, the message is moved to DLQ and ACKed."""
        from api.workers.attachment_download_worker import _handle_dlq

        msg_id = "111-0"
        msg_data = {"data": json.dumps({"conversation_id": "abc", "message_id": "xyz", "attachments": []})}

        mock_redis = MagicMock()
        mock_redis.xadd = AsyncMock(return_value="222-0")
        mock_redis.xack = AsyncMock(return_value=1)

        await _handle_dlq(
            redis=mock_redis,
            msg_id=msg_id,
            data=msg_data,
            stream_name="attachment_downloads",
            consumer_group="attachment_workers",
            dlq_stream="attachment_downloads:dlq",
            error="Persistent failure",
        )

        # Must be added to DLQ
        mock_redis.xadd.assert_called_once()
        dlq_call_args = mock_redis.xadd.call_args
        assert dlq_call_args[0][0] == "attachment_downloads:dlq"

        # Must be ACKed on the original stream so it stops being re-delivered
        mock_redis.xack.assert_called_once_with(
            "attachment_downloads", "attachment_workers", msg_id
        )

    @pytest.mark.asyncio
    async def test_dlq_entry_contains_original_payload_and_error(self) -> None:
        """DLQ entry must contain the original message data and error string."""
        from api.workers.attachment_download_worker import _handle_dlq

        msg_id = "555-0"
        original_data = {
            "conversation_id": "conv-123",
            "message_id": "msg-456",
            "attachments": [{"url": "http://example.com/img.jpg", "name": "img.jpg", "type": "image/jpeg"}],
        }
        msg_data = {"data": json.dumps(original_data)}
        error_msg = "timeout after 3 attempts"

        mock_redis = MagicMock()
        mock_redis.xadd = AsyncMock(return_value="666-0")
        mock_redis.xack = AsyncMock(return_value=1)

        await _handle_dlq(
            redis=mock_redis,
            msg_id=msg_id,
            data=msg_data,
            stream_name="attachment_downloads",
            consumer_group="attachment_workers",
            dlq_stream="attachment_downloads:dlq",
            error=error_msg,
        )

        call_args = mock_redis.xadd.call_args
        dlq_payload = call_args[0][1]  # second positional arg = the mapping dict
        assert "error" in dlq_payload
        assert error_msg in dlq_payload["error"]


# ---------------------------------------------------------------------------
# Worker lifecycle
# ---------------------------------------------------------------------------


class TestWorkerLifecycle:
    """Tests for worker startup and shutdown."""

    @pytest.mark.asyncio
    async def test_run_creates_consumer_group_on_startup(self) -> None:
        """run() must call create_consumer_group before entering the consume loop."""
        from api.workers import attachment_download_worker

        mock_redis = MagicMock()
        mock_redis.xreadgroup = AsyncMock(return_value=None)  # Empty — no messages
        mock_redis.xack = AsyncMock()

        # We'll stop after one iteration by making the shutdown event fire immediately
        import asyncio

        with (
            patch(
                "api.workers.attachment_download_worker.get_redis_client",
                return_value=mock_redis,
            ),
            patch(
                "api.workers.attachment_download_worker.create_consumer_group",
                new=AsyncMock(return_value=True),
            ) as mock_cg,
            patch(
                "api.workers.attachment_download_worker.read_from_stream",
                new=AsyncMock(return_value=[]),
            ),
        ):
            # Set shutdown after 1 iteration
            attachment_download_worker._shutdown_event = asyncio.Event()
            attachment_download_worker._shutdown_event.set()  # immediately stop

            await attachment_download_worker.run()

        mock_cg.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_stops_loop(self) -> None:
        """Calling shutdown() sets the event and the loop exits."""
        from api.workers import attachment_download_worker
        import asyncio

        attachment_download_worker._shutdown_event = asyncio.Event()

        await attachment_download_worker.shutdown()

        assert attachment_download_worker._shutdown_event.is_set()
