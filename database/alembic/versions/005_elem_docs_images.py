"""Add element documentation and uploaded images tables

Revision ID: 005_elem_docs_images
Revises: 004_customer_to_user
Create Date: 2026-01-07 00:00:00.000000

Changes:
- Add element_documentation table for keyword-based documentation
- Add uploaded_images table for image storage metadata
- Add GIN index for keyword search on element_documentation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005_elem_docs_images"
down_revision: Union[str, None] = "004_customer_to_user"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create element_documentation table
    # =========================================================================
    op.create_table(
        "element_documentation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicle_categories.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "element_keywords",
            postgresql.JSONB(),
            nullable=False,
            comment="Keywords that trigger this documentation",
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            comment="Documentation requirement description",
        ),
        sa.Column(
            "image_url",
            sa.String(500),
            nullable=True,
            comment="URL of example image",
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, default=0),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # =========================================================================
    # 2. Create GIN index for keyword search
    # =========================================================================
    op.create_index(
        "ix_element_documentation_keywords_gin",
        "element_documentation",
        ["element_keywords"],
        postgresql_using="gin",
    )

    # =========================================================================
    # 3. Create uploaded_images table
    # =========================================================================
    op.create_table(
        "uploaded_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "filename",
            sa.String(255),
            nullable=False,
            comment="Original filename",
        ),
        sa.Column(
            "stored_filename",
            sa.String(255),
            unique=True,
            nullable=False,
            comment="UUID-based stored filename",
        ),
        sa.Column(
            "mime_type",
            sa.String(100),
            nullable=False,
            comment="MIME type",
        ),
        sa.Column(
            "file_size",
            sa.Integer(),
            nullable=False,
            comment="File size in bytes",
        ),
        sa.Column(
            "width",
            sa.Integer(),
            nullable=True,
            comment="Image width in pixels",
        ),
        sa.Column(
            "height",
            sa.Integer(),
            nullable=True,
            comment="Image height in pixels",
        ),
        sa.Column(
            "category",
            sa.String(50),
            nullable=True,
            index=True,
            comment="Image category",
        ),
        sa.Column(
            "description",
            sa.String(500),
            nullable=True,
            comment="Image description",
        ),
        sa.Column(
            "uploaded_by",
            sa.String(100),
            nullable=True,
            comment="Username who uploaded",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    # =========================================================================
    # 1. Drop uploaded_images table
    # =========================================================================
    op.drop_table("uploaded_images")

    # =========================================================================
    # 2. Drop GIN index
    # =========================================================================
    op.drop_index(
        "ix_element_documentation_keywords_gin",
        table_name="element_documentation",
    )

    # =========================================================================
    # 3. Drop element_documentation table
    # =========================================================================
    op.drop_table("element_documentation")
