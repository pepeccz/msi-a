"""Separate categories by client type

Revision ID: 013_separate_categories_by_type
Revises: 012_element_system
Create Date: 2026-01-11 12:00:00.000000

Changes:
- Add client_type column to vehicle_categories (differentiation moves up)
- Remove client_type column from tariff_tiers (no longer needed at tier level)
- Update unique constraints accordingly

After this migration:
- Categories are separated by type: motos-part, motos-prof, aseicars-part, aseicars-prof
- Elements belong to categories (and implicitly to a client type)
- Tariff tiers are unique by (category_id, code) only
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "013_separate_categories_by_type"
down_revision: Union[str, None] = "012_element_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Add client_type to vehicle_categories
    # =========================================================================
    op.add_column(
        "vehicle_categories",
        sa.Column(
            "client_type",
            sa.String(20),
            nullable=False,
            server_default="particular",
            comment="Client type: particular or professional",
        ),
    )

    # Create index for efficient filtering by client_type
    op.create_index(
        "idx_vehicle_categories_client_type",
        "vehicle_categories",
        ["client_type"],
    )

    # =========================================================================
    # 2. Remove client_type from tariff_tiers
    # =========================================================================
    # First drop the old unique constraint that includes client_type
    op.drop_constraint(
        "uq_category_tier_code_client",
        "tariff_tiers",
        type_="unique",
    )

    # Drop the client_type column
    op.drop_column("tariff_tiers", "client_type")

    # Create new unique constraint without client_type
    op.create_unique_constraint(
        "uq_category_tier_code",
        "tariff_tiers",
        ["category_id", "code"],
    )


def downgrade() -> None:
    # =========================================================================
    # 1. Restore client_type to tariff_tiers
    # =========================================================================
    # Drop the new unique constraint
    op.drop_constraint(
        "uq_category_tier_code",
        "tariff_tiers",
        type_="unique",
    )

    # Add client_type column back
    op.add_column(
        "tariff_tiers",
        sa.Column(
            "client_type",
            sa.String(20),
            nullable=False,
            server_default="all",
        ),
    )

    # Restore the old unique constraint
    op.create_unique_constraint(
        "uq_category_tier_code_client",
        "tariff_tiers",
        ["category_id", "code", "client_type"],
    )

    # =========================================================================
    # 2. Remove client_type from vehicle_categories
    # =========================================================================
    op.drop_index("idx_vehicle_categories_client_type", "vehicle_categories")
    op.drop_column("vehicle_categories", "client_type")
