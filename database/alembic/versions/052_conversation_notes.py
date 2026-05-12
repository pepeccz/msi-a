"""Add conversation_notes table

Stores internal admin notes linked to a ConversationHistory row.
Notes are admin-only (never sent to WhatsApp) and support per-conversation
handoff context between agents.

Revision ID: 052_conversation_notes
Revises: 051_message_attachments
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "052_conversation_notes"
down_revision: str = "051_message_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_notes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            comment="UUID v4 primary key (generated Python-side via SQLAlchemy default)",
        ),
        sa.Column(
            "conversation_history_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversation_history.id", ondelete="CASCADE"),
            nullable=False,
            comment="FK to conversation_history — CASCADE on delete",
        ),
        sa.Column(
            "admin_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
            comment="FK to admin_users — SET NULL when author is deleted; preserves note content",
        ),
        sa.Column(
            "content",
            sa.Text,
            nullable=False,
            comment="Note body text (1–2000 chars enforced at service layer)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Row creation timestamp",
        ),
    )

    # Composite index on (conversation_history_id, created_at DESC)
    # Supports the list-by-conversation query ordered newest-first
    op.create_index(
        "idx_conversation_notes_conv_id_created_desc",
        "conversation_notes",
        ["conversation_history_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_conversation_notes_conv_id_created_desc",
        table_name="conversation_notes",
    )
    op.drop_table("conversation_notes")
