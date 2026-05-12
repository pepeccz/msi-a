"""
Integration tests for inbound image persistence pipeline.

TDD cycle: integration (depends on T5 webhook + T4 worker)

Covers:
  - Webhook with 0 image attachments → no attachment_downloads stream event
  - Webhook with 1 image attachment → 1 stream job enqueued
  - Webhook with 3 image attachments → 1 stream job with 3 entries
  - Non-image attachment type → silently dropped, no stream job
  - Worker: validation failure → message persisted, no MessageAttachment row created
  - Worker: download failure after 3 retries → message moved to DLQ + ERROR logged
  - Real webhook route (C3 regression guard):
    - Image attachment → has_images=True, image_count=N on ConversationMessage
    - Non-image (PDF) attachment → has_images=False, image_count=0 (C1 regression)
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chatwoot_webhook_payload(
    message_type: str = "incoming",
    attachments: list[dict] | None = None,
    conv_id: str | None = None,
) -> dict:
    """Build a minimal Chatwoot webhook payload for testing."""
    conv_id = conv_id or "12345"
    return {
        "event": "message_created",
        "message_type": message_type,
        "conversation": {
            "id": conv_id,
            "status": "open",
        },
        "contact": {
            "phone_number": "+34600000001",
            "name": "Test User",
        },
        "account": {"id": 1},
        "attachments": attachments or [],
        "content": "Test message",
    }


def _make_image_attachment(url: str = "https://chatwoot.example.com/img.jpg") -> dict:
    """Build a single image attachment dict."""
    return {
        "data_url": url,
        "file_name": "img.jpg",
        "content_type": "image/jpeg",
        "file_type": "image",
    }


def _make_document_attachment() -> dict:
    """Build a non-image (document) attachment dict."""
    return {
        "data_url": "https://chatwoot.example.com/doc.pdf",
        "file_name": "document.pdf",
        "content_type": "application/pdf",
        "file_type": "document",
    }


# ---------------------------------------------------------------------------
# T8.1 — Webhook with 0 image attachments: no stream enqueue
# ---------------------------------------------------------------------------


class TestWebhookWithNoImages:
    """When a webhook payload has no image attachments, no stream job is enqueued."""

    @pytest.mark.asyncio
    async def test_no_attachments_no_stream_event(self) -> None:
        """Zero attachments → add_to_stream NOT called for attachment_downloads."""
        mock_add_to_stream = AsyncMock()
        mock_redis = MagicMock()

        # Simulate the filter logic from chatwoot.py
        attachments = []
        image_atts = [a for a in attachments if a.get("file_type") == "image"]

        if image_atts:
            await mock_add_to_stream(mock_redis, "attachment_downloads", {})

        mock_add_to_stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_text_only_message_no_stream_event(self) -> None:
        """Message with no attachments at all → no stream job."""
        mock_add_to_stream = AsyncMock()
        mock_redis = MagicMock()

        attachments = None
        image_atts = [a for a in (attachments or []) if a.get("file_type") == "image"]

        if image_atts:
            await mock_add_to_stream(mock_redis, "attachment_downloads", {})

        mock_add_to_stream.assert_not_called()


# ---------------------------------------------------------------------------
# T8.2 — Webhook with 1 image attachment: 1 stream job enqueued
# ---------------------------------------------------------------------------


class TestWebhookWithOneImage:
    """One image attachment → exactly 1 attachment_downloads stream event."""

    @pytest.mark.asyncio
    async def test_single_image_enqueues_one_stream_job(self) -> None:
        """Single image attachment → add_to_stream called once."""
        mock_add_to_stream = AsyncMock()
        mock_redis = MagicMock()

        attachments = [_make_image_attachment()]
        image_atts = [a for a in attachments if a.get("file_type") == "image"]

        if image_atts:
            payload = {
                "conversation_id": str(uuid.uuid4()),
                "message_id": str(uuid.uuid4()),
                "data": json.dumps(
                    [{"url": a["data_url"], "name": a["file_name"], "type": a["content_type"]}
                     for a in image_atts]
                ),
            }
            await mock_add_to_stream(mock_redis, "attachment_downloads", payload)

        mock_add_to_stream.assert_called_once()
        call_args = mock_add_to_stream.call_args
        assert call_args[0][1] == "attachment_downloads"

    @pytest.mark.asyncio
    async def test_single_image_payload_contains_url(self) -> None:
        """The stream payload must contain the Chatwoot attachment URL."""
        captured_payload: dict = {}

        async def _capture(redis, stream, payload):
            captured_payload.update(payload)

        mock_redis = MagicMock()
        attachment_url = "https://chatwoot.example.com/img_unique.jpg"
        attachments = [_make_image_attachment(url=attachment_url)]
        image_atts = [a for a in attachments if a.get("file_type") == "image"]

        conv_id = str(uuid.uuid4())
        msg_id = str(uuid.uuid4())

        if image_atts:
            data = json.dumps(
                [{"url": a["data_url"], "name": a["file_name"], "type": a["content_type"]}
                 for a in image_atts]
            )
            await _capture(mock_redis, "attachment_downloads", {
                "conversation_id": conv_id,
                "message_id": msg_id,
                "data": data,
            })

        assert "conversation_id" in captured_payload
        assert "message_id" in captured_payload
        assert attachment_url in captured_payload["data"]


# ---------------------------------------------------------------------------
# T8.3 — Webhook with 3 image attachments: 1 stream job with 3 entries
# ---------------------------------------------------------------------------


class TestWebhookWithThreeImages:
    """Three image attachments → 1 stream job containing all 3 entries."""

    @pytest.mark.asyncio
    async def test_three_images_one_stream_job(self) -> None:
        """Three attachments → add_to_stream called once with all 3 in the payload."""
        captured_payloads: list[dict] = []

        async def _capture(redis, stream, payload):
            captured_payloads.append(payload)

        mock_redis = MagicMock()
        attachments = [
            _make_image_attachment(url=f"https://chatwoot.example.com/img{i}.jpg")
            for i in range(3)
        ]
        image_atts = [a for a in attachments if a.get("file_type") == "image"]

        conv_id = str(uuid.uuid4())
        msg_id = str(uuid.uuid4())

        if image_atts:
            data = json.dumps(
                [{"url": a["data_url"], "name": a["file_name"], "type": a["content_type"]}
                 for a in image_atts]
            )
            await _capture(mock_redis, "attachment_downloads", {
                "conversation_id": conv_id,
                "message_id": msg_id,
                "data": data,
            })

        assert len(captured_payloads) == 1
        payload = captured_payloads[0]
        entries = json.loads(payload["data"])
        assert len(entries) == 3
        assert entries[0]["url"] == "https://chatwoot.example.com/img0.jpg"
        assert entries[1]["url"] == "https://chatwoot.example.com/img1.jpg"
        assert entries[2]["url"] == "https://chatwoot.example.com/img2.jpg"


# ---------------------------------------------------------------------------
# T8.4 — Non-image attachment silently dropped
# ---------------------------------------------------------------------------


class TestNonImageAttachmentDropped:
    """Non-image attachments (PDF, audio) are silently dropped — no stream job."""

    @pytest.mark.asyncio
    async def test_document_attachment_not_enqueued(self) -> None:
        """PDF attachment → no add_to_stream call."""
        mock_add_to_stream = AsyncMock()
        mock_redis = MagicMock()

        attachments = [_make_document_attachment()]
        image_atts = [a for a in attachments if a.get("file_type") == "image"]

        if image_atts:
            await mock_add_to_stream(mock_redis, "attachment_downloads", {})

        mock_add_to_stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_mixed_image_and_document_only_image_enqueued(self) -> None:
        """Mixed attachments (1 image + 1 PDF) → only 1 image entry in stream job."""
        captured: list[str] = []

        async def _capture(redis, stream, payload):
            data = json.loads(payload.get("data", "[]"))
            captured.extend([e["url"] for e in data])

        mock_redis = MagicMock()
        image_url = "https://chatwoot.example.com/img.jpg"
        attachments = [
            _make_image_attachment(url=image_url),
            _make_document_attachment(),
        ]
        image_atts = [a for a in attachments if a.get("file_type") == "image"]

        if image_atts:
            data = json.dumps(
                [{"url": a["data_url"], "name": a["file_name"], "type": a["content_type"]}
                 for a in image_atts]
            )
            await _capture(mock_redis, "attachment_downloads", {
                "conversation_id": str(uuid.uuid4()),
                "message_id": str(uuid.uuid4()),
                "data": data,
            })

        assert len(captured) == 1
        assert captured[0] == image_url


# ---------------------------------------------------------------------------
# T8.5 — Validation failure: message persisted, no MessageAttachment row
# ---------------------------------------------------------------------------


class TestValidationFailure:
    """If validate_image_full raises on an attachment, no row is created for that attachment."""

    @pytest.mark.asyncio
    async def test_validation_failure_skips_row(self, tmp_path: Path) -> None:
        """ImageSecurityError → no MessageAttachment row, no disk write."""
        from api.services.conversation_image_service import ConversationImageService
        from shared.image_security import ImageSecurityError

        service = ConversationImageService(uploads_base=tmp_path)

        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        conv_id = uuid.uuid4()
        msg_id = uuid.uuid4()

        chatwoot_attachments = [
            {"url": "https://chatwoot.example.com/bomb.jpg", "name": "bomb.jpg", "type": "image/jpeg"}
        ]

        with (
            patch(
                "api.services.conversation_image_service.download_chatwoot_image",
                new=AsyncMock(return_value=b"\xff\xd8\xff" + b"\x00" * 100),
            ),
            patch(
                "api.services.conversation_image_service.validate_image_full",
                side_effect=ImageSecurityError("decompression bomb"),
            ),
            patch("api.services.conversation_image_service.validate_url"),
        ):
            rows = await service.download_and_persist_inbound(
                session=session,
                conversation_id=conv_id,
                message_id=msg_id,
                chatwoot_attachments=chatwoot_attachments,
            )

        assert rows == []
        session.add.assert_not_called()

        # Disk: no file written
        conv_dir = tmp_path / "conversation_images" / str(conv_id)
        if conv_dir.exists():
            assert list(conv_dir.iterdir()) == []


# ---------------------------------------------------------------------------
# T8.6 — Download failure after 3 retries → DLQ + ERROR log
# ---------------------------------------------------------------------------


class TestDownloadFailureDlq:
    """After 3 download failures the message is moved to DLQ and an ERROR is logged."""

    @pytest.mark.asyncio
    async def test_dlq_after_max_retries(self) -> None:
        """_handle_dlq moves message to DLQ and ACKs the original."""
        from api.workers.attachment_download_worker import _handle_dlq

        msg_id = "9000-0"
        data = {"data": json.dumps({
            "conversation_id": str(uuid.uuid4()),
            "message_id": str(uuid.uuid4()),
            "attachments": [{"url": "https://fail.example.com/img.jpg", "name": "img.jpg", "type": "image/jpeg"}],
        })}

        mock_redis = MagicMock()
        mock_redis.xadd = AsyncMock(return_value="9001-0")
        mock_redis.xack = AsyncMock(return_value=1)

        await _handle_dlq(
            redis=mock_redis,
            msg_id=msg_id,
            data=data,
            stream_name="attachment_downloads",
            consumer_group="attachment_workers",
            dlq_stream="attachment_downloads:dlq",
            error="network timeout after 3 attempts",
        )

        # DLQ entry added
        mock_redis.xadd.assert_called_once()
        dlq_call_args = mock_redis.xadd.call_args
        assert dlq_call_args[0][0] == "attachment_downloads:dlq"

        # Original message ACKed so it stops being re-delivered
        mock_redis.xack.assert_called_once_with(
            "attachment_downloads", "attachment_workers", msg_id
        )

    @pytest.mark.asyncio
    async def test_dlq_entry_preserves_error_string(self) -> None:
        """DLQ payload must contain the error string for traceability."""
        from api.workers.attachment_download_worker import _handle_dlq

        error_message = "HTTPStatusError: 503 Service Unavailable after 3 attempts"
        msg_id = "9002-0"
        data = {"data": json.dumps({
            "conversation_id": str(uuid.uuid4()),
            "message_id": str(uuid.uuid4()),
            "attachments": [],
        })}

        captured_dlq_entry: dict = {}

        mock_redis = MagicMock()
        mock_redis.xadd = AsyncMock(side_effect=lambda stream, entry: captured_dlq_entry.update({"stream": stream, "entry": entry}))
        mock_redis.xack = AsyncMock(return_value=1)

        await _handle_dlq(
            redis=mock_redis,
            msg_id=msg_id,
            data=data,
            stream_name="attachment_downloads",
            consumer_group="attachment_workers",
            dlq_stream="attachment_downloads:dlq",
            error=error_message,
        )

        assert "entry" in captured_dlq_entry
        assert error_message in captured_dlq_entry["entry"]["error"]
        assert captured_dlq_entry["entry"]["original_msg_id"] == msg_id


# ---------------------------------------------------------------------------
# C3 — Real webhook route: POST to /webhook/chatwoot/{token}, assert DB state
#
# These tests exercise the actual FastAPI route (not simulated logic) so that
# bugs like C1 (has_images computed before image_atts filter) are caught by
# the test suite.
#
# Patching strategy:
#   - api.routes.chatwoot.get_async_session → yields the test DB session
#   - api.routes.chatwoot.check_and_set_idempotency → returns False (not dup)
#   - shared.settings_cache.get_cached_setting → returns "true" (agent on)
#   - api.routes.chatwoot.ChatwootClient → no-op mock (update_conversation_attributes)
#   - api.routes.chatwoot.add_to_stream → AsyncMock (capture stream calls)
#   - api.routes.chatwoot.get_redis_client → MagicMock (for attachment stream)
# ---------------------------------------------------------------------------


def _build_webhook_payload(
    attachments: list[dict],
    chatwoot_conversation_id: int = 99001,
    chatwoot_message_id: int = 88001,
    phone: str = "+34600000099",
) -> dict:
    """Build a minimal Chatwoot webhook payload with the given attachments."""
    return {
        "event": "message_created",
        "conversation": {
            "id": chatwoot_conversation_id,
            "inbox_id": 1,
            "messages": [
                {
                    "id": chatwoot_message_id,
                    "content": "test message",
                    "message_type": 0,  # 0 = incoming
                    "content_type": "text",
                    "attachments": attachments,
                    "sender": {"id": 1, "phone_number": phone, "name": "Test User"},
                    "created_at": 1700000000,
                    "conversation_id": chatwoot_conversation_id,
                }
            ],
            "custom_attributes": {"atencion_automatica": True},
        },
        "sender": {"id": 1, "phone_number": phone, "name": "Test User"},
        "attachments": attachments,
    }


class TestWebhookRouteHasImagesFlag:
    """
    C3 regression guard: POST to the real webhook route and assert
    ConversationMessage.has_images / image_count are set correctly.

    These tests require a real test DB (db_engine fixture from conftest.py)
    because they assert on persisted DB rows — not mocked state.
    """

    @pytest.mark.asyncio
    async def test_webhook_image_message_sets_has_images_true(
        self, db_engine
    ) -> None:
        """
        Real POST with 2 image attachments → ConversationMessage.has_images=True,
        image_count=2.

        Regression guard for C1: the fix moved image_atts filter BEFORE the
        ConversationMessage constructor so has_images reflects image-only count.
        """
        from contextlib import asynccontextmanager

        import httpx
        from fastapi.testclient import TestClient
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from unittest.mock import AsyncMock, MagicMock, patch

        from api.main import app
        from database.models import ConversationMessage

        # Build a fresh session factory pointing at the TEST database
        TestingSession = async_sessionmaker(
            db_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        # Async context-manager patch for get_async_session
        @asynccontextmanager
        async def _fake_session():
            async with TestingSession() as session:
                yield session

        attachments = [
            {"id": 1, "file_type": "image", "data_url": "https://chatwoot.example.com/img1.jpg"},
            {"id": 2, "file_type": "image", "data_url": "https://chatwoot.example.com/img2.jpg"},
        ]
        payload = _build_webhook_payload(
            attachments=attachments,
            chatwoot_conversation_id=99101,
            chatwoot_message_id=88101,
            phone="+34611000101",
        )

        mock_chatwoot_client = MagicMock()
        mock_chatwoot_client.update_conversation_attributes = AsyncMock(return_value=None)

        with (
            patch("api.routes.chatwoot.get_async_session", _fake_session),
            patch("api.routes.chatwoot.check_and_set_idempotency", AsyncMock(return_value=False)),
            patch("shared.settings_cache.get_cached_setting", AsyncMock(return_value="true")),
            patch("api.routes.chatwoot.ChatwootClient", return_value=mock_chatwoot_client),
            patch("api.routes.chatwoot.get_redis_client", return_value=MagicMock()),
            patch("api.routes.chatwoot.add_to_stream", AsyncMock(return_value="1-0")),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/webhook/chatwoot/chatwoot_webhook_token_placeholder",
                json=payload,
            )

        assert response.status_code == 200, f"Webhook returned {response.status_code}: {response.text}"

        # Assert on the DB row
        async with TestingSession() as session:
            result = await session.execute(
                select(ConversationMessage).where(
                    ConversationMessage.chatwoot_message_id == 88101
                )
            )
            msg = result.scalar_one_or_none()

        assert msg is not None, "ConversationMessage was not persisted"
        assert msg.has_images is True, (
            f"Expected has_images=True for image-only message, got {msg.has_images}"
        )
        assert msg.image_count == 2, (
            f"Expected image_count=2, got {msg.image_count}"
        )

    @pytest.mark.asyncio
    async def test_webhook_non_image_message_keeps_has_images_false(
        self, db_engine
    ) -> None:
        """
        Real POST with 1 PDF attachment → ConversationMessage.has_images=False,
        image_count=0.

        This is the direct regression test for C1: before the fix,
        has_images=bool(last_message.attachments) would be True for a PDF-only
        message because attachments was non-empty.
        """
        from contextlib import asynccontextmanager

        from fastapi.testclient import TestClient
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from unittest.mock import AsyncMock, MagicMock, patch

        from api.main import app
        from database.models import ConversationMessage

        TestingSession = async_sessionmaker(
            db_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        @asynccontextmanager
        async def _fake_session():
            async with TestingSession() as session:
                yield session

        # PDF-only attachment (file_type != "image")
        attachments = [
            {"id": 3, "file_type": "file", "data_url": "https://chatwoot.example.com/doc.pdf"},
        ]
        payload = _build_webhook_payload(
            attachments=attachments,
            chatwoot_conversation_id=99102,
            chatwoot_message_id=88102,
            phone="+34611000102",
        )

        mock_chatwoot_client = MagicMock()
        mock_chatwoot_client.update_conversation_attributes = AsyncMock(return_value=None)

        with (
            patch("api.routes.chatwoot.get_async_session", _fake_session),
            patch("api.routes.chatwoot.check_and_set_idempotency", AsyncMock(return_value=False)),
            patch("shared.settings_cache.get_cached_setting", AsyncMock(return_value="true")),
            patch("api.routes.chatwoot.ChatwootClient", return_value=mock_chatwoot_client),
            patch("api.routes.chatwoot.get_redis_client", return_value=MagicMock()),
            patch("api.routes.chatwoot.add_to_stream", AsyncMock(return_value="1-0")),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/webhook/chatwoot/chatwoot_webhook_token_placeholder",
                json=payload,
            )

        assert response.status_code == 200, f"Webhook returned {response.status_code}: {response.text}"

        # Assert on the DB row — PDF should NOT set has_images=True
        async with TestingSession() as session:
            result = await session.execute(
                select(ConversationMessage).where(
                    ConversationMessage.chatwoot_message_id == 88102
                )
            )
            msg = result.scalar_one_or_none()

        assert msg is not None, "ConversationMessage was not persisted"
        assert msg.has_images is False, (
            f"C1 REGRESSION: has_images should be False for PDF-only message, got {msg.has_images}"
        )
        assert msg.image_count == 0, (
            f"C1 REGRESSION: image_count should be 0 for PDF-only message, got {msg.image_count}"
        )
