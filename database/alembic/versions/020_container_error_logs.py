"""Add container_error_logs table for system monitoring

Revision ID: 020_container_error_logs
Revises: 019_move_personal_data_to_user
Create Date: 2026-01-14 00:00:00.000000

Changes:
- Add container_error_logs table for storing parsed Docker errors
- Supports admin resolution workflow (open, resolved, ignored)
- Tracks errors from all MSI-a services for monitoring
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "020_container_error_logs"
down_revision: Union[str, None] = "019_move_personal_data_to_user"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create container_error_logs table
    # =========================================================================
    op.create_table(
        "container_error_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "service_name",
            sa.String(50),
            nullable=False,
            index=True,
            comment="Service name: api, agent, postgres, redis, ollama, qdrant, document-processor",
        ),
        sa.Column(
            "container_name",
            sa.String(100),
            nullable=False,
            comment="Docker container name (e.g., msia-api)",
        ),
        sa.Column(
            "level",
            sa.String(20),
            nullable=False,
            index=True,
            comment="Log level: ERROR, CRITICAL, FATAL, WARNING",
        ),
        sa.Column(
            "message",
            sa.Text(),
            nullable=False,
            comment="Error message content",
        ),
        sa.Column(
            "stack_trace",
            sa.Text(),
            nullable=True,
            comment="Full stack trace if available",
        ),
        sa.Column(
            "context",
            postgresql.JSONB(),
            nullable=True,
            comment="Additional context: request_id, conversation_id, user info, etc.",
        ),
        sa.Column(
            "log_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            index=True,
            comment="Original timestamp from Docker log",
        ),
        sa.Column(
            "raw_log",
            sa.Text(),
            nullable=True,
            comment="Original raw log line for debugging",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="open",
            index=True,
            comment="Status: open, resolved, ignored",
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the error was resolved/ignored",
        ),
        sa.Column(
            "resolved_by",
            sa.String(100),
            nullable=True,
            comment="Admin username who resolved/ignored",
        ),
        sa.Column(
            "resolution_notes",
            sa.Text(),
            nullable=True,
            comment="Notes about the resolution",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # =========================================================================
    # 2. Create composite index for common queries
    # =========================================================================
    op.create_index(
        "ix_container_error_logs_service_status",
        "container_error_logs",
        ["service_name", "status"],
    )


def downgrade() -> None:
    # =========================================================================
    # 1. Drop composite index
    # =========================================================================
    op.drop_index(
        "ix_container_error_logs_service_status",
        table_name="container_error_logs",
    )

    # =========================================================================
    # 2. Drop container_error_logs table
    # =========================================================================
    op.drop_table("container_error_logs")
