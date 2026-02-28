"""Phase 1 foundation tests for conversation reset implementation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from api.models.conversation_reset import ConversationResetResponse, ResetDomainResult
from api.services.conversation_reset_coordinator import (
    ConversationResetCoordinator,
    ResetExecutionContext,
)


class _FakeExecutor:
    def __init__(self, domain: str, status: str = "success") -> None:
        self.domain = domain
        self.status = status
        self.calls: list[str] = []

    async def execute(self, context: ResetExecutionContext) -> ResetDomainResult:
        self.calls.append(context.conversation_id)
        return ResetDomainResult(domain=self.domain, status=self.status)


def test_reset_response_contract_serializes_domain_statuses() -> None:
    now = datetime.now(UTC)
    response = ConversationResetResponse(
        success=True,
        message="Conversation reset completed",
        conversation_uuid=uuid4(),
        conversation_id="123",
        scope="standard",
        include_chatwoot=False,
        requested_at=now,
        completed_at=now,
        partial_failure=False,
        domains=[
            ResetDomainResult(domain="database", status="success"),
            ResetDomainResult(domain="redis", status="success"),
            ResetDomainResult(domain="files", status="skipped"),
            ResetDomainResult(domain="chatwoot", status="skipped"),
        ],
    )

    payload = response.model_dump(mode="json")
    assert payload["scope"] == "standard"
    assert payload["domains"][0]["domain"] == "database"
    assert payload["domains"][2]["status"] == "skipped"


@pytest.mark.asyncio
async def test_reset_coordinator_keeps_db_first_order_and_skips_chatwoot() -> None:
    executors = {
        "database": _FakeExecutor("database"),
        "redis": _FakeExecutor("redis"),
        "files": _FakeExecutor("files"),
    }
    coordinator = ConversationResetCoordinator(executors=executors)
    context = ResetExecutionContext(
        conversation_uuid=uuid4(),
        conversation_id="cw-11",
        include_chatwoot=False,
    )

    response = await coordinator.run(context)

    assert response.success is True
    assert [result.domain for result in response.domains] == [
        "database",
        "redis",
        "files",
        "chatwoot",
    ]
    assert response.domains[-1].status == "skipped"


@pytest.mark.asyncio
async def test_reset_coordinator_aborts_when_database_fails() -> None:
    executors = {
        "database": _FakeExecutor("database", status="failed"),
        "redis": _FakeExecutor("redis"),
        "files": _FakeExecutor("files"),
    }
    coordinator = ConversationResetCoordinator(executors=executors)
    context = ResetExecutionContext(
        conversation_uuid=uuid4(),
        conversation_id="cw-12",
        include_chatwoot=True,
    )

    response = await coordinator.run(context)

    assert response.success is False
    assert [result.domain for result in response.domains] == ["database"]


@pytest.mark.asyncio
async def test_conversation_footprint_fixture_provisions_local_assets(
    conversation_footprint,
) -> None:
    assert conversation_footprint.chatwoot_conversation_id.startswith("reset-")
    assert conversation_footprint.image_path.exists()
    assert any(key.startswith("checkpoint:") for key in conversation_footprint.redis_keys)
    assert any(key.startswith("image_batch:") for key in conversation_footprint.redis_keys)
