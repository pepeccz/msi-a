"""Add variant_position to elements table

Revision ID: 036_add_variant_position
Revises: 035_restructure_motos_elements
Create Date: 2026-02-21 00:00:00.000000

Adds variant_position (INT NULL) to elements table.
- Only populated for child elements (parent_element_id IS NOT NULL)
- Defines canonical presentation order to the user (1, 2, 3...)
- Independent of sort_order (which is only for admin panel display)
- Populated via ROW_NUMBER() OVER (PARTITION BY parent_element_id ORDER BY sort_order)
  so existing sort_order values define the initial variant_position values

This field is used by the agent to reliably map user responses ("A", "B", "C")
to the correct variant in the database, replacing the fragile index-based approach.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "036_add_variant_position"
down_revision: Union[str, None] = "035_restructure_motos_elements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add column as nullable (no server default — only variants get a value)
    op.add_column(
        "elements",
        sa.Column("variant_position", sa.Integer(), nullable=True),
    )

    # 2. Populate existing variants using ROW_NUMBER() ordered by sort_order
    # Only elements WITH a parent (variants) receive a value; base elements stay NULL
    op.execute(
        """
        UPDATE elements
        SET variant_position = subq.rn
        FROM (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY parent_element_id
                    ORDER BY sort_order ASC NULLS LAST
                ) AS rn
            FROM elements
            WHERE parent_element_id IS NOT NULL
              AND is_active = true
        ) AS subq
        WHERE elements.id = subq.id
        """
    )


def downgrade() -> None:
    op.drop_column("elements", "variant_position")
