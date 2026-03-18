"""Add partial unique index for one active case per user.

Ensures that a given user_id can have at most ONE case in an active status
(collecting, pending_images) at any time. This prevents the race-condition
where multiple active expedientes are created for the same particular user.

Before creating the index, existing duplicates are cleaned up:
- For each user_id with multiple active cases, the most recent (by created_at)
  is kept and all others are set to status='abandoned'.

Revision ID: 039_case_user_active_unique
Revises: 038_case_image_upload_batches
Create Date: 2026-03-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "039_case_user_active_unique"
down_revision: Union[str, None] = "038_case_image_upload_batches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Deduplicate active cases and create partial unique index.

    Steps:
    1. For each user_id with >1 active case, keep the most recent by
       created_at (tie-break by id) and set the rest to 'abandoned'.
    2. Create partial unique index on (user_id) WHERE status IN
       ('collecting', 'pending_images') AND user_id IS NOT NULL.
    """
    # Step 1: Deduplicate — abandon older active cases per user
    # Uses a CTE to rank active cases per user, then updates all but rank=1.
    op.execute(
        sa.text("""
            WITH ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY user_id
                        ORDER BY created_at DESC, id DESC
                    ) AS rn
                FROM cases
                WHERE user_id IS NOT NULL
                  AND status IN ('collecting', 'pending_images')
            )
            UPDATE cases
            SET status = 'abandoned',
                metadata_ = COALESCE(metadata_, '{}'::jsonb)
                    || '{"abandoned_by_migration": "039_case_user_active_unique"}'::jsonb
            FROM ranked
            WHERE cases.id = ranked.id
              AND ranked.rn > 1
        """)
    )

    # Step 2: Create partial unique index
    op.create_index(
        "uq_cases_user_active",
        "cases",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('collecting', 'pending_images') AND user_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    """Drop the partial unique index.

    NOTE: Cases that were abandoned by the upgrade are NOT restored —
    there is no reliable way to distinguish migration-abandoned cases
    from legitimately abandoned ones.
    """
    op.drop_index(
        "uq_cases_user_active",
        table_name="cases",
    )
