"""Remove deprecated element_documentation table

Revision ID: 015_remove_element_documentation
Revises: 014_warnings_scoping
Create Date: 2026-01-12 00:00:00.000000

Changes:
- Drop element_documentation table (replaced by Element + ElementImage system)
- The new Element system provides:
  - Structured element catalog with codes
  - ElementImage for per-element images
  - TierElementInclusion for tier-element relationships
  - Better keyword matching via element_service.py

Note: This is a destructive migration. Ensure all data has been migrated
to the new Element system before running.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "015_remove_element_documentation"
down_revision: Union[str, None] = "014_warnings_scoping"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Drop GIN index for keyword search
    # =========================================================================
    op.drop_index(
        "ix_element_documentation_keywords_gin",
        table_name="element_documentation",
    )

    # =========================================================================
    # 2. Drop element_documentation table
    # =========================================================================
    op.drop_table("element_documentation")


def downgrade() -> None:
    # =========================================================================
    # 1. Recreate element_documentation table
    # =========================================================================
    op.create_table(
        "element_documentation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicle_categories.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "element_keywords",
            postgresql.JSONB(),
            nullable=False,
            comment="Keywords that trigger this documentation",
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            comment="Documentation requirement description",
        ),
        sa.Column(
            "image_url",
            sa.String(500),
            nullable=True,
            comment="URL of example image",
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, default=0),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
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
    )

    # =========================================================================
    # 2. Recreate GIN index for keyword search
    # =========================================================================
    op.create_index(
        "ix_element_documentation_keywords_gin",
        "element_documentation",
        ["element_keywords"],
        postgresql_using="gin",
    )
