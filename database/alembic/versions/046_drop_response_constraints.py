"""Drop response_constraints table (unused feature removal)

Revision ID: 046_drop_response_constraints
Revises: 045_unique_element_image_url
Create Date: 2026-04-15

Changes:
- Drop response_constraints table (feature was built but never integrated into agent v2)

Downgrade:
- Recreate response_constraints table with all original columns and indexes
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "046_drop_response_constraints"
down_revision: Union[str, Sequence[str]] = "045_unique_element_image_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_response_constraints_category_id", table_name="response_constraints")
    op.drop_table("response_constraints")


def downgrade() -> None:
    op.create_table(
        "response_constraints",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("category_id", UUID(as_uuid=True), sa.ForeignKey("vehicle_categories.id", ondelete="CASCADE"), nullable=True),
        sa.Column("constraint_type", sa.String(50), nullable=False),
        sa.Column("detection_pattern", sa.String(500), nullable=False),
        sa.Column("required_tool", sa.String(200), nullable=False),
        sa.Column("error_injection", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_response_constraints_category_id", "response_constraints", ["category_id"])
