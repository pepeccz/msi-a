"""
MSI-a — Idempotent case creation helper.

Provides `get_or_create_active_case()` which is a concurrency-safe helper
for creating or retrieving the active expediente for a user.

Uses the INSERT ... ON CONFLICT DO NOTHING + SELECT pattern to handle
race conditions when multiple concurrent requests (e.g. webhook retries)
attempt to create a case for the same user simultaneously.

The partial unique index ``uq_cases_user_active`` on
``cases(user_id) WHERE status IN ('collecting', 'pending_images') AND user_id IS NOT NULL``
(created by migration 039) enforces at most one active case per particular user
at the database level.

Professional users bypass this constraint — they may have multiple active
cases simultaneously (different conversations/vehicles).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from database.connection import get_async_session
from database.models import Case

logger = structlog.get_logger(__name__)

# Statuses that represent an actively-worked case (not yet submitted/closed).
# Matches the partial unique index ``uq_cases_user_active`` and the constants
# used in ``_get_active_case_for_user()`` in ``case_tools.py``.
ACTIVE_STATUSES: list[str] = ["collecting", "pending_images"]


async def get_or_create_active_case(
    *,
    user_id: str | None,
    conversation_id: str,
    category_id: str | None = None,
    element_codes: list[str] | None = None,
    tariff_tier_id: str | None = None,
    tariff_amount: float | None = None,
    client_type: str | None = None,
) -> tuple[Case, bool]:
    """Get existing active case or create a new one.  Idempotent.

    Uses INSERT ... ON CONFLICT DO NOTHING + SELECT pattern for particulars
    (who have the ``uq_cases_user_active`` partial unique index).

    For **professionals** (``client_type == "professional"``), the uniqueness
    check is skipped because business rules allow multiple simultaneous
    expedientes.

    When ``user_id`` is ``None`` (new users without a DB record), the function
    falls back to a conversation-scoped SELECT before attempting INSERT.
    The partial unique index does not cover ``user_id IS NULL`` rows, so the
    application-level SELECT provides the guard in this edge case.

    Args:
        user_id: Database UUID string of the user (may be None for new users).
        conversation_id: Chatwoot conversation ID (required).
        category_id: Vehicle category UUID string (optional, used on creation).
        element_codes: List of element codes to homologate (optional).
        tariff_tier_id: UUID string of the tariff tier (optional).
        tariff_amount: Calculated price without VAT (optional).
        client_type: ``"particular"`` | ``"professional"`` | ``None``.

    Returns:
        ``(case, created)`` — ``created=True`` if a new case was inserted,
        ``False`` if an existing active case was found.

    Raises:
        RuntimeError: If the case could not be created or retrieved after
            the INSERT + SELECT cycle (should never happen in practice).
    """
    # ------------------------------------------------------------------
    # Step 1: Try to find an existing active case
    # ------------------------------------------------------------------
    existing = await _find_active_case(
        user_id=user_id,
        conversation_id=conversation_id,
        client_type=client_type,
    )
    if existing is not None:
        logger.info(
            "get_or_create_active_case_found_existing",
            case_id=str(existing.id),
            user_id=user_id,
            conversation_id=conversation_id,
            client_type=client_type,
        )
        return existing, False

    # ------------------------------------------------------------------
    # Step 2: No existing case — attempt to create a new one
    # ------------------------------------------------------------------
    case_id = uuid.uuid4()
    user_uuid = uuid.UUID(user_id) if user_id else None
    category_uuid = uuid.UUID(category_id) if category_id else None
    tier_uuid = uuid.UUID(tariff_tier_id) if tariff_tier_id else None
    amount = Decimal(str(tariff_amount)) if tariff_amount is not None else None

    values: dict[str, Any] = {
        "id": case_id,
        "conversation_id": conversation_id,
        "user_id": user_uuid,
        "status": "collecting",
        "category_id": category_uuid,
        "element_codes": element_codes or [],
        "tariff_tier_id": tier_uuid,
        "tariff_amount": amount,
        "metadata_": {
            "started_at": datetime.now(UTC).isoformat(),
            "current_step": "collect_element_data",
        },
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }

    is_particular = client_type != "professional"

    try:
        async with get_async_session() as session:
            if is_particular and user_uuid is not None:
                # ----------------------------------------------------------
                # Particular with known user_id → use INSERT ON CONFLICT
                # leveraging the ``uq_cases_user_active`` partial unique index.
                # ----------------------------------------------------------
                insert_stmt = (
                    insert(Case)
                    .values(**values)
                    .on_conflict_do_nothing(
                        constraint="uq_cases_user_active",
                    )
                )
                result = await session.execute(insert_stmt)
                await session.commit()

                # Check if our INSERT actually created a row
                inserted = result.rowcount > 0  # type: ignore[union-attr]

                if inserted:
                    # Re-SELECT to get the full ORM object with relationships
                    case = await _select_case_by_id(session, case_id)
                    if case is not None:
                        logger.info(
                            "get_or_create_active_case_created",
                            case_id=str(case_id),
                            user_id=user_id,
                            conversation_id=conversation_id,
                        )
                        return case, True

                # Our INSERT was a no-op (conflict) → another row won the race.
                # SELECT the winner.
                winner = await _select_active_case_for_user(session, user_uuid)
                if winner is not None:
                    logger.info(
                        "get_or_create_active_case_conflict_resolved",
                        case_id=str(winner.id),
                        user_id=user_id,
                        conversation_id=conversation_id,
                    )
                    return winner, False

                # Fallback: neither our row nor a conflicting row — shouldn't happen
                raise RuntimeError(
                    f"INSERT ON CONFLICT produced no row and no existing case "
                    f"found for user_id={user_id}"
                )
            else:
                # ----------------------------------------------------------
                # Professional OR user_id is None → plain INSERT (no conflict
                # constraint to leverage).  The application-level SELECT in
                # Step 1 already checked for duplicates.
                # ----------------------------------------------------------
                case = Case(**values)
                session.add(case)
                await session.commit()
                await session.refresh(case)

                logger.info(
                    "get_or_create_active_case_created",
                    case_id=str(case.id),
                    user_id=user_id,
                    conversation_id=conversation_id,
                    client_type=client_type,
                )
                return case, True

    except Exception:
        logger.error(
            "get_or_create_active_case_failed",
            user_id=user_id,
            conversation_id=conversation_id,
            client_type=client_type,
            exc_info=True,
        )
        raise


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _find_active_case(
    *,
    user_id: str | None,
    conversation_id: str,
    client_type: str | None,
) -> Case | None:
    """Find an existing active case using the appropriate query strategy.

    - **Particulars with user_id**: query by ``user_id`` (cross-conversation
      awareness — catches cases started in a different WhatsApp thread).
    - **Particulars without user_id**: query by ``conversation_id`` (fallback
      for new users without a DB record).
    - **Professionals**: query by ``conversation_id`` (resume same-thread case
      only; they may have other active cases in different conversations).

    Returns:
        The most recent active ``Case`` or ``None``.
    """
    try:
        async with get_async_session() as session:
            is_particular = client_type != "professional"

            if is_particular and user_id:
                return await _select_active_case_for_user(
                    session, uuid.UUID(user_id),
                )
            else:
                # Professional or user_id is None → scope to conversation
                result = await session.execute(
                    select(Case)
                    .where(Case.conversation_id == conversation_id)
                    .where(Case.status.in_(ACTIVE_STATUSES))
                    .order_by(Case.created_at.desc())
                    .limit(1)
                )
                return result.scalar_one_or_none()

    except Exception:
        logger.error(
            "find_active_case_failed",
            user_id=user_id,
            conversation_id=conversation_id,
            client_type=client_type,
            exc_info=True,
        )
        return None


async def _select_active_case_for_user(
    session: Any,
    user_uuid: uuid.UUID,
) -> Case | None:
    """SELECT the most recent active case for a given user within a session."""
    result = await session.execute(
        select(Case)
        .where(Case.user_id == user_uuid)
        .where(Case.status.in_(ACTIVE_STATUSES))
        .order_by(Case.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _select_case_by_id(
    session: Any,
    case_id: uuid.UUID,
) -> Case | None:
    """SELECT a case by its primary key within a session."""
    result = await session.execute(
        select(Case).where(Case.id == case_id)
    )
    return result.scalar_one_or_none()
