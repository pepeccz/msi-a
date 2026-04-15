"""Add chatwoot_user_id to admin_users for Platform API support

Revision ID: 048_chatwoot_user_id
Revises: 047_centralized_agent_management
"""

from alembic import op
import sqlalchemy as sa

revision: str = "048_chatwoot_user_id"
down_revision: str = "047_centralized_agent_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("chatwoot_user_id", sa.Integer, nullable=True,
                  comment="Chatwoot Platform API user ID (system-managed)"),
    )
    op.create_index(
        "ix_admin_users_chatwoot_user_id_unique",
        "admin_users",
        ["chatwoot_user_id"],
        unique=True,
        postgresql_where=sa.text("chatwoot_user_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_admin_users_chatwoot_user_id_unique", table_name="admin_users")
    op.drop_column("admin_users", "chatwoot_user_id")
