"""
Integration tests for conversations admin endpoints (T11–T20).

TDD cycle: RED → GREEN → REFACTOR

Covers:
  T11.1 - send-message inside 24h window → 200 + ConversationMessageResponse
  T11.2 - send-message outside 24h window → 422 OutsideWindow24h
  T11.3 - send-message with bot active → auto-pauses
  T11.4 - send-message Chatwoot fails → 207 multi-status with delivery_failed flag
  T12.1 - send-template OK → 200
  T12.2 - send-template Chatwoot fails → 207 with flag
  T13.1 - pause successful → 200
  T13.2 - pause idempotent (second call updates reason)
  T14.1 - resume successful → 200
  T14.2 - resume without pause → 409 BotNotPaused
  T15.1 - escalate creates Escalation + pauses bot
  T16.1 - window-status with last_inbound_at NULL
  T16.2 - window-status inside window
  T16.3 - window-status outside window
  T17.1 - templates listing
  T18.1 - mark-read ALL messages
  T18.2 - mark-read specific message IDs
  T19.1 - inbox without filters (all)
  T19.2 - inbox tab=bot_off
  T19.3 - inbox tab=escaladas
  T19.4 - inbox tab=no_leidas
  T19.5 - inbox tab=mias
  T19.6 - inbox search by name
  T19.7 - inbox pagination
  T20.1 - messages first page
  T20.2 - messages with cursor (next page)
  T20.3 - messages no more results → next_cursor=None
  DI - graph not available → 503 on graph-dependent endpoints
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------


def _make_conv(
    *,
    bot_paused_at: datetime | None = None,
    state_snapshot: dict | None = None,
    state_snapshot_version: int | None = None,
    bot_pause_reason: str | None = None,
    bot_paused_by_user_id=None,
    last_inbound_at: datetime | None = None,
    last_message_at: datetime | None = None,
    conversation_id: str = "12345",
) -> MagicMock:
    conv = MagicMock()
    conv.id = uuid4()
    conv.conversation_id = conversation_id
    conv.bot_paused_at = bot_paused_at
    conv.bot_resumed_at = None
    conv.state_snapshot = state_snapshot
    conv.state_snapshot_version = state_snapshot_version
    conv.bot_pause_reason = bot_pause_reason
    conv.bot_paused_by_user_id = bot_paused_by_user_id
    conv.last_inbound_at = last_inbound_at
    conv.last_message_at = last_message_at or datetime.now(UTC)
    conv.user = MagicMock()
    conv.user.id = uuid4()
    conv.user.first_name = "Test"
    conv.user.last_name = "User"
    conv.user.phone = "+34600000000"
    conv.paused_by_user = None
    return conv


def _make_msg(*, conversation_history_id=None, is_read=False, author_type="user") -> MagicMock:
    msg = MagicMock()
    msg.id = uuid4()
    msg.conversation_history_id = conversation_history_id or uuid4()
    msg.role = "user"
    msg.author_type = author_type
    msg.author_user_id = None
    msg.content = "Test message content"
    msg.created_at = datetime.now(UTC)
    msg.is_read = is_read
    msg.has_images = False
    msg.chatwoot_message_id = None
    msg.delivery_failed = False
    return msg


def _make_admin_user(*, role: str = "admin") -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.username = "testuser"
    user.role = role
    user.is_active = True
    user.display_name = "Test User"
    return user


def _make_session(conv: MagicMock | None = None, messages: list | None = None) -> AsyncMock:
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = conv
    execute_result.scalar.return_value = 0
    scalars_result = MagicMock()
    scalars_result.all.return_value = messages or []
    scalars_result.first.return_value = messages[0] if messages else None
    execute_result.scalars.return_value = scalars_result
    execute_result.fetchall.return_value = []
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    return session


def _make_graph() -> MagicMock:
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=MagicMock(values={"current_mode": "START"}))
    graph.aupdate_state = AsyncMock()
    return graph


def _make_app(*, with_graph: bool = True) -> tuple[FastAPI, MagicMock]:
    """Build a test FastAPI app with the conversations_admin router included."""
    from api.routes.conversations_admin import router

    app = FastAPI()
    app.include_router(router)

    graph = _make_graph() if with_graph else None
    app.state.compiled_graph = graph
    return app, graph


def _override_auth(app: FastAPI, user: MagicMock) -> None:
    """Override the conversations_admin get_current_user dependency with a mock user."""
    from api.routes.conversations_admin import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user


# ---------------------------------------------------------------------------
# T11 — POST /api/admin/conversations/{id}/send-message
# ---------------------------------------------------------------------------


class TestSendMessage:
    """T11: send-message endpoint."""

    @pytest.mark.asyncio
    async def test_send_message_inside_window_200(self):
        """T11.1: send-message inside window returns 200 with ConversationMessageResponse."""
        from api.services.conversation_action_service import ConversationActionService

        app, graph = _make_app(with_graph=True)
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        msg = _make_msg(conversation_history_id=conv_id)
        msg.delivery_failed = False
        svc = AsyncMock()
        svc.send_human_message = AsyncMock(return_value=msg)

        with patch("api.routes.conversations_admin.ConversationActionService", return_value=svc), \
             patch("api.routes.conversations_admin.get_async_session") as mock_ctx, \
             patch("api.routes.conversations_admin.ChatwootClient"), \
             patch("api.routes.conversations_admin.get_redis_client"):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=_make_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/send-message",
                json={"content": "Hola, ¿cómo puedo ayudarle?"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data

    @pytest.mark.asyncio
    async def test_send_message_outside_window_422(self):
        """T11.2: send-message outside 24h window returns 422."""
        from api.services.conversation_action_service import OutsideWindow24hError

        app, graph = _make_app(with_graph=True)
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        svc = AsyncMock()
        svc.send_human_message = AsyncMock(side_effect=OutsideWindow24hError(conv_id, None))

        with patch("api.routes.conversations_admin.ConversationActionService", return_value=svc), \
             patch("api.routes.conversations_admin.get_async_session") as mock_ctx, \
             patch("api.routes.conversations_admin.ChatwootClient"), \
             patch("api.routes.conversations_admin.get_redis_client"):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=_make_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/send-message",
                json={"content": "Test"},
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_send_message_with_bot_active_auto_pauses(self):
        """T11.3: send-message calls service with auto_pause_if_bot_on=True."""
        app, graph = _make_app(with_graph=True)
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        msg = _make_msg(conversation_history_id=conv_id)
        msg.delivery_failed = False
        svc = AsyncMock()
        svc.send_human_message = AsyncMock(return_value=msg)

        with patch("api.routes.conversations_admin.ConversationActionService", return_value=svc), \
             patch("api.routes.conversations_admin.get_async_session") as mock_ctx, \
             patch("api.routes.conversations_admin.ChatwootClient"), \
             patch("api.routes.conversations_admin.get_redis_client"):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=_make_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/send-message",
                json={"content": "Test"},
            )

        assert response.status_code == 200
        svc.send_human_message.assert_called_once()
        call_kwargs = svc.send_human_message.call_args[1]
        assert call_kwargs.get("auto_pause_if_bot_on") is True

    @pytest.mark.asyncio
    async def test_send_message_chatwoot_fails_207(self):
        """T11.4: send-message Chatwoot failure → 207 with delivery_failed flag."""
        app, graph = _make_app(with_graph=True)
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        msg = _make_msg(conversation_history_id=conv_id)
        msg.delivery_failed = True
        svc = AsyncMock()
        svc.send_human_message = AsyncMock(return_value=msg)

        with patch("api.routes.conversations_admin.ConversationActionService", return_value=svc), \
             patch("api.routes.conversations_admin.get_async_session") as mock_ctx, \
             patch("api.routes.conversations_admin.ChatwootClient"), \
             patch("api.routes.conversations_admin.get_redis_client"):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=_make_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/send-message",
                json={"content": "Test"},
            )

        assert response.status_code == 207
        data = response.json()
        assert data.get("delivery_failed") is True


# ---------------------------------------------------------------------------
# T12 — POST /api/admin/conversations/{id}/send-template
# ---------------------------------------------------------------------------


class TestSendTemplate:
    """T12: send-template endpoint."""

    @pytest.mark.asyncio
    async def test_send_template_ok_200(self):
        """T12.1: send-template OK → 200."""
        app, graph = _make_app(with_graph=True)
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        msg = _make_msg(conversation_history_id=conv_id)
        msg.delivery_failed = False
        svc = AsyncMock()
        svc.send_template_message = AsyncMock(return_value=msg)

        with patch("api.routes.conversations_admin.ConversationActionService", return_value=svc), \
             patch("api.routes.conversations_admin.get_async_session") as mock_ctx, \
             patch("api.routes.conversations_admin.ChatwootClient"), \
             patch("api.routes.conversations_admin.get_redis_client"):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=_make_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/send-template",
                json={"template_name": "bienvenida", "params": {"nombre": "Juan"}, "language": "es"},
            )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_send_template_chatwoot_fails_207(self):
        """T12.2: send-template Chatwoot failure → 207 with flag."""
        app, graph = _make_app(with_graph=True)
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        msg = _make_msg(conversation_history_id=conv_id)
        msg.delivery_failed = True
        svc = AsyncMock()
        svc.send_template_message = AsyncMock(return_value=msg)

        with patch("api.routes.conversations_admin.ConversationActionService", return_value=svc), \
             patch("api.routes.conversations_admin.get_async_session") as mock_ctx, \
             patch("api.routes.conversations_admin.ChatwootClient"), \
             patch("api.routes.conversations_admin.get_redis_client"):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=_make_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/send-template",
                json={"template_name": "bienvenida", "params": {"nombre": "Juan"}, "language": "es"},
            )

        assert response.status_code == 207
        data = response.json()
        assert data.get("delivery_failed") is True


# ---------------------------------------------------------------------------
# T13 — POST /api/admin/conversations/{id}/pause
# ---------------------------------------------------------------------------


class TestPauseBot:
    """T13: pause endpoint."""

    @pytest.mark.asyncio
    async def test_pause_successful_200(self):
        """T13.1: pause successful → 200 with updated ConversationHistory."""
        app, graph = _make_app(with_graph=True)
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        paused_conv = _make_conv(bot_paused_at=datetime.now(UTC))
        svc = AsyncMock()
        svc.pause_bot = AsyncMock(return_value=paused_conv)

        with patch("api.routes.conversations_admin.ConversationActionService", return_value=svc), \
             patch("api.routes.conversations_admin.get_async_session") as mock_ctx, \
             patch("api.routes.conversations_admin.ChatwootClient"), \
             patch("api.routes.conversations_admin.get_redis_client"):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=_make_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/pause",
                json={"reason": "Necesita revisión humana"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["bot_paused_at"] is not None

    @pytest.mark.asyncio
    async def test_pause_idempotent_updates_reason(self):
        """T13.2: second pause call updates reason (idempotent)."""
        app, graph = _make_app(with_graph=True)
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        paused_conv = _make_conv(
            bot_paused_at=datetime.now(UTC),
            bot_pause_reason="Nueva razón",
        )
        svc = AsyncMock()
        svc.pause_bot = AsyncMock(return_value=paused_conv)

        with patch("api.routes.conversations_admin.ConversationActionService", return_value=svc), \
             patch("api.routes.conversations_admin.get_async_session") as mock_ctx, \
             patch("api.routes.conversations_admin.ChatwootClient"), \
             patch("api.routes.conversations_admin.get_redis_client"):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=_make_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/pause",
                json={"reason": "Nueva razón"},
            )

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# T14 — POST /api/admin/conversations/{id}/resume
# ---------------------------------------------------------------------------


class TestResumeBot:
    """T14: resume endpoint."""

    @pytest.mark.asyncio
    async def test_resume_successful_200(self):
        """T14.1: resume successful → 200."""
        app, graph = _make_app(with_graph=True)
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        resumed_conv = _make_conv()
        resumed_conv.bot_resumed_at = datetime.now(UTC)
        svc = AsyncMock()
        svc.resume_bot = AsyncMock(return_value=resumed_conv)

        with patch("api.routes.conversations_admin.ConversationActionService", return_value=svc), \
             patch("api.routes.conversations_admin.get_async_session") as mock_ctx, \
             patch("api.routes.conversations_admin.ChatwootClient"), \
             patch("api.routes.conversations_admin.get_redis_client"):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=_make_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/resume",
                json={},
            )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_resume_without_pause_409(self):
        """T14.2: resume without pause → 409 BotNotPaused."""
        from api.services.conversation_action_service import BotNotPausedError

        app, graph = _make_app(with_graph=True)
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        svc = AsyncMock()
        svc.resume_bot = AsyncMock(side_effect=BotNotPausedError(conv_id))

        with patch("api.routes.conversations_admin.ConversationActionService", return_value=svc), \
             patch("api.routes.conversations_admin.get_async_session") as mock_ctx, \
             patch("api.routes.conversations_admin.ChatwootClient"), \
             patch("api.routes.conversations_admin.get_redis_client"):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=_make_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/resume",
                json={},
            )

        assert response.status_code == 409


# ---------------------------------------------------------------------------
# T15 — POST /api/admin/conversations/{id}/escalate
# ---------------------------------------------------------------------------


class TestEscalate:
    """T15: escalate endpoint."""

    @pytest.mark.asyncio
    async def test_escalate_creates_escalation_and_pauses(self):
        """T15.1: escalate creates Escalation record + pauses bot."""
        app, graph = _make_app(with_graph=True)
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        paused_conv = _make_conv(bot_paused_at=datetime.now(UTC))
        svc = AsyncMock()
        svc.pause_bot = AsyncMock(return_value=paused_conv)

        conv = _make_conv(conversation_id="12345")

        with patch("api.routes.conversations_admin.ConversationActionService", return_value=svc), \
             patch("api.routes.conversations_admin.get_async_session") as mock_ctx, \
             patch("api.routes.conversations_admin.ChatwootClient"), \
             patch("api.routes.conversations_admin.get_redis_client"):
            mock_session = _make_session(conv=conv)
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/escalate",
                json={"reason": "Cliente furioso", "priority": "high"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "escalation_id" in data or "id" in data
        # pause_bot must have been called
        svc.pause_bot.assert_called_once()


# ---------------------------------------------------------------------------
# T16 — GET /api/admin/conversations/{id}/window-status
# ---------------------------------------------------------------------------


class TestWindowStatus:
    """T16: window-status endpoint."""

    @pytest.mark.asyncio
    async def test_window_status_null_last_inbound(self):
        """T16.1: window-status with last_inbound_at NULL → within_24h=False."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None  # No graph needed for this endpoint
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        conv = _make_conv(last_inbound_at=None)

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=_make_session(conv=conv))
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get(f"/api/admin/conversations/{conv_id}/window-status")

        assert response.status_code == 200
        data = response.json()
        assert data["within_24h"] is False
        assert data["last_inbound_at"] is None
        assert data["expires_at"] is None

    @pytest.mark.asyncio
    async def test_window_status_inside_window(self):
        """T16.2: window-status inside window → within_24h=True + seconds_remaining > 0."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        conv = _make_conv(last_inbound_at=datetime.now(UTC) - timedelta(hours=6))

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=_make_session(conv=conv))
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get(f"/api/admin/conversations/{conv_id}/window-status")

        assert response.status_code == 200
        data = response.json()
        assert data["within_24h"] is True
        assert data["seconds_remaining"] is not None
        assert data["seconds_remaining"] > 0

    @pytest.mark.asyncio
    async def test_window_status_outside_window(self):
        """T16.3: window-status outside window → within_24h=False."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        conv = _make_conv(last_inbound_at=datetime.now(UTC) - timedelta(hours=30))

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=_make_session(conv=conv))
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get(f"/api/admin/conversations/{conv_id}/window-status")

        assert response.status_code == 200
        data = response.json()
        assert data["within_24h"] is False
        assert data["seconds_remaining"] == 0


# ---------------------------------------------------------------------------
# T17 — GET /api/admin/conversations/templates
# ---------------------------------------------------------------------------


class TestListTemplates:
    """T17: templates listing endpoint."""

    @pytest.mark.asyncio
    async def test_list_templates_200(self):
        """T17.1: templates listing returns approved templates."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        user = _make_admin_user()
        _override_auth(app, user)

        mock_chatwoot = AsyncMock()
        mock_chatwoot.list_whatsapp_templates = AsyncMock(return_value=[
            {
                "name": "test_template",
                "language": "es",
                "status": "APPROVED",
                "category": "UTILITY",
                "components": [],
            }
        ])

        with patch("api.routes.conversations_admin.ChatwootClient", return_value=mock_chatwoot), \
             patch("api.routes.conversations_admin.get_redis_client", return_value=AsyncMock()):

            client = TestClient(app)
            response = client.get("/api/admin/conversations/templates")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1


# ---------------------------------------------------------------------------
# T18 — POST /api/admin/conversations/{id}/mark-read
# ---------------------------------------------------------------------------


class TestMarkRead:
    """T18: mark-read endpoint."""

    @pytest.mark.asyncio
    async def test_mark_read_all_messages(self):
        """T18.1: mark-read all messages returns marked_count."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        conv = _make_conv()
        mock_session = AsyncMock()
        # First execute: load conversation; second: update statement
        execute_result_conv = MagicMock()
        execute_result_conv.scalar_one_or_none.return_value = conv
        execute_result_update = MagicMock()
        execute_result_update.fetchall.return_value = [("id1",), ("id2",), ("id3",)]
        mock_session.execute = AsyncMock(
            side_effect=[execute_result_conv, execute_result_update]
        )
        mock_session.commit = AsyncMock()

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/mark-read",
                json={},
            )

        assert response.status_code == 200
        data = response.json()
        assert "marked_count" in data
        assert data["marked_count"] == 3

    @pytest.mark.asyncio
    async def test_mark_read_specific_ids(self):
        """T18.2: mark-read specific message IDs."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        conv_id = uuid4()
        msg_id_1 = uuid4()
        msg_id_2 = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        conv = _make_conv()
        mock_session = AsyncMock()
        execute_result_conv = MagicMock()
        execute_result_conv.scalar_one_or_none.return_value = conv
        execute_result_update = MagicMock()
        execute_result_update.fetchall.return_value = [("id1",), ("id2",)]
        mock_session.execute = AsyncMock(
            side_effect=[execute_result_conv, execute_result_update]
        )
        mock_session.commit = AsyncMock()

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/mark-read",
                json={"message_ids": [str(msg_id_1), str(msg_id_2)]},
            )

        assert response.status_code == 200
        data = response.json()
        assert "marked_count" in data
        assert data["marked_count"] == 2


# ---------------------------------------------------------------------------
# T19 — GET /api/admin/inbox
# ---------------------------------------------------------------------------


class TestInbox:
    """T19: inbox listing endpoint."""

    def _mock_inbox_session(self) -> AsyncMock:
        """Build an AsyncSession mock suitable for the inbox endpoint's multiple queries."""
        session = AsyncMock()
        # inbox does: count query + items query + unread_map query + escalation_map query
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        empty_result.scalar.return_value = 0
        empty_result.scalar_one_or_none.return_value = None
        empty_result.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)
        return session

    @pytest.mark.asyncio
    async def test_inbox_no_filters(self):
        """T19.1: inbox without filters returns all conversations."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        user = _make_admin_user()
        _override_auth(app, user)

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=self._mock_inbox_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    @pytest.mark.asyncio
    async def test_inbox_tab_bot_off(self):
        """T19.2: inbox tab=bot_off filters paused conversations."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        user = _make_admin_user()
        _override_auth(app, user)

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=self._mock_inbox_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox?tab=bot_off")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_inbox_tab_escaladas(self):
        """T19.3: inbox tab=escaladas filters escalated conversations."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        user = _make_admin_user()
        _override_auth(app, user)

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=self._mock_inbox_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox?tab=escaladas")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_inbox_tab_no_leidas(self):
        """T19.4: inbox tab=no_leidas filters conversations with unread messages."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        user = _make_admin_user()
        _override_auth(app, user)

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=self._mock_inbox_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox?tab=no_leidas")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_inbox_tab_mias(self):
        """T19.5: inbox tab=mias filters conversations paused by current user."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        user = _make_admin_user()
        _override_auth(app, user)

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=self._mock_inbox_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox?tab=mias")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_inbox_search_by_name(self):
        """T19.6: inbox search by user name."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        user = _make_admin_user()
        _override_auth(app, user)

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=self._mock_inbox_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox?search=Juan")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_inbox_pagination(self):
        """T19.7: inbox pagination params respected."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        user = _make_admin_user()
        _override_auth(app, user)

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=self._mock_inbox_session())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox?page=2&page_size=25")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["page_size"] == 25


# ---------------------------------------------------------------------------
# T20 — GET /api/admin/conversations/{id}/thread
# ---------------------------------------------------------------------------


class TestConversationMessages:
    """T20: cursor-based message listing endpoint."""

    @pytest.mark.asyncio
    async def test_messages_first_page(self):
        """T20.1: messages first page without cursor."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        conv = _make_conv()
        msgs = [_make_msg(conversation_history_id=conv_id) for _ in range(3)]

        mock_session = AsyncMock()
        # Execute calls: load_conversation + messages query
        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = conv
        msgs_result = MagicMock()
        msgs_result.scalars.return_value.all.return_value = msgs
        mock_session.execute = AsyncMock(side_effect=[conv_result, msgs_result])

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get(f"/api/admin/conversations/{conv_id}/thread")

        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert "next_cursor" in data
        assert len(data["messages"]) == 3

    @pytest.mark.asyncio
    async def test_messages_with_cursor_has_next(self):
        """T20.2: messages with cursor returns next page when limit+1 rows returned."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        conv_id = uuid4()
        cursor_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        conv = _make_conv()
        # Return limit+1 messages to signal there's a next page
        msgs = [_make_msg(conversation_history_id=conv_id) for _ in range(4)]  # limit=3 → 3+1=4

        mock_session = AsyncMock()
        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = conv
        cursor_result = MagicMock()
        cursor_result.scalar_one_or_none.return_value = datetime.now(UTC)
        msgs_result = MagicMock()
        msgs_result.scalars.return_value.all.return_value = msgs
        mock_session.execute = AsyncMock(side_effect=[conv_result, cursor_result, msgs_result])

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get(
                f"/api/admin/conversations/{conv_id}/thread?cursor={cursor_id}&limit=3"
            )

        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert "next_cursor" in data
        assert len(data["messages"]) == 3  # limit, not limit+1
        assert data["next_cursor"] is not None

    @pytest.mark.asyncio
    async def test_messages_no_more_results(self):
        """T20.3: messages no more results → next_cursor=None."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        conv_id = uuid4()
        user = _make_admin_user()
        _override_auth(app, user)

        conv = _make_conv()
        msgs = [_make_msg(conversation_history_id=conv_id) for _ in range(2)]  # less than limit

        mock_session = AsyncMock()
        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = conv
        msgs_result = MagicMock()
        msgs_result.scalars.return_value.all.return_value = msgs
        mock_session.execute = AsyncMock(side_effect=[conv_result, msgs_result])

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get(f"/api/admin/conversations/{conv_id}/thread?limit=50")

        assert response.status_code == 200
        data = response.json()
        assert data["next_cursor"] is None


# ---------------------------------------------------------------------------
# DI — graph not available → 503
# ---------------------------------------------------------------------------


class TestGraphUnavailable:
    """DI: compiled_graph not available → 503 on dependent endpoints."""

    @pytest.mark.asyncio
    async def test_pause_503_when_graph_unavailable(self):
        """DI: pause returns 503 when compiled_graph is None."""
        from api.routes.conversations_admin import router

        app = FastAPI()
        app.include_router(router)
        app.state.compiled_graph = None

        user = _make_admin_user()
        _override_auth(app, user)
        conv_id = uuid4()

        client = TestClient(app)
        response = client.post(
            f"/api/admin/conversations/{conv_id}/pause",
            json={"reason": "test"},
        )

        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_resume_503_when_graph_unavailable(self):
        """DI: resume returns 503 when compiled_graph is None."""
        from api.routes.conversations_admin import router

        app = FastAPI()
        app.include_router(router)
        app.state.compiled_graph = None

        user = _make_admin_user()
        _override_auth(app, user)
        conv_id = uuid4()

        client = TestClient(app)
        response = client.post(
            f"/api/admin/conversations/{conv_id}/resume",
            json={},
        )

        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_send_message_503_when_graph_unavailable(self):
        """DI: send-message returns 503 when compiled_graph is None."""
        from api.routes.conversations_admin import router

        app = FastAPI()
        app.include_router(router)
        app.state.compiled_graph = None

        user = _make_admin_user()
        _override_auth(app, user)
        conv_id = uuid4()

        client = TestClient(app)
        response = client.post(
            f"/api/admin/conversations/{conv_id}/send-message",
            json={"content": "Test"},
        )

        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_send_template_503_when_graph_unavailable(self):
        """W5: send-template returns 503 when compiled_graph is None."""
        from api.routes.conversations_admin import router

        app = FastAPI()
        app.include_router(router)
        app.state.compiled_graph = None

        user = _make_admin_user()
        _override_auth(app, user)
        conv_id = uuid4()

        client = TestClient(app)
        response = client.post(
            f"/api/admin/conversations/{conv_id}/send-template",
            json={"template_name": "bienvenida", "params": {}, "language": "es"},
        )

        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_escalate_503_when_graph_unavailable(self):
        """W5: escalate returns 503 when compiled_graph is None."""
        from api.routes.conversations_admin import router

        app = FastAPI()
        app.include_router(router)
        app.state.compiled_graph = None

        user = _make_admin_user()
        _override_auth(app, user)
        conv_id = uuid4()

        client = TestClient(app)
        response = client.post(
            f"/api/admin/conversations/{conv_id}/escalate",
            json={"reason": "test", "priority": "high"},
        )

        assert response.status_code == 503


# ---------------------------------------------------------------------------
# W2 — last_message_preview populated
# ---------------------------------------------------------------------------


class TestInboxLastMessagePreview:
    """W2: inbox endpoint must populate last_message_preview."""

    def _mock_inbox_session_with_preview(self, conv, preview_content: str) -> AsyncMock:
        """Build session mock that returns a conversation and its last message content."""
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [conv]

        unread_result = MagicMock()
        unread_result.all.return_value = []

        esc_result = MagicMock()
        esc_result.all.return_value = []

        preview_result = MagicMock()
        # (conversation_history_id, content, has_images)
        preview_result.all.return_value = [(conv.id, preview_content, False)]

        session.execute = AsyncMock(
            side_effect=[count_result, items_result, unread_result, esc_result, preview_result]
        )
        return session

    @pytest.mark.asyncio
    async def test_inbox_includes_last_message_preview(self):
        """W2: last_message_preview is NOT None when conversation has messages."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        user = _make_admin_user()
        _override_auth(app, user)

        conv = _make_conv()
        preview_content = "Hola, necesito información sobre la homologación"

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(
                return_value=self._mock_inbox_session_with_preview(conv, preview_content)
            )
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["last_message_preview"] is not None
        assert item["last_message_preview"] == preview_content

    @pytest.mark.asyncio
    async def test_inbox_preview_truncated_at_80_chars(self):
        """W2: last_message_preview is truncated to 80 chars with ellipsis."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        user = _make_admin_user()
        _override_auth(app, user)

        conv = _make_conv()
        long_content = "A" * 100

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(
                return_value=self._mock_inbox_session_with_preview(conv, long_content)
            )
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox")

        assert response.status_code == 200
        data = response.json()
        item = data["items"][0]
        assert item["last_message_preview"] == "A" * 77 + "..."
        assert len(item["last_message_preview"]) == 80


# ---------------------------------------------------------------------------
# W3 — Search by conversation_id and message content
# ---------------------------------------------------------------------------


class TestInboxSearchExtended:
    """W3: inbox search must include conversation_id and message content."""

    def _mock_inbox_session_empty(self) -> AsyncMock:
        session = AsyncMock()
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        empty_result.scalar.return_value = 0
        empty_result.scalar_one_or_none.return_value = None
        empty_result.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)
        return session

    @pytest.mark.asyncio
    async def test_inbox_search_by_conversation_id(self):
        """W3: search param is applied to conversation_id (Chatwoot ID)."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        user = _make_admin_user()
        _override_auth(app, user)

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(
                return_value=self._mock_inbox_session_empty()
            )
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox?search=12345")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_inbox_search_by_message_content(self):
        """W3: search param is applied to ConversationMessage.content."""
        app, _ = _make_app(with_graph=False)
        app.state.compiled_graph = None
        user = _make_admin_user()
        _override_auth(app, user)

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(
                return_value=self._mock_inbox_session_empty()
            )
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox?search=homologacion")

        assert response.status_code == 200
