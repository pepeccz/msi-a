"""
Migration B — Backfill bot_paused_at from Chatwoot conversation scan.

One-shot operator script to find conversations with atencion_automatica=false
in Chatwoot and set ConversationHistory.bot_paused_at for matching DB rows.

Usage:
    python scripts/backfill_bot_paused_chatwoot_scan.py
    python scripts/backfill_bot_paused_chatwoot_scan.py --dry-run

Environment requirements:
    CHATWOOT_API_TOKEN   — must be set; exits cleanly if absent.
    CHATWOOT_API_URL     — Chatwoot API base URL.
    CHATWOOT_ACCOUNT_ID  — Chatwoot account ID.
    DATABASE_URL         — PostgreSQL async URL.

Idempotency:
    Running twice is a no-op — rows with bot_paused_at already set are skipped.
    Rows already marked with metadata_->>'backfilled_by_migration_b' = 'true'
    are also skipped.

Rate limiting:
    Controlled by MIGRATION_B_CHATWOOT_PAGES_PER_MINUTE (default 60 = 1 req/sec).

Returns (via stdout):
    JSON dict with keys: scanned, backfilled, skipped, dry_run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, UTC
from typing import Any

# Module-level imports so tests can patch them with `patch("scripts.backfill_bot_paused_chatwoot_scan.<name>")`.
# These imports require PYTHONPATH=/app at runtime.
try:  # graceful fallback if invoked without the project on the path
    from shared.config import get_settings
    from database.connection import get_async_session
    from database.models import ConversationHistory
    from sqlalchemy import select
except ImportError:  # pragma: no cover — defer to runtime resolution
    get_settings = None  # type: ignore[assignment]
    get_async_session = None  # type: ignore[assignment]
    ConversationHistory = None  # type: ignore[assignment]
    select = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)


# ---------------------------------------------------------------------------
# Guard: require CHATWOOT_API_TOKEN
# ---------------------------------------------------------------------------

def _check_env() -> bool:
    """Return True if all required env vars are present, else warn and return False."""
    token = os.environ.get("CHATWOOT_API_TOKEN", "")
    if not token:
        logger.warning(
            "CHATWOOT_API_TOKEN is not set. "
            "Cannot scan Chatwoot conversations. "
            "Exiting cleanly (no DB changes made)."
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Chatwoot pagination helper (does not use ChatwootClient to avoid the
# full import chain with structlog etc.)
# ---------------------------------------------------------------------------

async def _fetch_open_conversations_page(
    api_url: str,
    account_id: str,
    token: str,
    page: int,
    per_page: int = 50,
) -> tuple[list[dict[str, Any]], bool]:
    """Fetch one page of open conversations from Chatwoot.

    Returns (conversations, has_more).
    """
    import httpx  # local import to avoid import failure when token is missing

    url = f"{api_url}/api/v1/accounts/{account_id}/conversations"
    headers = {
        "api_access_token": token,
        "Content-Type": "application/json",
    }
    params = {
        "status": "open",
        "page": page,
        "per_page": per_page,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

    conversations = data.get("data", {}).get("payload", [])
    meta = data.get("data", {}).get("meta", {})
    total_count = meta.get("all_count", 0)

    has_more = (page * per_page) < total_count and len(conversations) == per_page
    return conversations, has_more


# ---------------------------------------------------------------------------
# Main backfill logic
# ---------------------------------------------------------------------------

async def run_backfill(dry_run: bool = False) -> dict[str, Any]:
    """
    Scan Chatwoot open conversations for atencion_automatica=false and
    backfill ConversationHistory.bot_paused_at for matching DB rows.

    Args:
        dry_run: If True, compute stats but do not write to DB.

    Returns:
        dict with keys: scanned, backfilled, skipped, dry_run.
    """
    if get_settings is None:
        raise RuntimeError(
            "Project modules not importable. Run with PYTHONPATH=/app or from the project root."
        )

    settings = get_settings()

    api_url = settings.CHATWOOT_API_URL
    account_id = str(settings.CHATWOOT_ACCOUNT_ID)
    token = os.environ.get("CHATWOOT_API_TOKEN", "")
    pages_per_minute = settings.MIGRATION_B_CHATWOOT_PAGES_PER_MINUTE
    sleep_between_pages = 60.0 / max(pages_per_minute, 1)

    stats: dict[str, Any] = {
        "scanned": 0,
        "backfilled": 0,
        "skipped": 0,
        "dry_run": dry_run,
    }

    logger.info(
        "Migration B backfill started",
        extra={
            "dry_run": dry_run,
            "pages_per_minute": pages_per_minute,
            "sleep_between_pages_s": sleep_between_pages,
        },
    )

    page = 1
    while True:
        logger.info(f"Fetching Chatwoot conversations page {page}...")
        conversations, has_more = await _fetch_open_conversations_page(
            api_url=api_url,
            account_id=account_id,
            token=token,
            page=page,
        )

        for conv in conversations:
            stats["scanned"] += 1
            conv_id = str(conv.get("id", ""))
            custom_attrs = conv.get("custom_attributes") or {}
            atencion_automatica = custom_attrs.get("atencion_automatica")

            if atencion_automatica is not True and atencion_automatica is not False:
                # Not set — skip
                stats["skipped"] += 1
                continue

            if atencion_automatica is not False:
                # True — bot is active in Chatwoot, no backfill needed
                stats["skipped"] += 1
                continue

            # atencion_automatica=False — check DB row
            async with get_async_session() as session:
                result = await session.execute(
                    select(ConversationHistory).where(
                        ConversationHistory.conversation_id == conv_id
                    )
                )
                row = result.scalar_one_or_none()

                if row is None:
                    logger.debug(
                        f"Conversation {conv_id}: no ConversationHistory row, skipping."
                    )
                    stats["skipped"] += 1
                    continue

                if row.bot_paused_at is not None:
                    # Already paused — idempotent skip
                    logger.debug(
                        f"Conversation {conv_id}: bot_paused_at already set, skipping."
                    )
                    stats["skipped"] += 1
                    continue

                metadata = row.metadata_ or {}
                if metadata.get("backfilled_by_migration_b"):
                    # Already backfilled — idempotent skip
                    stats["skipped"] += 1
                    continue

                logger.info(
                    f"Backfilling conversation {conv_id}: "
                    f"atencion_automatica=false → setting bot_paused_at."
                )

                if not dry_run:
                    now = datetime.now(UTC)
                    row.bot_paused_at = now
                    row.metadata_ = {
                        **metadata,
                        "backfilled_by_migration_b": True,
                        "backfilled_at": now.isoformat(),
                    }
                    await session.commit()

                stats["backfilled"] += 1

        if not has_more:
            break

        page += 1
        # Rate limiting
        if sleep_between_pages > 0:
            await asyncio.sleep(sleep_between_pages)

    logger.info(
        "Migration B backfill complete.",
        extra=stats,
    )
    return stats


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migration B: backfill bot_paused_at from Chatwoot scan."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute stats but do not write to DB.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if not _check_env():
        sys.exit(0)

    result = asyncio.run(run_backfill(dry_run=args.dry_run))
    print(json.dumps(result, indent=2))
