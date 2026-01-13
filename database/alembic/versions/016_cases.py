"""Add cases and case_images tables for expediente management

Revision ID: 016_cases
Revises: 015_remove_element_documentation
Create Date: 2026-01-12 00:00:00.000000

Changes:
- Add cases table for tracking homologation expedientes
- Add case_images table for storing user-uploaded images
- Supports FSM-based data collection from WhatsApp users
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "016_cases"
down_revision: Union[str, None] = "015_remove_element_documentation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create cases table
    # =========================================================================
    op.create_table(
        "cases",
        # Primary key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # Conversation and user references
        sa.Column(
            "conversation_id",
            sa.String(100),
            nullable=False,
            index=True,
            comment="Chatwoot conversation ID",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),

        # Status
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="collecting",
            index=True,
            comment="Status: collecting, pending_images, pending_review, in_progress, resolved, cancelled, abandoned",
        ),

        # Personal data
        sa.Column("nombre", sa.String(100), nullable=True),
        sa.Column("apellidos", sa.String(150), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("telefono", sa.String(30), nullable=True),

        # Vehicle data
        sa.Column("vehiculo_marca", sa.String(100), nullable=True),
        sa.Column("vehiculo_modelo", sa.String(100), nullable=True),
        sa.Column("vehiculo_anio", sa.Integer(), nullable=True),
        sa.Column("vehiculo_matricula", sa.String(20), nullable=True),
        sa.Column("vehiculo_bastidor", sa.String(50), nullable=True),

        # Category and elements
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicle_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "element_codes",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
            comment="List of element codes to homologate",
        ),

        # Tariff information
        sa.Column(
            "tariff_tier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tariff_tiers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "tariff_amount",
            sa.Numeric(10, 2),
            nullable=True,
            comment="Calculated tariff amount (without IVA)",
        ),

        # Auto-escalation link
        sa.Column(
            "escalation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("escalations.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
            comment="Link to escalation when case is completed",
        ),

        # Notes and metadata
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
            comment="Internal notes from agents",
        ),
        sa.Column(
            "metadata_",
            postgresql.JSONB(),
            nullable=True,
            server_default="{}",
            comment="Additional metadata: fsm_state, context, etc.",
        ),

        # Timestamps
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
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When all data was collected",
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When case was resolved by agent",
        ),
        sa.Column(
            "resolved_by",
            sa.String(100),
            nullable=True,
            comment="Name of agent who resolved the case",
        ),
    )

    # =========================================================================
    # 2. Create case_images table
    # =========================================================================
    op.create_table(
        "case_images",
        # Primary key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # Case reference (CASCADE delete)
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),

        # Storage info
        sa.Column(
            "stored_filename",
            sa.String(255),
            nullable=False,
            unique=True,
            comment="UUID-based filename on disk",
        ),
        sa.Column(
            "original_filename",
            sa.String(255),
            nullable=True,
            comment="Original filename from user",
        ),
        sa.Column(
            "mime_type",
            sa.String(100),
            nullable=False,
            server_default="image/jpeg",
        ),
        sa.Column(
            "file_size",
            sa.Integer(),
            nullable=True,
            comment="File size in bytes",
        ),

        # Descriptive metadata
        sa.Column(
            "display_name",
            sa.String(255),
            nullable=False,
            comment="Descriptive name: escape_vista_lateral, ficha_tecnica",
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="Description of what the image shows",
        ),
        sa.Column(
            "element_code",
            sa.String(50),
            nullable=True,
            index=True,
            comment="Related element code if applicable",
        ),
        sa.Column(
            "image_type",
            sa.String(30),
            nullable=False,
            server_default="element_photo",
            comment="Type: base_documentation, element_photo, other",
        ),

        # Validation by human agent
        sa.Column(
            "is_valid",
            sa.Boolean(),
            nullable=True,
            comment="NULL=not reviewed, True/False after review",
        ),
        sa.Column(
            "validation_notes",
            sa.Text(),
            nullable=True,
            comment="Notes from agent validation",
        ),

        # Timestamp
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # =========================================================================
    # 3. Create composite indexes for common queries
    # =========================================================================
    op.create_index(
        "ix_cases_status_created",
        "cases",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_cases_user_status",
        "cases",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_cases_conversation_status",
        "cases",
        ["conversation_id", "status"],
    )


def downgrade() -> None:
    # =========================================================================
    # 1. Drop composite indexes
    # =========================================================================
    op.drop_index("ix_cases_conversation_status", table_name="cases")
    op.drop_index("ix_cases_user_status", table_name="cases")
    op.drop_index("ix_cases_status_created", table_name="cases")

    # =========================================================================
    # 2. Drop case_images table (must be before cases due to FK)
    # =========================================================================
    op.drop_table("case_images")

    # =========================================================================
    # 3. Drop cases table
    # =========================================================================
    op.drop_table("cases")
