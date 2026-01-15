"""Add element hierarchy support for variants and sub-elements

Revision ID: 021_element_hierarchy
Revises: 020_container_error_logs
Create Date: 2026-01-15 00:00:00.000000

Changes:
- Add parent_element_id column: Self-referential FK for parent/child relationships
- Add variant_type column: Type of variant (mmr_option, installation_type, etc.)
- Add variant_code column: Short code for variant (SIN_MMR, CON_MMR, etc.)
- Add index on parent_element_id for efficient hierarchy queries

This enables elements to have variants/sub-elements:
- BOLA_REMOLQUE (parent) → BOLA_SIN_MMR, BOLA_CON_MMR (children)
- GLP_INSTALACION (parent) → GLP_KIT_BOMBONA, GLP_DEPOSITO, GLP_DUOCONTROL (children)
- Elementos sin variantes mantienen parent_element_id = NULL
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "021_element_hierarchy"
down_revision: Union[str, None] = "020_container_error_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Add parent_element_id column (self-referential FK)
    # =========================================================================
    op.add_column(
        "elements",
        sa.Column(
            "parent_element_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Parent element for variants/sub-elements. NULL = base element.",
        ),
    )

    # =========================================================================
    # 2. Add variant_type column
    # =========================================================================
    op.add_column(
        "elements",
        sa.Column(
            "variant_type",
            sa.String(50),
            nullable=True,
            comment="Type of variant: mmr_option, installation_type, suspension_type, etc.",
        ),
    )

    # =========================================================================
    # 3. Add variant_code column
    # =========================================================================
    op.add_column(
        "elements",
        sa.Column(
            "variant_code",
            sa.String(50),
            nullable=True,
            comment="Short code for this variant: SIN_MMR, CON_MMR, FULL_AIR, etc.",
        ),
    )

    # =========================================================================
    # 4. Add foreign key constraint for parent_element_id
    # =========================================================================
    op.create_foreign_key(
        "fk_elements_parent_element_id",
        "elements",
        "elements",
        ["parent_element_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # =========================================================================
    # 5. Add index for efficient parent_element_id queries
    # =========================================================================
    op.create_index(
        "ix_elements_parent_element_id",
        "elements",
        ["parent_element_id"],
    )


def downgrade() -> None:
    # Drop in reverse order
    op.drop_index("ix_elements_parent_element_id", table_name="elements")
    op.drop_constraint("fk_elements_parent_element_id", "elements", type_="foreignkey")
    op.drop_column("elements", "variant_code")
    op.drop_column("elements", "variant_type")
    op.drop_column("elements", "parent_element_id")
