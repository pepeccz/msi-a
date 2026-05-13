"""
Unit tests for C1.2: pause_bot/resume_bot mirror atencion_automatica to Chatwoot.

TDD cycle: RED → GREEN → REFACTOR

Covers:
  - test_pause_bot_mirrors_to_chatwoot: pause_bot calls update_conversation_attributes(False).
  - test_pause_bot_chatwoot_failure_is_non_fatal: Chatwoot raises, pause_bot still returns conv.
  - test_resume_bot_mirrors_to_chatwoot: resume_bot calls update_conversation_attributes(True).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conv(
    *,
    bot_paused_at: datetime | None = None,
    state_snapshot: dict | None = None,
    state_snapshot_version: int | None = None,
) -> MagicMock:
    """Build a mock ConversationHistory ORM object."""
    conv = MagicMock()
    conv.id = uuid4()
    conv.conversation_id = "12345"
    conv.bot_paused_at = bot_paused_at
    conv.bot_resumed_at = None
    conv.state_snapshot = state_snapshot or {"version": 1, "state": {}}
    conv.state_snapshot_version = state_snapshot_version
    conv.bot_pause_reason = None
    conv.bot_paused_by_user_id = None
    conv.last_inbound_at = datetime.now(UTC)
    return conv


def _make_session(conv: MagicMock) -> AsyncMock:
    """Return an AsyncSession mock that yields *conv* on scalar_one_or_none()."""
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = conv
    execute_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# C1.2 RED — test_pause_bot_mirrors_to_chatwoot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_bot_mirrors_to_chatwoot() -> None:
    """pause_bot must call update_conversation_attributes with atencion_automatica=False."""
    conv = _make_conv(bot_paused_at=None)
    session = _make_session(conv)
    chatwoot = AsyncMock()
    chatwoot.update_conversation_attributes = AsyncMock()

    user_id = uuid4()
    conv_history_id = conv.id

    with (
        patch("api.services.conversation_action_service.snapshot_state") as mock_snapshot,
        patch("api.services.conversation_action_service.restore_state"),
        patch("api.services.conversation_action_service.inject_human_messages_to_state"),
    ):
        mock_snapshot.return_value = {"version": 1, "state": {}}

        from api.services.conversation_action_service import ConversationActionService

        service = ConversationActionService(
            session=session,
            chatwoot_client=chatwoot,
            redis_client=AsyncMock(),
            graph=AsyncMock(),
        )

        result = await service.pause_bot(
            conversation_history_id=conv_history_id,
            paused_by_user_id=user_id,
            reason="Test pause",
        )

    # Must have called Chatwoot to mirror atencion_automatica=False
    chatwoot.update_conversation_attributes.assert_called_once()
    call_kwargs = chatwoot.update_conversation_attributes.call_args
    # Accept both positional and keyword args
    attributes = (
        call_kwargs.kwargs.get("attributes")
        or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
    )
    assert attributes == {"atencion_automatica": False}, (
        f"Expected atencion_automatica=False mirror call, got: {attributes}"
    )
    assert result is conv


# ---------------------------------------------------------------------------
# C1.2 RED — test_pause_bot_chatwoot_failure_is_non_fatal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_bot_chatwoot_failure_is_non_fatal() -> None:
    """If Chatwoot raises, pause_bot must still return the conv (non-fatal)."""
    conv = _make_conv(bot_paused_at=None)
    session = _make_session(conv)
    chatwoot = AsyncMock()
    chatwoot.update_conversation_attributes = AsyncMock(
        side_effect=Exception("Chatwoot connection refused")
    )

    user_id = uuid4()
    conv_history_id = conv.id

    with (
        patch("api.services.conversation_action_service.snapshot_state") as mock_snapshot,
    ):
        mock_snapshot.return_value = {"version": 1, "state": {}}

        from api.services.conversation_action_service import ConversationActionService

        service = ConversationActionService(
            session=session,
            chatwoot_client=chatwoot,
            redis_client=AsyncMock(),
            graph=AsyncMock(),
        )

        # Must NOT raise even if Chatwoot fails
        result = await service.pause_bot(
            conversation_history_id=conv_history_id,
            paused_by_user_id=user_id,
            reason="Test pause chatwoot down",
        )

    # DB commit must still have happened
    session.commit.assert_awaited()
    # Result is the conv (pause succeeded in DB)
    assert result is conv


# ---------------------------------------------------------------------------
# C1.2 RED — test_resume_bot_mirrors_to_chatwoot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_bot_mirrors_to_chatwoot() -> None:
    """resume_bot must call update_conversation_attributes with atencion_automatica=True."""
    conv = _make_conv(
        bot_paused_at=datetime.now(UTC),
        state_snapshot={"version": 1, "state": {}},
        state_snapshot_version=1,
    )
    session = _make_session(conv)
    chatwoot = AsyncMock()
    chatwoot.update_conversation_attributes = AsyncMock()

    user_id = uuid4()
    conv_history_id = conv.id

    with (
        patch(
            "api.services.conversation_action_service.restore_state",
            new_callable=AsyncMock,
        ),
        patch(
            "api.services.conversation_action_service.inject_human_messages_to_state",
            return_value=0,
            new_callable=AsyncMock,
        ),
    ):
        from api.services.conversation_action_service import ConversationActionService

        service = ConversationActionService(
            session=session,
            chatwoot_client=chatwoot,
            redis_client=AsyncMock(),
            graph=AsyncMock(),
        )

        result = await service.resume_bot(
            conversation_history_id=conv_history_id,
            resumed_by_user_id=user_id,
        )

    # Must have called Chatwoot to mirror atencion_automatica=True
    chatwoot.update_conversation_attributes.assert_called_once()
    call_kwargs = chatwoot.update_conversation_attributes.call_args
    attributes = (
        call_kwargs.kwargs.get("attributes")
        or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
    )
    assert attributes == {"atencion_automatica": True}, (
        f"Expected atencion_automatica=True mirror call, got: {attributes}"
    )
    assert result is conv
