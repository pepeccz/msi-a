"""Informational migration: backfill bot_paused_at from Chatwoot scan.

Migration B: Documents the one-shot data migration step to backfill
ConversationHistory.bot_paused_at for conversations that had
atencion_automatica=False in Chatwoot but bot_paused_at IS NULL in the DB.

IMPORTANT: This migration does NOT execute the Chatwoot API scan.
The actual backfill is triggered by the operator running:

    python scripts/backfill_bot_paused_chatwoot_scan.py

That script:
  - Pages through open Chatwoot conversations
  - Finds rows with atencion_automatica=false
  - Sets ConversationHistory.bot_paused_at = NOW() for matching DB rows
  - Marks backfilled rows with metadata_->>'backfilled_by_migration_b' = 'true'
  - Is idempotent (running twice is a no-op)
  - Supports --dry-run mode

Deployment order (CRITICAL):
  1. Deploy Migration A (053_escalation_assignment) first
  2. Run this migration (054_backfill_bot_paused) to mark the boundary
  3. Run the operator script: python scripts/backfill_bot_paused_chatwoot_scan.py
  4. Run diagnostic: python scripts/diagnostic_bot_paused_drift.py
  5. Deploy C2.9 code (webhook gate simplified to bot_paused_at only)

downgrade() clears bot_paused_at only for rows backfilled by this migration
(identified by metadata_->>'backfilled_by_migration_b' = 'true'), to avoid
clearing legitimately paused conversations.

Revision ID: 054_backfill_bot_paused
Revises: 053_escalation_assignment
"""

from alembic import op
import sqlalchemy as sa


revision = "054_backfill_bot_paused"
down_revision = "053_escalation_assignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Documents the Migration B boundary.

    Adds an informational marker row to system_settings (if the table exists)
    to record when Migration B was applied. The actual data backfill is done
    by the operator script (scripts/backfill_bot_paused_chatwoot_scan.py).
    """
    # Add SQL comment marker — this is a no-op DDL change that records intent.
    # The actual data migration happens via the operator script.
    #
    # For traceability, we insert a system_setting record marking this boundary.
    # ON CONFLICT DO NOTHING ensures idempotency if this migration is re-run.
    op.execute(
        sa.text("""
        INSERT INTO system_settings (id, key, value, value_type, description, is_mutable, created_at, updated_at)
        VALUES (
            gen_random_uuid(),
            'migration_b_applied',
            'false',
            'boolean',
            'Set to true after running scripts/backfill_bot_paused_chatwoot_scan.py. '
            'False means the operator script has NOT yet been run.',
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (key) DO NOTHING
        """)
    )


def downgrade() -> None:
    """
    Reverts Migration B marker.

    Clears bot_paused_at ONLY for rows that were backfilled by the operator
    script (metadata_->>'backfilled_by_migration_b' = 'true'), to avoid
    clearing legitimately paused conversations.

    Also removes the migration_b_applied system_setting marker.
    """
    # Clear bot_paused_at only for backfilled rows
    op.execute(
        sa.text("""
        UPDATE conversation_history
        SET bot_paused_at = NULL,
            metadata_ = metadata_ - 'backfilled_by_migration_b'
        WHERE metadata_ ->> 'backfilled_by_migration_b' = 'true'
        """)
    )

    # Remove the migration marker from system_settings
    op.execute(
        sa.text("DELETE FROM system_settings WHERE key = 'migration_b_applied'")
    )
