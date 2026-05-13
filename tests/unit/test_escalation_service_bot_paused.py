"""
Unit tests for C1.1: perform_escalation() syncs bot_paused_at to ConversationHistory.

TDD cycle: RED → GREEN → REFACTOR

Covers:
  - test_perform_escalation_writes_bot_paused_at: after successful escalation, conv.bot_paused_at is set.
  - test_perform_escalation_first_pause_wins_when_already_paused: preexisting timestamp not overwritten.
  - test_perform_escalation_skips_if_no_conv_history: conv is None → no AttributeError, no crash.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_conv(*, bot_paused_at: datetime | None = None) -> MagicMock:
    """Build a mock ConversationHistory ORM object."""
    conv = MagicMock()
    conv.id = uuid4()
    conv.conversation_id = "99999"
    conv.bot_paused_at = bot_paused_at
    conv.bot_pause_reason = None
    return conv


def _make_session(conv: MagicMock | None) -> AsyncMock:
    """Return an AsyncSession mock that yields *conv* on scalar()."""
    session = AsyncMock()
    # scalar() is used via session.scalar(select(...))
    session.scalar = AsyncMock(return_value=conv)
    session.commit = AsyncMock()
    return session


def _make_escalation_row() -> MagicMock:
    """Build a mock Escalation ORM row (returned after insert)."""
    esc = MagicMock()
    esc.id = uuid4()
    return esc


# ---------------------------------------------------------------------------
# C1.1 RED — test_perform_escalation_writes_bot_paused_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_perform_escalation_writes_bot_paused_at() -> None:
    """After a successful escalation, ConversationHistory.bot_paused_at must be set."""
    conv = _make_conv(bot_paused_at=None)  # not yet paused
    session = _make_session(conv)

    with (
        patch(
            "agent.services.escalation_service.get_async_session",
        ) as mock_get_session,
        patch(
            "agent.services.escalation_service.ChatwootClient",
            return_value=AsyncMock(
                update_conversation_attributes=AsyncMock(),
                add_labels=AsyncMock(),
                add_private_note=AsyncMock(),
                assign_to_team=AsyncMock(),
            ),
        ),
        patch("agent.services.escalation_service.get_settings") as mock_settings,
    ):
        # First call to get_async_session: duplicate check (no existing)
        # Second call: save escalation + bot_paused_at write
        # We make it return the same session both times for simplicity
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_settings.return_value.CHATWOOT_TEAM_GROUP_ID = None

        # session.execute for duplicate check returns no existing escalation
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=execute_result)

        from agent.services.escalation_service import perform_escalation

        result = await perform_escalation(
            conversation_id="99999",
            user_phone="+34600000000",
            reason="Test reason",
            source="tool_call",
        )

    # The service must have set bot_paused_at on the conv mock
    assert conv.bot_paused_at is not None, "bot_paused_at must be set after escalation"
    assert isinstance(conv.bot_paused_at, datetime), "bot_paused_at must be a datetime"
    assert result["success"] is True


# ---------------------------------------------------------------------------
# C1.1 RED — test_perform_escalation_first_pause_wins_when_already_paused
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_perform_escalation_first_pause_wins_when_already_paused() -> None:
    """If bot_paused_at is already set, do NOT overwrite it (first-pause-wins)."""
    existing_ts = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    conv = _make_conv(bot_paused_at=existing_ts)
    session = _make_session(conv)

    with (
        patch(
            "agent.services.escalation_service.get_async_session",
        ) as mock_get_session,
        patch(
            "agent.services.escalation_service.ChatwootClient",
            return_value=AsyncMock(
                update_conversation_attributes=AsyncMock(),
                add_labels=AsyncMock(),
                add_private_note=AsyncMock(),
                assign_to_team=AsyncMock(),
            ),
        ),
        patch("agent.services.escalation_service.get_settings") as mock_settings,
    ):
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_settings.return_value.CHATWOOT_TEAM_GROUP_ID = None

        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=execute_result)

        from agent.services.escalation_service import perform_escalation

        result = await perform_escalation(
            conversation_id="99999",
            user_phone="+34600000000",
            reason="Another escalation",
            source="tool_call",
        )

    # The timestamp must NOT be overwritten — first-pause-wins
    assert conv.bot_paused_at == existing_ts, (
        f"First-pause-wins violated: expected {existing_ts}, got {conv.bot_paused_at}"
    )
    assert result["success"] is True


# ---------------------------------------------------------------------------
# C1.1 RED — test_perform_escalation_skips_if_no_conv_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_perform_escalation_skips_if_no_conv_history() -> None:
    """If ConversationHistory is not found (conv=None), must not raise AttributeError."""
    session = _make_session(conv=None)  # scalar() returns None

    with (
        patch(
            "agent.services.escalation_service.get_async_session",
        ) as mock_get_session,
        patch(
            "agent.services.escalation_service.ChatwootClient",
            return_value=AsyncMock(
                update_conversation_attributes=AsyncMock(),
                add_labels=AsyncMock(),
                add_private_note=AsyncMock(),
                assign_to_team=AsyncMock(),
            ),
        ),
        patch("agent.services.escalation_service.get_settings") as mock_settings,
    ):
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_settings.return_value.CHATWOOT_TEAM_GROUP_ID = None

        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=execute_result)

        from agent.services.escalation_service import perform_escalation

        # Must complete without AttributeError when conv is None
        result = await perform_escalation(
            conversation_id="99999",
            user_phone="+34600000000",
            reason="No conv history",
            source="tool_call",
        )

    # Service must return success (the escalation itself still persisted)
    assert result["success"] is True
