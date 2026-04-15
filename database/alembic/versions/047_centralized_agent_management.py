"""Centralized agent management: rename role user→agent, add email and chatwoot_agent_id

Revision ID: 047_centralized_agent_management
Revises: 046_drop_response_constraints
"""

from alembic import op
import sqlalchemy as sa

revision: str = "047_centralized_agent_management"
down_revision: str = "046_drop_response_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Rename role value 'user' → 'agent'
    op.execute("UPDATE admin_users SET role = 'agent' WHERE role = 'user'")

    # Step 2: Add email column
    op.add_column(
        "admin_users",
        sa.Column("email", sa.String(255), nullable=True,
                  comment="Email address (required for Chatwoot agent sync)"),
    )

    # Step 3: Add chatwoot_agent_id column
    op.add_column(
        "admin_users",
        sa.Column("chatwoot_agent_id", sa.Integer, nullable=True,
                  comment="Chatwoot agent ID (system-managed, read-only)"),
    )

    # Step 4: Partial unique indexes (allow multiple NULLs)
    op.create_index(
        "ix_admin_users_email_unique",
        "admin_users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.create_index(
        "ix_admin_users_chatwoot_agent_id_unique",
        "admin_users",
        ["chatwoot_agent_id"],
        unique=True,
        postgresql_where=sa.text("chatwoot_agent_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_admin_users_chatwoot_agent_id_unique", table_name="admin_users")
    op.drop_index("ix_admin_users_email_unique", table_name="admin_users")
    op.drop_column("admin_users", "chatwoot_agent_id")
    op.drop_column("admin_users", "email")
    op.execute("UPDATE admin_users SET role = 'user' WHERE role = 'agent'")
