"""Add escalations table for tracking human escalations

Revision ID: 009_escalations
Revises: 008_fix_rag_queries_fk
Create Date: 2026-01-08 00:00:00.000000

Changes:
- Add escalations table for tracking when bot escalates to human agents
- Supports both explicit escalations (user request) and auto-escalations (errors)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "009_escalations"
down_revision: Union[str, None] = "008_fix_rag_queries_fk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create escalations table
    # =========================================================================
    op.create_table(
        "escalations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(100),
            nullable=False,
            index=True,
            comment="Chatwoot conversation ID",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "reason",
            sa.Text(),
            nullable=False,
            comment="Reason for escalation provided by agent or system",
        ),
        sa.Column(
            "source",
            sa.String(50),
            nullable=False,
            server_default="tool_call",
            comment="Escalation source: tool_call, auto_escalation, error",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            index=True,
            comment="Status: pending, in_progress, resolved",
        ),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "resolved_by",
            sa.String(100),
            nullable=True,
            comment="Name of agent who resolved the escalation",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=True,
            server_default="{}",
            comment="Additional data: priority, user_phone, context, etc.",
        ),
    )

    # =========================================================================
    # 2. Create composite index for common queries
    # =========================================================================
    op.create_index(
        "ix_escalations_status_triggered",
        "escalations",
        ["status", "triggered_at"],
    )


def downgrade() -> None:
    # =========================================================================
    # 1. Drop composite index
    # =========================================================================
    op.drop_index("ix_escalations_status_triggered", table_name="escalations")

    # =========================================================================
    # 2. Drop escalations table
    # =========================================================================
    op.drop_table("escalations")
