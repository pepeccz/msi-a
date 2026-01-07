"""Rename customers to users

Revision ID: 004_customer_to_user
Revises: 003_tariff_restructure
Create Date: 2026-01-07 00:00:00.000000

Changes:
- Rename table customers -> users
- Rename column customer_id -> user_id in conversation_history
- Update foreign key constraint
- Update indexes
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "004_customer_to_user"
down_revision: Union[str, None] = "003_tariff_restructure"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Rename customers table to users
    # =========================================================================
    op.rename_table("customers", "users")

    # =========================================================================
    # 2. Rename index on phone column
    # =========================================================================
    op.drop_index("ix_customers_phone", table_name="users")
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)

    # =========================================================================
    # 3. Drop old foreign key constraint on conversation_history
    # =========================================================================
    op.drop_constraint(
        "conversation_history_customer_id_fkey",
        "conversation_history",
        type_="foreignkey",
    )

    # =========================================================================
    # 4. Drop old index on customer_id
    # =========================================================================
    op.drop_index("ix_conversation_history_customer_id", table_name="conversation_history")

    # =========================================================================
    # 5. Rename column customer_id -> user_id in conversation_history
    # =========================================================================
    op.alter_column(
        "conversation_history",
        "customer_id",
        new_column_name="user_id",
    )

    # =========================================================================
    # 6. Create new foreign key constraint pointing to users table
    # =========================================================================
    op.create_foreign_key(
        "conversation_history_user_id_fkey",
        "conversation_history",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # =========================================================================
    # 7. Create new index on user_id
    # =========================================================================
    op.create_index(
        "ix_conversation_history_user_id",
        "conversation_history",
        ["user_id"],
    )


def downgrade() -> None:
    # =========================================================================
    # 1. Drop new index on user_id
    # =========================================================================
    op.drop_index("ix_conversation_history_user_id", table_name="conversation_history")

    # =========================================================================
    # 2. Drop new foreign key constraint
    # =========================================================================
    op.drop_constraint(
        "conversation_history_user_id_fkey",
        "conversation_history",
        type_="foreignkey",
    )

    # =========================================================================
    # 3. Rename column user_id -> customer_id
    # =========================================================================
    op.alter_column(
        "conversation_history",
        "user_id",
        new_column_name="customer_id",
    )

    # =========================================================================
    # 4. Create old index on customer_id
    # =========================================================================
    op.create_index(
        "ix_conversation_history_customer_id",
        "conversation_history",
        ["customer_id"],
    )

    # =========================================================================
    # 5. Create old foreign key constraint pointing to customers table
    # =========================================================================
    op.create_foreign_key(
        "conversation_history_customer_id_fkey",
        "conversation_history",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # =========================================================================
    # 6. Rename index on phone column back
    # =========================================================================
    op.drop_index("ix_users_phone", table_name="users")
    op.create_index("ix_customers_phone", "users", ["phone"], unique=True)

    # =========================================================================
    # 7. Rename users table back to customers
    # =========================================================================
    op.rename_table("users", "customers")
