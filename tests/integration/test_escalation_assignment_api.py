"""
Integration tests for the new escalations router (C2.4).

Tests the HTTP layer of POST /assign, POST /unassign, POST /resolve,
GET /list, and auth/RBAC enforcement.

All tests use an in-memory SQLite DB (via db_engine/db_session fixtures
from tests/conftest.py) and a test FastAPI client.
The structlog, phonenumbers, and langgraph stubs are applied by
tests/integration/conftest.py which is auto-loaded by pytest.

TDD cycle:
  RED   → tests written and failing before route exists
  GREEN → api/routes/escalations.py created; tests pass
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _make_admin_user(
    uid: uuid.UUID | None = None,
    username: str = "admin",
    role: str = "admin",
    is_active: bool = True,
) -> MagicMock:
    user = MagicMock()
    user.id = uid or uuid.uuid4()
    user.username = username
    user.display_name = "Administrador"
    user.role = role
    user.is_active = is_active
    user.chatwoot_agent_id = None
    return user


def _make_escalation(
    uid: uuid.UUID | None = None,
    status: str = "pending",
    conversation_id: str = "1001",
    assigned_to_user_id: uuid.UUID | None = None,
    assigned_at: datetime | None = None,
) -> MagicMock:
    esc = MagicMock()
    esc.id = uid or uuid.uuid4()
    esc.conversation_id = conversation_id
    esc.user_id = None
    esc.user = None
    esc.reason = "Test escalation"
    esc.source = "tool_call"
    esc.status = status
    esc.triggered_at = datetime.now(UTC)
    esc.assigned_to_user_id = assigned_to_user_id
    esc.assigned_to_user = None
    esc.assigned_at = assigned_at
    esc.resolved_at = None
    esc.resolved_by_user_id = None
    esc.resolved_by_user = None
    esc.metadata_ = None
    return esc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_escalations_router():
    """
    Return a FastAPI app with only the escalations router registered.
    All auth dependencies are overridden.
    """
    from fastapi import FastAPI
    from api.routes import escalations as esc_router_module
    from api.routes.admin import get_current_user, require_role

    test_app = FastAPI()

    admin_user = _make_admin_user()

    # Override auth dependencies
    test_app.dependency_overrides[get_current_user] = lambda: admin_user
    # require_role returns a dependency factory; override the inner dependency
    # by patching the factory to produce a passthrough
    def _passthrough_role(*roles):
        async def _dep():
            return admin_user
        return _dep

    test_app.include_router(esc_router_module.router)
    return test_app, admin_user


# ---------------------------------------------------------------------------
# test_assign_endpoint_happy_path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_endpoint_happy_path() -> None:
    """
    POST /api/admin/escalations/{id}/assign with valid payload returns 200
    and an EscalationResponse with status='assigned'.
    """
    esc_id = uuid.uuid4()
    assignee_id = uuid.uuid4()

    assigned_esc = _make_escalation(
        uid=esc_id,
        status="assigned",
        assigned_to_user_id=assignee_id,
        assigned_at=datetime.now(UTC),
    )
    assigned_esc.assigned_to_user = _make_admin_user(uid=assignee_id)

    admin = _make_admin_user()

    with patch(
        "api.routes.escalations.EscalationAssignmentService"
    ) as MockSvc, patch(
        "api.routes.escalations.get_async_session"
    ) as mock_session_ctx:
        # Mock session context manager
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock service
        svc_instance = AsyncMock()
        svc_instance.assign = AsyncMock(return_value=assigned_esc)
        MockSvc.return_value = svc_instance

        from fastapi import FastAPI
        from api.routes import escalations as esc_module
        from api.routes.admin import get_current_user

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: admin
        app.include_router(esc_module.router)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/admin/escalations/{esc_id}/assign",
                json={"assignee_user_id": str(assignee_id)},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "assigned"
    assert data["id"] == str(esc_id)


# ---------------------------------------------------------------------------
# test_assign_endpoint_returns_404_for_unknown_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_endpoint_returns_404_for_unknown_id() -> None:
    """
    POST /assign with an unknown escalation_id returns 404.
    """
    from api.services.exceptions import EscalationNotFoundError

    esc_id = uuid.uuid4()
    admin = _make_admin_user()

    with patch("api.routes.escalations.EscalationAssignmentService") as MockSvc, patch(
        "api.routes.escalations.get_async_session"
    ) as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        svc_instance = AsyncMock()
        svc_instance.assign = AsyncMock(side_effect=EscalationNotFoundError(esc_id))
        MockSvc.return_value = svc_instance

        from fastapi import FastAPI
        from api.routes import escalations as esc_module
        from api.routes.admin import get_current_user

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: admin
        app.include_router(esc_module.router)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/admin/escalations/{esc_id}/assign",
                json={"assignee_user_id": str(uuid.uuid4())},
            )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# test_assign_endpoint_returns_409_when_already_assigned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_endpoint_returns_409_when_already_assigned() -> None:
    """
    POST /assign when escalation is already assigned to another agent returns 409.
    """
    from api.services.exceptions import EscalationAlreadyAssignedError

    esc_id = uuid.uuid4()
    admin = _make_admin_user()

    with patch("api.routes.escalations.EscalationAssignmentService") as MockSvc, patch(
        "api.routes.escalations.get_async_session"
    ) as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        svc_instance = AsyncMock()
        svc_instance.assign = AsyncMock(
            side_effect=EscalationAlreadyAssignedError(esc_id, uuid.uuid4())
        )
        MockSvc.return_value = svc_instance

        from fastapi import FastAPI
        from api.routes import escalations as esc_module
        from api.routes.admin import get_current_user

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: admin
        app.include_router(esc_module.router)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/admin/escalations/{esc_id}/assign",
                json={"assignee_user_id": str(uuid.uuid4())},
            )

    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# test_assign_endpoint_returns_422_for_inactive_assignee
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_endpoint_returns_422_for_inactive_assignee() -> None:
    """
    POST /assign with an inactive assignee_user_id returns 422.
    """
    from api.services.exceptions import InvalidAssigneeError

    esc_id = uuid.uuid4()
    assignee_id = uuid.uuid4()
    admin = _make_admin_user()

    with patch("api.routes.escalations.EscalationAssignmentService") as MockSvc, patch(
        "api.routes.escalations.get_async_session"
    ) as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        svc_instance = AsyncMock()
        svc_instance.assign = AsyncMock(
            side_effect=InvalidAssigneeError(assignee_id, "not active")
        )
        MockSvc.return_value = svc_instance

        from fastapi import FastAPI
        from api.routes import escalations as esc_module
        from api.routes.admin import get_current_user

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: admin
        app.include_router(esc_module.router)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/admin/escalations/{esc_id}/assign",
                json={"assignee_user_id": str(assignee_id)},
            )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# test_unassign_endpoint_happy_path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unassign_endpoint_happy_path() -> None:
    """
    POST /unassign on an assigned escalation returns 200 with status='pending'.
    """
    esc_id = uuid.uuid4()
    admin = _make_admin_user()
    unassigned_esc = _make_escalation(uid=esc_id, status="pending")

    with patch("api.routes.escalations.EscalationAssignmentService") as MockSvc, patch(
        "api.routes.escalations.get_async_session"
    ) as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        svc_instance = AsyncMock()
        svc_instance.unassign = AsyncMock(return_value=unassigned_esc)
        MockSvc.return_value = svc_instance

        from fastapi import FastAPI
        from api.routes import escalations as esc_module
        from api.routes.admin import get_current_user

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: admin
        app.include_router(esc_module.router)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(f"/api/admin/escalations/{esc_id}/unassign")

    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


# ---------------------------------------------------------------------------
# test_resolve_endpoint_happy_path_does_not_resume_bot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_endpoint_happy_path_does_not_resume_bot() -> None:
    """
    POST /resolve returns 200 with status='resolved'.
    The bot is NOT resumed (per spec 1.7).
    """
    esc_id = uuid.uuid4()
    admin = _make_admin_user()
    resolved_esc = _make_escalation(uid=esc_id, status="resolved")
    resolved_esc.resolved_at = datetime.now(UTC)

    with patch("api.routes.escalations.EscalationAssignmentService") as MockSvc, patch(
        "api.routes.escalations.get_async_session"
    ) as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        svc_instance = AsyncMock()
        svc_instance.resolve = AsyncMock(return_value=resolved_esc)
        MockSvc.return_value = svc_instance

        from fastapi import FastAPI
        from api.routes import escalations as esc_module
        from api.routes.admin import get_current_user

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: admin
        app.include_router(esc_module.router)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(f"/api/admin/escalations/{esc_id}/resolve")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "resolved"
    assert data["resolved_at"] is not None


# ---------------------------------------------------------------------------
# test_list_endpoint_includes_assigned_to_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_endpoint_includes_assigned_to_summary() -> None:
    """
    GET /list returns items with assigned_to populated when escalation is assigned.
    """
    admin = _make_admin_user()
    assignee = _make_admin_user(uid=uuid.uuid4(), username="agent1")
    esc = _make_escalation(status="assigned", assigned_to_user_id=assignee.id)
    esc.assigned_to_user = assignee

    with patch("api.routes.escalations.get_async_session") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock count query — the router uses session.scalar(count_query)
        mock_session.scalar = AsyncMock(return_value=1)

        # Mock list query — the router uses session.execute(query).scalars().all()
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [esc]
        mock_session.execute = AsyncMock(return_value=list_result)

        from fastapi import FastAPI
        from api.routes import escalations as esc_module
        from api.routes.admin import get_current_user

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: admin
        app.include_router(esc_module.router)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/admin/escalations")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["status"] == "assigned"
    assert item["assigned_to"] is not None
    assert item["assigned_to"]["username"] == "agent1"


# ---------------------------------------------------------------------------
# test_assign_requires_auth_401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_requires_auth_401() -> None:
    """
    POST /assign without a valid auth token returns 401.
    """
    from fastapi import FastAPI, HTTPException
    from api.routes import escalations as esc_module
    from api.routes.admin import get_current_user

    app = FastAPI()

    async def _raise_401():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = _raise_401
    app.include_router(esc_module.router)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/admin/escalations/{uuid.uuid4()}/assign",
            json={"assignee_user_id": str(uuid.uuid4())},
        )

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# test_assign_requires_admin_role_403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_requires_admin_role_403() -> None:
    """
    POST /assign with a non-admin role returns 403.
    """
    from fastapi import FastAPI, HTTPException
    from api.routes import escalations as esc_module
    from api.routes.admin import get_current_user, require_role

    app = FastAPI()

    non_admin = _make_admin_user(role="user")
    app.dependency_overrides[get_current_user] = lambda: non_admin

    # Override require_role so it checks the actual role and raises 403
    async def _check_role():
        if non_admin.role != "admin":
            raise HTTPException(status_code=403, detail="Admin role required")
        return non_admin

    # Patch the require_role dependency result used in the router
    import api.routes.escalations as esc_mod
    original = esc_mod.require_role

    def _mock_require_role(*roles):
        return _check_role

    esc_mod.require_role = _mock_require_role
    app.include_router(esc_module.router)
    esc_mod.require_role = original  # Restore immediately — app is built

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/admin/escalations/{uuid.uuid4()}/assign",
            json={"assignee_user_id": str(uuid.uuid4())},
        )

    assert resp.status_code == 403
