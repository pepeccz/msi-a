"""
MSI Automotive — EscalationAssignmentService.

Owns the full lifecycle of Escalation assignment:
  - assign()   : pending → assigned  (SELECT FOR UPDATE, first-pause-wins bot gate)
  - unassign() : assigned → pending  (does NOT touch bot_paused_at per spec 1.6)
  - resolve()  : any → resolved      (does NOT auto-resume bot per spec 1.7)

All mutations are atomic (single session.commit() per method).
Rule 5 (promote linked Case to in_progress) and Rule 7 (cascade resolve linked Case)
are stubs; wired in slices C2.5 and C2.6 respectively.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.exceptions import (
    EscalationAlreadyAssignedError,
    EscalationAlreadyResolvedError,
    EscalationNotFoundError,
    InvalidAssigneeError,
)
from database.models import AdminUser, ConversationHistory, Escalation

_log = structlog.get_logger(__name__)


class EscalationAssignmentService:
    """
    Service for the Escalation assignment lifecycle.

    All public methods operate inside a single DB transaction (commit once).
    The session is injected by the caller (route layer via FastAPI Depends).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # assign
    # ------------------------------------------------------------------

    async def assign(
        self,
        escalation_id: uuid.UUID,
        assignee_user_id: uuid.UUID,
        current_user: AdminUser,
    ) -> Escalation:
        """
        Assign an Escalation to an admin user.

        Atomically:
          1. SELECT FOR UPDATE the Escalation row.
          2. Validate existence (404), status (409), assignee (422).
          3. Write status='assigned', assigned_to_user_id, assigned_at=NOW().
          4. First-pause-wins: set ConversationHistory.bot_paused_at if NULL.
          5. Rule 5 stub: promote linked Case (wired in C2.5).
          6. commit().

        Returns:
            The updated Escalation row.

        Raises:
            EscalationNotFoundError: Escalation row not found.
            EscalationAlreadyResolvedError: Escalation is already resolved.
            EscalationAlreadyAssignedError: Escalation is assigned to a different agent.
            InvalidAssigneeError: Assignee does not exist or is not active.
        """
        logger = _log.bind(
            escalation_id=str(escalation_id),
            assignee_user_id=str(assignee_user_id),
            caller=str(current_user.id),
        )

        # 1. SELECT FOR UPDATE — serialize concurrent assign attempts
        stmt = (
            select(Escalation)
            .where(Escalation.id == escalation_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        escalation = result.scalar_one_or_none()

        if escalation is None:
            logger.warning("escalation_assign_not_found")
            raise EscalationNotFoundError(escalation_id)

        # 2a. Already resolved → conflict
        if escalation.status == "resolved":
            logger.warning("escalation_assign_already_resolved", status=escalation.status)
            raise EscalationAlreadyResolvedError(escalation_id)

        # 2b. Already assigned to a *different* agent → conflict
        if (
            escalation.status == "assigned"
            and escalation.assigned_to_user_id != assignee_user_id
        ):
            logger.warning(
                "escalation_assign_already_taken",
                current_assignee=str(escalation.assigned_to_user_id),
            )
            raise EscalationAlreadyAssignedError(
                escalation_id, escalation.assigned_to_user_id
            )

        # 2c. Idempotent: already assigned to the same agent → return as-is
        if (
            escalation.status == "assigned"
            and escalation.assigned_to_user_id == assignee_user_id
        ):
            logger.info("escalation_assign_idempotent")
            return escalation

        # 3. Validate assignee
        assignee: AdminUser | None = await self.session.get(AdminUser, assignee_user_id)
        if assignee is None or not assignee.is_active:
            logger.warning(
                "escalation_assign_invalid_assignee",
                exists=assignee is not None,
                is_active=getattr(assignee, "is_active", False),
            )
            raise InvalidAssigneeError(assignee_user_id)

        # 4. Write assignment fields
        now = datetime.now(UTC)
        escalation.status = "assigned"
        escalation.assigned_to_user_id = assignee_user_id
        escalation.assigned_at = now

        # 5. First-pause-wins: update ConversationHistory.bot_paused_at only if NULL
        conv_stmt = select(ConversationHistory).where(
            ConversationHistory.conversation_id == escalation.conversation_id
        )
        conv_result = await self.session.execute(conv_stmt)
        conv = conv_result.scalar_one_or_none()

        if conv is not None:
            if conv.bot_paused_at is None:
                conv.bot_paused_at = now
                conv.bot_paused_by_user_id = current_user.id
                conv.bot_pause_reason = "Escalation assigned via /assign"
                logger.info("escalation_assign_bot_paused", conversation_id=escalation.conversation_id)
            else:
                logger.info(
                    "escalation_assign_first_pause_wins_noop",
                    conversation_id=escalation.conversation_id,
                    existing_paused_at=str(conv.bot_paused_at),
                )
        else:
            logger.warning(
                "escalation_assign_conv_history_not_found",
                conversation_id=escalation.conversation_id,
            )

        # TODO C2.5: promote linked Case to in_progress when status == 'pending_review'
        # Example stub:
        # case = await self._find_pending_review_case(escalation.conversation_id)
        # if case is not None:
        #     await TakeCaseService(self.session).take_case_internal(
        #         case.id, assignee_user_id, _from_assignment=True
        #     )

        await self.session.commit()
        logger.info("escalation_assigned", status=escalation.status)

        # Reload after commit to pick up relationship lazy-loads
        reload_stmt = (
            select(Escalation)
            .where(Escalation.id == escalation_id)
        )
        reload_result = await self.session.execute(reload_stmt)
        reloaded = reload_result.scalar_one_or_none()
        return reloaded if reloaded is not None else escalation

    # ------------------------------------------------------------------
    # unassign
    # ------------------------------------------------------------------

    async def unassign(
        self,
        escalation_id: uuid.UUID,
        current_user: AdminUser,
    ) -> Escalation:
        """
        Release an assigned Escalation back to 'pending' status.

        Per spec 1.6: does NOT touch ConversationHistory.bot_paused_at.
        The bot remains paused — only a manual resume or case resolution clears it.

        Raises:
            EscalationNotFoundError: Escalation row not found.
            EscalationAlreadyAssignedError: Used as sentinel for "wrong state"
                (spec maps non-assigned unassign to 409).
        """
        logger = _log.bind(
            escalation_id=str(escalation_id),
            caller=str(current_user.id),
        )

        stmt = (
            select(Escalation)
            .where(Escalation.id == escalation_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        escalation = result.scalar_one_or_none()

        if escalation is None:
            logger.warning("escalation_unassign_not_found")
            raise EscalationNotFoundError(escalation_id)

        if escalation.status != "assigned":
            logger.warning(
                "escalation_unassign_invalid_status", status=escalation.status
            )
            raise EscalationAlreadyAssignedError(escalation_id, None)

        # Reset assignment fields — bot_paused_at intentionally NOT touched
        escalation.status = "pending"
        escalation.assigned_to_user_id = None
        escalation.assigned_at = None

        await self.session.commit()
        logger.info("escalation_unassigned")

        # Reload
        reload_stmt = select(Escalation).where(Escalation.id == escalation_id)
        reload_result = await self.session.execute(reload_stmt)
        reloaded = reload_result.scalar_one_or_none()
        return reloaded if reloaded is not None else escalation

    # ------------------------------------------------------------------
    # resolve
    # ------------------------------------------------------------------

    async def resolve(
        self,
        escalation_id: uuid.UUID,
        current_user: AdminUser,
    ) -> Escalation:
        """
        Mark an Escalation as resolved.

        Per spec 1.7: does NOT clear ConversationHistory.bot_paused_at.
        Bot resumption is a separate explicit action.

        Idempotent: returns unchanged if already resolved (HTTP 200 per spec 4.5).

        Raises:
            EscalationNotFoundError: Escalation row not found.
            EscalationAlreadyResolvedError: Already resolved (→ 409).
        """
        logger = _log.bind(
            escalation_id=str(escalation_id),
            caller=str(current_user.id),
        )

        stmt = (
            select(Escalation)
            .where(Escalation.id == escalation_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        escalation = result.scalar_one_or_none()

        if escalation is None:
            logger.warning("escalation_resolve_not_found")
            raise EscalationNotFoundError(escalation_id)

        if escalation.status == "resolved":
            logger.warning("escalation_resolve_already_resolved")
            raise EscalationAlreadyResolvedError(escalation_id)

        now = datetime.now(UTC)
        escalation.status = "resolved"
        escalation.resolved_at = now
        escalation.resolved_by_user_id = current_user.id

        # TODO C2.6: cascade-resolve linked Case if any
        # Example stub:
        # await self._cascade_resolve_case(escalation.conversation_id, current_user)

        await self.session.commit()
        logger.info("escalation_resolved", status=escalation.status)

        # Reload
        reload_stmt = select(Escalation).where(Escalation.id == escalation_id)
        reload_result = await self.session.execute(reload_stmt)
        reloaded = reload_result.scalar_one_or_none()
        return reloaded if reloaded is not None else escalation
