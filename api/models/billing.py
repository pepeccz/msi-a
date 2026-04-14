"""
MSI Automotive - Billing Pydantic schemas.

Schemas for invoice management, payment tracking, Stripe integration,
and fiscal party information.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


# =============================================================================
# Request Schemas
# =============================================================================


class GenerateInvoiceRequest(BaseModel):
    """Request body for invoice generation."""

    year: int = Field(..., ge=2020, le=2100, description="Billing year")
    month: int = Field(..., ge=1, le=12, description="Billing month (1-12)")


class VoidInvoiceRequest(BaseModel):
    """Optional request body for voiding an invoice."""

    reason: str | None = Field(default=None, max_length=500, description="Reason for voiding")


# =============================================================================
# Payment Schema
# =============================================================================


class PaymentResponse(BaseModel):
    """Schema for a payment record."""

    model_config = {"from_attributes": True}

    id: str
    stripe_payment_intent_id: str | None
    stripe_charge_id: str | None
    amount_eur: Decimal
    fee_eur: Decimal | None
    status: str
    failure_reason: str | None
    created_at: datetime


# =============================================================================
# Invoice Schemas
# =============================================================================


class InvoiceResponse(BaseModel):
    """Schema for a full invoice response, including associated payments."""

    model_config = {"from_attributes": True}

    id: str
    invoice_number: str
    year: int
    month: int
    maintenance_amount_eur: Decimal
    token_amount_eur: Decimal
    subtotal_eur: Decimal
    iva_rate: Decimal
    iva_amount_eur: Decimal
    total_eur: Decimal
    status: Literal["draft", "issued", "paid", "overdue", "void"]
    stripe_invoice_id: str | None
    pdf_path: str | None
    due_date: date | None
    issued_at: datetime | None
    paid_at: datetime | None
    notes: str | None
    payments: list[PaymentResponse] = []
    created_at: datetime
    updated_at: datetime


class InvoiceListResponse(BaseModel):
    """Schema for a paginated list of invoices."""

    invoices: list[InvoiceResponse]
    total: int
    page: int
    page_size: int


# =============================================================================
# Estimate Schema
# =============================================================================


class CurrentEstimateResponse(BaseModel):
    """Schema for the current billing period cost estimate."""

    year: int
    month: int
    maintenance_eur: str
    token_eur: str
    subtotal_eur: str
    iva_rate: str
    iva_amount_eur: str
    total_eur: str
    input_tokens: int
    output_tokens: int


# =============================================================================
# Stripe Schemas
# =============================================================================


class StripeStatusResponse(BaseModel):
    """Schema for Stripe payment method status."""

    has_payment_method: bool
    payment_method_type: str | None
    last4: str | None
    bank_name: str | None


class StripeSetupSessionResponse(BaseModel):
    """Schema for Stripe Checkout setup session."""

    session_url: str


# =============================================================================
# Fiscal Party Schemas
# =============================================================================


class FiscalPartyResponse(BaseModel):
    """Schema for a fiscal party (company or client)."""

    name: str
    nif: str
    address: str


class FiscalDetailsResponse(BaseModel):
    """Schema for full fiscal details (company and client)."""

    company: FiscalPartyResponse
    client: FiscalPartyResponse
