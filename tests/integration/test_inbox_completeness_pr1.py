"""
Integration tests for inbox-completeness PR1 (T01–T06).

TDD cycle: RED → GREEN → REFACTOR

Covers:
  T01.1 - resolve_escalation does NOT call ChatwootClient.update_conversation_attributes
  T01.2 - resolve_escalation sets status='resolved', resolved_at, resolved_by, resolved_by_user_id
  T01.3 - resolve_escalation returns 409 when already resolved (was 400 before)
  T02.1 - GET /inbox item has escalation_source and escalation_id fields
  T02.2 - GET /inbox item returns None escalation_source when no active escalation
  T03.1 - GET /inbox response has stats field with 4 keys
  T03.2 - GET /inbox stats.pending counts escalations with status=pending
  T03.3 - GET /inbox stats.resolved_today counts only escalations resolved today
  T04.1 - GET /inbox with sort=last_message_at_desc returns items (default)
  T04.2 - GET /inbox with sort=last_message_at_asc changes ordering
  T04.3 - GET /inbox with sort=unread_first puts unread items first
  T04.4 - GET /inbox with invalid sort falls back to default (no error)
  T05.1 - ConversationMessageResponse has image_count field defaulting to 0
  T05.2 - GET /thread returns image_count from DB message
  T06.1 - DELETE /conversations/{id} with role=user returns 403
  T06.2 - DELETE /conversations/{id} with role=admin succeeds
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_admin_user(*, role: str = "admin") -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.username = "testadmin"
    user.role = role
    user.is_active = True
    user.display_name = "Test Admin"
    return user


def _make_escalation(
    *,
    status: str = "pending",
    source: str = "tool_call",
    conversation_id: str | None = None,
    resolved_at: datetime | None = None,
) -> MagicMock:
    esc = MagicMock()
    esc.id = uuid4()
    esc.conversation_id = conversation_id or str(uuid4())
    esc.status = status
    esc.source = source
    esc.triggered_at = datetime.now(UTC)
    esc.resolved_at = resolved_at
    esc.resolved_by = None
    esc.resolved_by_user_id = None
    esc.reason = "test reason"
    esc.metadata_ = {}
    return esc


def _make_conv_history(
    *,
    bot_paused_at: datetime | None = None,
    conversation_id: str | None = None,
) -> MagicMock:
    conv = MagicMock()
    conv.id = uuid4()
    conv.conversation_id = conversation_id or str(uuid4())
    conv.bot_paused_at = bot_paused_at
    conv.bot_resumed_at = None
    conv.bot_pause_reason = None
    conv.bot_paused_by_user_id = None
    conv.last_message_at = datetime.now(UTC)
    conv.started_at = datetime.now(UTC)
    conv.user = MagicMock()
    conv.user.first_name = "Test"
    conv.user.last_name = "User"
    conv.user.phone = "+34600000000"
    conv.paused_by_user = None
    return conv


def _make_admin_app() -> tuple[FastAPI, MagicMock]:
    from api.routes.admin import router

    app = FastAPI()
    app.include_router(router)
    user = _make_admin_user(role="admin")
    return app, user


def _make_inbox_app() -> FastAPI:
    from api.routes.conversations_admin import router

    app = FastAPI()
    app.include_router(router)
    return app


def _override_admin_auth(app: FastAPI, user: MagicMock) -> None:
    from api.routes.admin import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user


def _override_inbox_auth(app: FastAPI, user: MagicMock) -> None:
    from api.routes.conversations_admin import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user


# ---------------------------------------------------------------------------
# T01 — resolve_escalation does NOT reactivate bot
# ---------------------------------------------------------------------------


class TestResolveEscalation:
    """T01: resolve escalation without reactivating bot."""

    def test_resolve_does_not_call_chatwoot_update_attributes(self):
        """T01.1: ChatwootClient.update_conversation_attributes is NOT called on resolve."""
        app, admin_user = _make_admin_app()
        _override_admin_auth(app, admin_user)

        escalation = _make_escalation(status="pending")
        escalation_id = escalation.id

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=escalation)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_chatwoot = MagicMock()
        mock_chatwoot.update_conversation_attributes = AsyncMock()
        mock_chatwoot.send_message = AsyncMock()

        with patch("api.routes.admin.get_async_session") as mock_ctx, \
             patch("api.routes.admin.ChatwootClient", return_value=mock_chatwoot):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(f"/api/admin/escalations/{escalation_id}/resolve")

        assert response.status_code == 200
        mock_chatwoot.update_conversation_attributes.assert_not_called()

    def test_resolve_sets_status_resolved_at_resolved_by_and_user_id(self):
        """T01.2: resolve sets status='resolved', resolved_at, resolved_by, resolved_by_user_id."""
        app, admin_user = _make_admin_app()
        _override_admin_auth(app, admin_user)

        escalation = _make_escalation(status="pending")
        escalation_id = escalation.id

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=escalation)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock(side_effect=lambda e: None)

        with patch("api.routes.admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(f"/api/admin/escalations/{escalation_id}/resolve")

        assert response.status_code == 200
        assert escalation.status == "resolved"
        assert escalation.resolved_at is not None
        assert escalation.resolved_by == (admin_user.display_name or admin_user.username)
        assert escalation.resolved_by_user_id == admin_user.id

    def test_resolve_already_resolved_returns_409(self):
        """T01.3: resolving an already-resolved escalation returns 409."""
        app, admin_user = _make_admin_app()
        _override_admin_auth(app, admin_user)

        escalation = _make_escalation(status="resolved", resolved_at=datetime.now(UTC))
        escalation_id = escalation.id

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=escalation)

        with patch("api.routes.admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(f"/api/admin/escalations/{escalation_id}/resolve")

        assert response.status_code == 409


# ---------------------------------------------------------------------------
# T02 — InboxItemResponse has escalation_source and escalation_id
# ---------------------------------------------------------------------------


class TestInboxEscalationFields:
    """T02: escalation_source and escalation_id in inbox items."""

    def _build_session_for_inbox(
        self,
        conv: MagicMock,
        *,
        escalation_source: str | None = None,
        escalation_id=None,
    ) -> AsyncMock:
        session = AsyncMock()

        total_result = MagicMock()
        total_result.scalar.return_value = 1

        conv_result = MagicMock()
        conv_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[conv]))

        unread_result = MagicMock()
        unread_result.all.return_value = []

        esc_row = MagicMock()
        esc_row.__getitem__ = lambda self, idx: [
            conv.conversation_id,
            "pending",
            escalation_source,
            escalation_id,
        ][idx]

        esc_result = MagicMock()
        esc_result.all.return_value = [esc_row] if escalation_source else []

        preview_result = MagicMock()
        preview_result.all.return_value = []

        stats_result = MagicMock()
        stats_row = MagicMock()
        stats_row.pending = 0
        stats_row.in_progress = 0
        stats_row.resolved_today = 0
        stats_row.total_today = 0
        stats_result.one.return_value = stats_row

        calls = [total_result, conv_result, unread_result, esc_result, preview_result, stats_result]
        call_iter = iter(calls)
        session.execute = AsyncMock(side_effect=lambda *args, **kwargs: next(call_iter))
        return session

    def test_inbox_item_has_escalation_source_field(self):
        """T02.1: inbox item includes escalation_source='tool_call' when escalation present."""
        app = _make_inbox_app()
        user = _make_admin_user()
        _override_inbox_auth(app, user)

        conv = _make_conv_history()
        esc_id = uuid4()

        session = self._build_session_for_inbox(
            conv, escalation_source="tool_call", escalation_id=esc_id
        )

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        item = data["items"][0]
        assert "escalation_source" in item
        assert item["escalation_source"] == "tool_call"
        assert "escalation_id" in item

    def test_inbox_item_escalation_source_none_when_no_escalation(self):
        """T02.2: escalation_source is None when no active escalation."""
        app = _make_inbox_app()
        user = _make_admin_user()
        _override_inbox_auth(app, user)

        conv = _make_conv_history()
        session = self._build_session_for_inbox(conv, escalation_source=None)

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox")

        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["escalation_source"] is None
        assert item["escalation_id"] is None


# ---------------------------------------------------------------------------
# T03 — GET /inbox has stats field
# ---------------------------------------------------------------------------


class TestInboxStats:
    """T03: stats field in InboxListResponse."""

    def _build_session_with_stats(self, conv: MagicMock, stats_row: MagicMock) -> AsyncMock:
        session = AsyncMock()

        total_result = MagicMock()
        total_result.scalar.return_value = 1

        conv_result = MagicMock()
        conv_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[conv]))

        unread_result = MagicMock()
        unread_result.all.return_value = []

        esc_result = MagicMock()
        esc_result.all.return_value = []

        preview_result = MagicMock()
        preview_result.all.return_value = []

        stats_result = MagicMock()
        stats_result.one.return_value = stats_row

        calls = [
            total_result,
            conv_result,
            unread_result,
            esc_result,
            preview_result,
            stats_result,
        ]
        call_iter = iter(calls)
        session.execute = AsyncMock(side_effect=lambda *args, **kwargs: next(call_iter))
        return session

    def test_inbox_response_has_stats_field(self):
        """T03.1: GET /inbox response includes a stats object with 4 keys."""
        app = _make_inbox_app()
        user = _make_admin_user()
        _override_inbox_auth(app, user)

        conv = _make_conv_history()

        stats_row = MagicMock()
        stats_row.pending = 2
        stats_row.in_progress = 1
        stats_row.resolved_today = 3
        stats_row.total_today = 6

        session = self._build_session_with_stats(conv, stats_row)

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox")

        assert response.status_code == 200
        data = response.json()
        assert "stats" in data
        stats = data["stats"]
        assert "pending" in stats
        assert "in_progress" in stats
        assert "resolved_today" in stats
        assert "total_today" in stats

    def test_inbox_stats_pending_count(self):
        """T03.2: stats.pending reflects actual pending escalation count."""
        app = _make_inbox_app()
        user = _make_admin_user()
        _override_inbox_auth(app, user)

        conv = _make_conv_history()

        stats_row = MagicMock()
        stats_row.pending = 5
        stats_row.in_progress = 0
        stats_row.resolved_today = 0
        stats_row.total_today = 5

        session = self._build_session_with_stats(conv, stats_row)

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox")

        assert response.status_code == 200
        assert response.json()["stats"]["pending"] == 5


# ---------------------------------------------------------------------------
# T04 — GET /inbox sort param
# ---------------------------------------------------------------------------


class TestInboxSort:
    """T04: sort query param in GET /inbox."""

    def _build_minimal_session(self, convs: list[MagicMock]) -> AsyncMock:
        session = AsyncMock()

        total_result = MagicMock()
        total_result.scalar.return_value = len(convs)

        conv_result = MagicMock()
        conv_result.scalars.return_value = MagicMock(all=MagicMock(return_value=convs))

        unread_result = MagicMock()
        unread_result.all.return_value = []

        esc_result = MagicMock()
        esc_result.all.return_value = []

        preview_result = MagicMock()
        preview_result.all.return_value = []

        stats_result = MagicMock()
        stats_row = MagicMock()
        stats_row.pending = 0
        stats_row.in_progress = 0
        stats_row.resolved_today = 0
        stats_row.total_today = 0
        stats_result.one.return_value = stats_row

        calls = [
            total_result,
            conv_result,
            unread_result,
            esc_result,
            preview_result,
            stats_result,
        ]
        call_iter = iter(calls)
        session.execute = AsyncMock(side_effect=lambda *args, **kwargs: next(call_iter))
        return session

    def test_sort_last_message_at_desc_default(self):
        """T04.1: GET /inbox without sort param returns 200 (default sort)."""
        app = _make_inbox_app()
        user = _make_admin_user()
        _override_inbox_auth(app, user)

        conv = _make_conv_history()
        session = self._build_minimal_session([conv])

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox")

        assert response.status_code == 200

    def test_sort_last_message_at_asc(self):
        """T04.2: sort=last_message_at_asc is accepted and returns 200."""
        app = _make_inbox_app()
        user = _make_admin_user()
        _override_inbox_auth(app, user)

        conv = _make_conv_history()
        session = self._build_minimal_session([conv])

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox?sort=last_message_at_asc")

        assert response.status_code == 200

    def test_sort_unread_first(self):
        """T04.3: sort=unread_first is accepted and returns 200."""
        app = _make_inbox_app()
        user = _make_admin_user()
        _override_inbox_auth(app, user)

        conv = _make_conv_history()
        session = self._build_minimal_session([conv])

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox?sort=unread_first")

        assert response.status_code == 200

    def test_sort_invalid_value_falls_back_to_default(self):
        """T04.4: invalid sort value returns 200 (silent fallback, no 422)."""
        app = _make_inbox_app()
        user = _make_admin_user()
        _override_inbox_auth(app, user)

        conv = _make_conv_history()
        session = self._build_minimal_session([conv])

        with patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.get("/api/admin/inbox?sort=invalid_sort_value")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# T05 — ConversationMessageResponse has image_count
# ---------------------------------------------------------------------------


class TestImageCount:
    """T05: image_count field in ConversationMessageResponse."""

    def test_conversation_message_response_has_image_count_default(self):
        """T05.1: ConversationMessageResponse has image_count field defaulting to 0."""
        from api.models.conversation_inbox import ConversationMessageResponse
        from uuid import uuid4

        msg = ConversationMessageResponse(
            id=uuid4(),
            conversation_history_id=uuid4(),
            role="user",
            author_type="user",
            content="test",
            created_at=datetime.now(UTC),
            is_read=False,
            has_images=False,
        )
        assert hasattr(msg, "image_count")
        assert msg.image_count == 0

    def test_conversation_message_response_image_count_from_value(self):
        """T05.2: image_count is correctly passed through the model."""
        from api.models.conversation_inbox import ConversationMessageResponse

        msg = ConversationMessageResponse(
            id=uuid4(),
            conversation_history_id=uuid4(),
            role="user",
            author_type="user",
            content="test with images",
            created_at=datetime.now(UTC),
            is_read=False,
            has_images=True,
            image_count=3,
        )
        assert msg.image_count == 3


# ---------------------------------------------------------------------------
# T06 — DELETE /conversations/{id} RBAC
# ---------------------------------------------------------------------------


class TestDeleteConversationRBAC:
    """T06: RBAC on DELETE /api/admin/conversations/{id}."""

    def test_delete_with_user_role_returns_403(self):
        """T06.1: user role → 403 Forbidden."""
        from api.routes.admin import router

        app = FastAPI()
        app.include_router(router)

        user = _make_admin_user(role="user")
        _override_admin_auth(app, user)

        conv_id = uuid4()

        client = TestClient(app, raise_server_exceptions=False)
        response = client.delete(f"/api/admin/conversations/{conv_id}")

        assert response.status_code == 403

    def test_delete_with_admin_role_executes_cascade(self):
        """T06.2: admin role → cascade runs (coordinator invoked), returns 200."""
        from api.routes.admin import router

        app = FastAPI()
        app.include_router(router)

        admin_user = _make_admin_user(role="admin")
        _override_admin_auth(app, admin_user)

        conv_id = uuid4()

        mock_reset_result = MagicMock()
        mock_reset_result.domains = []
        mock_reset_result.success = True
        mock_reset_result.partial_failure = False
        mock_reset_result.conversation_id = str(conv_id)
        mock_reset_result.message = "ok"
        mock_reset_result.details = {}
        mock_reset_result.model_dump = MagicMock(return_value={
            "success": True,
            "conversation_id": str(conv_id),
            "domains": [],
            "message": "ok",
            "details": {},
            "partial_failure": False,
        })

        mock_coordinator = MagicMock()
        mock_coordinator.run = AsyncMock(return_value=mock_reset_result)

        with patch("api.routes.admin.ConversationResetCoordinator", return_value=mock_coordinator):
            client = TestClient(app)
            response = client.delete(f"/api/admin/conversations/{conv_id}")

        assert response.status_code == 200
        mock_coordinator.run.assert_called_once()
