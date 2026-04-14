"""Add lifecycle tracking fields to cases table

Revision ID: 043_case_lifecycle_fields
Revises: 042_unify_warning_system
Create Date: 2026-04-14

Changes:
- Add last_activity_at (DateTime, nullable) to cases
- Add reminder_sent_at (DateTime, nullable) to cases
- Add abandoned_at (DateTime, nullable) to cases
- Add composite index ix_cases_lifecycle on (status, last_activity_at)

Downgrade:
- Drop ix_cases_lifecycle index first
- Drop the three columns
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "043_case_lifecycle_fields"
down_revision: Union[str, None] = "042_unify_warning_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last time the user sent a message while in expediente flow",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "reminder_sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the lifecycle worker sent the inactivity reminder",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "abandoned_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the worker marked the case as abandoned",
        ),
    )
    op.create_index(
        "ix_cases_lifecycle",
        "cases",
        ["status", "last_activity_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_cases_lifecycle", table_name="cases")
    op.drop_column("cases", "abandoned_at")
    op.drop_column("cases", "reminder_sent_at")
    op.drop_column("cases", "last_activity_at")
