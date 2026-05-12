"""Add message_attachments table

Stores per-image attachments linked to ConversationMessage rows.
Inbound images are downloaded asynchronously by the attachment_download_worker
and stored locally at uploads/conversation_images/{conv_id}/{uuid}.{ext}.

Revision ID: 051_message_attachments
Revises: 050_escalation_resolved_by_fk
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "051_message_attachments"
down_revision: str = "050_escalation_resolved_by_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_attachments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            comment="UUID v4 primary key",
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversation_messages.id", ondelete="CASCADE"),
            nullable=False,
            comment="FK to conversation_messages — CASCADE on delete",
        ),
        sa.Column(
            "kind",
            sa.String(32),
            nullable=False,
            server_default="image",
            comment="Attachment kind: image (only supported kind for now)",
        ),
        sa.Column(
            "url",
            sa.Text,
            nullable=False,
            comment="Relative URL path served by GET /conversation-images/{conv_id}/{filename}",
        ),
        sa.Column(
            "chatwoot_url",
            sa.Text,
            nullable=True,
            comment="Original Chatwoot data_url — only set on inbound attachments",
        ),
        sa.Column(
            "content_type",
            sa.String(64),
            nullable=True,
            comment="Detected MIME type (e.g. image/jpeg)",
        ),
        sa.Column(
            "filename",
            sa.String(255),
            nullable=True,
            comment="Original filename from Chatwoot or admin upload",
        ),
        sa.Column(
            "size_bytes",
            sa.Integer,
            nullable=True,
            comment="File size in bytes",
        ),
        sa.Column(
            "width",
            sa.Integer,
            nullable=True,
            comment="Image width in pixels; null for bot-outbound attachments",
        ),
        sa.Column(
            "height",
            sa.Integer,
            nullable=True,
            comment="Image height in pixels; null for bot-outbound attachments",
        ),
        sa.Column(
            "position",
            sa.SmallInteger,
            nullable=False,
            server_default="0",
            comment="0-indexed position within the message attachments",
        ),
        sa.Column(
            "uploaded_by_admin_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
            comment="AdminUser who uploaded; null for inbound and bot-outbound",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Row creation timestamp",
        ),
    )

    # Composite index on (message_id, position) — supports ordered fetch per message
    op.create_index(
        "ix_message_attachments_message_position",
        "message_attachments",
        ["message_id", "position"],
    )

    # Partial index on uploaded_by_admin_user_id for audit queries
    op.create_index(
        "ix_message_attachments_uploaded_by",
        "message_attachments",
        ["uploaded_by_admin_user_id"],
        postgresql_where=sa.text("uploaded_by_admin_user_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_message_attachments_uploaded_by", table_name="message_attachments")
    op.drop_index("ix_message_attachments_message_position", table_name="message_attachments")
    op.drop_table("message_attachments")
