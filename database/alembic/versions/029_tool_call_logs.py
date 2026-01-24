"""Add tool_call_logs table for persistent agent debugging

Revision ID: 029_tool_call_logs
Revises: 028_element_image_status
Create Date: 2026-01-24 00:00:00.000000

Changes:
- Create tool_call_logs table for permanent storage of agent tool invocations.
  Unlike Redis checkpointer (24h TTL), these persist indefinitely in PostgreSQL
  for post-hoc conversation debugging and analysis.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "029_tool_call_logs"
down_revision: Union[str, None] = "028_element_image_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tool_call_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", sa.String(100), nullable=False, index=True),
        sa.Column("tool_name", sa.String(100), nullable=False, index=True),
        sa.Column("parameters", JSONB, nullable=True),
        sa.Column("result_summary", sa.String(500), nullable=True),
        sa.Column("result_type", sa.String(20), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("iteration", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Composite index for conversation timeline queries
    op.create_index(
        "ix_tool_call_logs_conv_timestamp",
        "tool_call_logs",
        ["conversation_id", "timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_tool_call_logs_conv_timestamp", table_name="tool_call_logs")
    op.drop_table("tool_call_logs")
