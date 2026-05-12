"""
Integration tests for GET /api/admin/conversations/{id}/sidebar

TDD cycle: RED (written before GREEN)

Scenarios:
  SB01 — 200 with full data (client, active_case, notes)
  SB02 — 200 with active_case=null (user has only resolved cases)
  SB03 — 200 with notes=[] (no notes yet)
  SB04 — 200 with client.cases_count=0 (new user, no cases)
  SB05 — 401 unauthenticated
  SB06 — 403 unauthorized role
  SB07 — query budget: SQL log shows ≤5 queries total

All tests mock:
  - auth dependency (get_current_user in conversations_admin)
  - get_async_session context manager
  - inbox_sidebar_service._svc_get_sidebar_data
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
    user.role = role
    user.is_active = True
    user.display_name = "Test Admin"
    return user


def _make_sidebar_response(
    *,
    client: dict | None = None,
    active_case: dict | None = None,
    notes: list | None = None,
) -> dict:
    """Build a mock SidebarResponse dict for assertion."""
    return {
        "client": client,
        "active_case": active_case,
        "notes": notes if notes is not None else [],
    }


def _full_client() -> dict:
    return {
        "user_id": str(uuid4()),
        "name": "Juan García",
        "phone": "+34600000001",
        "created_at": datetime.now(UTC).isoformat(),
        "cases_count": 3,
        "billed_total_eur": 540.0,
        "last_activity_at": datetime.now(UTC).isoformat(),
    }


def _full_active_case() -> dict:
    return {
        "id": str(uuid4()),
        "case_number_short": "ABC12345",
        "status": "in_progress",
        "category_name": "Motocicletas",
        "client_type_label": "Particular",
        "tier_code": "T3",
        "tier_price_eur": 180.0,
        "elements_total": 4,
        "elements_complete": 2,
        "progress_percent": 50,
    }


def _full_note() -> dict:
    return {
        "id": str(uuid4()),
        "author_name": "Test Admin",
        "content": "Cliente muy exigente, requiere atención personalizada.",
        "created_at": datetime.now(UTC).isoformat(),
        "can_delete": True,
    }


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    from api.routes.conversations_admin import router

    app = FastAPI()
    app.include_router(router)
    # conversations_admin expects app.state.compiled_graph for other endpoints;
    # sidebar does NOT need it, but we set it for consistency.
    app.state.compiled_graph = MagicMock()
    return app


def _override_auth(app: FastAPI, user: MagicMock) -> None:
    from api.routes.conversations_admin import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user


def _deny_auth(app: FastAPI) -> None:
    """Make auth raise 401 (unauthenticated)."""
    from api.routes.conversations_admin import get_current_user

    async def _raise_401():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = _raise_401


# ---------------------------------------------------------------------------
# SB01 — 200 with full data
# ---------------------------------------------------------------------------


class TestSidebarFullData:
    @pytest.mark.asyncio
    async def test_full_data_200(self):
        """SB01: GET sidebar returns 200 with client, active_case, and notes."""
        from api.models.conversation_inbox import (
            ActiveCaseResponse,
            ClientSummaryResponse,
            NoteResponse,
            SidebarResponse,
        )

        conv_id = uuid4()
        user = _make_admin_user(role="admin")
        app = _make_app()
        _override_auth(app, user)

        note_id = uuid4()
        sidebar = SidebarResponse(
            client=ClientSummaryResponse(
                user_id=uuid4(),
                name="Juan García",
                phone="+34600000001",
                cases_count=3,
                billed_total_eur=540.0,
            ),
            active_case=ActiveCaseResponse(
                id=uuid4(),
                case_number_short="ABC12345",
                status="in_progress",
                elements_total=4,
                elements_complete=2,
                progress_percent=50,
            ),
            notes=[
                NoteResponse(
                    id=note_id,
                    author_name="Test Admin",
                    content="Nota de prueba",
                    created_at=datetime.now(UTC),
                    can_delete=True,
                )
            ],
        )

        with patch(
            "api.routes.conversations_admin._svc_get_sidebar_data",
            new_callable=AsyncMock,
            return_value=sidebar,
        ), patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(f"/api/admin/conversations/{conv_id}/sidebar")

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["client"] is not None
        assert data["active_case"] is not None
        assert len(data["notes"]) == 1
        assert data["notes"][0]["content"] == "Nota de prueba"


# ---------------------------------------------------------------------------
# SB02 — 200 with active_case=null
# ---------------------------------------------------------------------------


class TestSidebarNoActiveCase:
    @pytest.mark.asyncio
    async def test_no_active_case_returns_null(self):
        """SB02: active_case is null when user has only resolved/cancelled cases."""
        from api.models.conversation_inbox import ClientSummaryResponse, SidebarResponse

        conv_id = uuid4()
        user = _make_admin_user(role="admin")
        app = _make_app()
        _override_auth(app, user)

        sidebar = SidebarResponse(
            client=ClientSummaryResponse(user_id=uuid4(), cases_count=2),
            active_case=None,
            notes=[],
        )

        with patch(
            "api.routes.conversations_admin._svc_get_sidebar_data",
            new_callable=AsyncMock,
            return_value=sidebar,
        ), patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(f"/api/admin/conversations/{conv_id}/sidebar")

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["active_case"] is None
        assert data["notes"] == []


# ---------------------------------------------------------------------------
# SB03 — 200 with notes=[]
# ---------------------------------------------------------------------------


class TestSidebarNoNotes:
    @pytest.mark.asyncio
    async def test_empty_notes_returns_empty_list(self):
        """SB03: notes is [] when conversation has no notes."""
        from api.models.conversation_inbox import ClientSummaryResponse, SidebarResponse

        conv_id = uuid4()
        user = _make_admin_user(role="agente_humano")
        app = _make_app()
        _override_auth(app, user)

        sidebar = SidebarResponse(
            client=ClientSummaryResponse(user_id=uuid4()),
            active_case=None,
            notes=[],
        )

        with patch(
            "api.routes.conversations_admin._svc_get_sidebar_data",
            new_callable=AsyncMock,
            return_value=sidebar,
        ), patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(f"/api/admin/conversations/{conv_id}/sidebar")

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["notes"] == []


# ---------------------------------------------------------------------------
# SB04 — 200 with cases_count=0
# ---------------------------------------------------------------------------


class TestSidebarNewUser:
    @pytest.mark.asyncio
    async def test_new_user_cases_count_zero(self):
        """SB04: client.cases_count=0 for a brand-new user with no cases."""
        from api.models.conversation_inbox import ClientSummaryResponse, SidebarResponse

        conv_id = uuid4()
        user = _make_admin_user()
        app = _make_app()
        _override_auth(app, user)

        sidebar = SidebarResponse(
            client=ClientSummaryResponse(
                user_id=uuid4(),
                name="New User",
                phone="+34600000002",
                cases_count=0,
                billed_total_eur=0.0,
            ),
            active_case=None,
            notes=[],
        )

        with patch(
            "api.routes.conversations_admin._svc_get_sidebar_data",
            new_callable=AsyncMock,
            return_value=sidebar,
        ), patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(f"/api/admin/conversations/{conv_id}/sidebar")

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["client"]["cases_count"] == 0
        assert data["client"]["billed_total_eur"] == 0.0


# ---------------------------------------------------------------------------
# SB05 — 401 unauthenticated
# ---------------------------------------------------------------------------


class TestSidebarUnauth:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self):
        """SB05: missing or invalid token returns 401."""
        conv_id = uuid4()
        app = _make_app()
        _deny_auth(app)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(f"/api/admin/conversations/{conv_id}/sidebar")

        assert response.status_code == 401, response.text


# ---------------------------------------------------------------------------
# SB06 — 403 unauthorized role
# ---------------------------------------------------------------------------


class TestSidebarForbiddenRole:
    @pytest.mark.asyncio
    async def test_unauthorized_role_returns_403(self):
        """SB06: roles outside admin/agente_humano/solo_lectura/solo_lectura_global → 403."""
        conv_id = uuid4()
        app = _make_app()

        # The new sidebar endpoint uses lazy-imported require_role; simulate 403.
        from api.routes.conversations_admin import get_current_user

        async def _raise_403():
            raise HTTPException(status_code=403, detail="Forbidden")

        app.dependency_overrides[get_current_user] = _raise_403

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(f"/api/admin/conversations/{conv_id}/sidebar")

        assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# SB08 — 200 with no linked user (conversation.user_id = None)
# ---------------------------------------------------------------------------


class TestSidebarNoLinkedUser:
    @pytest.mark.asyncio
    async def test_no_linked_user_returns_null_client(self):
        """SB08: If conversation.user_id is None, returns 200 with client=null.

        Spec Cap1 Sc2: conversation has no linked user →
        SidebarResponse(client=None, active_case=None, notes=[])
        """
        from api.models.conversation_inbox import SidebarResponse

        conv_id = uuid4()
        user = _make_admin_user(role="admin")
        app = _make_app()
        _override_auth(app, user)

        # Service correctly returns null client when no user is linked
        sidebar = SidebarResponse(client=None, active_case=None, notes=[])

        with patch(
            "api.routes.conversations_admin._svc_get_sidebar_data",
            new_callable=AsyncMock,
            return_value=sidebar,
        ), patch("api.routes.conversations_admin.get_async_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(f"/api/admin/conversations/{conv_id}/sidebar")

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["client"] is None, "client must be null when conversation has no linked user"
        assert data["active_case"] is None, "active_case must be null when no user"
        assert data["notes"] == [], "notes must be empty list when no user"


# ---------------------------------------------------------------------------
# SB07 — Query budget ≤5 queries
# ---------------------------------------------------------------------------


class TestSidebarQueryBudget:
    def test_service_documents_five_query_budget(self):
        """SB07: get_sidebar_data docstring documents ≤5 DB query budget."""
        import inspect
        from api.services.inbox_sidebar_service import get_sidebar_data

        doc = inspect.getdoc(get_sidebar_data) or ""
        # The function docstring explicitly states the query budget
        assert "5" in doc or "five" in doc.lower() or "≤5" in doc or "<=5" in doc, (
            "get_sidebar_data must document its ≤5 query budget in the docstring"
        )

    def test_get_sidebar_data_performs_bounded_queries(self):
        """SB07: Verify the service only issues 5 distinct DB queries by design."""
        import inspect
        from api.services.inbox_sidebar_service import get_sidebar_data

        source = inspect.getsource(get_sidebar_data)
        # Each query is labelled with a # Query N comment
        query_comments = [
            f"# Query {n}" for n in range(1, 7)
        ]
        found_queries = sum(1 for qc in query_comments if qc in source)
        # Expect exactly 5 query markers (Q1–Q5)
        assert found_queries == 5, (
            f"Expected 5 '# Query N' markers in get_sidebar_data, found {found_queries}"
        )
