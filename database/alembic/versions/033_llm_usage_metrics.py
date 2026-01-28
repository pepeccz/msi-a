"""Create llm_usage_metrics table for hybrid LLM architecture.

This migration creates the table for tracking LLM usage metrics,
enabling monitoring of:
- Model tier usage (local vs cloud)
- Cost analysis and savings from hybrid routing
- Latency comparison between tiers
- Success/failure rates by provider

Revision ID: 033_llm_usage_metrics
Revises: 032_unique_conversation_id
Create Date: 2026-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "033_llm_usage_metrics"
down_revision: Union[str, None] = "032_unique_conversation_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create llm_usage_metrics table."""
    op.create_table(
        "llm_usage_metrics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        
        # Task categorization
        sa.Column(
            "task_type",
            sa.String(50),
            nullable=False,
            index=True,
            comment="Task type: classification, extraction, rag_simple, rag_complex, conversation, tool_calling",
        ),
        
        # Model routing info
        sa.Column(
            "tier",
            sa.String(30),
            nullable=False,
            index=True,
            comment="Model tier: local_fast, local_capable, cloud_standard, cloud_advanced",
        ),
        sa.Column(
            "provider",
            sa.String(30),
            nullable=False,
            index=True,
            comment="Provider: ollama, openrouter",
        ),
        sa.Column(
            "model",
            sa.String(100),
            nullable=False,
            comment="Specific model used (e.g., qwen2.5:3b, llama3:8b, openai/gpt-4o-mini)",
        ),
        
        # Performance metrics
        sa.Column(
            "latency_ms",
            sa.Integer,
            nullable=False,
            comment="Request latency in milliseconds",
        ),
        sa.Column(
            "input_tokens",
            sa.Integer,
            nullable=True,
            comment="Input/prompt tokens (if available)",
        ),
        sa.Column(
            "output_tokens",
            sa.Integer,
            nullable=True,
            comment="Output/completion tokens (if available)",
        ),
        
        # Status
        sa.Column("success", sa.Boolean, nullable=False, default=True, index=True),
        sa.Column(
            "error",
            sa.Text,
            nullable=True,
            comment="Error message if failed",
        ),
        
        # Fallback tracking
        sa.Column(
            "fallback_used",
            sa.Boolean,
            nullable=False,
            default=False,
            comment="Whether this was a fallback from a failed primary call",
        ),
        sa.Column(
            "original_tier",
            sa.String(30),
            nullable=True,
            comment="Original tier if fallback was used",
        ),
        
        # Cost estimation
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(10, 6),
            nullable=True,
            comment="Estimated cost in USD (cloud only)",
        ),
        
        # Context
        sa.Column(
            "conversation_id",
            sa.String(100),
            nullable=True,
            index=True,
            comment="Chatwoot conversation ID if applicable",
        ),
        
        # Timestamp
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
    )
    
    # Composite indexes for common queries
    op.create_index(
        "ix_llm_usage_metrics_created_tier",
        "llm_usage_metrics",
        ["created_at", "tier"],
    )
    op.create_index(
        "ix_llm_usage_metrics_task_tier",
        "llm_usage_metrics",
        ["task_type", "tier"],
    )
    op.create_index(
        "ix_llm_usage_metrics_provider_success",
        "llm_usage_metrics",
        ["provider", "success"],
    )


def downgrade() -> None:
    """Drop llm_usage_metrics table."""
    op.drop_index("ix_llm_usage_metrics_provider_success", "llm_usage_metrics")
    op.drop_index("ix_llm_usage_metrics_task_tier", "llm_usage_metrics")
    op.drop_index("ix_llm_usage_metrics_created_tier", "llm_usage_metrics")
    op.drop_table("llm_usage_metrics")
