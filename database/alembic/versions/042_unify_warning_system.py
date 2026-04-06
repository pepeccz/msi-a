"""Remove element_id from warnings table — unify to M2M only

Revision ID: 042_unify_warning_system
Revises: 041_drop_monitoring_tables
Create Date: 2026-04-06

Changes:
- Drop element_id column from warnings table
- Drop associated FK constraint and index
- Recreate ck_warning_scope_exclusive without element_id
  (category and tier remain as scope options; element scope
  is now expressed exclusively via element_warning_associations)

Downgrade:
- Re-adds element_id with FK to elements (nullable)
- Re-adds index and updated scope check constraint
- NOTE: element_id values are NOT restored on downgrade (data loss expected)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "042_unify_warning_system"
down_revision: Union[str, None] = "041_drop_monitoring_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop the scope check constraint (it references element_id)
    op.execute("ALTER TABLE warnings DROP CONSTRAINT IF EXISTS ck_warning_scope_exclusive")

    # 2. Drop the partial index on element_id
    op.drop_index("idx_warnings_element", table_name="warnings")

    # 3. Drop the element_id FK column
    op.drop_column("warnings", "element_id")

    # 4. Recreate scope check constraint without element_id
    #    Valid scopes now: global (both NULL), category-only, tier-only
    op.execute("""
        ALTER TABLE warnings ADD CONSTRAINT ck_warning_scope_exclusive CHECK (
            (CASE WHEN category_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN tier_id IS NOT NULL THEN 1 ELSE 0 END) <= 1
        )
    """)


def downgrade() -> None:
    # 1. Drop the updated scope check constraint
    op.execute("ALTER TABLE warnings DROP CONSTRAINT IF EXISTS ck_warning_scope_exclusive")

    # 2. Re-add element_id column (nullable, FK to elements)
    op.add_column(
        "warnings",
        sa.Column(
            "element_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("elements.id", ondelete="CASCADE"),
            nullable=True,
            comment="If set, warning only shows when this element is matched",
        ),
    )

    # 3. Re-create the partial index on element_id
    op.create_index(
        "idx_warnings_element",
        "warnings",
        ["element_id"],
        postgresql_where=sa.text("element_id IS NOT NULL"),
    )

    # 4. Restore original three-way scope check constraint
    op.execute("""
        ALTER TABLE warnings ADD CONSTRAINT ck_warning_scope_exclusive CHECK (
            (CASE WHEN category_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN tier_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN element_id IS NOT NULL THEN 1 ELSE 0 END) <= 1
        )
    """)
