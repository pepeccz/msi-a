"""Add section_mappings to regulatory_documents

Revision ID: 011_section_mappings
Revises: 010_panic_button_settings
Create Date: 2026-01-08 12:00:00.000000

Changes:
- Add section_mappings JSONB column for AI-extracted section mappings
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "011_section_mappings"
down_revision: Union[str, None] = "010_panic_button_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "regulatory_documents",
        sa.Column(
            "section_mappings",
            postgresql.JSONB(),
            nullable=True,
            comment="AI-extracted section number to description mappings (e.g., {'6.2': 'Luces de cruce'})",
        ),
    )


def downgrade() -> None:
    op.drop_column("regulatory_documents", "section_mappings")
