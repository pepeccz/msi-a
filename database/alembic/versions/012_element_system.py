"""Add element system tables for hierarchical tariff inclusions

Revision ID: 012_element_system
Revises: 011_section_mappings
Create Date: 2026-01-09 12:00:00.000000

Changes:
- Add elements table: Catalog of homologable elements per category
- Add element_images table: Multiple images per element (examples, required documents)
- Add tier_element_inclusions table: Relationships between tiers and elements/tiers (with CHECK constraint)
- Add element_warning_associations table: Link warnings to elements
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "012_element_system"
down_revision: Union[str, None] = "011_section_mappings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create elements table
    # =========================================================================
    op.create_table(
        "elements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicle_categories.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            comment="FK to VehicleCategory - each element belongs to exactly one category",
        ),
        sa.Column(
            "code",
            sa.String(50),
            nullable=False,
            comment="Unique element code (e.g., 'ESC_MEC', 'TOLDO_LAT')",
        ),
        sa.Column(
            "name",
            sa.String(200),
            nullable=False,
            comment="Element display name",
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="Detailed description",
        ),
        sa.Column(
            "keywords",
            postgresql.JSONB(),
            nullable=False,
            comment="Keywords for matching (e.g., ['escalera', 'escalera mecanica'])",
        ),
        sa.Column(
            "aliases",
            postgresql.JSONB(),
            nullable=True,
            comment="Alternative names for the element",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Soft delete via is_active flag",
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Display order in admin panel",
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
        sa.UniqueConstraint(
            "category_id",
            "code",
            name="uq_category_element_code",
        ),
    )

    # =========================================================================
    # 2. Create element_images table
    # =========================================================================
    op.create_table(
        "element_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "element_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("elements.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "image_url",
            sa.String(500),
            nullable=False,
            comment="URL to image (S3/Cloudinary)",
        ),
        sa.Column(
            "title",
            sa.String(200),
            nullable=True,
            comment="Image title",
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="Image description for client",
        ),
        sa.Column(
            "image_type",
            sa.String(50),
            nullable=False,
            comment="Type: 'example', 'required_document', or 'warning'",
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Display order",
        ),
        sa.Column(
            "is_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether this image/document is required from client",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # =========================================================================
    # 3. Create tier_element_inclusions table (CRITICAL)
    # =========================================================================
    op.create_table(
        "tier_element_inclusions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tariff_tiers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            comment="The tier that includes element(s)",
        ),
        sa.Column(
            "element_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("elements.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
            comment="Specific element included (mutually exclusive with included_tier_id)",
        ),
        sa.Column(
            "included_tier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tariff_tiers.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
            comment="Another tier's elements included (mutually exclusive with element_id)",
        ),
        sa.Column(
            "min_quantity",
            sa.Integer(),
            nullable=True,
            comment="Minimum number of items (rarely used)",
        ),
        sa.Column(
            "max_quantity",
            sa.Integer(),
            nullable=True,
            comment="Maximum number of items (NULL = unlimited)",
        ),
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
            comment="Admin notes about this inclusion",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "(element_id IS NOT NULL AND included_tier_id IS NULL) OR "
            "(element_id IS NULL AND included_tier_id IS NOT NULL)",
            name="ck_tier_inclusion_xor",
        ),
    )

    # =========================================================================
    # 4. Create element_warning_associations table
    # =========================================================================
    op.create_table(
        "element_warning_associations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "element_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("elements.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "warning_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warnings.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "show_condition",
            sa.String(50),
            nullable=False,
            comment="When to show: 'always' or 'if_selected'",
        ),
        sa.Column(
            "threshold_quantity",
            sa.Integer(),
            nullable=True,
            comment="Show warning only if quantity >= this value",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "element_id",
            "warning_id",
            name="uq_element_warning",
        ),
    )

    # =========================================================================
    # 5. Create indices for optimal query performance
    # =========================================================================
    op.create_index(
        "idx_elements_category_active",
        "elements",
        ["category_id", "is_active"],
    )
    op.create_index(
        "idx_element_images_element_type",
        "element_images",
        ["element_id", "image_type"],
    )
    op.create_index(
        "idx_tier_inclusions_element",
        "tier_element_inclusions",
        ["element_id"],
    )
    op.create_index(
        "idx_tier_inclusions_included",
        "tier_element_inclusions",
        ["included_tier_id"],
    )


def downgrade() -> None:
    # =========================================================================
    # 1. Drop indices
    # =========================================================================
    op.drop_index("idx_tier_inclusions_included")
    op.drop_index("idx_tier_inclusions_element")
    op.drop_index("idx_element_images_element_type")
    op.drop_index("idx_elements_category_active")

    # =========================================================================
    # 2. Drop tables in reverse order (respecting foreign key dependencies)
    # =========================================================================
    op.drop_table("element_warning_associations")
    op.drop_table("tier_element_inclusions")
    op.drop_table("element_images")
    op.drop_table("elements")
