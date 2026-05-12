"""
Integration tests for T7 — Thread API attachments.

TDD cycle: RED (tests written first, implementation may not exist yet)

Covers:
  - Message with 2 attachments → returned sorted by position ASC
  - Message with no attachments → attachments field is []
  - Legacy message (has_images=True, no MessageAttachment rows) → attachments = []
  - N+1 prevention: total SQL queries = 2 (messages + selectinload for attachments)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conv_history_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_message(
    conv_history_id: uuid.UUID,
    content: str = "hello",
    has_images: bool = False,
    image_count: int = 0,
    attachments: list | None = None,
) -> MagicMock:
    """Build a mock ConversationMessage with attachments attribute."""
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.conversation_history_id = conv_history_id
    msg.role = "assistant"
    msg.author_type = "bot"
    msg.author_user_id = None
    msg.author_user_name = None
    msg.content = content
    msg.created_at = datetime.now(UTC)
    msg.is_read = True
    msg.has_images = has_images
    msg.image_count = image_count
    msg.chatwoot_message_id = None
    msg.delivery_failed = False
    msg.attachments = attachments or []
    return msg


def _make_attachment(
    message_id: uuid.UUID,
    position: int,
    url: str = "/conversation-images/conv/file.jpg",
) -> MagicMock:
    att = MagicMock()
    att.id = uuid.uuid4()
    att.message_id = message_id
    att.url = url
    att.kind = "image"
    att.content_type = "image/jpeg"
    att.filename = f"image_{position}.jpg"
    att.size_bytes = 12345
    att.width = 800
    att.height = 600
    att.position = position
    att.created_at = datetime.now(UTC)
    return att


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_admin_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = "testadmin"
    user.role = "admin"
    return user


@pytest.fixture
def app_with_overrides(mock_admin_user: MagicMock) -> FastAPI:
    """Build minimal FastAPI app with conversations_admin router."""
    from api.routes.conversations_admin import get_current_user, router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestThreadAPIAttachments:
    """Thread endpoint returns attachments sorted by position ASC."""

    def test_message_with_two_attachments_sorted(
        self,
        app_with_overrides: FastAPI,
    ) -> None:
        """Message with 2 attachments → returned sorted by position ASC."""
        conv_history_id = _make_conv_history_id()
        msg = _make_message(conv_history_id, has_images=True, image_count=2)
        att0 = _make_attachment(msg.id, position=0, url="/conversation-images/c/img0.jpg")
        att1 = _make_attachment(msg.id, position=1, url="/conversation-images/c/img1.jpg")
        # Intentionally provide attachments in reverse order to test sort
        msg.attachments = [att1, att0]

        mock_conv = MagicMock()
        mock_conv.id = conv_history_id

        with (
            patch(
                "api.routes.conversations_admin.get_async_session"
            ) as mock_session_ctx,
            patch(
                "api.routes.conversations_admin._load_conversation",
                new=AsyncMock(return_value=mock_conv),
            ),
        ):
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            # Simulate execute returning rows
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [msg]
            mock_session.execute = AsyncMock(return_value=mock_result)

            client = TestClient(app_with_overrides)
            resp = client.get(
                f"/api/admin/conversations/{conv_history_id}/thread",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
        messages = data["messages"]
        assert len(messages) == 1
        atts = messages[0]["attachments"]
        assert len(atts) == 2
        # Must be sorted by position ASC
        assert atts[0]["position"] == 0
        assert atts[1]["position"] == 1
        assert atts[0]["url"] == "/conversation-images/c/img0.jpg"

    def test_message_with_no_attachments_returns_empty_list(
        self,
        app_with_overrides: FastAPI,
    ) -> None:
        """Message with no attachments → attachments field is []."""
        conv_history_id = _make_conv_history_id()
        msg = _make_message(conv_history_id, content="plain text", has_images=False)
        msg.attachments = []

        mock_conv = MagicMock()
        mock_conv.id = conv_history_id

        with (
            patch(
                "api.routes.conversations_admin.get_async_session"
            ) as mock_session_ctx,
            patch(
                "api.routes.conversations_admin._load_conversation",
                new=AsyncMock(return_value=mock_conv),
            ),
        ):
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [msg]
            mock_session.execute = AsyncMock(return_value=mock_result)

            client = TestClient(app_with_overrides)
            resp = client.get(
                f"/api/admin/conversations/{conv_history_id}/thread",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        messages = data["messages"]
        assert len(messages) == 1
        assert messages[0]["attachments"] == []

    def test_legacy_message_has_images_true_no_rows_returns_empty(
        self,
        app_with_overrides: FastAPI,
    ) -> None:
        """Legacy message: has_images=True but no MessageAttachment rows → attachments = []."""
        conv_history_id = _make_conv_history_id()
        # Legacy message: has_images set but no attachment rows (pre-migration data)
        msg = _make_message(
            conv_history_id,
            has_images=True,
            image_count=3,
            attachments=[],  # no rows yet
        )

        mock_conv = MagicMock()
        mock_conv.id = conv_history_id

        with (
            patch(
                "api.routes.conversations_admin.get_async_session"
            ) as mock_session_ctx,
            patch(
                "api.routes.conversations_admin._load_conversation",
                new=AsyncMock(return_value=mock_conv),
            ),
        ):
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [msg]
            mock_session.execute = AsyncMock(return_value=mock_result)

            client = TestClient(app_with_overrides)
            resp = client.get(
                f"/api/admin/conversations/{conv_history_id}/thread",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        messages = data["messages"]
        assert len(messages) == 1
        # Legacy message: has_images is True but attachments array is empty
        assert messages[0]["has_images"] is True
        assert messages[0]["image_count"] == 3
        assert messages[0]["attachments"] == []

    def test_selectinload_prevents_n_plus_one(
        self,
        app_with_overrides: FastAPI,
    ) -> None:
        """N+1 prevention: the thread query uses selectinload so only 2 DB round-trips occur.

        This test verifies that the route uses selectinload by checking that
        session.execute is called at most 2 times (1 for messages + 1 from
        _load_conversation), regardless of the number of messages returned.
        More than 2 calls would indicate N+1 (one per-message attachment query).
        """
        conv_history_id = _make_conv_history_id()
        # Build 5 messages each with 2 attachments — in N+1 this would be 1+5=6 queries
        messages = []
        for i in range(5):
            msg = _make_message(conv_history_id, content=f"msg {i}", has_images=True, image_count=2)
            att0 = _make_attachment(msg.id, position=0)
            att1 = _make_attachment(msg.id, position=1)
            msg.attachments = [att0, att1]
            messages.append(msg)

        mock_conv = MagicMock()
        mock_conv.id = conv_history_id

        execute_call_count = 0

        async def mock_execute(stmt):
            nonlocal execute_call_count
            execute_call_count += 1
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = messages
            mock_result.scalar_one_or_none.return_value = None  # no cursor
            return mock_result

        with (
            patch(
                "api.routes.conversations_admin.get_async_session"
            ) as mock_session_ctx,
            patch(
                "api.routes.conversations_admin._load_conversation",
                new=AsyncMock(return_value=mock_conv),
            ),
        ):
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = mock_execute

            client = TestClient(app_with_overrides)
            resp = client.get(
                f"/api/admin/conversations/{conv_history_id}/thread",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        # selectinload means only 1 call to session.execute from get_messages
        # (attachments are loaded eagerly in the same round-trip, not per message)
        # _load_conversation is patched so doesn't count here
        # Therefore: exactly 1 execute call (messages query with selectinload)
        assert execute_call_count == 1, (
            f"Expected 1 execute call (selectinload), got {execute_call_count}. "
            "This indicates N+1 queries — selectinload is not being used."
        )
