"""add_conversation_messages_table

Revision ID: 7dc32f4a106a
Revises: 033_llm_usage_metrics
Create Date: 2026-01-29 10:15:09.888247

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7dc32f4a106a'
down_revision: Union[str, None] = '033_llm_usage_metrics'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create conversation_messages table for storing individual messages."""
    op.create_table(
        'conversation_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_history_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, comment='Message role: user, assistant'),
        sa.Column('content', sa.Text(), nullable=False, comment='Message text content'),
        sa.Column('chatwoot_message_id', sa.Integer(), nullable=True, comment='Chatwoot message ID for correlation'),
        sa.Column('has_images', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('image_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['conversation_history_id'], ['conversation_history.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_conversation_messages_conversation_history_id', 'conversation_messages', ['conversation_history_id'])
    op.create_index('ix_conversation_messages_chatwoot_message_id', 'conversation_messages', ['chatwoot_message_id'])
    op.create_index('ix_conversation_messages_created_at', 'conversation_messages', ['created_at'])
    op.create_index('ix_conversation_messages_conv_created', 'conversation_messages', ['conversation_history_id', 'created_at'])


def downgrade() -> None:
    """Drop conversation_messages table."""
    op.drop_index('ix_conversation_messages_conv_created', table_name='conversation_messages')
    op.drop_index('ix_conversation_messages_created_at', table_name='conversation_messages')
    op.drop_index('ix_conversation_messages_chatwoot_message_id', table_name='conversation_messages')
    op.drop_index('ix_conversation_messages_conversation_history_id', table_name='conversation_messages')
    op.drop_table('conversation_messages')
