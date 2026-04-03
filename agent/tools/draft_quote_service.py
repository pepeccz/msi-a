"""
MSI-a — DraftQuote Service (Phase 3).

Provides fire-and-forget upsert and load functions for the DraftQuote model.
These functions are used by:
- agent/tools/element_tools.py (write after calcular_tarifa_con_elementos)
- agent/modes/presupuesto_mode.py (read on resume)

All writes are fire-and-forget: DB errors are caught and logged as warnings
so they never surface to the LLM or the user.
"""

from __future__ import annotations

import uuid
from datetime import datetime, UTC
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


async def _resolve_conversation_uuid(
    session: AsyncSession,
    chatwoot_id: str,
) -> uuid.UUID | None:
    """
    Resolve a Chatwoot conversation ID (e.g. "1") to the internal UUID
    from conversation_history.

    Returns None if no matching row exists.
    """
    from database.models import ConversationHistory

    result = await session.execute(
        select(ConversationHistory.id).where(
            ConversationHistory.conversation_id == chatwoot_id
        )
    )
    row = result.scalar_one_or_none()
    return row


async def _upsert_draft_quote(
    *,
    session: AsyncSession,
    conversation_id: str,
    category_slug: str,
    elements: list[str],
    tier_id: str | None,
    precio_final: Decimal,
) -> None:
    """
    Upsert a DraftQuote for the given conversation.

    Strategy:
    1. Deactivate any existing is_active=True DraftQuote for this conversation.
    2. Insert a new DraftQuote with is_active=True.

    This ensures at most one is_active=True row per conversation at all times.

    Args:
        session: Async SQLAlchemy session (caller manages commit/rollback).
        conversation_id: Conversation UUID as string.
        category_slug: Vehicle category slug.
        elements: List of element codes.
        tier_id: Resolved tariff tier UUID as string (nullable).
        precio_final: Final price without VAT.
    """
    from database.models import DraftQuote

    conv_uuid = await _resolve_conversation_uuid(session, conversation_id)
    if conv_uuid is None:
        logger.warning(
            "draft_quote_upsert_skipped",
            conversation_id=conversation_id,
            reason="no matching conversation_history row",
        )
        return

    # Step 1: Deactivate existing active drafts for this conversation
    await session.execute(
        update(DraftQuote)
        .where(
            DraftQuote.conversation_id == conv_uuid,
            DraftQuote.is_active == True,
        )
        .values(is_active=False)
    )

    # Step 2: Insert new active draft
    new_draft = DraftQuote(
        id=uuid.uuid4(),
        conversation_id=conv_uuid,
        category_slug=category_slug,
        elements=elements,
        tier_id=uuid.UUID(tier_id) if tier_id else None,
        precio_final=precio_final,
        calculated_at=datetime.now(UTC),
        is_active=True,
        created_at=datetime.now(UTC),
    )
    session.add(new_draft)


async def _deactivate_draft_quote(
    conversation_id: str,
) -> None:
    """
    Deactivate all active DraftQuotes for a conversation.

    Called when the agent transitions OUT of PRESUPUESTO_MODE.
    Self-managing: opens its own session (fire-and-forget).

    Args:
        conversation_id: Chatwoot conversation ID as string (e.g. "1").
    """
    from database.connection import get_async_session
    from database.models import DraftQuote

    try:
        async with get_async_session() as session:
            conv_uuid = await _resolve_conversation_uuid(session, conversation_id)
            if conv_uuid is None:
                logger.warning(
                    "draft_quote_deactivation_skipped",
                    conversation_id=conversation_id,
                    reason="no matching conversation_history row",
                )
                return

            await session.execute(
                update(DraftQuote)
                .where(
                    DraftQuote.conversation_id == conv_uuid,
                    DraftQuote.is_active == True,
                )
                .values(is_active=False)
            )
            await session.commit()
    except Exception as exc:
        logger.warning(
            "draft_quote_deactivation_failed",
            conversation_id=conversation_id,
            error=str(exc),
        )


async def _load_active_draft_quote(
    conversation_id: str,
) -> Any | None:
    """
    Load the active DraftQuote for a conversation from the database.

    Returns None if no active draft exists or if an error occurs.

    Args:
        conversation_id: Conversation UUID as string.

    Returns:
        DraftQuote ORM instance or None.
    """
    from database.connection import get_async_session
    from database.models import DraftQuote

    try:
        async with get_async_session() as session:
            conv_uuid = await _resolve_conversation_uuid(session, conversation_id)
            if conv_uuid is None:
                return None

            result = await session.execute(
                select(DraftQuote).where(
                    DraftQuote.conversation_id == conv_uuid,
                    DraftQuote.is_active == True,
                )
            )
            return result.scalar_one_or_none()

    except Exception as exc:
        logger.warning(
            "draft_quote_load_failed",
            conversation_id=conversation_id,
            error=str(exc),
        )
        return None
