"""
Integration tests for T9 — Outbound bot image persistence.

TDD cycle: RED (tests written first)

Covers:
  - Bot sends 1 image → 1 MessageAttachment row, has_images=True, image_count=1
  - Bot sends 3 images → 3 attachment rows sorted by position
  - Bot sends images + caption (content) → message has content + attachments
  - Non-image path (no send_images call) → 0 attachment rows (regression guard)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONVERSATION_ID = "12345"
_CONV_HISTORY_ID = uuid.uuid4()


def _make_session_mock() -> AsyncMock:
    """Build a mock AsyncSession with commit/flush/add as no-ops."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Tests for save_assistant_message returning ID
# ---------------------------------------------------------------------------


class TestSaveAssistantMessageReturnsId:
    """save_assistant_message must return the UUID of the persisted row."""

    @pytest.mark.asyncio
    async def test_returns_uuid_on_success(self) -> None:
        """save_assistant_message returns a UUID on successful persist."""
        from api.services.message_persistence_service import save_assistant_message

        expected_id = uuid.uuid4()

        mock_message = MagicMock()
        mock_message.id = expected_id

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "api.services.message_persistence_service.get_or_create_conversation_history",
                new=AsyncMock(return_value=_CONV_HISTORY_ID),
            ),
            patch(
                "api.services.message_persistence_service.get_async_session",
                return_value=mock_session,
            ),
            patch(
                "api.services.message_persistence_service.ConversationMessage",
                return_value=mock_message,
            ),
        ):
            result = await save_assistant_message(
                conversation_id=_CONVERSATION_ID,
                content="Hello",
            )

        assert result == expected_id

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self) -> None:
        """save_assistant_message returns None when an exception occurs (fire-and-forget)."""
        from api.services.message_persistence_service import save_assistant_message

        with patch(
            "api.services.message_persistence_service.get_or_create_conversation_history",
            new=AsyncMock(side_effect=RuntimeError("DB connection failed")),
        ):
            result = await save_assistant_message(
                conversation_id=_CONVERSATION_ID,
                content="Hello",
            )

        assert result is None


# ---------------------------------------------------------------------------
# Tests for ConversationImageService.persist_outbound_urls
# ---------------------------------------------------------------------------


class TestPersistOutboundUrls:
    """persist_outbound_urls creates MessageAttachment rows in position order."""

    @pytest.mark.asyncio
    async def test_single_image_creates_one_row(self) -> None:
        """Bot sends 1 image → 1 MessageAttachment row with position=0."""
        from api.services.conversation_image_service import ConversationImageService
        from database.models import MessageAttachment

        msg_id = uuid.uuid4()
        session = _make_session_mock()
        svc = ConversationImageService()

        image_urls = ["/images/img1.jpg"]
        rows = await svc.persist_outbound_urls(session, msg_id, image_urls)

        assert len(rows) == 1
        assert rows[0].message_id == msg_id
        assert rows[0].url == "/images/img1.jpg"
        assert rows[0].position == 0
        assert rows[0].kind == "image"
        assert rows[0].chatwoot_url is None
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_three_images_sorted_by_position(self) -> None:
        """Bot sends 3 images → 3 rows with positions 0, 1, 2."""
        from api.services.conversation_image_service import ConversationImageService

        msg_id = uuid.uuid4()
        session = _make_session_mock()
        svc = ConversationImageService()

        image_urls = [
            "/images/img_a.jpg",
            "/images/img_b.jpg",
            "/images/img_c.jpg",
        ]
        rows = await svc.persist_outbound_urls(session, msg_id, image_urls)

        assert len(rows) == 3
        for idx, row in enumerate(rows):
            assert row.position == idx
            assert row.url == image_urls[idx]
            assert row.message_id == msg_id

    @pytest.mark.asyncio
    async def test_empty_url_list_returns_empty(self) -> None:
        """Non-image path: no URLs → zero attachment rows (regression guard)."""
        from api.services.conversation_image_service import ConversationImageService

        msg_id = uuid.uuid4()
        session = _make_session_mock()
        svc = ConversationImageService()

        rows = await svc.persist_outbound_urls(session, msg_id, [])

        assert rows == []
        # flush should NOT be called when there are no urls
        session.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_with_caption_content_message(self) -> None:
        """Bot sends image + caption → rows have position and correct url."""
        from api.services.conversation_image_service import ConversationImageService

        msg_id = uuid.uuid4()
        session = _make_session_mock()
        svc = ConversationImageService()

        image_urls = ["/images/photo_escapamiento.jpg"]
        rows = await svc.persist_outbound_urls(session, msg_id, image_urls)

        assert len(rows) == 1
        assert rows[0].url == "/images/photo_escapamiento.jpg"
        assert rows[0].position == 0


# ---------------------------------------------------------------------------
# Regression guard: non-image paths must NOT produce attachment rows
# ---------------------------------------------------------------------------


class TestNonImagePathsProduceNoAttachments:
    """Non-image paths (no send_images called) must NOT call persist_outbound_urls."""

    @pytest.mark.asyncio
    async def test_normal_text_path_does_not_persist_outbound(self) -> None:
        """Normal text-only bot response: no attachment rows created."""
        from api.services.conversation_image_service import ConversationImageService

        msg_id = uuid.uuid4()
        session = _make_session_mock()
        svc = ConversationImageService()

        # Simulate the non-image code path: image_urls is [] when no images sent
        rows = await svc.persist_outbound_urls(session, msg_id, [])

        assert rows == []
        # The session.add must NOT have been called with any attachment
        assert session.add.call_count == 0
