"""Add admin users and access log tables

Revision ID: 006_admin_users
Revises: 005_elem_docs_images
Create Date: 2026-01-07 00:00:00.000000

Changes:
- Add admin_users table for admin panel authentication
- Add admin_access_log table for tracking login/logout activity
- Seed initial admin user from environment variables
"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006_admin_users"
down_revision: Union[str, None] = "005_elem_docs_images"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create admin_users table
    # =========================================================================
    op.create_table(
        "admin_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "username",
            sa.String(50),
            unique=True,
            nullable=False,
            index=True,
            comment="Unique username for login",
        ),
        sa.Column(
            "password_hash",
            sa.String(255),
            nullable=False,
            comment="Bcrypt password hash",
        ),
        sa.Column(
            "role",
            sa.String(20),
            nullable=False,
            server_default="user",
            comment="User role: admin or user",
        ),
        sa.Column(
            "display_name",
            sa.String(100),
            nullable=True,
            comment="Display name for UI",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Soft delete flag",
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
            onupdate=sa.func.now(),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
            comment="Admin user who created this user",
        ),
    )

    # =========================================================================
    # 2. Create admin_access_log table
    # =========================================================================
    op.create_table(
        "admin_access_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "action",
            sa.String(20),
            nullable=False,
            comment="Action: login, logout, login_failed",
        ),
        sa.Column(
            "ip_address",
            sa.String(45),
            nullable=True,
            comment="Client IP address (IPv4 or IPv6)",
        ),
        sa.Column(
            "user_agent",
            sa.String(500),
            nullable=True,
            comment="Client user agent string",
        ),
        sa.Column(
            "details",
            postgresql.JSONB(),
            nullable=True,
            comment="Additional details (error messages, etc.)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
    )

    # =========================================================================
    # 3. Seed initial admin user from environment variables
    # =========================================================================
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password_hash = os.getenv("ADMIN_PASSWORD_HASH", "")

    if admin_password_hash:
        # Use raw SQL to insert the seed user
        op.execute(
            sa.text(
                """
                INSERT INTO admin_users (id, username, password_hash, role, display_name, is_active)
                VALUES (
                    gen_random_uuid(),
                    :username,
                    :password_hash,
                    'admin',
                    'Administrador',
                    true
                )
                ON CONFLICT (username) DO NOTHING
                """
            ).bindparams(
                username=admin_username,
                password_hash=admin_password_hash,
            )
        )


def downgrade() -> None:
    # =========================================================================
    # 1. Drop admin_access_log table
    # =========================================================================
    op.drop_table("admin_access_log")

    # =========================================================================
    # 2. Drop admin_users table
    # =========================================================================
    op.drop_table("admin_users")
