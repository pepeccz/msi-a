"""
Tests for Case Model Lifecycle Fields — Batch 1 (RED phase)

Spec 1: Case Lifecycle Timestamp Fields

Requirements verified:
  - Case model has last_activity_at (nullable DateTime, timezone-aware)
  - Case model has reminder_sent_at (nullable DateTime, timezone-aware)
  - Case model has abandoned_at (nullable DateTime, timezone-aware)
  - All three fields default to None
  - Fields are settable with datetime values
  - ix_cases_lifecycle composite index is declared in __table_args__
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


class TestCaseModelLifecycleFields:
    """Case model must declare all three lifecycle timestamp fields."""

    def test_case_has_last_activity_at_attribute(self) -> None:
        """Case model must have last_activity_at attribute."""
        from database.models import Case

        case = Case(conversation_id="test-conv")
        assert hasattr(case, "last_activity_at"), (
            "Case model is missing last_activity_at field"
        )

    def test_case_has_reminder_sent_at_attribute(self) -> None:
        """Case model must have reminder_sent_at attribute."""
        from database.models import Case

        case = Case(conversation_id="test-conv")
        assert hasattr(case, "reminder_sent_at"), (
            "Case model is missing reminder_sent_at field"
        )

    def test_case_has_abandoned_at_attribute(self) -> None:
        """Case model must have abandoned_at attribute."""
        from database.models import Case

        case = Case(conversation_id="test-conv")
        assert hasattr(case, "abandoned_at"), (
            "Case model is missing abandoned_at field"
        )


class TestCaseModelLifecycleDefaults:
    """All three lifecycle fields must default to None."""

    def test_last_activity_at_defaults_to_none(self) -> None:
        """last_activity_at must default to None for new cases."""
        from database.models import Case

        case = Case(conversation_id="test-conv")
        assert case.last_activity_at is None, (
            f"last_activity_at should default to None, got {case.last_activity_at!r}"
        )

    def test_reminder_sent_at_defaults_to_none(self) -> None:
        """reminder_sent_at must default to None for new cases."""
        from database.models import Case

        case = Case(conversation_id="test-conv")
        assert case.reminder_sent_at is None, (
            f"reminder_sent_at should default to None, got {case.reminder_sent_at!r}"
        )

    def test_abandoned_at_defaults_to_none(self) -> None:
        """abandoned_at must default to None for new cases."""
        from database.models import Case

        case = Case(conversation_id="test-conv")
        assert case.abandoned_at is None, (
            f"abandoned_at should default to None, got {case.abandoned_at!r}"
        )


class TestCaseModelLifecycleFieldsSettable:
    """All three lifecycle fields must be settable with datetime values."""

    def test_last_activity_at_is_settable(self) -> None:
        """last_activity_at must accept a timezone-aware datetime."""
        from database.models import Case

        now = datetime.now(timezone.utc)
        case = Case(conversation_id="test-conv")
        case.last_activity_at = now
        assert case.last_activity_at == now

    def test_reminder_sent_at_is_settable(self) -> None:
        """reminder_sent_at must accept a timezone-aware datetime."""
        from database.models import Case

        now = datetime.now(timezone.utc)
        case = Case(conversation_id="test-conv")
        case.reminder_sent_at = now
        assert case.reminder_sent_at == now

    def test_abandoned_at_is_settable(self) -> None:
        """abandoned_at must accept a timezone-aware datetime."""
        from database.models import Case

        now = datetime.now(timezone.utc)
        case = Case(conversation_id="test-conv")
        case.abandoned_at = now
        assert case.abandoned_at == now


class TestCaseModelLifecycleIndex:
    """ix_cases_lifecycle composite index must be declared in __table_args__."""

    def test_ix_cases_lifecycle_index_declared(self) -> None:
        """__table_args__ must contain ix_cases_lifecycle index."""
        from database.models import Case
        from sqlalchemy import Index

        table_args = Case.__table_args__
        index_names = [
            arg.name
            for arg in table_args
            if isinstance(arg, Index)
        ]
        assert "ix_cases_lifecycle" in index_names, (
            f"ix_cases_lifecycle not found in Case.__table_args__. "
            f"Found: {index_names}"
        )

    def test_ix_cases_lifecycle_covers_status_and_last_activity_at(self) -> None:
        """ix_cases_lifecycle must index (status, last_activity_at) columns."""
        from database.models import Case
        from sqlalchemy import Index

        table_args = Case.__table_args__
        lifecycle_index = next(
            (arg for arg in table_args if isinstance(arg, Index) and arg.name == "ix_cases_lifecycle"),
            None,
        )
        assert lifecycle_index is not None, "ix_cases_lifecycle index not found"

        col_names = [col.key for col in lifecycle_index.columns]
        assert "status" in col_names, (
            f"ix_cases_lifecycle must include 'status' column. Got: {col_names}"
        )
        assert "last_activity_at" in col_names, (
            f"ix_cases_lifecycle must include 'last_activity_at' column. Got: {col_names}"
        )
