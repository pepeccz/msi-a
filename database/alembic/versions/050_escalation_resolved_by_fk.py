"""Escalation: add resolved_by_user_id FK to admin_users with backfill

Adds a typed FK column resolved_by_user_id to escalations.
The legacy resolved_by (string) column is kept for rollback safety.
Backfill matches existing resolved_by values against admin_users username/display_name.
Unmatched rows remain NULL; count logged via RAISE NOTICE.

Revision ID: 050_escalation_resolved_by_fk
Revises: 049_inbox_foundation
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "050_escalation_resolved_by_fk"
down_revision: str = "049_inbox_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "escalations",
        sa.Column(
            "resolved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
            comment="AdminUser FK for the agent who resolved the escalation",
        ),
    )

    op.create_index(
        "ix_escalations_resolved_by_user_id",
        "escalations",
        ["resolved_by_user_id"],
        postgresql_where=sa.text("resolved_by_user_id IS NOT NULL"),
    )

    # Backfill: match resolved_by string against admin_users username or display_name
    op.execute(
        """
        UPDATE escalations e
        SET resolved_by_user_id = au.id
        FROM admin_users au
        WHERE e.resolved_by IS NOT NULL
          AND e.resolved_by_user_id IS NULL
          AND (
              LOWER(au.username) = LOWER(e.resolved_by)
              OR LOWER(au.display_name) = LOWER(e.resolved_by)
          )
        """
    )

    # Log unmatched rows so the developer knows how many need manual intervention
    op.execute(
        """
        DO $$
        DECLARE unmatched_count int;
        BEGIN
          SELECT COUNT(*) INTO unmatched_count
          FROM escalations
          WHERE resolved_by IS NOT NULL
            AND resolved_by_user_id IS NULL;
          RAISE NOTICE 'Escalation backfill: % unmatched resolved_by values left as NULL (manual intervention required)', unmatched_count;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_escalations_resolved_by_user_id", table_name="escalations")
    op.drop_column("escalations", "resolved_by_user_id")
