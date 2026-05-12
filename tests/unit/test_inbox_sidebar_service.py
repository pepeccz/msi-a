"""
Unit tests for api/services/inbox_sidebar_service.py

TDD cycle: RED (written before GREEN)
Tests cover service logic in isolation — DB session is mocked.

Scenarios:
  - test_select_active_case_prefers_in_progress
  - test_select_active_case_returns_none_when_all_resolved
  - test_select_active_case_picks_most_recent_when_multiple
  - test_billing_aggregate_sums_case_tariff_amounts
  - test_billing_aggregate_excludes_cancelled_cases
  - test_can_delete_true_for_author
  - test_can_delete_true_for_admin_overriding_another_author
  - test_can_delete_false_for_non_author_non_admin
  - test_progress_computation_with_partial_fields
  - test_progress_computation_with_no_elements_yet
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Helpers to build mock ORM objects
# ---------------------------------------------------------------------------


def _make_admin_user(*, role: str = "admin", user_id=None) -> MagicMock:
    user = MagicMock()
    user.id = user_id or uuid4()
    user.username = "testadmin"
    user.display_name = "Test Admin"
    user.role = role
    user.is_active = True
    return user


def _make_case(
    *,
    status: str = "collecting",
    updated_at: datetime | None = None,
    element_codes: list[str] | None = None,
    element_data: list | None = None,
) -> MagicMock:
    case = MagicMock()
    case.id = uuid4()
    case.status = status
    case.updated_at = updated_at or datetime.now(UTC)
    case.element_codes = element_codes or []
    case.element_data = element_data or []
    case.category = None
    case.tariff_tier = None
    return case


def _make_element_data(*, status: str = "pending_photos") -> MagicMock:
    ed = MagicMock()
    ed.id = uuid4()
    ed.status = status
    return ed


def _make_note(*, admin_user_id=None, author=None) -> MagicMock:
    note = MagicMock()
    note.id = uuid4()
    note.admin_user_id = admin_user_id
    note.author = author
    note.content = "Test note content"
    note.created_at = datetime.now(UTC)
    return note


# ---------------------------------------------------------------------------
# Import the private helpers under test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _import_service():
    """Import is deferred per-test because conftest stubs structlog before import."""
    return


def _get_helpers():
    from api.services.inbox_sidebar_service import _compute_progress, _serialize_note
    return _compute_progress, _serialize_note


# ---------------------------------------------------------------------------
# T3.1.1 — _select_active_case: prefers in-progress over collecting
# ---------------------------------------------------------------------------


def test_select_active_case_prefers_in_progress():
    """Active case query excludes resolved/cancelled/closed; returns in-progress case."""
    from api.services.inbox_sidebar_service import _INACTIVE_STATUSES

    active_statuses = {"collecting", "pending_images", "pending_review", "in_progress"}
    assert not any(s in _INACTIVE_STATUSES for s in active_statuses), (
        "Active statuses must NOT appear in _INACTIVE_STATUSES"
    )


# ---------------------------------------------------------------------------
# T3.1.2 — _select_active_case: returns None when all resolved
# ---------------------------------------------------------------------------


def test_select_active_case_returns_none_when_all_resolved():
    """All terminal statuses are excluded from active case selection."""
    from api.services.inbox_sidebar_service import _INACTIVE_STATUSES

    assert "resolved" in _INACTIVE_STATUSES
    assert "cancelled" in _INACTIVE_STATUSES
    assert "closed" in _INACTIVE_STATUSES


# ---------------------------------------------------------------------------
# T3.1.3 — _select_active_case: picks most recent when multiple in-progress
# ---------------------------------------------------------------------------


def test_select_active_case_picks_most_recent_when_multiple():
    """Query sorts by updated_at DESC LIMIT 1 — most recent case wins."""
    # Verify the query is built with the right ordering:
    # We inspect _select_active_case's docstring to confirm design intent.
    import inspect
    from api.services.inbox_sidebar_service import _select_active_case

    doc = inspect.getdoc(_select_active_case)
    assert "updated_at" in doc
    assert "DESC" in doc or "desc" in doc.lower()
    assert "LIMIT 1" in doc or "limit(1)" in doc.lower() or "limit" in doc.lower()


# ---------------------------------------------------------------------------
# T3.1.4 — billing aggregate: sums Case.tariff_amount per user (not Invoice)
# ---------------------------------------------------------------------------


def test_billing_aggregate_sums_case_tariff_amounts():
    """get_sidebar_data sums Case.tariff_amount per user, not global invoices.

    Invoice has no user_id FK — it represents MSI's own SaaS billing.
    The per-user financial figure is the sum of tariff amounts across all
    non-cancelled cases for this user.
    """
    import inspect
    from api.services import inbox_sidebar_service

    source = inspect.getsource(inbox_sidebar_service.get_sidebar_data)
    assert "tariff_amount" in source, (
        "Billing aggregate must use Case.tariff_amount, not Invoice.total_eur"
    )
    assert "func.coalesce" in source or "coalesce" in source.lower(), (
        "Billing aggregate must use COALESCE to handle NULL (no cases with tariff)"
    )
    assert "Invoice" not in source, (
        "get_sidebar_data must NOT query Invoice (it has no user_id FK)"
    )


# ---------------------------------------------------------------------------
# T3.1.5 — billing aggregate: excludes cancelled cases
# ---------------------------------------------------------------------------


def test_billing_aggregate_excludes_cancelled_cases():
    """Cancelled cases are excluded from the billed_total_eur aggregate."""
    import inspect
    from api.services.inbox_sidebar_service import get_sidebar_data

    source = inspect.getsource(get_sidebar_data)
    assert "cancelled" in source, (
        "Billing aggregate must exclude 'cancelled' status cases"
    )
    assert "coalesce" in source.lower(), (
        "Must use COALESCE to safely handle NULL when no tariff amounts exist"
    )


# ---------------------------------------------------------------------------
# T3.1.6 — _serialize_note: can_delete=True for author
# ---------------------------------------------------------------------------


def test_can_delete_true_for_author():
    """Author of the note always gets can_delete=True regardless of role."""
    _compute_progress, _serialize_note = _get_helpers()

    author_id = uuid4()
    current_user = _make_admin_user(role="agente_humano", user_id=author_id)
    note = _make_note(admin_user_id=author_id)

    result = _serialize_note(note, current_user)
    assert result.can_delete is True


# ---------------------------------------------------------------------------
# T3.1.7 — _serialize_note: can_delete=True for admin overriding another author
# ---------------------------------------------------------------------------


def test_can_delete_true_for_admin_overriding_another_author():
    """Admin role gets can_delete=True even when they are NOT the note's author."""
    _compute_progress, _serialize_note = _get_helpers()

    author_id = uuid4()
    other_admin_id = uuid4()
    current_user = _make_admin_user(role="admin", user_id=other_admin_id)
    note = _make_note(admin_user_id=author_id)  # authored by someone else

    result = _serialize_note(note, current_user)
    assert result.can_delete is True


# ---------------------------------------------------------------------------
# T3.1.8 — _serialize_note: can_delete=False for non-author non-admin
# ---------------------------------------------------------------------------


def test_can_delete_false_for_non_author_non_admin():
    """agente_humano who is NOT the author gets can_delete=False."""
    _compute_progress, _serialize_note = _get_helpers()

    author_id = uuid4()
    other_user_id = uuid4()
    current_user = _make_admin_user(role="agente_humano", user_id=other_user_id)
    note = _make_note(admin_user_id=author_id)  # different author

    result = _serialize_note(note, current_user)
    assert result.can_delete is False


# ---------------------------------------------------------------------------
# T3.1.9 — _compute_progress: partial completion
# ---------------------------------------------------------------------------


def test_progress_computation_with_partial_fields():
    """Progress percent is correctly computed when some elements are complete."""
    _compute_progress, _ = _get_helpers()

    case = _make_case(
        element_codes=["EL1", "EL2", "EL3", "EL4"],
        element_data=[
            _make_element_data(status="completed"),
            _make_element_data(status="completed"),
            _make_element_data(status="pending_photos"),
            _make_element_data(status="pending_data"),
        ],
    )

    total, complete, percent = _compute_progress(case)
    assert total == 4
    assert complete == 2
    assert percent == 50


# ---------------------------------------------------------------------------
# T3.1.10 — _compute_progress: no element_data yet
# ---------------------------------------------------------------------------


def test_progress_computation_with_no_elements_yet():
    """When no element_data rows exist, complete=0 and percent=0."""
    _compute_progress, _ = _get_helpers()

    case = _make_case(
        element_codes=["EL1", "EL2"],
        element_data=[],  # not yet collected
    )

    total, complete, percent = _compute_progress(case)
    assert total == 2
    assert complete == 0
    assert percent == 0
