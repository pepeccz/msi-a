"""Fix field length discrepancies between migrations and models

Revision ID: 018_fix_field_lengths
Revises: 017_expand_case_fields
Create Date: 2026-01-13 00:00:00.000000

Changes:
- Expand cases.apellidos from String(150) to String(200) to match model
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "018_fix_field_lengths"
down_revision: Union[str, None] = "017_expand_case_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Expand apellidos from 150 to 200 characters
    op.alter_column(
        "cases",
        "apellidos",
        existing_type=sa.String(150),
        type_=sa.String(200),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Shrink back to 150 (may truncate data!)
    op.alter_column(
        "cases",
        "apellidos",
        existing_type=sa.String(200),
        type_=sa.String(150),
        existing_nullable=True,
    )
