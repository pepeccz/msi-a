"""Initial schema for MSI Automotive

Revision ID: 001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create customers table
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False, comment="E.164 format phone number"),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("nif_cif", sa.String(20), nullable=True, comment="Spanish NIF/CIF tax ID"),
        sa.Column("company_name", sa.String(200), nullable=True, comment="Company name for B2B customers"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Additional customer data"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone"),
    )
    op.create_index("ix_customers_phone", "customers", ["phone"])

    # Create conversation_history table
    op.create_table(
        "conversation_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", sa.String(100), nullable=False, comment="Chatwoot conversation ID"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, default=0),
        sa.Column("summary", sa.Text(), nullable=True, comment="AI-generated conversation summary"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Additional conversation data"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversation_history_customer_id", "conversation_history", ["customer_id"])
    op.create_index("ix_conversation_history_conversation_id", "conversation_history", ["conversation_id"])
    op.create_index("ix_conversation_history_conversation_started", "conversation_history", ["conversation_id", "started_at"])

    # Create policies table
    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(100), nullable=False, comment="Unique policy identifier"),
        sa.Column("value", sa.Text(), nullable=False, comment="Policy content (markdown supported)"),
        sa.Column("category", sa.String(50), nullable=False, comment="Policy category"),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_policies_key", "policies", ["key"])
    op.create_index("ix_policies_category", "policies", ["category"])

    # Create system_settings table
    op.create_table(
        "system_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(100), nullable=False, comment="Setting key"),
        sa.Column("value", sa.String(1000), nullable=False, comment="Setting value"),
        sa.Column("value_type", sa.String(20), nullable=False, default="string", comment="Value type: string, integer, boolean, json"),
        sa.Column("description", sa.String(500), nullable=True, comment="Human-readable description"),
        sa.Column("is_mutable", sa.Boolean(), nullable=False, default=True, comment="Whether the setting can be changed at runtime"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_system_settings_key", "system_settings", ["key"])


def downgrade() -> None:
    op.drop_table("system_settings")
    op.drop_table("policies")
    op.drop_table("conversation_history")
    op.drop_table("customers")
