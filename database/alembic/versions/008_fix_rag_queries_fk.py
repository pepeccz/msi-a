"""Fix rag_queries user_id FK to reference admin_users

Revision ID: 008_fix_rag_queries_fk
Revises: 007_rag_system
Create Date: 2026-01-08 14:40:00.000000

Changes:
- Drop FK constraint from rag_queries.user_id -> users.id
- Add FK constraint from rag_queries.user_id -> admin_users.id
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "008_fix_rag_queries_fk"
down_revision: Union[str, None] = "007_rag_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the incorrect FK to users table
    op.drop_constraint(
        "rag_queries_user_id_fkey",
        "rag_queries",
        type_="foreignkey"
    )

    # Add correct FK to admin_users table
    op.create_foreign_key(
        "rag_queries_user_id_fkey",
        "rag_queries",
        "admin_users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL"
    )


def downgrade() -> None:
    # Revert: drop FK to admin_users
    op.drop_constraint(
        "rag_queries_user_id_fkey",
        "rag_queries",
        type_="foreignkey"
    )

    # Recreate original FK to users
    op.create_foreign_key(
        "rag_queries_user_id_fkey",
        "rag_queries",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL"
    )
