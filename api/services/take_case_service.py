"""
MSI Automotive — TakeCaseService.

Extracted DB logic for the "take case" operation, shared between:
  - POST /api/admin/cases/{id}/take          (route layer keeps Chatwoot side-effects)
  - EscalationAssignmentService.assign()     (Rule 5: promote Case when assigning escalation)

Public API
----------
    svc = TakeCaseService(session)
    case, escalation = await svc.take_case_internal(case_id, admin_user_id)

The method is wrapped in the caller's transaction — it does NOT open its own
session.  It calls session.commit() once at the end.

Chatwoot side-effects (agent assignment, WhatsApp template) are intentionally
kept in the route layer so this service remains unit-testable with a mocked session.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.services.exceptions import CaseNotFoundError, CaseNotInPendingReviewError
from database.models import Case, ConversationHistory, Escalation

_log = structlog.get_logger(__name__)


class TakeCaseService:
    """
    Owns the DB-side of taking a case (Case → in_progress + Escalation assignment).

    All mutations are committed at the end of take_case_internal.
    The caller (route or EscalationAssignmentService) handles Chatwoot side-effects
    and any additional HTTP response construction.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def take_case_internal(
        self,
        case_id: uuid.UUID,
        admin_user_id: uuid.UUID,
        *,
        _from_assignment: bool = False,
    ) -> tuple[Case, Escalation | None]:
        """
        Promote a Case to in_progress and link/create its Escalation.

        Args:
            case_id:           UUID of the Case to take.
            admin_user_id:     AdminUser taking the case.
            _from_assignment:  When True (called from EscalationAssignmentService),
                               skip all Escalation create/assign logic — the caller
                               already handled the Escalation.

        Returns:
            Tuple of (case, escalation_or_none).

        Raises:
            CaseNotFoundError:           Case not found.
            CaseNotInPendingReviewError: Case status is not pending_review
                                         (and not in_progress for idempotency).
        """
        logger = _log.bind(
            case_id=str(case_id),
            admin_user_id=str(admin_user_id),
            from_assignment=_from_assignment,
        )

        # ------------------------------------------------------------------
        # 1. Load Case (SELECT FOR UPDATE to serialize concurrent takes)
        # ------------------------------------------------------------------
        stmt = (
            select(Case)
            .options(selectinload(Case.user))
            .where(Case.id == case_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        case = result.scalar_one_or_none()

        if case is None:
            logger.warning("take_case_not_found")
            raise CaseNotFoundError(case_id)

        # ------------------------------------------------------------------
        # 2. Status guard + idempotency
        # ------------------------------------------------------------------
        if case.status == "in_progress":
            # Already taken — idempotent return (Scenario 4.5)
            logger.info("take_case_idempotent", status=case.status)
            return case, None

        if case.status != "pending_review":
            logger.warning("take_case_invalid_status", status=case.status)
            raise CaseNotInPendingReviewError(case_id, case.status)

        # ------------------------------------------------------------------
        # 3. Promote Case to in_progress
        # ------------------------------------------------------------------
        now = datetime.now(UTC)
        case.status = "in_progress"
        case.updated_at = now

        # Append timestamped note (same format as the original route)
        timestamp = now.strftime("%Y-%m-%d %H:%M")
        note = f"[{timestamp}] Expediente tomado por agente {admin_user_id}"
        case.notes = f"{case.notes or ''}\n{note}".strip()

        logger.info("take_case_promoted", conversation_id=case.conversation_id)

        # ------------------------------------------------------------------
        # 4. First-pause-wins: write bot_paused_at to ConversationHistory
        # ------------------------------------------------------------------
        escalation: Escalation | None = None

        conv_stmt = select(ConversationHistory).where(
            ConversationHistory.conversation_id == case.conversation_id
        )
        conv_result = await self.session.execute(conv_stmt)
        conv = conv_result.scalar_one_or_none()

        if conv is not None:
            if conv.bot_paused_at is None:
                conv.bot_paused_at = now
                conv.bot_paused_by_user_id = admin_user_id
                conv.bot_pause_reason = f"Case taken via /cases/{case_id}/take"
                logger.info(
                    "take_case_bot_paused",
                    conversation_id=case.conversation_id,
                )
            else:
                logger.info(
                    "take_case_first_pause_wins_noop",
                    conversation_id=case.conversation_id,
                    existing_paused_at=str(conv.bot_paused_at),
                )
        else:
            logger.warning(
                "take_case_conv_history_not_found",
                conversation_id=case.conversation_id,
            )

        # ------------------------------------------------------------------
        # 5. Escalation logic — skipped when called from EscalationAssignmentService
        # ------------------------------------------------------------------
        if not _from_assignment:
            esc_stmt = (
                select(Escalation)
                .where(
                    Escalation.conversation_id == case.conversation_id,
                    Escalation.status.in_(["pending", "assigned"]),
                )
                .order_by(Escalation.triggered_at.desc())
                .limit(1)
            )
            esc_result = await self.session.execute(esc_stmt)
            existing_esc = esc_result.scalar_one_or_none()

            if existing_esc is not None:
                if existing_esc.status == "pending":
                    # Assign the pending escalation
                    existing_esc.status = "assigned"
                    existing_esc.assigned_to_user_id = admin_user_id
                    existing_esc.assigned_at = now
                    escalation = existing_esc
                    logger.info(
                        "take_case_escalation_assigned",
                        escalation_id=str(existing_esc.id),
                    )
                else:
                    # Already assigned — idempotent, don't reassign
                    escalation = existing_esc
                    logger.info(
                        "take_case_escalation_already_assigned",
                        escalation_id=str(existing_esc.id),
                        assigned_to=str(existing_esc.assigned_to_user_id),
                    )
            else:
                # No linked Escalation — create one
                new_esc = Escalation(
                    conversation_id=case.conversation_id,
                    source="case_completion",
                    status="assigned",
                    assigned_to_user_id=admin_user_id,
                    assigned_at=now,
                    triggered_at=now,
                    reason=f"Case taken via /cases/{case_id}/take",
                    user_id=case.user_id,
                )
                self.session.add(new_esc)
                await self.session.flush()  # Get PK before commit
                escalation = new_esc
                logger.info(
                    "take_case_escalation_created",
                    escalation_id=str(new_esc.id),
                    conversation_id=case.conversation_id,
                )

        # ------------------------------------------------------------------
        # 6. Commit (single transaction boundary)
        # ------------------------------------------------------------------
        await self.session.commit()
        logger.info("take_case_committed", escalation_id=str(escalation.id) if escalation else None)

        return case, escalation
