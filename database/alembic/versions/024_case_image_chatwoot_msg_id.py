"""Add chatwoot_message_id to case_images for reconciliation

Revision ID: 024_case_image_chatwoot_msg_id
Revises: 023_token_usage
Create Date: 2026-01-23 00:00:00.000000

Changes:
- Add chatwoot_message_id column to case_images for deduplication
  during image reconciliation (when Chatwoot drops webhooks)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "024_case_image_chatwoot_msg_id"
down_revision: Union[str, None] = "023_token_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "case_images",
        sa.Column("chatwoot_message_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_case_images_chatwoot_message_id",
        "case_images",
        ["chatwoot_message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_case_images_chatwoot_message_id", table_name="case_images")
    op.drop_column("case_images", "chatwoot_message_id")
