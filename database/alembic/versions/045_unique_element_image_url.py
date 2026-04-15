"""Add UNIQUE constraint on element_images(element_id, image_url)

Revision ID: 045_unique_element_image_url
Revises: 044_billing_tables
Create Date: 2026-04-15

Changes:
- Remove duplicate element_image rows (keep oldest per element_id + image_url)
- Add unique constraint uq_element_images_element_url(element_id, image_url)

Downgrade:
- Drop unique constraint uq_element_images_element_url
"""

from typing import Sequence, Union

from alembic import op

revision: str = "045_unique_element_image_url"
down_revision: Union[str, Sequence[str]] = "044_billing_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Delete duplicate element_images, keeping the oldest (earliest created_at) per pair
    op.execute("""
        DELETE FROM element_images
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY element_id, image_url
                           ORDER BY created_at ASC
                       ) AS rn
                FROM element_images
            ) ranked
            WHERE rn > 1
        )
    """)

    op.create_unique_constraint(
        "uq_element_images_element_url",
        "element_images",
        ["element_id", "image_url"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_element_images_element_url",
        "element_images",
        type_="unique",
    )
