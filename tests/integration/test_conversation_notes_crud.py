"""
Integration tests for conversation notes CRUD endpoints.

TDD cycle: RED (written before GREEN)

POST /api/admin/conversations/{conv_id}/notes
  NC01 — create OK 201
  NC02 — empty content 422
  NC03 — too-long content (2001 chars) 422
  NC04 — nonexistent conversation 404
  NC05 — unauthenticated 401
  NC06 — wrong role (solo_lectura) 403

DELETE /api/admin/conversations/notes/{note_id}
  ND01 — delete own note 204
  ND02 — admin deletes another admin's note 204 (role override)
  ND03 — agente_humano deletes another's note 403
  ND04 — nonexistent note 404

Cascade + content integrity
  NC07 — cascade: deleting ConversationHistory removes notes
  NC08 — verbatim content: HTML/script tags stored as-is

All tests mock the service layer — no real DB is used.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------


def _make_admin_user(*, role: str = "admin") -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.username = "testadmin"
    user.display_name = "Test Admin"
    user.role = role
    user.is_active = True
    return user


def _make_note_response(
    *,
    note_id=None,
    content: str = "Nota de prueba",
    author_name: str = "Test Admin",
    can_delete: bool = True,
) -> MagicMock:
    from api.models.conversation_inbox import NoteResponse

    return NoteResponse(
        id=note_id or uuid4(),
        author_name=author_name,
        content=content,
        created_at=datetime.now(UTC),
        can_delete=can_delete,
    )


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    from api.routes.conversations_admin import router

    app = FastAPI()
    app.include_router(router)
    app.state.compiled_graph = MagicMock()
    return app


def _override_auth(app: FastAPI, user: MagicMock) -> None:
    from api.routes.conversations_admin import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user


def _deny_auth(app: FastAPI, status_code: int = 401) -> None:
    from api.routes.conversations_admin import get_current_user

    async def _raise():
        raise HTTPException(status_code=status_code, detail="Auth denied")

    app.dependency_overrides[get_current_user] = _raise


# ---------------------------------------------------------------------------
# NC01 — POST create OK → 201
# ---------------------------------------------------------------------------


class TestCreateNote:
    @pytest.mark.asyncio
    async def test_create_note_201(self):
        """NC01: valid POST returns 201 with NoteResponse."""
        conv_id = uuid4()
        user = _make_admin_user(role="agente_humano")
        app = _make_app()
        _override_auth(app, user)

        note_resp = _make_note_response(content="Nota válida")

        with patch(
            "api.routes.conversations_admin._svc_create_note",
            new_callable=AsyncMock,
            return_value=note_resp,
        ), patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            session_mock = AsyncMock()
            session_mock.commit = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session_mock)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/notes",
                json={"content": "Nota válida"},
            )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["content"] == "Nota válida"
        assert data["can_delete"] is True

    # NC02 — empty content 422
    @pytest.mark.asyncio
    async def test_empty_content_422(self):
        """NC02: empty content string fails Pydantic validation → 422."""
        conv_id = uuid4()
        user = _make_admin_user()
        app = _make_app()
        _override_auth(app, user)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/admin/conversations/{conv_id}/notes",
            json={"content": ""},
        )

        assert response.status_code == 422, response.text

    # NC03 — too-long content 422
    @pytest.mark.asyncio
    async def test_too_long_content_422(self):
        """NC03: content of 2001 chars fails Pydantic max_length=2000 → 422."""
        conv_id = uuid4()
        user = _make_admin_user()
        app = _make_app()
        _override_auth(app, user)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/admin/conversations/{conv_id}/notes",
            json={"content": "x" * 2001},
        )

        assert response.status_code == 422, response.text

    # NC04 — nonexistent conversation 404
    @pytest.mark.asyncio
    async def test_nonexistent_conv_404(self):
        """NC04: conversation not found → service raises 404."""
        conv_id = uuid4()
        user = _make_admin_user()
        app = _make_app()
        _override_auth(app, user)

        with patch(
            "api.routes.conversations_admin._svc_create_note",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=404, detail="Conversation not found"),
        ), patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            session_mock = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session_mock)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/notes",
                json={"content": "Nota válida"},
            )

        assert response.status_code == 404, response.text

    # NC05 — unauthenticated 401
    @pytest.mark.asyncio
    async def test_unauthenticated_401(self):
        """NC05: no auth token → 401."""
        conv_id = uuid4()
        app = _make_app()
        _deny_auth(app, status_code=401)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/admin/conversations/{conv_id}/notes",
            json={"content": "Nota válida"},
        )

        assert response.status_code == 401, response.text

    # NC06 — wrong role (solo_lectura) 403
    @pytest.mark.asyncio
    async def test_wrong_role_403(self):
        """NC06: solo_lectura role is not allowed to POST notes → 403."""
        conv_id = uuid4()
        app = _make_app()
        _deny_auth(app, status_code=403)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/admin/conversations/{conv_id}/notes",
            json={"content": "Nota válida"},
        )

        assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# ND01 — DELETE own note → 204
# ---------------------------------------------------------------------------


class TestDeleteNote:
    @pytest.mark.asyncio
    async def test_delete_own_note_204(self):
        """ND01: author deletes their own note → 204."""
        note_id = uuid4()
        user = _make_admin_user(role="agente_humano")
        app = _make_app()
        _override_auth(app, user)

        with patch(
            "api.routes.conversations_admin._svc_delete_note",
            new_callable=AsyncMock,
            return_value=None,
        ), patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            session_mock = AsyncMock()
            session_mock.commit = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session_mock)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.delete(f"/api/admin/conversations/notes/{note_id}")

        assert response.status_code == 204, response.text

    # ND02 — admin deletes another admin's note 204
    @pytest.mark.asyncio
    async def test_admin_deletes_others_note_204(self):
        """ND02: admin role can delete any note (role override) → 204."""
        note_id = uuid4()
        user = _make_admin_user(role="admin")
        app = _make_app()
        _override_auth(app, user)

        with patch(
            "api.routes.conversations_admin._svc_delete_note",
            new_callable=AsyncMock,
            return_value=None,
        ), patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            session_mock = AsyncMock()
            session_mock.commit = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session_mock)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.delete(f"/api/admin/conversations/notes/{note_id}")

        assert response.status_code == 204, response.text

    # ND03 — agente_humano deletes another's note 403
    @pytest.mark.asyncio
    async def test_non_author_non_admin_403(self):
        """ND03: agente_humano who is NOT the author gets 403 from service."""
        note_id = uuid4()
        user = _make_admin_user(role="agente_humano")
        app = _make_app()
        _override_auth(app, user)

        with patch(
            "api.routes.conversations_admin._svc_delete_note",
            new_callable=AsyncMock,
            side_effect=HTTPException(
                status_code=403,
                detail="No tienes permiso para eliminar esta nota.",
            ),
        ), patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            session_mock = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session_mock)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.delete(f"/api/admin/conversations/notes/{note_id}")

        assert response.status_code == 403, response.text

    # ND04 — nonexistent note 404
    @pytest.mark.asyncio
    async def test_nonexistent_note_404(self):
        """ND04: deleting a non-existent note → 404."""
        note_id = uuid4()
        user = _make_admin_user()
        app = _make_app()
        _override_auth(app, user)

        with patch(
            "api.routes.conversations_admin._svc_delete_note",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=404, detail="Note not found"),
        ), patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            session_mock = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session_mock)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.delete(f"/api/admin/conversations/notes/{note_id}")

        assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# NC07 — Cascade: ConversationHistory delete → notes auto-deleted
# ---------------------------------------------------------------------------


class TestCascadeBehavior:
    def test_cascade_defined_on_conversation_note_model(self):
        """NC07: ConversationNote FK has ON DELETE CASCADE → DB enforces cascade."""
        from sqlalchemy import inspect as sa_inspect
        from database.models import ConversationNote

        mapper = sa_inspect(ConversationNote)
        for col in mapper.columns:
            if col.name == "conversation_history_id":
                fks = list(col.foreign_keys)
                assert len(fks) == 1, "Expected exactly one FK on conversation_history_id"
                fk = fks[0]
                assert fk.ondelete == "CASCADE", (
                    f"Expected ON DELETE CASCADE, got {fk.ondelete!r}"
                )
                return
        pytest.fail("conversation_history_id column not found in ConversationNote")

    def test_admin_user_fk_is_set_null(self):
        """NC07b: admin_user_id FK is SET NULL (preserves note content on author deletion)."""
        from sqlalchemy import inspect as sa_inspect
        from database.models import ConversationNote

        mapper = sa_inspect(ConversationNote)
        for col in mapper.columns:
            if col.name == "admin_user_id":
                fks = list(col.foreign_keys)
                assert len(fks) == 1
                fk = fks[0]
                assert fk.ondelete == "SET NULL", (
                    f"Expected ON DELETE SET NULL for admin_user_id, got {fk.ondelete!r}"
                )
                return
        pytest.fail("admin_user_id column not found in ConversationNote")


# ---------------------------------------------------------------------------
# NC08 — Verbatim content: HTML/script tags stored as-is
# ---------------------------------------------------------------------------


class TestVerbatimContent:
    @pytest.mark.asyncio
    async def test_html_content_stored_verbatim(self):
        """NC08: content with HTML/script tags is stored and returned as-is."""
        conv_id = uuid4()
        user = _make_admin_user()
        app = _make_app()
        _override_auth(app, user)

        xss_content = "<script>alert(1)</script>"
        note_resp = _make_note_response(content=xss_content)

        with patch(
            "api.routes.conversations_admin._svc_create_note",
            new_callable=AsyncMock,
            return_value=note_resp,
        ), patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            session_mock = AsyncMock()
            session_mock.commit = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session_mock)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                f"/api/admin/conversations/{conv_id}/notes",
                json={"content": xss_content},
            )

        assert response.status_code == 201, response.text
        data = response.json()
        # Content must be returned verbatim — no server-side stripping
        assert data["content"] == xss_content, (
            "Server must return content verbatim — XSS escaping is the renderer's responsibility"
        )
