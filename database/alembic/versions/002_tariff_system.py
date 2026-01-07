"""Add tariff system tables

Revision ID: 002_tariff_system
Revises: 001_initial
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002_tariff_system"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # Create vehicle_categories table
    # =========================================================================
    op.create_table(
        "vehicle_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(50), nullable=False, comment="URL-friendly identifier"),
        sa.Column("name", sa.String(100), nullable=False, comment="Display name"),
        sa.Column("description", sa.Text(), nullable=True, comment="Category description"),
        sa.Column("icon", sa.String(50), nullable=True, comment="Lucide icon name"),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_vehicle_categories_slug", "vehicle_categories", ["slug"])

    # =========================================================================
    # Create warnings table
    # =========================================================================
    op.create_table(
        "warnings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(50), nullable=False, comment="Warning code"),
        sa.Column("message", sa.Text(), nullable=False, comment="Warning message"),
        sa.Column("severity", sa.String(20), nullable=False, default="warning", comment="Severity: info, warning, error"),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_warnings_code", "warnings", ["code"])

    # =========================================================================
    # Create tariff_tiers table
    # =========================================================================
    op.create_table(
        "tariff_tiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(20), nullable=False, comment="Tier code (T1, T2, etc.)"),
        sa.Column("name", sa.String(100), nullable=False, comment="Tier name"),
        sa.Column("description", sa.Text(), nullable=True, comment="Detailed description"),
        sa.Column("price", sa.Numeric(10, 2), nullable=False, comment="Price in EUR"),
        sa.Column("conditions", sa.Text(), nullable=True, comment="Tier conditions"),
        sa.Column("min_elements", sa.Integer(), nullable=True, comment="Minimum elements for this tier"),
        sa.Column("max_elements", sa.Integer(), nullable=True, comment="Maximum elements (NULL = unlimited)"),
        sa.Column("sort_order", sa.Integer(), nullable=False, default=0),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["vehicle_categories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", "code", name="uq_category_tier_code"),
    )
    op.create_index("ix_tariff_tiers_category_id", "tariff_tiers", ["category_id"])

    # =========================================================================
    # Create base_documentation table
    # =========================================================================
    op.create_table(
        "base_documentation",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, comment="Documentation requirement"),
        sa.Column("image_url", sa.String(500), nullable=True, comment="Example image URL"),
        sa.Column("sort_order", sa.Integer(), nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["vehicle_categories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_base_documentation_category_id", "base_documentation", ["category_id"])

    # =========================================================================
    # Create additional_services table
    # =========================================================================
    op.create_table(
        "additional_services",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True, comment="NULL = global service"),
        sa.Column("code", sa.String(50), nullable=False, comment="Service code"),
        sa.Column("name", sa.String(150), nullable=False, comment="Display name"),
        sa.Column("description", sa.Text(), nullable=True, comment="Service description"),
        sa.Column("price", sa.Numeric(10, 2), nullable=False, comment="Price in EUR"),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["vehicle_categories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_additional_services_category_id", "additional_services", ["category_id"])

    # =========================================================================
    # Create homologation_elements table
    # =========================================================================
    op.create_table(
        "homologation_elements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tier_id", postgresql.UUID(as_uuid=True), nullable=True, comment="Default tier assignment"),
        sa.Column("code", sa.String(50), nullable=False, comment="Element code"),
        sa.Column("name", sa.String(150), nullable=False, comment="Display name"),
        sa.Column("description", sa.Text(), nullable=True, comment="Element description"),
        sa.Column("requires_marking", sa.Boolean(), nullable=False, default=False, comment="Requires homologation marking"),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["vehicle_categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tier_id"], ["tariff_tiers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", "code", name="uq_category_element_code"),
    )
    op.create_index("ix_homologation_elements_category_id", "homologation_elements", ["category_id"])
    op.create_index("ix_homologation_elements_tier_id", "homologation_elements", ["tier_id"])

    # =========================================================================
    # Create element_documentation table
    # =========================================================================
    op.create_table(
        "element_documentation",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("element_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, comment="Documentation requirement"),
        sa.Column("image_url", sa.String(500), nullable=True, comment="Example image URL"),
        sa.Column("sort_order", sa.Integer(), nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["element_id"], ["homologation_elements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_element_documentation_element_id", "element_documentation", ["element_id"])

    # =========================================================================
    # Create element_warnings table (junction table)
    # =========================================================================
    op.create_table(
        "element_warnings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("element_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("warning_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["element_id"], ["homologation_elements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warning_id"], ["warnings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("element_id", "warning_id", name="uq_element_warning"),
    )
    op.create_index("ix_element_warnings_element_id", "element_warnings", ["element_id"])
    op.create_index("ix_element_warnings_warning_id", "element_warnings", ["warning_id"])

    # =========================================================================
    # Create audit_log table
    # =========================================================================
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False, comment="Entity type"),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False, comment="Entity ID"),
        sa.Column("action", sa.String(20), nullable=False, comment="Action: create, update, delete"),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Old/new values"),
        sa.Column("user", sa.String(100), nullable=True, comment="Username"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_entity", "audit_log", ["entity_type", "entity_id"])


def downgrade() -> None:
    # Drop tables in reverse order due to foreign key constraints
    op.drop_table("audit_log")
    op.drop_table("element_warnings")
    op.drop_table("element_documentation")
    op.drop_table("homologation_elements")
    op.drop_table("additional_services")
    op.drop_table("base_documentation")
    op.drop_table("tariff_tiers")
    op.drop_table("warnings")
    op.drop_table("vehicle_categories")
