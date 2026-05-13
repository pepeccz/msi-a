"""
Unit tests for Migration B backfill script.

Spec 5.5: Idempotency, no-token guard, and dry-run behavior.

TDD Cycle: RED → GREEN (C2.10 apply, 2026-05-13).
"""

from __future__ import annotations

import os
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conv_row(
    *,
    conversation_id: str = "12345",
    bot_paused_at: datetime | None = None,
    metadata: dict | None = None,
) -> MagicMock:
    """Build a mock ConversationHistory row."""
    row = MagicMock()
    row.id = uuid4()
    row.conversation_id = conversation_id
    row.bot_paused_at = bot_paused_at
    row.metadata_ = metadata or {}
    return row


def _make_chatwoot_conv(
    *,
    conv_id: int = 12345,
    atencion_automatica: bool | None = None,
) -> dict:
    """Build a minimal Chatwoot conversation payload."""
    custom_attrs = {}
    if atencion_automatica is not None:
        custom_attrs["atencion_automatica"] = atencion_automatica
    return {
        "id": conv_id,
        "custom_attributes": custom_attrs,
    }


# ---------------------------------------------------------------------------
# Scenario 5.5: Idempotency — running twice writes 0 rows on second run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_is_idempotent():
    """
    GIVEN a conversation with atencion_automatica=false in Chatwoot
    AND bot_paused_at is already set (first run already applied)
    WHEN run_backfill is called a second time
    THEN 0 rows are backfilled (skipped = 1)
    AND no DB writes occur
    """
    # Row already has bot_paused_at set (simulates first run having completed)
    existing_row = _make_conv_row(
        conversation_id="12345",
        bot_paused_at=datetime.now(UTC),
        metadata={"backfilled_by_migration_b": True},
    )

    chatwoot_convs = [_make_chatwoot_conv(conv_id=12345, atencion_automatica=False)]

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none = MagicMock(return_value=existing_row)
    mock_session.execute = AsyncMock(return_value=scalar_result)
    mock_session.commit = AsyncMock()

    with (
        patch(
            "scripts.backfill_bot_paused_chatwoot_scan._fetch_open_conversations_page",
            new_callable=AsyncMock,
            return_value=(chatwoot_convs, False),
        ),
        patch(
            "scripts.backfill_bot_paused_chatwoot_scan.get_async_session",
            return_value=mock_session,
        ),
        patch(
            "scripts.backfill_bot_paused_chatwoot_scan.get_settings",
        ) as mock_settings,
    ):
        settings_obj = MagicMock()
        settings_obj.CHATWOOT_API_URL = "https://chatwoot.test"
        settings_obj.CHATWOOT_ACCOUNT_ID = "1"
        settings_obj.MIGRATION_B_CHATWOOT_PAGES_PER_MINUTE = 300
        mock_settings.return_value = settings_obj

        from scripts.backfill_bot_paused_chatwoot_scan import run_backfill

        result = await run_backfill(dry_run=False)

    assert result["backfilled"] == 0
    assert result["skipped"] >= 1
    mock_session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Guard: no CHATWOOT_API_TOKEN → exit cleanly
# ---------------------------------------------------------------------------


def test_backfill_skips_when_no_api_token(monkeypatch):
    """
    GIVEN CHATWOOT_API_TOKEN is not set in environment
    WHEN _check_env() is called
    THEN it returns False with a warning (no exception raised)
    """
    monkeypatch.delenv("CHATWOOT_API_TOKEN", raising=False)

    from scripts.backfill_bot_paused_chatwoot_scan import _check_env

    result = _check_env()
    assert result is False


def test_backfill_check_env_returns_true_when_token_present(monkeypatch):
    """
    GIVEN CHATWOOT_API_TOKEN is set
    WHEN _check_env() is called
    THEN it returns True
    """
    monkeypatch.setenv("CHATWOOT_API_TOKEN", "test-token-abc")

    from scripts.backfill_bot_paused_chatwoot_scan import _check_env

    result = _check_env()
    assert result is True


# ---------------------------------------------------------------------------
# Dry-run: does not write to DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_dry_run_writes_nothing():
    """
    GIVEN a conversation with atencion_automatica=false AND bot_paused_at IS NULL
    WHEN run_backfill is called with dry_run=True
    THEN stats report backfilled=1 (found the row) but no DB commit is made
    """
    driftable_row = _make_conv_row(
        conversation_id="99999",
        bot_paused_at=None,
        metadata={},
    )

    chatwoot_convs = [_make_chatwoot_conv(conv_id=99999, atencion_automatica=False)]

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none = MagicMock(return_value=driftable_row)
    mock_session.execute = AsyncMock(return_value=scalar_result)
    mock_session.commit = AsyncMock()

    with (
        patch(
            "scripts.backfill_bot_paused_chatwoot_scan._fetch_open_conversations_page",
            new_callable=AsyncMock,
            return_value=(chatwoot_convs, False),
        ),
        patch(
            "scripts.backfill_bot_paused_chatwoot_scan.get_async_session",
            return_value=mock_session,
        ),
        patch(
            "scripts.backfill_bot_paused_chatwoot_scan.get_settings",
        ) as mock_settings,
    ):
        settings_obj = MagicMock()
        settings_obj.CHATWOOT_API_URL = "https://chatwoot.test"
        settings_obj.CHATWOOT_ACCOUNT_ID = "1"
        settings_obj.MIGRATION_B_CHATWOOT_PAGES_PER_MINUTE = 300
        mock_settings.return_value = settings_obj

        from scripts.backfill_bot_paused_chatwoot_scan import run_backfill

        result = await run_backfill(dry_run=True)

    # Stats reflect detection but no write
    assert result["backfilled"] == 1
    assert result["dry_run"] is True
    # Commit must NOT be called in dry-run mode
    mock_session.commit.assert_not_called()
    # bot_paused_at must NOT have been set on the row
    assert driftable_row.bot_paused_at is None


# ---------------------------------------------------------------------------
# Happy path: actual backfill sets bot_paused_at and metadata marker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_happy_path_sets_bot_paused_at():
    """
    GIVEN a conversation with atencion_automatica=false AND bot_paused_at IS NULL
    WHEN run_backfill is called with dry_run=False
    THEN bot_paused_at is set AND metadata_ backfill marker is written
    AND session.commit() is called
    """
    driftable_row = _make_conv_row(
        conversation_id="11111",
        bot_paused_at=None,
        metadata={},
    )

    chatwoot_convs = [_make_chatwoot_conv(conv_id=11111, atencion_automatica=False)]

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none = MagicMock(return_value=driftable_row)
    mock_session.execute = AsyncMock(return_value=scalar_result)
    mock_session.commit = AsyncMock()

    with (
        patch(
            "scripts.backfill_bot_paused_chatwoot_scan._fetch_open_conversations_page",
            new_callable=AsyncMock,
            return_value=(chatwoot_convs, False),
        ),
        patch(
            "scripts.backfill_bot_paused_chatwoot_scan.get_async_session",
            return_value=mock_session,
        ),
        patch(
            "scripts.backfill_bot_paused_chatwoot_scan.get_settings",
        ) as mock_settings,
    ):
        settings_obj = MagicMock()
        settings_obj.CHATWOOT_API_URL = "https://chatwoot.test"
        settings_obj.CHATWOOT_ACCOUNT_ID = "1"
        settings_obj.MIGRATION_B_CHATWOOT_PAGES_PER_MINUTE = 300
        mock_settings.return_value = settings_obj

        from scripts.backfill_bot_paused_chatwoot_scan import run_backfill

        result = await run_backfill(dry_run=False)

    assert result["backfilled"] == 1
    assert result["scanned"] == 1
    assert driftable_row.bot_paused_at is not None
    assert driftable_row.metadata_.get("backfilled_by_migration_b") is True
    mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Skip: atencion_automatica=true (bot is active in Chatwoot)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_skips_active_conversations():
    """
    GIVEN a conversation with atencion_automatica=true
    WHEN run_backfill runs
    THEN it is skipped (no DB lookup, no write)
    """
    chatwoot_convs = [_make_chatwoot_conv(conv_id=22222, atencion_automatica=True)]

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with (
        patch(
            "scripts.backfill_bot_paused_chatwoot_scan._fetch_open_conversations_page",
            new_callable=AsyncMock,
            return_value=(chatwoot_convs, False),
        ),
        patch(
            "scripts.backfill_bot_paused_chatwoot_scan.get_async_session",
            return_value=mock_session,
        ),
        patch(
            "scripts.backfill_bot_paused_chatwoot_scan.get_settings",
        ) as mock_settings,
    ):
        settings_obj = MagicMock()
        settings_obj.CHATWOOT_API_URL = "https://chatwoot.test"
        settings_obj.CHATWOOT_ACCOUNT_ID = "1"
        settings_obj.MIGRATION_B_CHATWOOT_PAGES_PER_MINUTE = 300
        mock_settings.return_value = settings_obj

        from scripts.backfill_bot_paused_chatwoot_scan import run_backfill

        result = await run_backfill(dry_run=False)

    assert result["backfilled"] == 0
    assert result["skipped"] == 1
    # No DB execute should be called for atencion_automatica=true
    mock_session.execute.assert_not_called()
