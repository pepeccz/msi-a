"""
MSI Automotive - Add scoping fields to warnings table.

Revision ID: 014_warnings_scoping
Revises: 013_separate_categories_by_type
Create Date: 2026-01-11

Changes:
- Add category_id, tier_id, element_id to warnings table (nullable for global warnings)
- Add indexes for efficient filtering by scope
- Add check constraint: max one scope field can be set (or none for global)

This allows warnings to be:
- Global (all scope fields NULL): Apply everywhere based on trigger_conditions
- Category-specific: Only show for a specific category
- Tier-specific: Only show when a specific tariff tier is selected
- Element-specific: Only show when a specific element is matched
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "014_warnings_scoping"
down_revision = "013_separate_categories_by_type"
branch_labels = None
depends_on = None


def upgrade():
    # Add scope columns to warnings table
    op.add_column(
        "warnings",
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicle_categories.id", ondelete="CASCADE"),
            nullable=True,
            comment="If set, warning only applies to this category"
        )
    )
    op.add_column(
        "warnings",
        sa.Column(
            "tier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tariff_tiers.id", ondelete="CASCADE"),
            nullable=True,
            comment="If set, warning only shows when this tier is selected"
        )
    )
    op.add_column(
        "warnings",
        sa.Column(
            "element_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("elements.id", ondelete="CASCADE"),
            nullable=True,
            comment="If set, warning only shows when this element is matched"
        )
    )

    # Create indexes for efficient filtering
    op.create_index(
        "idx_warnings_category",
        "warnings",
        ["category_id"],
        postgresql_where=sa.text("category_id IS NOT NULL")
    )
    op.create_index(
        "idx_warnings_tier",
        "warnings",
        ["tier_id"],
        postgresql_where=sa.text("tier_id IS NOT NULL")
    )
    op.create_index(
        "idx_warnings_element",
        "warnings",
        ["element_id"],
        postgresql_where=sa.text("element_id IS NOT NULL")
    )

    # Add check constraint: at most one scope field can be set
    # (NULL, NULL, NULL) = global warning (allowed)
    # (uuid, NULL, NULL) = category warning (allowed)
    # (NULL, uuid, NULL) = tier warning (allowed)
    # (NULL, NULL, uuid) = element warning (allowed)
    # (uuid, uuid, NULL) = NOT ALLOWED
    op.execute("""
        ALTER TABLE warnings ADD CONSTRAINT ck_warning_scope_exclusive CHECK (
            (CASE WHEN category_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN tier_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN element_id IS NOT NULL THEN 1 ELSE 0 END) <= 1
        )
    """)


def downgrade():
    # Remove check constraint
    op.execute("ALTER TABLE warnings DROP CONSTRAINT IF EXISTS ck_warning_scope_exclusive")

    # Remove indexes
    op.drop_index("idx_warnings_element", table_name="warnings")
    op.drop_index("idx_warnings_tier", table_name="warnings")
    op.drop_index("idx_warnings_category", table_name="warnings")

    # Remove columns
    op.drop_column("warnings", "element_id")
    op.drop_column("warnings", "tier_id")
    op.drop_column("warnings", "category_id")
