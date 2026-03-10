"""add case image upload batch ownership fields

Revision ID: 038_case_image_upload_batches
Revises: 037_taller_propio_nullable
Create Date: 2026-03-10

"""

from alembic import op
import sqlalchemy as sa


revision = "038_case_image_upload_batches"
down_revision = "037_taller_propio_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_image_upload_batches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("upload_scope_key", sa.String(length=255), nullable=False),
        sa.Column("owner_scope", sa.String(length=50), nullable=False),
        sa.Column("owner_element_code", sa.String(length=50), nullable=True),
        sa.Column("expediente_sub_mode", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="open"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name=op.f("fk_case_image_upload_batches_case_id_cases"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", name="uq_case_image_upload_batches_batch_id"),
    )
    op.create_index(
        op.f("ix_case_image_upload_batches_batch_id"),
        "case_image_upload_batches",
        ["batch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_case_image_upload_batches_case_id"),
        "case_image_upload_batches",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_case_image_upload_batches_upload_scope_key"),
        "case_image_upload_batches",
        ["upload_scope_key"],
        unique=False,
    )
    op.create_index(
        "ix_case_image_upload_batches_case_scope",
        "case_image_upload_batches",
        ["case_id", "upload_scope_key"],
        unique=False,
    )
    op.create_index(
        "ix_case_image_upload_batches_case_status",
        "case_image_upload_batches",
        ["case_id", "status"],
        unique=False,
    )

    with op.batch_alter_table("case_images") as batch_op:
        batch_op.add_column(
            sa.Column(
                "attachment_fingerprint",
                sa.String(length=64),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "upload_scope_key",
                sa.String(length=255),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "upload_batch_id",
                sa.String(length=36),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_case_images_upload_batch_id_case_image_upload_batches",
            "case_image_upload_batches",
            ["upload_batch_id"],
            ["batch_id"],
            ondelete="SET NULL",
        )

    op.create_index(
        op.f("ix_case_images_attachment_fingerprint"),
        "case_images",
        ["attachment_fingerprint"],
        unique=False,
    )
    op.create_index(
        op.f("ix_case_images_upload_scope_key"),
        "case_images",
        ["upload_scope_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_case_images_upload_batch_id"),
        "case_images",
        ["upload_batch_id"],
        unique=False,
    )
    op.create_index(
        "ix_case_images_case_batch",
        "case_images",
        ["case_id", "upload_batch_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_case_images_case_attachment_fingerprint",
        "case_images",
        ["case_id", "attachment_fingerprint"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_case_images_case_attachment_fingerprint",
        "case_images",
        type_="unique",
    )
    op.drop_index("ix_case_images_case_batch", table_name="case_images")
    op.drop_index(op.f("ix_case_images_upload_batch_id"), table_name="case_images")
    op.drop_index(op.f("ix_case_images_upload_scope_key"), table_name="case_images")
    op.drop_index(
        op.f("ix_case_images_attachment_fingerprint"),
        table_name="case_images",
    )

    with op.batch_alter_table("case_images") as batch_op:
        batch_op.drop_constraint(
            "fk_case_images_upload_batch_id_case_image_upload_batches",
            type_="foreignkey",
        )
        batch_op.drop_column("upload_batch_id")
        batch_op.drop_column("upload_scope_key")
        batch_op.drop_column("attachment_fingerprint")

    op.drop_index("ix_case_image_upload_batches_case_status", table_name="case_image_upload_batches")
    op.drop_index("ix_case_image_upload_batches_case_scope", table_name="case_image_upload_batches")
    op.drop_index(
        op.f("ix_case_image_upload_batches_upload_scope_key"),
        table_name="case_image_upload_batches",
    )
    op.drop_index(
        op.f("ix_case_image_upload_batches_case_id"),
        table_name="case_image_upload_batches",
    )
    op.drop_index(
        op.f("ix_case_image_upload_batches_batch_id"),
        table_name="case_image_upload_batches",
    )
    op.drop_table("case_image_upload_batches")
