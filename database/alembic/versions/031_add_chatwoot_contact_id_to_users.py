"""Add chatwoot_contact_id to users table for Chatwoot sync.

Revision ID: 031_chatwoot_contact_id
Revises: 030_element_required_fields
Create Date: 2026-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "031_chatwoot_contact_id"
down_revision: Union[str, None] = "030_element_required_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add chatwoot_contact_id column to users table."""
    op.add_column(
        "users",
        sa.Column(
            "chatwoot_contact_id",
            sa.Integer(),
            nullable=True,
            comment="Chatwoot contact ID for synchronization",
        ),
    )
    op.create_index(
        "ix_users_chatwoot_contact_id",
        "users",
        ["chatwoot_contact_id"],
    )


def downgrade() -> None:
    """Remove chatwoot_contact_id column from users table."""
    op.drop_index("ix_users_chatwoot_contact_id", table_name="users")
    op.drop_column("users", "chatwoot_contact_id")
