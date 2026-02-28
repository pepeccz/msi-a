"""make taller_propio nullable (tri-state: None=not specified, True=own workshop, False=MSI provides)

Revision ID: 037_taller_propio_nullable
Revises: 036_add_variant_position
Create Date: 2026-02-26

"""
from alembic import op
import sqlalchemy as sa

revision = "037_taller_propio_nullable"
down_revision = "036_add_variant_position"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove server default first, then alter nullable
    op.alter_column(
        "cases",
        "taller_propio",
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=None,
    )

    # Set existing False rows to NULL (they were set by the old default,
    # not by explicit user input — they are actually "not yet specified")
    op.execute("UPDATE cases SET taller_propio = NULL WHERE taller_propio = FALSE")


def downgrade() -> None:
    # Restore NULLs to FALSE before making non-nullable again
    op.execute("UPDATE cases SET taller_propio = FALSE WHERE taller_propio IS NULL")

    op.alter_column(
        "cases",
        "taller_propio",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
    )
