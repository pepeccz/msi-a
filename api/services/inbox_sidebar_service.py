"""
Inbox sidebar service — aggregates client summary, active case, and notes
for the right-sidebar panel in the unified inbox.

Design refs: A1–A8 (inbox-enrichment design doc)

Query budget: ≤5 DB queries per get_sidebar_data call:
  1. Fetch ConversationHistory + User (load user_id)
  2. COUNT(cases) for user
  3. SUM(cases.tariff_amount) WHERE user_id=user AND status != 'cancelled'
     (total quoted to this customer — Invoice has no user_id FK)
  4. SELECT active case + element_data (selectinload)
  5. SELECT notes (already eager-loaded via selectinload on conversation)

Progress computation (design A7):
  No existing helper was found for required_fields_status in api/services/.
  Progress is computed here using Case.element_codes (list) and Case.element_data
  (list of CaseElementData). An element is "complete" when its CaseElementData
  status == "completed". If no element_data rows exist yet, total = len(element_codes),
  complete = 0.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.conversation_inbox import (
    ActiveCaseResponse,
    ClientSummaryResponse,
    CreateNoteRequest,
    NoteResponse,
    SidebarResponse,
)
from database.models import (
    AdminUser,
    Case,
    ConversationHistory,
    ConversationNote,
    User,
)

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Active case status exclusions (design A6)
# ---------------------------------------------------------------------------

_INACTIVE_STATUSES = frozenset({"resolved", "cancelled", "closed"})


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _compute_progress(case: Case) -> tuple[int, int, int]:
    """Compute (elements_total, elements_complete, progress_percent) for a case.

    Progress is derived from Case.element_codes (declared intent) and
    Case.element_data (collected per-element data rows).

    Design A7: reuse existing helper if one exists. No helper was found
    in api/services/ for this logic — implemented here instead.

    An element is "complete" when its CaseElementData.status == "completed".
    If no element_data rows exist yet, total = len(element_codes), complete = 0.
    """
    element_codes: list[str] = case.element_codes or []
    total = len(element_codes)

    if total == 0:
        return 0, 0, 0

    element_data_list = case.element_data or []
    complete = sum(1 for ed in element_data_list if ed.status == "completed")
    percent = int((complete / total) * 100)
    return total, complete, percent


def _serialize_note(note: ConversationNote, current_user: AdminUser) -> NoteResponse:
    """Build NoteResponse from ORM object, computing can_delete (design A5).

    can_delete = True when:
      - note.admin_user_id == current_user.id (author), OR
      - current_user.role == "admin" (admin override)
    """
    author_name: str | None
    if note.admin_user_id is None:
        author_name = "Eliminado"
    elif note.author is not None:
        author_name = note.author.display_name or note.author.username
    else:
        author_name = None

    can_delete = (
        note.admin_user_id == current_user.id
        or current_user.role == "admin"
    )

    return NoteResponse(
        id=note.id,
        author_name=author_name,
        content=note.content,
        created_at=note.created_at,
        can_delete=can_delete,
    )


async def _select_active_case(session: AsyncSession, user_id: uuid.UUID) -> Case | None:
    """Return the most-recent non-terminal case for user (design A6).

    Active = status NOT IN ('resolved', 'cancelled', 'closed')
    Sorted by updated_at DESC, LIMIT 1.
    """
    result = await session.execute(
        select(Case)
        .where(
            Case.user_id == user_id,
            Case.status.not_in(list(_INACTIVE_STATUSES)),
        )
        .options(
            selectinload(Case.category),
            selectinload(Case.tariff_tier),
            selectinload(Case.element_data),
        )
        .order_by(Case.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_sidebar_data(
    session: AsyncSession,
    conv_id: uuid.UUID,
    current_user: AdminUser,
) -> SidebarResponse:
    """Aggregate sidebar data for a conversation in ≤5 DB queries.

    Returns SidebarResponse with client, active_case, and notes fields.
    If the conversation has no linked user, all three fields are empty/null.
    """
    # Query 1 — load ConversationHistory with notes eager-loaded
    conv_result = await session.execute(
        select(ConversationHistory)
        .where(ConversationHistory.id == conv_id)
        .options(
            selectinload(ConversationHistory.user),
            selectinload(ConversationHistory.notes).selectinload(
                ConversationNote.author
            ),
        )
    )
    conv = conv_result.scalar_one_or_none()

    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user: User | None = conv.user

    if user is None:
        _log = logger.bind(conv_id=str(conv_id))
        _log.info("sidebar_loaded", has_user=False)
        return SidebarResponse(client=None, active_case=None, notes=[])

    user_id = user.id

    # Query 2 — COUNT cases for user (all statuses, including resolved)
    cases_count_result = await session.execute(
        select(func.count(Case.id)).where(Case.user_id == user_id)
    )
    cases_count: int = cases_count_result.scalar() or 0

    # Query 3 — SUM per-user billing: total contracted tariff amount for this user.
    # Invoice has no user_id FK (it is MSI's own SaaS billing, not per-customer).
    # Instead we sum Case.tariff_amount for all non-cancelled cases belonging to
    # this user — this is the real per-user financial figure (total quoted to them).
    billing_result = await session.execute(
        select(func.coalesce(func.sum(Case.tariff_amount), 0)).where(
            Case.user_id == user_id,
            Case.status.notin_(["cancelled"]),
        )
    )
    billed_total_raw = billing_result.scalar() or Decimal("0")
    billed_total_eur = float(billed_total_raw)

    # Compute last_activity_at from user.created_at as a fallback
    # (User model doesn't have a last_activity_at; use created_at)
    user_created_at = getattr(user, "created_at", None)
    user_last_activity = getattr(user, "last_activity_at", user_created_at)

    # Build client summary
    first_name: str | None = getattr(user, "first_name", None)
    last_name: str | None = getattr(user, "last_name", None)
    name_parts = [p for p in [first_name, last_name] if p]
    display_name = " ".join(name_parts) if name_parts else None

    client_summary = ClientSummaryResponse(
        user_id=user.id,
        name=display_name,
        phone=getattr(user, "phone", None),
        created_at=user_created_at,
        cases_count=cases_count,
        billed_total_eur=billed_total_eur,
        last_activity_at=user_last_activity,
    )

    # Query 4 — active case (selectinload already fetches category, tier, element_data)
    active_case = await _select_active_case(session, user_id)

    active_case_response: ActiveCaseResponse | None = None
    if active_case is not None:
        total, complete, percent = _compute_progress(active_case)

        category = active_case.category
        tier = active_case.tariff_tier
        client_type_label: str | None = None
        if category is not None:
            raw_ct = getattr(category, "client_type", None)
            if raw_ct == "particular":
                client_type_label = "Particular"
            elif raw_ct == "professional":
                client_type_label = "Profesional"
            else:
                client_type_label = raw_ct

        # Short case number: last 8 chars of UUID for display
        case_number_short = str(active_case.id)[-8:].upper()

        active_case_response = ActiveCaseResponse(
            id=active_case.id,
            case_number_short=case_number_short,
            status=active_case.status,
            category_name=category.name if category else None,
            client_type_label=client_type_label,
            tier_code=tier.code if tier else None,
            tier_price_eur=float(tier.price) if tier else None,
            elements_total=total,
            elements_complete=complete,
            progress_percent=percent,
        )

    # Query 5 — notes already loaded via selectinload in Query 1
    notes = conv.notes or []
    note_responses = [_serialize_note(n, current_user) for n in notes]

    logger.info(
        "sidebar_loaded",
        conv_id=str(conv_id),
        has_user=True,
        notes_count=len(note_responses),
        has_active_case=active_case_response is not None,
    )

    return SidebarResponse(
        client=client_summary,
        active_case=active_case_response,
        notes=note_responses,
    )


async def create_note(
    session: AsyncSession,
    conv_id: uuid.UUID,
    content: str,
    author: AdminUser,
) -> NoteResponse:
    """Create an internal note on a conversation.

    Returns the created NoteResponse with can_delete=True (author just created it).
    Raises 404 if conversation not found.
    """
    # Verify conversation exists
    conv_result = await session.execute(
        select(ConversationHistory).where(ConversationHistory.id == conv_id)
    )
    conv = conv_result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    note = ConversationNote(
        id=uuid.uuid4(),
        conversation_history_id=conv_id,
        admin_user_id=author.id,
        content=content,
    )
    session.add(note)
    await session.flush()  # assign created_at from DB default
    await session.refresh(note)

    logger.info(
        "note_created",
        conv_id=str(conv_id),
        note_id=str(note.id),
        author_id=str(author.id),
    )

    author_name = author.display_name or author.username
    return NoteResponse(
        id=note.id,
        author_name=author_name,
        content=note.content,
        created_at=note.created_at,
        can_delete=True,
    )


async def delete_note(
    session: AsyncSession,
    note_id: uuid.UUID,
    current_user: AdminUser,
) -> None:
    """Hard-delete a note with authorship enforcement (design A4).

    Authorship rules:
    - Author (note.admin_user_id == current_user.id) → allowed
    - admin role → allowed (override)
    - Any other case → 403

    Raises 404 if note not found, 403 if not authorized.
    """
    result = await session.execute(
        select(ConversationNote).where(ConversationNote.id == note_id)
    )
    note = result.scalar_one_or_none()

    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")

    is_author = note.admin_user_id == current_user.id
    is_admin = current_user.role == "admin"

    if not is_author and not is_admin:
        logger.warning(
            "note_delete_forbidden",
            note_id=str(note_id),
            requester_id=str(current_user.id),
            requester_role=current_user.role,
            author_id=str(note.admin_user_id),
        )
        raise HTTPException(
            status_code=403,
            detail="No tienes permiso para eliminar esta nota.",
        )

    await session.delete(note)
    await session.flush()

    logger.info(
        "note_deleted",
        note_id=str(note_id),
        deleted_by=str(current_user.id),
        was_admin_override=is_admin and not is_author,
    )
