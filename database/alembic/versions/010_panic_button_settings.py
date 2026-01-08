"""Add system settings for panic button feature

Revision ID: 010_panic_button_settings
Revises: 009_escalations
Create Date: 2026-01-08 00:00:00.000000

Changes:
- Add 'agent_enabled' setting to control if the agent is active
- Add 'agent_disabled_message' setting for the auto-response message
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "010_panic_button_settings"
down_revision: Union[str, None] = "009_escalations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Insert agent_enabled setting
    # =========================================================================
    op.execute(
        sa.text("""
            INSERT INTO system_settings (id, key, value, value_type, description, is_mutable, created_at, updated_at)
            VALUES (
                CAST(:id AS uuid),
                'agent_enabled',
                'true',
                'boolean',
                'Controla si el agente está activo. Si es false, se responde con mensaje por defecto.',
                true,
                now(),
                now()
            )
            ON CONFLICT (key) DO NOTHING
        """).bindparams(id=str(uuid4()))
    )

    # =========================================================================
    # 2. Insert agent_disabled_message setting
    # =========================================================================
    op.execute(
        sa.text("""
            INSERT INTO system_settings (id, key, value, value_type, description, is_mutable, created_at, updated_at)
            VALUES (
                CAST(:id AS uuid),
                'agent_disabled_message',
                'Disculpa las molestias. Nuestro asistente automático está temporalmente deshabilitado. Un agente humano te atenderá lo antes posible.',
                'string',
                'Mensaje que se envía cuando el agente está deshabilitado.',
                true,
                now(),
                now()
            )
            ON CONFLICT (key) DO NOTHING
        """).bindparams(id=str(uuid4()))
    )


def downgrade() -> None:
    # =========================================================================
    # 1. Remove panic button settings
    # =========================================================================
    op.execute(
        sa.text("""
            DELETE FROM system_settings
            WHERE key IN ('agent_enabled', 'agent_disabled_message')
        """)
    )
