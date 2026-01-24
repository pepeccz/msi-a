"""Add inherit_parent_data to elements

Revision ID: 026_inherit_parent_data
Revises: 025_multi_select_kw
Create Date: 2026-01-24 00:00:00.000000

Changes:
- Add inherit_parent_data Boolean column to elements table (default True).
  When enabled, child elements inherit their parent's warnings and images
  in agent responses. This is recursive through the ancestor chain.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "026_inherit_parent_data"
down_revision: Union[str, None] = "025_multi_select_kw"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "elements",
        sa.Column(
            "inherit_parent_data",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="If True, child element inherits parent's warnings and images in agent responses",
        ),
    )


def downgrade() -> None:
    op.drop_column("elements", "inherit_parent_data")
