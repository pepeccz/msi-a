"""Add element_required_fields and case_element_data tables

Revision ID: 030_element_required_fields
Revises: 029_tool_call_logs
Create Date: 2026-01-26 00:00:00.000000

Changes:
- Create element_required_fields table for defining required data per element.
  Each element can have multiple required fields (e.g., "marca_muelle", "longitud")
  that the agent must collect during case creation.

- Create case_element_data table for storing collected data per element in a case.
  Tracks photos and field values for each element, enabling:
  - Element-by-element collection flow (photos -> data -> next element)
  - Per-element status tracking
  - Structured storage of element-specific technical data

This enables the new case collection flow:
1. For each element: ask photos, then ask element-specific data
2. Ask base documentation
3. Ask personal/vehicle/workshop data
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "030_element_required_fields"
down_revision: Union[str, None] = "029_tool_call_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # Table: element_required_fields
    # ==========================================================================
    op.create_table(
        "element_required_fields",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("element_id", UUID(as_uuid=True), sa.ForeignKey("elements.id", ondelete="CASCADE"), nullable=False, index=True),
        
        # Field identification
        sa.Column("field_key", sa.String(50), nullable=False, comment="Unique key within element (e.g., 'marca_muelle')"),
        sa.Column("field_label", sa.String(200), nullable=False, comment="Human-readable label in Spanish"),
        
        # Field type and options
        sa.Column("field_type", sa.String(20), nullable=False, server_default="text", comment="Type: text, number, boolean, select"),
        sa.Column("options", JSONB, nullable=True, comment="Options for select type"),
        
        # Validation
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("true"), comment="Whether this field is mandatory"),
        sa.Column("validation_rules", JSONB, nullable=True, comment="Validation rules: {min, max, pattern, etc.}"),
        
        # LLM instructions
        sa.Column("example_value", sa.String(200), nullable=True, comment="Example value for prompts"),
        sa.Column("llm_instruction", sa.Text(), nullable=True, comment="Instruction for LLM on how to ask"),
        
        # Conditional display
        sa.Column("condition_field_id", UUID(as_uuid=True), sa.ForeignKey("element_required_fields.id", ondelete="SET NULL"), nullable=True),
        sa.Column("condition_operator", sa.String(20), nullable=True, comment="Operator: equals, not_equals, exists"),
        sa.Column("condition_value", sa.String(200), nullable=True, comment="Value to compare against"),
        
        # Ordering and status
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    
    # Unique constraint: one field_key per element
    op.create_unique_constraint(
        "uq_element_field_key",
        "element_required_fields",
        ["element_id", "field_key"],
    )
    
    # Index for fetching active fields for an element
    op.create_index(
        "ix_element_required_fields_element_active",
        "element_required_fields",
        ["element_id", "is_active"],
    )

    # ==========================================================================
    # Table: case_element_data
    # ==========================================================================
    op.create_table(
        "case_element_data",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_id", UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("element_code", sa.String(50), nullable=False, comment="Element code (e.g., 'SUSP_TRAS')"),
        
        # Collection status
        sa.Column("status", sa.String(30), nullable=False, server_default="pending_photos", comment="Status: pending_photos, pending_data, completed"),
        
        # Collected field values
        sa.Column("field_values", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"), comment="Collected field values"),
        
        # Timestamps for each phase
        sa.Column("photos_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    
    # Unique constraint: one entry per element per case
    op.create_unique_constraint(
        "uq_case_element_code",
        "case_element_data",
        ["case_id", "element_code"],
    )
    
    # Index for status queries
    op.create_index(
        "ix_case_element_data_case_status",
        "case_element_data",
        ["case_id", "status"],
    )


def downgrade() -> None:
    # Drop case_element_data
    op.drop_index("ix_case_element_data_case_status", table_name="case_element_data")
    op.drop_constraint("uq_case_element_code", "case_element_data", type_="unique")
    op.drop_table("case_element_data")
    
    # Drop element_required_fields
    op.drop_index("ix_element_required_fields_element_active", table_name="element_required_fields")
    op.drop_constraint("uq_element_field_key", "element_required_fields", type_="unique")
    op.drop_table("element_required_fields")
