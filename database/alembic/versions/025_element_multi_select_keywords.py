"""Add multi_select_keywords to elements and update variant keywords

Revision ID: 025_multi_select_kw
Revises: 024_case_image_chatwoot_msg_id
Create Date: 2026-01-23 00:00:00.000000

Changes:
- Add multi_select_keywords JSONB column to elements table
  This data-driven field allows base elements to define keywords that
  select ALL their variants (e.g., "ambos", "todos", "los dos").
- Update INTERMITENTES_DEL and INTERMITENTES_TRAS with single-word keywords
  for direct variant matching (fixes hybrid matching threshold issue).
- Set multi_select_keywords for INTERMITENTES and SUSPENSION base elements.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "025_multi_select_kw"
down_revision: Union[str, None] = "024_case_image_chatwoot_msg_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add multi_select_keywords column
    op.add_column(
        "elements",
        sa.Column(
            "multi_select_keywords",
            JSONB,
            nullable=True,
            comment="Keywords that select ALL variants (e.g., 'ambos', 'todos'). Data-driven multi-select.",
        ),
    )

    # 2. Update data directly in DB
    # Use raw SQL for data migrations (Alembic best practice)
    conn = op.get_bind()

    # --- INTERMITENTES_DEL: Add single-word keywords for direct matching ---
    conn.execute(
        sa.text("""
            UPDATE elements
            SET keywords = keywords || '["delanteros", "delantero", "frontales"]'::jsonb
            WHERE code = 'INTERMITENTES_DEL'
              AND NOT keywords @> '["delanteros"]'::jsonb
        """)
    )

    # --- INTERMITENTES_TRAS: Add single-word keywords for direct matching ---
    conn.execute(
        sa.text("""
            UPDATE elements
            SET keywords = keywords || '["traseros", "trasero", "posteriores"]'::jsonb
            WHERE code = 'INTERMITENTES_TRAS'
              AND NOT keywords @> '["traseros"]'::jsonb
        """)
    )

    # --- INTERMITENTES base: Set multi_select_keywords ---
    conn.execute(
        sa.text("""
            UPDATE elements
            SET multi_select_keywords = '["ambos", "todos", "los dos", "las dos", "delanteros y traseros", "traseros y delanteros"]'::jsonb
            WHERE code = 'INTERMITENTES'
              AND multi_select_keywords IS NULL
        """)
    )

    # --- SUSPENSION base: Set multi_select_keywords ---
    conn.execute(
        sa.text("""
            UPDATE elements
            SET multi_select_keywords = '["ambas", "las dos", "delantera y trasera", "trasera y delantera", "ambos amortiguadores", "los dos amortiguadores"]'::jsonb
            WHERE code = 'SUSPENSION'
              AND multi_select_keywords IS NULL
        """)
    )


def downgrade() -> None:
    # Remove added keywords from variants
    conn = op.get_bind()

    conn.execute(
        sa.text("""
            UPDATE elements
            SET keywords = keywords - 'delanteros' - 'delantero' - 'frontales'
            WHERE code = 'INTERMITENTES_DEL'
        """)
    )

    conn.execute(
        sa.text("""
            UPDATE elements
            SET keywords = keywords - 'traseros' - 'trasero' - 'posteriores'
            WHERE code = 'INTERMITENTES_TRAS'
        """)
    )

    # Remove column
    op.drop_column("elements", "multi_select_keywords")
