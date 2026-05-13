"""
Unit tests for EscalationAssignmentService.

TDD cycle: RED → GREEN → REFACTOR

C2.2 covers:
  - test_assign_writes_four_fields_atomically          (Scenarios 1.1, 1.2)
  - test_assign_select_for_update_blocks_race          (Scenario 1.3 — verify query uses with_for_update)
  - test_assign_to_inactive_admin_rejected_422         (Scenario 1.5)
  - test_assign_to_nonexistent_escalation_404
  - test_assign_to_already_assigned_returns_409        (Scenario 1.3 happy half)
  - test_assign_first_pause_wins_when_already_paused   (invariant 3)
  - test_assign_first_pause_wins_when_bot_paused_at_null
  - test_unassign_does_not_clear_bot_paused_at         (Scenario 1.6)
  - test_unassign_returns_404_for_unknown
  - test_resolve_sets_resolved_fields_no_bot_resume    (Scenario 1.7)
  - test_resolve_pending_escalation_no_prior_assignment (Scenario 1.8)
  - test_resolve_already_resolved_returns_409

C2.5 covers:
  - test_assign_rule_5_promotes_pending_review_case    (Rule 5: Case in pending_review → promoted)
  - test_assign_rule_5_no_op_when_no_case             (Rule 4 verification: no Case auto-create)
  - test_assign_rule_5_no_op_when_case_in_other_status (Case not in pending_review → unchanged)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from api.services.exceptions import (
    EscalationAlreadyAssignedError,
    EscalationAlreadyResolvedError,
    EscalationNotFoundError,
    InvalidAssigneeError,
)
from api.services.escalation_assignment_service import EscalationAssignmentService
from api.services.exceptions import CaseNotInPendingReviewError


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _make_admin_user(
    *,
    user_id: uuid.UUID | None = None,
    is_active: bool = True,
    username: str = "agent01",
    display_name: str | None = "Agent One",
    role: str = "agent",
) -> MagicMock:
    """Build a mock AdminUser ORM object."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.username = username
    user.display_name = display_name
    user.role = role
    user.is_active = is_active
    return user


def _make_escalation(
    *,
    esc_id: uuid.UUID | None = None,
    status: str = "pending",
    conversation_id: str = "conv-42",
    assigned_to_user_id: uuid.UUID | None = None,
    resolved_at: datetime | None = None,
) -> MagicMock:
    """Build a mock Escalation ORM object."""
    esc = MagicMock()
    esc.id = esc_id or uuid.uuid4()
    esc.status = status
    esc.conversation_id = conversation_id
    esc.assigned_to_user_id = assigned_to_user_id
    esc.assigned_at = None
    esc.resolved_at = resolved_at
    esc.resolved_by_user_id = None
    return esc


def _make_conv_history(
    *,
    bot_paused_at: datetime | None = None,
    conversation_id: str = "conv-42",
) -> MagicMock:
    """Build a mock ConversationHistory ORM object."""
    conv = MagicMock()
    conv.id = uuid.uuid4()
    conv.conversation_id = conversation_id
    conv.bot_paused_at = bot_paused_at
    conv.bot_paused_by_user_id = None
    conv.bot_pause_reason = None
    return conv


def _make_session(
    *,
    escalation: MagicMock | None = None,
    assignee: MagicMock | None = None,
    conv_history: MagicMock | None = None,
    case: MagicMock | None = None,
) -> AsyncMock:
    """
    Build a mock AsyncSession.

    - session.execute() returns a result whose scalar_one_or_none() gives the escalation.
    - session.get() returns the assignee AdminUser (or None).
    - A second execute() call (for ConversationHistory) returns conv_history via scalar_one_or_none.
    - A third execute() call is for the Rule 5 Case query (returns case, default None).
    - A fourth execute() call (for reload) returns the escalation again.

    With case=None (default), Rule 5 finds no pending_review Case — TakeCaseService
    is never called, so no additional mock is needed for existing tests.
    """
    session = AsyncMock()

    # First execute call → escalation (SELECT FOR UPDATE)
    escalation_execute_result = MagicMock()
    escalation_execute_result.scalar_one_or_none.return_value = escalation

    # Second execute call → ConversationHistory
    conv_execute_result = MagicMock()
    conv_execute_result.scalar_one_or_none.return_value = conv_history

    # Third execute call → Case (Rule 5 query, default None = no pending_review case)
    case_execute_result = MagicMock()
    case_execute_result.scalar_one_or_none.return_value = case

    # Fourth execute call (for reload) → escalation again
    refresh_execute_result = MagicMock()
    refresh_execute_result.scalar_one_or_none.return_value = escalation

    session.execute = AsyncMock(
        side_effect=[
            escalation_execute_result,
            conv_execute_result,
            case_execute_result,
            refresh_execute_result,
        ]
    )

    # session.get() is used to look up the AdminUser
    session.get = AsyncMock(return_value=assignee)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    return session


def _make_session_for_unassign(
    *,
    escalation: MagicMock | None = None,
) -> AsyncMock:
    """Session mock for unassign (only needs escalation execute + refresh)."""
    session = AsyncMock()

    esc_result = MagicMock()
    esc_result.scalar_one_or_none.return_value = escalation

    refresh_result = MagicMock()
    refresh_result.scalar_one_or_none.return_value = escalation

    session.execute = AsyncMock(side_effect=[esc_result, refresh_result])
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock(return_value=None)
    return session


def _make_session_for_resolve(
    *,
    escalation: MagicMock | None = None,
) -> AsyncMock:
    """Session mock for resolve (only needs escalation execute + refresh)."""
    session = AsyncMock()

    esc_result = MagicMock()
    esc_result.scalar_one_or_none.return_value = escalation

    refresh_result = MagicMock()
    refresh_result.scalar_one_or_none.return_value = escalation

    session.execute = AsyncMock(side_effect=[esc_result, refresh_result])
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock(return_value=None)
    return session


# ---------------------------------------------------------------------------
# Tests: assign()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_writes_four_fields_atomically() -> None:
    """
    C2.2 — Scenarios 1.1, 1.2:
    assign() must atomically write:
      1. status = 'assigned'
      2. assigned_to_user_id = assignee_user_id
      3. assigned_at = NOW()
      4. ConversationHistory.bot_paused_at = NOW() (first-pause-wins, currently NULL)
    and call session.commit() exactly once.
    """
    assignee_id = uuid.uuid4()
    assignee = _make_admin_user(user_id=assignee_id, is_active=True)
    esc = _make_escalation(status="pending")
    conv = _make_conv_history(bot_paused_at=None)

    current_user = _make_admin_user(username="caller")
    session = _make_session(escalation=esc, assignee=assignee, conv_history=conv)

    svc = EscalationAssignmentService(session)
    result = await svc.assign(esc.id, assignee_id, current_user)

    # Four fields written
    assert esc.status == "assigned"
    assert esc.assigned_to_user_id == assignee_id
    assert esc.assigned_at is not None
    assert conv.bot_paused_at is not None

    # Single transaction commit
    session.commit.assert_awaited_once()

    # Returned object is the escalation
    assert result is esc


@pytest.mark.asyncio
async def test_assign_select_for_update_blocks_race() -> None:
    """
    C2.2 — Scenario 1.3:
    The first DB query MUST include with_for_update() to serialize concurrent assigns.
    We verify by inspecting the select statement passed to session.execute.
    """
    from sqlalchemy import select
    from database.models import Escalation

    assignee_id = uuid.uuid4()
    assignee = _make_admin_user(user_id=assignee_id, is_active=True)
    esc = _make_escalation(status="pending")
    conv = _make_conv_history(bot_paused_at=None)

    current_user = _make_admin_user(username="caller")

    captured_stmt: list = []

    async def capture_execute(stmt, *args, **kwargs):
        captured_stmt.append(stmt)
        result = MagicMock()
        if not captured_stmt or len(captured_stmt) == 1:
            result.scalar_one_or_none.return_value = esc
        elif len(captured_stmt) == 2:
            result.scalar_one_or_none.return_value = conv
        else:
            result.scalar_one_or_none.return_value = esc
        return result

    session = AsyncMock()
    session.execute = capture_execute
    session.get = AsyncMock(return_value=assignee)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    svc = EscalationAssignmentService(session)
    await svc.assign(esc.id, assignee_id, current_user)

    # First captured statement must carry the with_for_update modifier.
    # SQLAlchemy sets _for_update_arg to a ForUpdateArg object (truthy) when
    # with_for_update() is applied, and to None otherwise.
    first_stmt = captured_stmt[0]
    assert hasattr(first_stmt, "_for_update_arg"), \
        "Expected a SQLAlchemy Select statement as first execute argument"
    assert first_stmt._for_update_arg is not None, \
        "First query to session.execute must use with_for_update()"


@pytest.mark.asyncio
async def test_assign_to_inactive_admin_rejected_422() -> None:
    """
    C2.2 — Scenario 1.5:
    assign() raises InvalidAssigneeError when the assignee is not active.
    """
    assignee_id = uuid.uuid4()
    inactive_assignee = _make_admin_user(user_id=assignee_id, is_active=False)
    esc = _make_escalation(status="pending")

    current_user = _make_admin_user(username="caller")
    session = _make_session(escalation=esc, assignee=inactive_assignee, conv_history=None)

    svc = EscalationAssignmentService(session)
    with pytest.raises(InvalidAssigneeError):
        await svc.assign(esc.id, assignee_id, current_user)


@pytest.mark.asyncio
async def test_assign_to_nonexistent_escalation_404() -> None:
    """
    assign() raises EscalationNotFoundError when the escalation does not exist.
    """
    session = _make_session(escalation=None, assignee=None, conv_history=None)
    current_user = _make_admin_user()
    svc = EscalationAssignmentService(session)

    with pytest.raises(EscalationNotFoundError):
        await svc.assign(uuid.uuid4(), uuid.uuid4(), current_user)


@pytest.mark.asyncio
async def test_assign_to_already_assigned_returns_409() -> None:
    """
    C2.2 — Scenario 1.3 (conflict half):
    assign() raises EscalationAlreadyAssignedError when status is 'assigned'
    and the escalation belongs to a different agent.
    """
    other_agent_id = uuid.uuid4()
    new_agent_id = uuid.uuid4()

    esc = _make_escalation(status="assigned", assigned_to_user_id=other_agent_id)
    assignee = _make_admin_user(user_id=new_agent_id, is_active=True)

    current_user = _make_admin_user(username="caller")
    session = _make_session(escalation=esc, assignee=assignee, conv_history=None)

    svc = EscalationAssignmentService(session)
    with pytest.raises(EscalationAlreadyAssignedError):
        await svc.assign(esc.id, new_agent_id, current_user)


@pytest.mark.asyncio
async def test_assign_first_pause_wins_when_already_paused() -> None:
    """
    Invariant 3:
    When ConversationHistory.bot_paused_at is already set (not NULL),
    assign() MUST NOT overwrite it (first-pause-wins).
    """
    assignee_id = uuid.uuid4()
    assignee = _make_admin_user(user_id=assignee_id, is_active=True)
    esc = _make_escalation(status="pending")
    original_paused_at = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    conv = _make_conv_history(bot_paused_at=original_paused_at)

    current_user = _make_admin_user()
    session = _make_session(escalation=esc, assignee=assignee, conv_history=conv)

    svc = EscalationAssignmentService(session)
    await svc.assign(esc.id, assignee_id, current_user)

    # bot_paused_at must remain the original value (not overwritten)
    assert conv.bot_paused_at == original_paused_at


@pytest.mark.asyncio
async def test_assign_first_pause_wins_when_bot_paused_at_null() -> None:
    """
    When ConversationHistory.bot_paused_at is NULL, assign() MUST set it to NOW().
    """
    assignee_id = uuid.uuid4()
    assignee = _make_admin_user(user_id=assignee_id, is_active=True)
    esc = _make_escalation(status="pending")
    conv = _make_conv_history(bot_paused_at=None)

    current_user = _make_admin_user()
    session = _make_session(escalation=esc, assignee=assignee, conv_history=conv)

    svc = EscalationAssignmentService(session)
    await svc.assign(esc.id, assignee_id, current_user)

    assert conv.bot_paused_at is not None
    # Must be a timezone-aware datetime
    assert conv.bot_paused_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Tests: unassign()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unassign_does_not_clear_bot_paused_at() -> None:
    """
    C2.2 — Scenario 1.6:
    unassign() must NOT touch ConversationHistory.bot_paused_at.
    It only resets: status → 'pending', assigned_to_user_id → None, assigned_at → None.
    """
    agent_id = uuid.uuid4()
    paused_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    esc = _make_escalation(status="assigned", assigned_to_user_id=agent_id)

    current_user = _make_admin_user()
    session = _make_session_for_unassign(escalation=esc)

    svc = EscalationAssignmentService(session)
    result = await svc.unassign(esc.id, current_user)

    # Status reverted
    assert esc.status == "pending"
    assert esc.assigned_to_user_id is None
    assert esc.assigned_at is None

    # bot_paused_at NOT touched — service must not call any execute for ConversationHistory
    # (only 1-2 execute calls: the SELECT FOR UPDATE and optionally the reload)
    execute_calls = session.execute.call_count
    assert execute_calls <= 2, (
        f"unassign() must not query ConversationHistory; got {execute_calls} execute calls"
    )

    assert result is esc


@pytest.mark.asyncio
async def test_unassign_returns_404_for_unknown() -> None:
    """
    unassign() raises EscalationNotFoundError when escalation does not exist.
    """
    session = _make_session_for_unassign(escalation=None)
    current_user = _make_admin_user()
    svc = EscalationAssignmentService(session)

    with pytest.raises(EscalationNotFoundError):
        await svc.unassign(uuid.uuid4(), current_user)


# ---------------------------------------------------------------------------
# Tests: resolve()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_sets_resolved_fields_no_bot_resume() -> None:
    """
    C2.2 — Scenario 1.7:
    resolve() sets status='resolved', resolved_at=NOW(), resolved_by_user_id=current_user.id.
    It must NOT touch ConversationHistory.bot_paused_at.
    """
    agent_id = uuid.uuid4()
    esc = _make_escalation(status="assigned", assigned_to_user_id=agent_id)
    current_user = _make_admin_user(user_id=agent_id)

    session = _make_session_for_resolve(escalation=esc)

    svc = EscalationAssignmentService(session)
    result = await svc.resolve(esc.id, current_user)

    assert esc.status == "resolved"
    assert esc.resolved_at is not None
    assert esc.resolved_by_user_id == current_user.id

    # Must not query ConversationHistory (bot stays paused per spec 1.7)
    execute_calls = session.execute.call_count
    assert execute_calls <= 2, (
        f"resolve() must not query ConversationHistory; got {execute_calls} execute calls"
    )

    session.commit.assert_awaited_once()
    assert result is esc


@pytest.mark.asyncio
async def test_resolve_pending_escalation_no_prior_assignment() -> None:
    """
    C2.2 — Scenario 1.8:
    resolve() works on a 'pending' escalation (no prior assignment).
    Status becomes 'resolved' regardless.
    """
    esc = _make_escalation(status="pending")
    current_user = _make_admin_user()

    session = _make_session_for_resolve(escalation=esc)

    svc = EscalationAssignmentService(session)
    result = await svc.resolve(esc.id, current_user)

    assert esc.status == "resolved"
    assert esc.resolved_by_user_id == current_user.id


@pytest.mark.asyncio
async def test_resolve_already_resolved_returns_409() -> None:
    """
    resolve() raises EscalationAlreadyResolvedError if status is already 'resolved'.
    """
    esc = _make_escalation(
        status="resolved",
        resolved_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    current_user = _make_admin_user()

    session = _make_session_for_resolve(escalation=esc)

    svc = EscalationAssignmentService(session)
    with pytest.raises(EscalationAlreadyResolvedError):
        await svc.resolve(esc.id, current_user)


# ---------------------------------------------------------------------------
# Helpers for C2.5 Rule 5 tests
# ---------------------------------------------------------------------------


def _make_case(
    *,
    case_id: uuid.UUID | None = None,
    status: str = "pending_review",
    conversation_id: str = "conv-42",
) -> MagicMock:
    """Build a mock Case ORM object."""
    case = MagicMock()
    case.id = case_id or uuid.uuid4()
    case.status = status
    case.conversation_id = conversation_id
    case.updated_at = None
    case.notes = None
    return case


def _make_session_with_rule5(
    *,
    escalation: MagicMock | None = None,
    assignee: MagicMock | None = None,
    conv_history: MagicMock | None = None,
    case: MagicMock | None = None,
) -> AsyncMock:
    """
    Build a mock AsyncSession that supports the full assign() path including Rule 5:
      execute[0] → escalation (SELECT FOR UPDATE)
      execute[1] → conv_history (ConversationHistory)
      execute[2] → case (Case query for Rule 5)
      execute[3] → escalation (reload after commit)
    session.get() → assignee (AdminUser)
    """
    session = AsyncMock()

    esc_result = MagicMock()
    esc_result.scalar_one_or_none.return_value = escalation

    conv_result = MagicMock()
    conv_result.scalar_one_or_none.return_value = conv_history

    case_result = MagicMock()
    case_result.scalar_one_or_none.return_value = case

    reload_result = MagicMock()
    reload_result.scalar_one_or_none.return_value = escalation

    session.execute = AsyncMock(
        side_effect=[esc_result, conv_result, case_result, reload_result]
    )
    session.get = AsyncMock(return_value=assignee)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    return session


# ---------------------------------------------------------------------------
# Tests: C2.5 — Rule 5 coupling in assign()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_rule_5_promotes_pending_review_case() -> None:
    """
    Rule 5: When an Escalation is assigned and a linked Case is in 'pending_review',
    assign() must promote that Case to 'in_progress' by calling
    TakeCaseService.take_case_internal with _from_assignment=True.

    Coupling rule matrix reference: Rule 5 (Scenario 4.7).
    """
    assignee_id = uuid.uuid4()
    assignee = _make_admin_user(user_id=assignee_id, is_active=True)
    esc = _make_escalation(status="pending", conversation_id="conv-99")
    conv = _make_conv_history(bot_paused_at=None, conversation_id="conv-99")
    case = _make_case(status="pending_review", conversation_id="conv-99")

    current_user = _make_admin_user(username="caller")
    session = _make_session_with_rule5(
        escalation=esc, assignee=assignee, conv_history=conv, case=case
    )

    # Mock TakeCaseService so we don't need a full DB
    with patch(
        "api.services.escalation_assignment_service.TakeCaseService"
    ) as MockTCS:
        mock_tcs_instance = AsyncMock()
        mock_tcs_instance.take_case_internal = AsyncMock(return_value=(case, None))
        MockTCS.return_value = mock_tcs_instance

        svc = EscalationAssignmentService(session)
        await svc.assign(esc.id, assignee_id, current_user)

    # TakeCaseService must be called with the same session, case_id, assignee_id,
    # and _from_assignment=True
    MockTCS.assert_called_once_with(session)
    mock_tcs_instance.take_case_internal.assert_awaited_once_with(
        case.id, assignee_id, _from_assignment=True, _skip_commit=True
    )
    # Escalation fields written
    assert esc.status == "assigned"


@pytest.mark.asyncio
async def test_assign_rule_5_no_op_when_no_case() -> None:
    """
    Rule 4 verification: When assigning an Escalation with no linked Case,
    assign() must succeed WITHOUT creating a Case.

    Coupling rule matrix reference: Rule 4 (Scenario 4.6).
    """
    assignee_id = uuid.uuid4()
    assignee = _make_admin_user(user_id=assignee_id, is_active=True)
    esc = _make_escalation(status="pending", conversation_id="conv-no-case")
    conv = _make_conv_history(bot_paused_at=None, conversation_id="conv-no-case")

    current_user = _make_admin_user(username="caller")
    # case=None → no Case for this conversation
    session = _make_session_with_rule5(
        escalation=esc, assignee=assignee, conv_history=conv, case=None
    )

    with patch(
        "api.services.escalation_assignment_service.TakeCaseService"
    ) as MockTCS:
        mock_tcs_instance = AsyncMock()
        MockTCS.return_value = mock_tcs_instance

        svc = EscalationAssignmentService(session)
        await svc.assign(esc.id, assignee_id, current_user)

    # TakeCaseService must NOT be called when there is no Case
    mock_tcs_instance.take_case_internal.assert_not_called()
    # Escalation still assigned successfully
    assert esc.status == "assigned"
    # No new Case created — session.add not called with a Case
    for add_call in session.add.call_args_list:
        args = add_call[0]
        from database.models import Case as CaseModel
        assert not isinstance(args[0], CaseModel), "No Case must be created (Rule 4)"


@pytest.mark.asyncio
async def test_assign_rule_5_no_op_when_case_in_other_status() -> None:
    """
    Rule 5 only fires for Cases in 'pending_review'. The DB query in assign()
    filters by status='pending_review', so a Case in 'collecting' or 'in_progress'
    produces a NULL result (same as no Case). The test simulates this DB-level
    filtering by returning None from the mock session's 3rd execute call.

    Coupling rule matrix reference: Rule 5 scope constraint.
    """
    assignee_id = uuid.uuid4()
    assignee = _make_admin_user(user_id=assignee_id, is_active=True)
    esc = _make_escalation(status="pending", conversation_id="conv-coll")
    conv = _make_conv_history(bot_paused_at=None, conversation_id="conv-coll")

    current_user = _make_admin_user(username="caller")
    # DB query filters by status='pending_review' — returns None for a 'collecting' case
    session = _make_session_with_rule5(
        escalation=esc,
        assignee=assignee,
        conv_history=conv,
        case=None,  # Simulates DB filter: no pending_review case for this conversation
    )

    with patch(
        "api.services.escalation_assignment_service.TakeCaseService"
    ) as MockTCS:
        mock_tcs_instance = AsyncMock()
        MockTCS.return_value = mock_tcs_instance

        svc = EscalationAssignmentService(session)
        await svc.assign(esc.id, assignee_id, current_user)

    # TakeCaseService must NOT be called when DB returns no pending_review case
    mock_tcs_instance.take_case_internal.assert_not_called()
    # Escalation assigned successfully
    assert esc.status == "assigned"
