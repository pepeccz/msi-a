"""
Unit tests for TakeCaseService.

Tests the extracted DB logic for POST /cases/{id}/take.
All tests use mock AsyncSession — no real DB required.

Scenarios covered:
  4.3  take_case assigns an existing pending Escalation
  4.4  take_case creates a new Escalation when none exists
  4.5  take_case is idempotent on double-click (in_progress + same escalation)
  -    _from_assignment=True skips all Escalation logic (Rule 5 guard)
  -    first-pause-wins: bot_paused_at written only when NULL
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.exceptions import CaseNotFoundError, CaseNotInPendingReviewError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_case(
    status: str = "pending_review",
    conversation_id: str = "999",
    notes: str | None = None,
) -> MagicMock:
    case = MagicMock()
    case.id = uuid.uuid4()
    case.status = status
    case.conversation_id = conversation_id
    case.notes = notes
    case.updated_at = None
    case.user = MagicMock(first_name="Juan", last_name="López")
    case.escalation_id = None
    return case


def _make_escalation(status: str = "pending") -> MagicMock:
    esc = MagicMock()
    esc.id = uuid.uuid4()
    esc.status = status
    esc.assigned_to_user_id = None
    esc.assigned_at = None
    return esc


def _make_conv(bot_paused_at: datetime | None = None) -> MagicMock:
    conv = MagicMock()
    conv.bot_paused_at = bot_paused_at
    conv.bot_paused_by_user_id = None
    conv.bot_pause_reason = None
    return conv


def _make_admin(uid: uuid.UUID | None = None) -> MagicMock:
    admin = MagicMock()
    admin.id = uid or uuid.uuid4()
    admin.username = "pepe"
    admin.display_name = "Pepe"
    return admin


def _make_session(
    *ordered_results: MagicMock | None,
) -> AsyncMock:
    """
    Build a mock AsyncSession that returns the given objects on execute()
    IN THE ORDER THEY ARE PROVIDED (matches the service's call sequence).

    The service calls execute() in this order:
      1. Case (with_for_update)
      2. ConversationHistory
      3. Escalation (only when _from_assignment=False)

    Pass objects in that exact order.
    """
    session = AsyncMock()

    def _scalar_result(obj: MagicMock | None) -> MagicMock:
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=obj)
        return r

    execute_returns = [_scalar_result(obj) for obj in ordered_results]
    session.execute = AsyncMock(side_effect=execute_returns)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# C2.3 — test_take_case_assigns_existing_pending_escalation  (Scenario 4.3)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_take_case_assigns_existing_pending_escalation() -> None:
    """
    When a pending Escalation exists for the case's conversation,
    take_case_internal must assign it (status='assigned') rather than
    creating a new one.
    """
    from api.services.take_case_service import TakeCaseService

    admin = _make_admin()
    case = _make_case(status="pending_review")
    escalation = _make_escalation(status="pending")
    conv = _make_conv(bot_paused_at=None)

    # Service calls execute() in order: Case → Conv → Escalation
    session = _make_session(case, conv, escalation)

    svc = TakeCaseService(session)
    returned_case, returned_esc = await svc.take_case_internal(
        case.id, admin.id
    )

    # Case promoted
    assert returned_case.status == "in_progress"

    # Escalation assigned
    assert escalation.status == "assigned"
    assert escalation.assigned_to_user_id == admin.id
    assert escalation.assigned_at is not None

    # ConversationHistory paused (first-pause-wins, was None)
    assert conv.bot_paused_at is not None

    session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# C2.3 — test_take_case_creates_escalation_when_none_exists  (Scenario 4.4)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_take_case_creates_escalation_when_none_exists() -> None:
    """
    When no Escalation exists for the conversation, take_case_internal must
    create one with source='case_completion' and status='assigned'.
    """
    from api.services.take_case_service import TakeCaseService

    admin = _make_admin()
    case = _make_case(status="pending_review")
    conv = _make_conv(bot_paused_at=None)

    # Service calls: Case → Conv → Escalation(None = not found)
    session = _make_session(case, conv, None)

    svc = TakeCaseService(session)
    returned_case, returned_esc = await svc.take_case_internal(
        case.id, admin.id
    )

    assert returned_case.status == "in_progress"

    # A new Escalation was added to the session
    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert added.source == "case_completion"
    assert added.status == "assigned"
    assert added.assigned_to_user_id == admin.id
    assert added.assigned_at is not None

    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# C2.3 — test_take_case_idempotent_on_double_click  (Scenario 4.5)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_take_case_idempotent_on_double_click() -> None:
    """
    When case is already in_progress, take_case_internal must return
    (case, None) without touching DB (no commit).
    """
    from api.services.take_case_service import TakeCaseService

    admin = _make_admin()
    case = _make_case(status="in_progress")

    # Only case needs to be returned; no conv or escalation lookup (early return)
    session = _make_session(case)

    svc = TakeCaseService(session)
    returned_case, returned_esc = await svc.take_case_internal(
        case.id, admin.id
    )

    assert returned_case.status == "in_progress"
    assert returned_esc is None
    session.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# C2.3 — test_take_case_internal_called_from_assignment_skips_escalation_logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_take_case_internal_called_from_assignment_skips_escalation_logic() -> None:
    """
    When _from_assignment=True, take_case_internal must NOT create or
    modify any Escalation (caller already handled it).
    """
    from api.services.take_case_service import TakeCaseService

    admin = _make_admin()
    case = _make_case(status="pending_review")
    conv = _make_conv(bot_paused_at=None)

    # Only case + conv — no escalation lookup when _from_assignment=True
    session = _make_session(case, conv)

    svc = TakeCaseService(session)
    returned_case, returned_esc = await svc.take_case_internal(
        case.id, admin.id, _from_assignment=True
    )

    assert returned_case.status == "in_progress"
    assert returned_esc is None
    session.add.assert_not_called()  # No escalation created
    session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# C2.3 — test_take_case_first_pause_wins
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_take_case_first_pause_wins() -> None:
    """
    When bot_paused_at is already set, take_case_internal must NOT
    overwrite the existing timestamp.
    """
    from api.services.take_case_service import TakeCaseService

    admin = _make_admin()
    case = _make_case(status="pending_review")
    existing_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    conv = _make_conv(bot_paused_at=existing_ts)
    escalation = _make_escalation(status="pending")

    # Service calls: Case → Conv → Escalation
    session = _make_session(case, conv, escalation)

    svc = TakeCaseService(session)
    await svc.take_case_internal(case.id, admin.id)

    # Timestamp must remain the original — not overwritten
    assert conv.bot_paused_at == existing_ts


# ---------------------------------------------------------------------------
# C2.3 — test_take_case_raises_not_found
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_take_case_raises_not_found() -> None:
    """
    When the Case does not exist, take_case_internal must raise
    CaseNotFoundError.
    """
    from api.services.take_case_service import TakeCaseService

    session = _make_session(None)

    svc = TakeCaseService(session)
    with pytest.raises(CaseNotFoundError):
        await svc.take_case_internal(uuid.uuid4(), uuid.uuid4())


# ---------------------------------------------------------------------------
# C2.3 — test_take_case_raises_not_in_pending_review
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_take_case_raises_not_in_pending_review() -> None:
    """
    When case status is anything other than pending_review or in_progress,
    take_case_internal must raise CaseNotInPendingReviewError.
    """
    from api.services.take_case_service import TakeCaseService

    case = _make_case(status="collecting")
    session = _make_session(case)

    svc = TakeCaseService(session)
    with pytest.raises(CaseNotInPendingReviewError):
        await svc.take_case_internal(case.id, uuid.uuid4())
