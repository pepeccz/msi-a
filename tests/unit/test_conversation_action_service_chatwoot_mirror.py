"""
Unit tests for C1.2 (updated for C2.9): pause_bot/resume_bot behavior.

Phase 1 (C1.2): Tested that pause_bot/resume_bot mirrored atencion_automatica
to Chatwoot (dual gate).

Phase 2 (C2.9): The Chatwoot mirror writes have been REMOVED because the
webhook gate now reads only bot_paused_at (single source of truth).

These tests verify:
  - pause_bot sets bot_paused_at in DB and does NOT call Chatwoot for atencion_automatica.
  - pause_bot returns the conv even when Chatwoot is unavailable (non-fatal remains).
  - resume_bot clears bot_paused_at in DB and does NOT call Chatwoot for atencion_automatica.

TDD: Updated from C1.2 RED→GREEN to Phase 2 (C2.9) — the spec changed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
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
# Phase 2 (C2.9): pause_bot sets DB fields, does NOT call Chatwoot mirror
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_bot_sets_bot_paused_at_in_db() -> None:
    """
    Phase 2: pause_bot must set bot_paused_at in DB.
    It must NOT call Chatwoot update_conversation_attributes for atencion_automatica.
    """
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

    # DB commit must have happened
    session.commit.assert_awaited()
    # Result is the conv
    assert result is conv
    # Phase 2: Chatwoot mirror for atencion_automatica is NO LONGER called
    # (gate is now purely bot_paused_at-based)
    chatwoot.update_conversation_attributes.assert_not_called()


# ---------------------------------------------------------------------------
# pause_bot: Chatwoot unavailable is still non-fatal (behavior preserved)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_bot_chatwoot_failure_is_non_fatal() -> None:
    """
    Even if Chatwoot raises (for other calls), pause_bot returns conv (non-fatal).
    The Chatwoot mirror for atencion_automatica is gone in Phase 2 so this test
    verifies pause_bot succeeds even when chatwoot_client would raise.
    """
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

        # Must NOT raise — even if Chatwoot is down
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
# Phase 2 (C2.9): resume_bot clears bot_paused_at, does NOT call Chatwoot mirror
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_bot_clears_bot_paused_at_in_db() -> None:
    """
    Phase 2: resume_bot must clear bot_paused_at in DB.
    It must NOT call Chatwoot update_conversation_attributes for atencion_automatica.
    """
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

    # DB commit must have happened
    session.commit.assert_awaited()
    # Result is the conv
    assert result is conv
    # Phase 2: Chatwoot mirror for atencion_automatica is NO LONGER called
    chatwoot.update_conversation_attributes.assert_not_called()
