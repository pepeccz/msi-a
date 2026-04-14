"""Add billing tables: invoices and payments

Revision ID: 044_billing_tables
Revises: 043_case_lifecycle_fields
Create Date: 2026-04-14

Changes:
- Create invoices table with all monetary, Stripe, and audit columns
- Create payments table with FK to invoices (ON DELETE CASCADE)
- Create indexes on year/month, status, stripe_invoice_id, invoice_id
- Create partial unique index uix_invoices_period_active (year, month) WHERE status != 'void'

Downgrade:
- Drop partial index uix_invoices_period_active
- Drop remaining indexes
- Drop payments table (FK dependency)
- Drop invoices table
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "044_billing_tables"
down_revision: Union[str, None] = "043_case_lifecycle_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("invoice_number", sa.String(20), unique=True, nullable=False),
        sa.Column("year", sa.Integer(), nullable=False, comment="Billing year (e.g. 2025)"),
        sa.Column("month", sa.Integer(), nullable=False, comment="Billing month (1-12)"),
        sa.Column(
            "maintenance_amount_eur",
            sa.Numeric(10, 2),
            nullable=False,
            comment="Flat monthly maintenance fee in EUR",
        ),
        sa.Column(
            "token_amount_eur",
            sa.Numeric(10, 2),
            nullable=False,
            comment="Variable token-usage charge in EUR",
        ),
        sa.Column(
            "subtotal_eur",
            sa.Numeric(10, 2),
            nullable=False,
            comment="Subtotal before IVA",
        ),
        sa.Column(
            "iva_rate",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="21.00",
            comment="IVA percentage applied (default 21%)",
        ),
        sa.Column(
            "iva_amount_eur",
            sa.Numeric(10, 2),
            nullable=False,
            comment="IVA amount in EUR",
        ),
        sa.Column(
            "total_eur",
            sa.Numeric(10, 2),
            nullable=False,
            comment="Total amount due including IVA",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="issued",
            comment="Invoice status: issued, paid, void, overdue",
        ),
        sa.Column("stripe_invoice_id", sa.String(100), nullable=True),
        sa.Column("stripe_hosted_invoice_url", sa.String(500), nullable=True),
        sa.Column("stripe_pdf_url", sa.String(500), nullable=True),
        sa.Column("pdf_path", sa.String(500), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("token_usage_snapshot", JSONB(), nullable=True),
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
        ),
    )

    op.create_table(
        "payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "invoice_id",
            UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stripe_payment_intent_id", sa.String(100), nullable=True),
        sa.Column("stripe_charge_id", sa.String(100), nullable=True),
        sa.Column(
            "amount_eur",
            sa.Numeric(10, 2),
            nullable=False,
            comment="Amount charged in EUR",
        ),
        sa.Column(
            "fee_eur",
            sa.Numeric(10, 2),
            nullable=True,
            comment="Stripe processing fee in EUR",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            comment="Payment status: pending, succeeded, failed, refunded",
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
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
        ),
    )

    # Indexes for invoices
    op.create_index("ix_invoices_year_month", "invoices", ["year", "month"])
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_stripe_invoice_id", "invoices", ["stripe_invoice_id"])

    # Indexes for payments
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])
    op.create_index("ix_payments_status", "payments", ["status"])

    # Partial unique index: only one active (non-void) invoice per period
    op.execute(
        "CREATE UNIQUE INDEX uix_invoices_period_active ON invoices (year, month) WHERE status != 'void'"
    )


def downgrade() -> None:
    # Drop partial unique index first
    op.execute("DROP INDEX IF EXISTS uix_invoices_period_active")

    # Drop remaining indexes
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_invoice_id", table_name="payments")
    op.drop_index("ix_invoices_stripe_invoice_id", table_name="invoices")
    op.drop_index("ix_invoices_status", table_name="invoices")
    op.drop_index("ix_invoices_year_month", table_name="invoices")

    # Drop tables in FK-safe order
    op.drop_table("payments")
    op.drop_table("invoices")
