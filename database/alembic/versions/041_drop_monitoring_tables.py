"""Drop monitoring tables: tool_call_logs, llm_usage_metrics, container_error_logs

Revision ID: 041_drop_monitoring_tables
Revises: 7dc32f4a106a
Create Date: 2026-04-06 00:00:00.000000

Changes:
- Drop tool_call_logs table (agent tool call audit)
- Drop llm_usage_metrics table (hybrid LLM architecture metrics)
- Drop container_error_logs table (Docker container error logs)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "041_drop_monitoring_tables"
down_revision: Union[str, None] = "7dc32f4a106a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop tool_call_logs (includes composite index)
    op.drop_index("ix_tool_call_logs_conv_timestamp", table_name="tool_call_logs")
    op.drop_table("tool_call_logs")

    # Drop llm_usage_metrics (includes composite indexes)
    op.drop_index("ix_llm_usage_metrics_provider_success", table_name="llm_usage_metrics")
    op.drop_index("ix_llm_usage_metrics_task_tier", table_name="llm_usage_metrics")
    op.drop_index("ix_llm_usage_metrics_created_tier", table_name="llm_usage_metrics")
    op.drop_table("llm_usage_metrics")

    # Drop container_error_logs (includes composite index)
    op.drop_index(
        "ix_container_error_logs_service_status",
        table_name="container_error_logs",
    )
    op.drop_table("container_error_logs")


def downgrade() -> None:
    # Recreate container_error_logs
    op.create_table(
        "container_error_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("service_name", sa.String(50), nullable=False, index=True),
        sa.Column("container_name", sa.String(100), nullable=False),
        sa.Column("level", sa.String(20), nullable=False, index=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("stack_trace", sa.Text(), nullable=True),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("log_timestamp", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("raw_log", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open", index=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(100), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_container_error_logs_service_status",
        "container_error_logs",
        ["service_name", "status"],
    )

    # Recreate llm_usage_metrics
    op.create_table(
        "llm_usage_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_type", sa.String(50), nullable=False, index=True),
        sa.Column("tier", sa.String(30), nullable=False, index=True),
        sa.Column("provider", sa.String(30), nullable=False, index=True),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("success", sa.Boolean, nullable=False, default=True, index=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("fallback_used", sa.Boolean, nullable=False, default=False),
        sa.Column("original_tier", sa.String(30), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("conversation_id", sa.String(100), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
    )
    op.create_index("ix_llm_usage_metrics_created_tier", "llm_usage_metrics", ["created_at", "tier"])
    op.create_index("ix_llm_usage_metrics_task_tier", "llm_usage_metrics", ["task_type", "tier"])
    op.create_index("ix_llm_usage_metrics_provider_success", "llm_usage_metrics", ["provider", "success"])

    # Recreate tool_call_logs
    op.create_table(
        "tool_call_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", sa.String(100), nullable=False, index=True),
        sa.Column("tool_name", sa.String(100), nullable=False, index=True),
        sa.Column("parameters", postgresql.JSONB, nullable=True),
        sa.Column("result_summary", sa.String(500), nullable=True),
        sa.Column("result_type", sa.String(20), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("iteration", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_tool_call_logs_conv_timestamp",
        "tool_call_logs",
        ["conversation_id", "timestamp"],
    )
