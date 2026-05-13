"""
MSI Automotive — Escalations Router.

Dedicated router for the Escalation assignment lifecycle.
Prefix: /api/admin/escalations

Endpoints moved FROM api/routes/admin.py:
  GET  /                          — list with pagination + status filter
  GET  /stats                     — aggregate statistics (by_status keys: pending/assigned/resolved)
  GET  /{escalation_id}           — single escalation detail
  POST /{escalation_id}/resolve   — mark resolved (delegates to EscalationAssignmentService)

NEW endpoints:
  POST /{escalation_id}/assign    — assign to an admin user (SELECT FOR UPDATE)
  POST /{escalation_id}/unassign  — release back to pending

Exception → HTTP mapping (applied here at the route boundary):
  EscalationNotFoundError         → 404
  EscalationAlreadyAssignedError  → 409
  EscalationAlreadyResolvedError  → 409
  InvalidAssigneeError            → 422

Registration order: register THIS router BEFORE admin.router in api/main.py to
avoid path-shadowing (same pattern as conversations_admin.router).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from api.models.escalation import (
    AssignedToSummary,
    EscalationAssignRequest,
    EscalationListResponse,
    EscalationResponse,
)
from api.routes.admin import get_current_user, require_role
from api.services.escalation_assignment_service import EscalationAssignmentService
from api.services.exceptions import (
    EscalationAlreadyAssignedError,
    EscalationAlreadyResolvedError,
    EscalationNotFoundError,
    InvalidAssigneeError,
)
from database.connection import get_async_session
from database.models import AdminUser, Escalation

_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/admin/escalations", tags=["escalations"])

# Known statuses for zero-filling stats (ordered for UI display)
_KNOWN_STATUSES: list[str] = ["pending", "assigned", "resolved"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _escalation_to_response(esc: Escalation) -> dict[str, Any]:
    """
    Serialize an Escalation ORM object to a JSON-serializable dict.

    Uses the same field names as EscalationResponse to stay consistent
    with Pydantic validation at the HTTP boundary.
    """
    assigned_to: dict[str, Any] | None = None
    if esc.assigned_to_user is not None:
        u = esc.assigned_to_user
        assigned_to = {
            "id": str(u.id),
            "username": u.username,
            "display_name": u.display_name,
            "role": u.role,
        }

    resolved_by: dict[str, Any] | None = None
    if esc.resolved_by_user is not None:
        u = esc.resolved_by_user
        resolved_by = {
            "id": str(u.id),
            "username": u.username,
            "display_name": u.display_name,
            "role": u.role,
        }

    user_phone: str | None = None
    if esc.user is not None:
        user_phone = esc.user.phone

    return {
        "id": str(esc.id),
        "conversation_id": esc.conversation_id,
        "user_id": str(esc.user_id) if esc.user_id else None,
        "user_phone": user_phone,
        "reason": esc.reason,
        "source": esc.source,
        "status": esc.status,
        "triggered_at": esc.triggered_at.isoformat(),
        "assigned_to_user_id": str(esc.assigned_to_user_id) if esc.assigned_to_user_id else None,
        "assigned_to": assigned_to,
        "assigned_at": esc.assigned_at.isoformat() if esc.assigned_at else None,
        "resolved_at": esc.resolved_at.isoformat() if esc.resolved_at else None,
        "resolved_by_user_id": (
            str(esc.resolved_by_user_id) if esc.resolved_by_user_id else None
        ),
        "resolved_by": resolved_by,
        "metadata_": esc.metadata_,
    }


# ---------------------------------------------------------------------------
# Read endpoints (moved from admin.py)
# ---------------------------------------------------------------------------


@router.get("")
async def list_escalations(
    current_user: AdminUser = Depends(get_current_user),
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    assigned_to_user_id: uuid.UUID | None = None,
) -> JSONResponse:
    """
    List escalations with pagination and optional filters.

    Query params:
        limit:              Max items to return (default 50)
        offset:             Number of items to skip
        status:             Filter by status (pending, assigned, resolved)
        assigned_to_user_id: Filter by assigned admin user UUID

    Returns:
        Paginated list of escalations with full assigned_to summary.
    """
    async with get_async_session() as session:
        # Build count query
        count_query = select(func.count(Escalation.id))
        if status:
            count_query = count_query.where(Escalation.status == status)
        if assigned_to_user_id:
            count_query = count_query.where(
                Escalation.assigned_to_user_id == assigned_to_user_id
            )
        total = await session.scalar(count_query) or 0

        # Build list query with relationship preloading
        query = (
            select(Escalation)
            .options(
                selectinload(Escalation.assigned_to_user),
                selectinload(Escalation.resolved_by_user),
                selectinload(Escalation.user),
            )
            .order_by(Escalation.triggered_at.desc())
        )
        if status:
            query = query.where(Escalation.status == status)
        if assigned_to_user_id:
            query = query.where(
                Escalation.assigned_to_user_id == assigned_to_user_id
            )
        query = query.offset(offset).limit(limit)

        result = await session.execute(query)
        escalations = result.scalars().all()

        return JSONResponse(
            content={
                "items": [_escalation_to_response(e) for e in escalations],
                "total": total,
                "has_more": offset + len(escalations) < total,
            }
        )


@router.get("/stats")
async def get_escalation_stats(
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Escalation statistics for the admin dashboard.

    Returns:
        pending:         Total pending escalations.
        assigned:        Total assigned escalations.
        resolved_today:  Escalations resolved today (UTC).
        total_today:     Escalations triggered today (UTC).
        by_status:       Per-status counts, zero-filled for pending/assigned/resolved.
    """
    async with get_async_session() as session:
        today_start = datetime.now(UTC).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        pending_count = (
            await session.scalar(
                select(func.count(Escalation.id)).where(Escalation.status == "pending")
            )
            or 0
        )
        assigned_count = (
            await session.scalar(
                select(func.count(Escalation.id)).where(Escalation.status == "assigned")
            )
            or 0
        )
        resolved_today = (
            await session.scalar(
                select(func.count(Escalation.id)).where(
                    Escalation.status == "resolved",
                    Escalation.resolved_at >= today_start,
                )
            )
            or 0
        )
        total_today = (
            await session.scalar(
                select(func.count(Escalation.id)).where(
                    Escalation.triggered_at >= today_start,
                )
            )
            or 0
        )

        # Per-status counts for FilterChips — always zero-fill all known statuses
        by_status_result = await session.execute(
            select(Escalation.status, func.count(Escalation.id)).group_by(
                Escalation.status
            )
        )
        by_status: dict[str, int] = {s: 0 for s in _KNOWN_STATUSES}
        for s, count in by_status_result.all():
            by_status[s] = int(count)

        return JSONResponse(
            content={
                "pending": pending_count,
                "assigned": assigned_count,
                "resolved_today": resolved_today,
                "total_today": total_today,
                "by_status": by_status,
            }
        )


@router.get("/{escalation_id}")
async def get_escalation(
    escalation_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Get a single escalation by ID.

    Returns:
        Full escalation detail including assigned_to and resolved_by summaries.
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(Escalation)
            .options(
                selectinload(Escalation.assigned_to_user),
                selectinload(Escalation.resolved_by_user),
                selectinload(Escalation.user),
            )
            .where(Escalation.id == escalation_id)
        )
        escalation = result.scalar_one_or_none()
        if escalation is None:
            raise HTTPException(status_code=404, detail="Escalation not found")

        return JSONResponse(content=_escalation_to_response(escalation))


# ---------------------------------------------------------------------------
# Write endpoints (moved + new)
# ---------------------------------------------------------------------------


@router.post("/{escalation_id}/assign")
async def assign_escalation(
    escalation_id: uuid.UUID,
    body: EscalationAssignRequest,
    current_user: AdminUser = Depends(get_current_user),
    _: AdminUser = Depends(require_role("admin")),
) -> JSONResponse:
    """
    Assign an Escalation to an admin user.

    Uses SELECT FOR UPDATE to serialize concurrent assign attempts.

    Request body:
        assignee_user_id: UUID of the AdminUser to assign to.

    Returns:
        Updated EscalationResponse (HTTP 200, also for idempotent re-assignment
        to the same admin).

    Status codes:
        200 — success or idempotent.
        401 — unauthenticated.
        403 — non-admin role.
        404 — escalation not found.
        409 — already assigned to a different admin, or already resolved.
        422 — assignee_user_id is inactive or does not exist.
    """
    try:
        async with get_async_session() as session:
            svc = EscalationAssignmentService(session)
            escalation = await svc.assign(
                escalation_id=escalation_id,
                assignee_user_id=body.assignee_user_id,
                current_user=current_user,
            )
    except EscalationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except EscalationAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except EscalationAlreadyAssignedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except InvalidAssigneeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    _log.info(
        "escalation_assigned_via_api",
        escalation_id=str(escalation_id),
        assignee_user_id=str(body.assignee_user_id),
        assigned_by=str(current_user.id),
    )
    return JSONResponse(content=_escalation_to_response(escalation))


@router.post("/{escalation_id}/unassign")
async def unassign_escalation(
    escalation_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
    _: AdminUser = Depends(require_role("admin")),
) -> JSONResponse:
    """
    Release an assigned Escalation back to 'pending'.

    Per spec 1.6: does NOT touch ConversationHistory.bot_paused_at.
    The bot remains paused until explicitly resumed or the case is resolved.

    Returns:
        Updated EscalationResponse with status='pending'.

    Status codes:
        200 — success.
        401 — unauthenticated.
        403 — non-admin role.
        404 — escalation not found.
        409 — escalation is not currently assigned.
    """
    try:
        async with get_async_session() as session:
            svc = EscalationAssignmentService(session)
            escalation = await svc.unassign(
                escalation_id=escalation_id,
                current_user=current_user,
            )
    except EscalationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except EscalationAlreadyAssignedError as exc:
        # Used as sentinel for "wrong state" in unassign (not currently assigned)
        raise HTTPException(status_code=409, detail=str(exc))

    _log.info(
        "escalation_unassigned_via_api",
        escalation_id=str(escalation_id),
        unassigned_by=str(current_user.id),
    )
    return JSONResponse(content=_escalation_to_response(escalation))


@router.post("/{escalation_id}/resolve")
async def resolve_escalation(
    escalation_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
    _: AdminUser = Depends(require_role("admin")),
) -> JSONResponse:
    """
    Mark an Escalation as resolved.

    Per spec 1.7: does NOT clear ConversationHistory.bot_paused_at.
    Bot resumption is a separate explicit action.

    Returns:
        Updated EscalationResponse with status='resolved'.

    Status codes:
        200 — success.
        401 — unauthenticated.
        403 — non-admin role.
        404 — escalation not found.
        409 — already resolved.
    """
    try:
        async with get_async_session() as session:
            svc = EscalationAssignmentService(session)
            escalation = await svc.resolve(
                escalation_id=escalation_id,
                current_user=current_user,
            )
    except EscalationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except EscalationAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    _log.info(
        "escalation_resolved_via_api",
        escalation_id=str(escalation_id),
        resolved_by=str(current_user.id),
    )
    return JSONResponse(content=_escalation_to_response(escalation))
