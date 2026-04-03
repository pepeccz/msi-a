"""Add draft_quotes table for DraftQuote persistence.

Stores the most recent price quote per conversation so the agent can
recover pricing context after a restart without recalculating.

At most one is_active=True row per conversation is maintained by the
application-level upsert logic in agent/tools/draft_quote_service.py.

Revision ID: 040_add_draft_quotes
Revises: 039_case_user_active_unique
Create Date: 2026-04-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "040_add_draft_quotes"
down_revision: Union[str, None] = "039_case_user_active_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create draft_quotes table."""
    op.create_table(
        "draft_quotes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversation_history.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category_slug",
            sa.String(100),
            nullable=False,
        ),
        sa.Column(
            "elements",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "tier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tariff_tiers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "precio_final",
            sa.Numeric(10, 2),
            nullable=False,
        ),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )

    # Index on conversation_id for fast lookup by conversation
    op.create_index(
        op.f("ix_draft_quotes_conversation_id"),
        "draft_quotes",
        ["conversation_id"],
    )


def downgrade() -> None:
    """Drop draft_quotes table."""
    op.drop_index(
        op.f("ix_draft_quotes_conversation_id"),
        table_name="draft_quotes",
    )
    op.drop_table("draft_quotes")
