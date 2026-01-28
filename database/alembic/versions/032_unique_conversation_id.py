"""Add unique constraint to conversation_history.conversation_id.

This migration adds a unique constraint to prevent duplicate conversation_id
values in the conversation_history table. This enables atomic upsert operations
using ON CONFLICT DO UPDATE.

IMPORTANT: Before running this migration, check for existing duplicates:
    python -m scripts.check_conversation_duplicates

If duplicates exist, clean them up first:
    python -m scripts.check_conversation_duplicates --cleanup

Revision ID: 032_unique_conversation_id
Revises: 031_chatwoot_contact_id
Create Date: 2026-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "032_unique_conversation_id"
down_revision: Union[str, None] = "031_chatwoot_contact_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint to conversation_history.conversation_id.
    
    Steps:
    1. Clean up any duplicate records (keep the one with highest message_count)
    2. Add unique constraint
    """
    # Step 1: Clean up duplicates (keep record with highest message_count/most recent)
    # This DELETE keeps only the "best" record for each conversation_id
    op.execute("""
        DELETE FROM conversation_history ch1
        USING conversation_history ch2
        WHERE ch1.conversation_id = ch2.conversation_id
          AND ch1.id != ch2.id
          AND (
              ch1.message_count < ch2.message_count
              OR (ch1.message_count = ch2.message_count AND ch1.started_at < ch2.started_at)
              OR (ch1.message_count = ch2.message_count AND ch1.started_at = ch2.started_at AND ch1.id < ch2.id)
          )
    """)
    
    # Step 2: Add unique constraint
    op.create_unique_constraint(
        "uq_conversation_history_conversation_id",
        "conversation_history",
        ["conversation_id"],
    )


def downgrade() -> None:
    """Remove unique constraint from conversation_history.conversation_id."""
    op.drop_constraint(
        "uq_conversation_history_conversation_id",
        "conversation_history",
        type_="unique",
    )
