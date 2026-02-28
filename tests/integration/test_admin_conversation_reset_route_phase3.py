"""Route integration tests for phase 3 conversation reset orchestration."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from api.models.conversation_reset import ResetDomainResult
from api.routes.admin import get_current_user
from api.services.conversation_reset_coordinator import ResetExecutionContext


class _FakeDbExecutor:
    domain = "database"

    async def execute(self, context: ResetExecutionContext) -> ResetDomainResult:
        context.conversation_id = "123"
        context.case_image_filenames = ["image-1.jpg"]
        return ResetDomainResult(
            domain="database",
            status="success",
            details={
                "cases": 2,
                "case_images": 3,
                "escalations": 1,
                "rag_queries": 4,
            },
        )


class _FakeRedisExecutor:
    domain = "redis"

    async def execute(self, context: ResetExecutionContext) -> ResetDomainResult:
        return ResetDomainResult(
            domain="redis",
            status="success",
            details={"deleted_keys_total": 6},
        )


class _FakeFilesExecutor:
    domain = "files"

    async def execute(self, context: ResetExecutionContext) -> ResetDomainResult:
        return ResetDomainResult(
            domain="files",
            status="success",
            details={"deleted_files": 1},
        )


class _FakeChatwootSuccessExecutor:
    domain = "chatwoot"

    async def execute(self, context: ResetExecutionContext) -> ResetDomainResult:
        return ResetDomainResult(
            domain="chatwoot",
            status="success",
            details={"operations_ok": 2},
        )


class _FakeChatwootPartialExecutor:
    domain = "chatwoot"

    async def execute(self, context: ResetExecutionContext) -> ResetDomainResult:
        return ResetDomainResult(
            domain="chatwoot",
            status="partial",
            details={"operations_ok": 1},
            error="add_labels=timeout",
        )


@pytest.fixture
def admin_auth_override():
    async def _fake_admin_user():
        return object()

    app.dependency_overrides[get_current_user] = _fake_admin_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_delete_conversation_route_returns_extended_success_contract(
    monkeypatch,
    admin_auth_override,
) -> None:
    monkeypatch.setattr("api.routes.admin.ConversationResetDatabaseExecutor", _FakeDbExecutor)
    monkeypatch.setattr("api.routes.admin.ConversationResetRedisExecutor", _FakeRedisExecutor)
    monkeypatch.setattr("api.routes.admin.ConversationResetFilesExecutor", _FakeFilesExecutor)
    monkeypatch.setattr(
        "api.routes.admin.ConversationResetChatwootExecutor",
        _FakeChatwootSuccessExecutor,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete(
            f"/api/admin/conversations/{uuid4()}",
            params={"include_chatwoot": "true"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["partial_failure"] is False
    assert payload["message"] == "Conversacion eliminada correctamente"
    assert payload["details"]["conversation_id"] == "123"
    assert payload["details"]["deleted_cases"] == 2
    assert payload["details"]["deleted_images"] == 3
    assert payload["details"]["deleted_escalations"] == 1
    assert payload["details"]["deleted_rag_queries"] == 4
    assert payload["details"]["deleted_redis_keys"] == 6
    assert len(payload["domains"]) == 4


@pytest.mark.asyncio
async def test_delete_conversation_route_reports_partial_failure_non_blocking(
    monkeypatch,
    admin_auth_override,
) -> None:
    monkeypatch.setattr("api.routes.admin.ConversationResetDatabaseExecutor", _FakeDbExecutor)
    monkeypatch.setattr("api.routes.admin.ConversationResetRedisExecutor", _FakeRedisExecutor)
    monkeypatch.setattr("api.routes.admin.ConversationResetFilesExecutor", _FakeFilesExecutor)
    monkeypatch.setattr(
        "api.routes.admin.ConversationResetChatwootExecutor",
        _FakeChatwootPartialExecutor,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete(
            f"/api/admin/conversations/{uuid4()}",
            params={"include_chatwoot": "true"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["partial_failure"] is True
    assert payload["message"] == "Conversacion eliminada correctamente"
    chatwoot_domain = next(domain for domain in payload["domains"] if domain["domain"] == "chatwoot")
    assert chatwoot_domain["status"] == "partial"
