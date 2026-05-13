"""
Diagnostic: bot_paused_at drift post-Migration B.

Reads ConversationHistory rows with metadata_->>'backfilled_by_migration_b' = 'true'
and prints a JSON summary. Used as post-deploy verification.

Usage:
    python scripts/diagnostic_bot_paused_drift.py

Output (stdout, JSON):
    {
      "total_backfilled": N,
      "sample": [
        {
          "conversation_id": "...",
          "bot_paused_at": "...",
          "backfilled_at": "..."
        },
        ...  (up to 5 rows)
      ]
    }
"""

from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)


async def run_diagnostic() -> dict:
    from database.connection import get_async_session
    from database.models import ConversationHistory
    from sqlalchemy import select, func

    async with get_async_session() as session:
        # Count rows backfilled by Migration B
        count_result = await session.execute(
            select(func.count(ConversationHistory.id)).where(
                ConversationHistory.metadata_["backfilled_by_migration_b"].astext == "true"
            )
        )
        total = count_result.scalar() or 0

        # Fetch sample of 5 rows
        sample_result = await session.execute(
            select(ConversationHistory)
            .where(
                ConversationHistory.metadata_["backfilled_by_migration_b"].astext == "true"
            )
            .limit(5)
        )
        sample_rows = sample_result.scalars().all()

    sample = [
        {
            "conversation_id": row.conversation_id,
            "bot_paused_at": row.bot_paused_at.isoformat() if row.bot_paused_at else None,
            "backfilled_at": (row.metadata_ or {}).get("backfilled_at"),
        }
        for row in sample_rows
    ]

    return {
        "total_backfilled": total,
        "sample": sample,
    }


if __name__ == "__main__":
    result = asyncio.run(run_diagnostic())
    print(json.dumps(result, indent=2))
