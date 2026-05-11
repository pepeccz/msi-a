"""Unified inbox foundation: ConversationHistory pause/snapshot + ConversationMessage attribution

Adds bot pause/resume/snapshot columns to conversation_history and
attribution + read-tracking columns to conversation_messages.

Revision ID: 049_inbox_foundation
Revises: 048_chatwoot_user_id
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "049_inbox_foundation"
down_revision: str = "048_chatwoot_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # ConversationHistory — pause / resume / snapshot / activity timestamps
    # -------------------------------------------------------------------------
    op.add_column(
        "conversation_history",
        sa.Column(
            "bot_paused_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when bot was paused; NULL means bot is active",
        ),
    )
    op.add_column(
        "conversation_history",
        sa.Column(
            "bot_resumed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of most recent bot resume",
        ),
    )
    op.add_column(
        "conversation_history",
        sa.Column(
            "bot_paused_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
            comment="AdminUser who triggered the pause",
        ),
    )
    op.add_column(
        "conversation_history",
        sa.Column(
            "bot_pause_reason",
            sa.Text(),
            nullable=True,
            comment="Optional reason for pausing (manual/escalation)",
        ),
    )
    op.add_column(
        "conversation_history",
        sa.Column(
            "state_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Versioned LangGraph ConversationState snapshot (v1 schema)",
        ),
    )
    op.add_column(
        "conversation_history",
        sa.Column(
            "state_snapshot_version",
            sa.Integer(),
            nullable=True,
            comment="Schema version of state_snapshot payload",
        ),
    )
    op.add_column(
        "conversation_history",
        sa.Column(
            "last_inbound_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of most recent inbound message from client",
        ),
    )
    op.add_column(
        "conversation_history",
        sa.Column(
            "last_human_message_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of most recent human-agent outbound message",
        ),
    )
    op.add_column(
        "conversation_history",
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of most recent message from any author",
        ),
    )

    # Indexes for ConversationHistory
    op.create_index(
        "ix_conversation_history_bot_paused_at",
        "conversation_history",
        ["bot_paused_at"],
        postgresql_where=sa.text("bot_paused_at IS NOT NULL"),
    )
    op.create_index(
        "ix_conversation_history_last_inbound_at",
        "conversation_history",
        ["last_inbound_at"],
    )
    op.create_index(
        "ix_conversation_history_last_message_at",
        "conversation_history",
        [sa.text("last_message_at DESC")],
        postgresql_using="btree",
    )
    op.create_index(
        "ix_conversation_history_bot_paused_by_user_id",
        "conversation_history",
        ["bot_paused_by_user_id"],
        postgresql_where=sa.text("bot_paused_by_user_id IS NOT NULL"),
    )

    # -------------------------------------------------------------------------
    # ConversationMessage — attribution (author_type, author_user_id) + read tracking
    # -------------------------------------------------------------------------

    # Add author_type with server default so NOT NULL constraint works on existing rows
    op.add_column(
        "conversation_messages",
        sa.Column(
            "author_type",
            sa.String(20),
            nullable=False,
            server_default="bot",
            comment="Message author type: bot, human_agent, system, user",
        ),
    )
    op.add_column(
        "conversation_messages",
        sa.Column(
            "author_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
            comment="AdminUser FK; only set when author_type = human_agent",
        ),
    )
    op.add_column(
        "conversation_messages",
        sa.Column(
            "is_read",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether an agent has read this message",
        ),
    )
    op.add_column(
        "conversation_messages",
        sa.Column(
            "is_legacy",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True for messages created before this migration",
        ),
    )

    # CHECK constraint: human_agent author_type requires author_user_id
    op.create_check_constraint(
        "chk_human_agent_has_user",
        "conversation_messages",
        "author_type != 'human_agent' OR author_user_id IS NOT NULL",
    )

    # CHECK constraint: author_type must be a known value
    op.create_check_constraint(
        "chk_author_type_valid",
        "conversation_messages",
        "author_type IN ('bot', 'human_agent', 'system', 'user')",
    )

    # Backfill: existing messages — mark them as legacy
    op.execute(
        "UPDATE conversation_messages SET is_legacy = TRUE WHERE TRUE"
    )

    # Backfill: role='assistant' → author_type='bot'
    op.execute(
        "UPDATE conversation_messages SET author_type = 'bot' WHERE role = 'assistant'"
    )

    # Backfill: role='user' → author_type='user' (WhatsApp customer messages)
    op.execute(
        "UPDATE conversation_messages SET author_type = 'user' WHERE role = 'user'"
    )

    # Indexes for ConversationMessage
    op.create_index(
        "ix_conversation_messages_author_user_id",
        "conversation_messages",
        ["author_user_id"],
        postgresql_where=sa.text("author_user_id IS NOT NULL"),
    )
    op.create_index(
        "ix_conversation_messages_unread",
        "conversation_messages",
        ["conversation_history_id", "is_read"],
        postgresql_where=sa.text("is_read = FALSE"),
    )


def downgrade() -> None:
    # ConversationMessage — drop in reverse order of creation
    op.drop_index("ix_conversation_messages_unread", table_name="conversation_messages")
    op.drop_index(
        "ix_conversation_messages_author_user_id", table_name="conversation_messages"
    )
    op.drop_constraint(
        "chk_author_type_valid", "conversation_messages", type_="check"
    )
    op.drop_constraint(
        "chk_human_agent_has_user", "conversation_messages", type_="check"
    )
    op.drop_column("conversation_messages", "is_legacy")
    op.drop_column("conversation_messages", "is_read")
    op.drop_column("conversation_messages", "author_user_id")
    op.drop_column("conversation_messages", "author_type")

    # ConversationHistory — drop in reverse order of creation
    op.drop_index(
        "ix_conversation_history_bot_paused_by_user_id",
        table_name="conversation_history",
    )
    op.drop_index(
        "ix_conversation_history_last_message_at", table_name="conversation_history"
    )
    op.drop_index(
        "ix_conversation_history_last_inbound_at", table_name="conversation_history"
    )
    op.drop_index(
        "ix_conversation_history_bot_paused_at", table_name="conversation_history"
    )
    op.drop_column("conversation_history", "last_message_at")
    op.drop_column("conversation_history", "last_human_message_at")
    op.drop_column("conversation_history", "last_inbound_at")
    op.drop_column("conversation_history", "state_snapshot_version")
    op.drop_column("conversation_history", "state_snapshot")
    op.drop_column("conversation_history", "bot_pause_reason")
    op.drop_column("conversation_history", "bot_paused_by_user_id")
    op.drop_column("conversation_history", "bot_resumed_at")
    op.drop_column("conversation_history", "bot_paused_at")
