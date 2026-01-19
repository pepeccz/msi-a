"""Add question_hint column to elements for data-driven variant selection

Revision ID: 022_element_question_hint
Revises: 021_element_hierarchy
Create Date: 2026-01-19 00:00:00.000000

Changes:
- Add question_hint column: Store the question to ask users when selecting variants

This enables base elements with variants to specify their own question,
making the variant selection system fully data-driven instead of hardcoded.

Example:
- BOLA_REMOLQUE.question_hint = "La instalacion aumenta la masa maxima del remolque (MMR)?"
- TOLDO_LAT.question_hint = "El toldo afecta a la luz de galibo del vehiculo?"
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "022_element_question_hint"
down_revision: Union[str, None] = "021_element_hierarchy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add question_hint column for variant selection questions
    op.add_column(
        "elements",
        sa.Column(
            "question_hint",
            sa.String(500),
            nullable=True,
            comment="Question to ask user when selecting variant (for base elements with variants)",
        ),
    )


def downgrade() -> None:
    op.drop_column("elements", "question_hint")
