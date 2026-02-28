"""Tests for delete_user Redis cleanup before cascade deletion.

Verifies that the delete_user route performs best-effort Redis cleanup
for each user conversation BEFORE issuing session.delete(user).

Change: verify-conversation-merelo — Phase 5 (tasks 5.1–5.3)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from api.models.conversation_reset import ResetDomainResult
from api.services.conversation_reset_coordinator import ResetExecutionContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conversation(conversation_id: str | None = None):
    """Create a lightweight mock ConversationHistory with required attrs."""
    conv = MagicMock()
    conv.id = uuid4()
    conv.conversation_id = conversation_id or f"conv-{uuid4().hex[:8]}"
    return conv


def _make_user(user_id=None, conversations=None):
    """Create a lightweight mock User object."""
    user = MagicMock()
    user.id = user_id or uuid4()
    user.conversations = conversations if conversations is not None else []
    return user


def _success_result() -> ResetDomainResult:
    return ResetDomainResult(
        domain="redis",
        status="success",
        details={"deleted_keys_total": 3},
    )


# ---------------------------------------------------------------------------
# Task 5.1 — delete_user with 2 conversations cleans Redis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_user_cleans_redis_for_each_conversation():
    """When user has 2 conversations, Redis executor is called once per conversation."""
    conv_a = _make_conversation("chatwoot-111")
    conv_b = _make_conversation("chatwoot-222")
    user = _make_user(conversations=[conv_a, conv_b])
    user_id = user.id

    # --- Mock session ---
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=user)
    mock_session.delete = AsyncMock()
    mock_session.commit = AsyncMock()

    @asynccontextmanager
    async def _session_factory():
        yield mock_session

    # --- Mock Redis executor ---
    mock_executor_instance = AsyncMock()
    mock_executor_instance.execute = AsyncMock(return_value=_success_result())

    with (
        patch(
            "api.routes.admin.get_async_session",
            _session_factory,
        ),
        patch(
            "api.routes.admin.ConversationResetRedisExecutor",
            return_value=mock_executor_instance,
        ),
    ):
        from api.routes.admin import delete_user

        # Simulate calling the endpoint (bypass FastAPI Depends)
        response = await delete_user(user_id=user_id, current_user={"id": "admin"})

    # Assert: Redis executor called exactly 2 times (one per conversation)
    assert mock_executor_instance.execute.call_count == 2

    # Verify the contexts passed to execute() match the conversations
    calls = mock_executor_instance.execute.call_args_list
    ctx_0: ResetExecutionContext = calls[0].args[0]
    ctx_1: ResetExecutionContext = calls[1].args[0]

    assert ctx_0.conversation_uuid == conv_a.id
    assert ctx_0.conversation_id == conv_a.conversation_id
    assert ctx_1.conversation_uuid == conv_b.id
    assert ctx_1.conversation_id == conv_b.conversation_id

    # Assert: user was still deleted after Redis cleanup
    mock_session.delete.assert_called_once_with(user)
    mock_session.commit.assert_called_once()

    # Assert: successful response
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Task 5.2 — Redis failure does NOT block user deletion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_user_continues_when_redis_cleanup_fails():
    """Redis ConnectionError must NOT prevent user deletion (best-effort)."""
    conv = _make_conversation("chatwoot-fail")
    user = _make_user(conversations=[conv])
    user_id = user.id

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=user)
    mock_session.delete = AsyncMock()
    mock_session.commit = AsyncMock()

    @asynccontextmanager
    async def _session_factory():
        yield mock_session

    mock_executor_instance = AsyncMock()
    mock_executor_instance.execute = AsyncMock(
        side_effect=ConnectionError("Redis unavailable"),
    )

    with (
        patch(
            "api.routes.admin.get_async_session",
            _session_factory,
        ),
        patch(
            "api.routes.admin.ConversationResetRedisExecutor",
            return_value=mock_executor_instance,
        ),
        patch("api.routes.admin.logger") as mock_logger,
    ):
        from api.routes.admin import delete_user

        response = await delete_user(user_id=user_id, current_user={"id": "admin"})

    # Assert: user was still deleted despite Redis failure
    mock_session.delete.assert_called_once_with(user)
    mock_session.commit.assert_called_once()
    assert response.status_code == 200

    # Assert: warning was logged about the failure
    mock_logger.warning.assert_called()
    warning_call_kwargs = mock_logger.warning.call_args
    # Accept positional or keyword style — just verify the call happened
    assert warning_call_kwargs is not None


# ---------------------------------------------------------------------------
# Task 5.3 — 0 conversations → no Redis calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_user_skips_redis_when_no_conversations():
    """When user has no conversations, Redis executor must NOT be instantiated/called."""
    user = _make_user(conversations=[])
    user_id = user.id

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=user)
    mock_session.delete = AsyncMock()
    mock_session.commit = AsyncMock()

    @asynccontextmanager
    async def _session_factory():
        yield mock_session

    mock_executor_cls = MagicMock()
    mock_executor_instance = AsyncMock()
    mock_executor_instance.execute = AsyncMock(return_value=_success_result())
    mock_executor_cls.return_value = mock_executor_instance

    with (
        patch(
            "api.routes.admin.get_async_session",
            _session_factory,
        ),
        patch(
            "api.routes.admin.ConversationResetRedisExecutor",
            mock_executor_cls,
        ),
    ):
        from api.routes.admin import delete_user

        response = await delete_user(user_id=user_id, current_user={"id": "admin"})

    # Assert: Redis executor.execute() was NEVER called
    mock_executor_instance.execute.assert_not_called()

    # Assert: user was still deleted normally
    mock_session.delete.assert_called_once_with(user)
    mock_session.commit.assert_called_once()
    assert response.status_code == 200
