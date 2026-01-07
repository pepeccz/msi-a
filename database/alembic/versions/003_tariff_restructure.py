"""Restructure tariff system - remove elements, add dynamic prompts

Revision ID: 003_tariff_restructure
Revises: 002_tariff_system
Create Date: 2025-01-15 00:00:00.000000

Changes:
- Add client_type to customers (particular/professional)
- Add client_type and classification_rules to tariff_tiers
- Add trigger_conditions to warnings
- Create tariff_prompt_sections table for dynamic prompts
- Remove homologation_elements, element_documentation, element_warnings tables
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003_tariff_restructure"
down_revision: Union[str, None] = "002_tariff_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Add client_type to customers table
    # =========================================================================
    op.add_column(
        "customers",
        sa.Column(
            "client_type",
            sa.String(20),
            nullable=False,
            server_default="particular",
            comment="Client type: particular or professional",
        ),
    )

    # =========================================================================
    # 2. Add client_type and classification_rules to tariff_tiers
    # =========================================================================
    op.add_column(
        "tariff_tiers",
        sa.Column(
            "client_type",
            sa.String(20),
            nullable=False,
            server_default="all",
            comment="Client type: particular, professional, or all",
        ),
    )
    op.add_column(
        "tariff_tiers",
        sa.Column(
            "classification_rules",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="JSON rules for AI classification",
        ),
    )

    # Update unique constraint to include client_type
    op.drop_constraint("uq_category_tier_code", "tariff_tiers", type_="unique")
    op.create_unique_constraint(
        "uq_category_tier_code_client",
        "tariff_tiers",
        ["category_id", "code", "client_type"],
    )

    # =========================================================================
    # 3. Add trigger_conditions to warnings
    # =========================================================================
    op.add_column(
        "warnings",
        sa.Column(
            "trigger_conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="JSON conditions that trigger this warning",
        ),
    )

    # =========================================================================
    # 4. Create tariff_prompt_sections table
    # =========================================================================
    op.create_table(
        "tariff_prompt_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "section_type",
            sa.String(50),
            nullable=False,
            comment="Section type: algorithm, recognition_table, special_cases, footer",
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            comment="Section content (markdown supported)",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            default=1,
            comment="Version number for tracking changes",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"], ["vehicle_categories.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", "section_type", name="uq_category_section"),
    )
    op.create_index(
        "ix_tariff_prompt_sections_category_id",
        "tariff_prompt_sections",
        ["category_id"],
    )

    # =========================================================================
    # 5. Drop obsolete tables (in order due to foreign key constraints)
    # =========================================================================
    op.drop_index("ix_element_warnings_warning_id", table_name="element_warnings")
    op.drop_index("ix_element_warnings_element_id", table_name="element_warnings")
    op.drop_table("element_warnings")

    op.drop_index("ix_element_documentation_element_id", table_name="element_documentation")
    op.drop_table("element_documentation")

    op.drop_index("ix_homologation_elements_tier_id", table_name="homologation_elements")
    op.drop_index("ix_homologation_elements_category_id", table_name="homologation_elements")
    op.drop_table("homologation_elements")


def downgrade() -> None:
    # =========================================================================
    # Recreate homologation_elements table
    # =========================================================================
    op.create_table(
        "homologation_elements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requires_marking", sa.Boolean(), nullable=False, default=False),
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
    # Recreate element_documentation table
    # =========================================================================
    op.create_table(
        "element_documentation",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("element_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["element_id"], ["homologation_elements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_element_documentation_element_id", "element_documentation", ["element_id"])

    # =========================================================================
    # Recreate element_warnings table
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
    # Drop tariff_prompt_sections table
    # =========================================================================
    op.drop_index("ix_tariff_prompt_sections_category_id", table_name="tariff_prompt_sections")
    op.drop_table("tariff_prompt_sections")

    # =========================================================================
    # Remove trigger_conditions from warnings
    # =========================================================================
    op.drop_column("warnings", "trigger_conditions")

    # =========================================================================
    # Restore original constraint and remove new columns from tariff_tiers
    # =========================================================================
    op.drop_constraint("uq_category_tier_code_client", "tariff_tiers", type_="unique")
    op.create_unique_constraint(
        "uq_category_tier_code",
        "tariff_tiers",
        ["category_id", "code"],
    )
    op.drop_column("tariff_tiers", "classification_rules")
    op.drop_column("tariff_tiers", "client_type")

    # =========================================================================
    # Remove client_type from customers
    # =========================================================================
    op.drop_column("customers", "client_type")
