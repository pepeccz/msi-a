"""Add token_usage table for LLM consumption tracking

Revision ID: 023_token_usage
Revises: 022_element_question_hint
Create Date: 2026-01-20 00:00:00.000000

Changes:
- Add token_usage table for monthly aggregated LLM token consumption
- Tracks input and output tokens separately for cost calculation
- Uses year/month as unique constraint for upsert pattern
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "023_token_usage"
down_revision: Union[str, None] = "022_element_question_hint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create token_usage table
    # =========================================================================
    op.create_table(
        "token_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "year",
            sa.Integer(),
            nullable=False,
            comment="Year (e.g., 2025)",
        ),
        sa.Column(
            "month",
            sa.Integer(),
            nullable=False,
            comment="Month (1-12)",
        ),
        sa.Column(
            "input_tokens",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
            comment="Total input/prompt tokens consumed",
        ),
        sa.Column(
            "output_tokens",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
            comment="Total output/completion tokens consumed",
        ),
        sa.Column(
            "total_requests",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of LLM requests made",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # =========================================================================
    # 2. Create unique constraint for year/month combination
    # =========================================================================
    op.create_unique_constraint(
        "uq_token_usage_year_month",
        "token_usage",
        ["year", "month"],
    )

    # =========================================================================
    # 3. Create composite index for queries
    # =========================================================================
    op.create_index(
        "ix_token_usage_year_month",
        "token_usage",
        ["year", "month"],
    )


def downgrade() -> None:
    # =========================================================================
    # 1. Drop index
    # =========================================================================
    op.drop_index(
        "ix_token_usage_year_month",
        table_name="token_usage",
    )

    # =========================================================================
    # 2. Drop unique constraint
    # =========================================================================
    op.drop_constraint(
        "uq_token_usage_year_month",
        "token_usage",
        type_="unique",
    )

    # =========================================================================
    # 3. Drop token_usage table
    # =========================================================================
    op.drop_table("token_usage")
