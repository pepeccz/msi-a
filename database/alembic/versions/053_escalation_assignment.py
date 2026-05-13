"""Add assigned_to_user_id and assigned_at columns to escalations table.

Introduces the assignment lifecycle for Escalation records:
  - pending → assigned → resolved
Replaces the legacy status value 'in_progress' with 'assigned'.

Data migration:
  upgrade:   UPDATE escalations SET status='assigned' WHERE status='in_progress'
  downgrade: UPDATE escalations SET status='in_progress'
             WHERE status='assigned' AND assigned_to_user_id IS NULL
             (only unassigned rows — rows actually assigned via the new system stay
             as 'assigned' since the old code wouldn't know what to do with them)

Revision ID: 053_escalation_assignment
Revises: 052_conversation_notes
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "053_escalation_assignment"
down_revision: str = "052_conversation_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add new nullable columns
    op.add_column(
        "escalations",
        sa.Column(
            "assigned_to_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="AdminUser FK for the agent the escalation is assigned to",
        ),
    )
    op.add_column(
        "escalations",
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when the escalation was assigned",
        ),
    )

    # 2. Create FK constraint
    op.create_foreign_key(
        "escalations_assigned_to_user_id_fkey",
        "escalations",
        "admin_users",
        ["assigned_to_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. Create composite index for assignment queries
    op.create_index(
        "ix_escalations_status_assigned",
        "escalations",
        ["status", "assigned_to_user_id"],
    )

    # 4. Data migration: rename legacy 'in_progress' status to 'assigned'
    #    (in_progress rows were implicitly assigned but lacked the FK column)
    op.execute("UPDATE escalations SET status='assigned' WHERE status='in_progress'")


def downgrade() -> None:
    # 1. Revert data migration — only revert rows where assigned_to_user_id IS NULL.
    #    Rows that were actually assigned via the new system (have a user FK) stay as
    #    'assigned' since downgrading code cannot handle the value anyway; the trade-off
    #    is documented and accepted.
    op.execute(
        "UPDATE escalations SET status='in_progress' "
        "WHERE status='assigned' AND assigned_to_user_id IS NULL"
    )

    # 2. Drop composite index
    op.drop_index(
        "ix_escalations_status_assigned",
        table_name="escalations",
    )

    # 3. Drop FK constraint
    op.drop_constraint(
        "escalations_assigned_to_user_id_fkey",
        "escalations",
        type_="foreignkey",
    )

    # 4. Drop columns (in reverse order of creation)
    op.drop_column("escalations", "assigned_at")
    op.drop_column("escalations", "assigned_to_user_id")
