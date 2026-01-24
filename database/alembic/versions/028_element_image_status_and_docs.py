"""Add status, validated_at, user_instruction to element_images

Revision ID: 028_element_image_status
Revises: 027_response_constraints
Create Date: 2026-01-24 00:00:00.000000

Changes:
- Add 'status' column to element_images (active/placeholder/unavailable).
  Controls whether images are actually sent to users.
- Add 'validated_at' timestamp for tracking URL accessibility checks.
- Add 'user_instruction' text field for human-readable photo requirements
  that the agent relays to users (instead of hallucinating requirements).
- Auto-mark non-placeholder URLs as 'active'.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "028_element_image_status"
down_revision: Union[str, None] = "027_response_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add status column with default 'placeholder'
    op.add_column(
        "element_images",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="placeholder",
            comment="Image status: active, placeholder, unavailable",
        ),
    )

    # Add validated_at timestamp
    op.add_column(
        "element_images",
        sa.Column(
            "validated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last time this image URL was validated as accessible",
        ),
    )

    # Add user_instruction text field
    op.add_column(
        "element_images",
        sa.Column(
            "user_instruction",
            sa.Text(),
            nullable=True,
            comment="Human-readable instruction for the user about this document/photo requirement",
        ),
    )

    # Mark images with real URLs (not placeholder) as 'active'
    op.execute("""
        UPDATE element_images
        SET status = 'active'
        WHERE image_url NOT LIKE '%via.placeholder.com%'
          AND image_url IS NOT NULL
          AND image_url != '';
    """)


def downgrade() -> None:
    op.drop_column("element_images", "user_instruction")
    op.drop_column("element_images", "validated_at")
    op.drop_column("element_images", "status")
