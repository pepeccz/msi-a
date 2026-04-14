"""
Unit tests for Billing Pydantic schemas — Task 7.

Coverage:
  - GenerateInvoiceRequest validation (valid, invalid month/year)
  - InvoiceResponse.model_validate with from_attributes
  - CurrentEstimateResponse fields are strings
  - FiscalDetailsResponse nested structure
  - PaymentResponse from_attributes
  - VoidInvoiceRequest optional reason

Import strategy:
  - Load api.models.billing via importlib.util.spec_from_file_location to avoid
    triggering api/models/__init__.py which imports phonenumbers and other heavy deps.
  - All classes are cached at module level from the loaded module.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, date, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Load the billing schemas module directly — bypasses api/models/__init__.py
# ---------------------------------------------------------------------------

_BILLING_MODELS_PATH = Path(__file__).parent.parent.parent / "api" / "models" / "billing.py"

if "api.models.billing" not in sys.modules:
    if "api.models" not in sys.modules:
        import types as _types
        _api_models_stub = _types.ModuleType("api.models")
        _api_models_stub.__path__ = [str(_BILLING_MODELS_PATH.parent)]
        _api_models_stub.__package__ = "api.models"
        sys.modules["api.models"] = _api_models_stub

    _spec = importlib.util.spec_from_file_location("api.models.billing", _BILLING_MODELS_PATH)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["api.models.billing"] = _mod
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_billing_mod = sys.modules["api.models.billing"]

GenerateInvoiceRequest = _billing_mod.GenerateInvoiceRequest
VoidInvoiceRequest = _billing_mod.VoidInvoiceRequest
PaymentResponse = _billing_mod.PaymentResponse
InvoiceResponse = _billing_mod.InvoiceResponse
InvoiceListResponse = _billing_mod.InvoiceListResponse
CurrentEstimateResponse = _billing_mod.CurrentEstimateResponse
StripeStatusResponse = _billing_mod.StripeStatusResponse
StripeSetupSessionResponse = _billing_mod.StripeSetupSessionResponse
FiscalPartyResponse = _billing_mod.FiscalPartyResponse
FiscalDetailsResponse = _billing_mod.FiscalDetailsResponse


# =============================================================================
# GenerateInvoiceRequest
# =============================================================================


class TestGenerateInvoiceRequest:
    """Validate GenerateInvoiceRequest field constraints."""

    def test_valid_request(self) -> None:
        """Valid year and month must be accepted."""
        req = GenerateInvoiceRequest(year=2025, month=6)
        assert req.year == 2025
        assert req.month == 6

    def test_month_zero_is_invalid(self) -> None:
        """month=0 must raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            GenerateInvoiceRequest(year=2025, month=0)
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("month",) for e in errors)

    def test_month_thirteen_is_invalid(self) -> None:
        """month=13 must raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            GenerateInvoiceRequest(year=2025, month=13)
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("month",) for e in errors)

    def test_year_below_minimum_is_invalid(self) -> None:
        """year=2019 (below ge=2020) must raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            GenerateInvoiceRequest(year=2019, month=1)
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("year",) for e in errors)

    def test_year_above_maximum_is_invalid(self) -> None:
        """year=2101 (above le=2100) must raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            GenerateInvoiceRequest(year=2101, month=1)
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("year",) for e in errors)

    def test_boundary_month_1(self) -> None:
        """month=1 must be accepted."""
        req = GenerateInvoiceRequest(year=2025, month=1)
        assert req.month == 1

    def test_boundary_month_12(self) -> None:
        """month=12 must be accepted."""
        req = GenerateInvoiceRequest(year=2025, month=12)
        assert req.month == 12

    def test_boundary_year_2020(self) -> None:
        """year=2020 must be accepted."""
        req = GenerateInvoiceRequest(year=2020, month=1)
        assert req.year == 2020

    def test_boundary_year_2100(self) -> None:
        """year=2100 must be accepted."""
        req = GenerateInvoiceRequest(year=2100, month=12)
        assert req.year == 2100


# =============================================================================
# VoidInvoiceRequest
# =============================================================================


class TestVoidInvoiceRequest:
    """Validate VoidInvoiceRequest."""

    def test_reason_is_optional(self) -> None:
        """VoidInvoiceRequest can be instantiated without reason."""
        req = VoidInvoiceRequest()
        assert req.reason is None

    def test_reason_can_be_set(self) -> None:
        """VoidInvoiceRequest accepts a reason string."""
        req = VoidInvoiceRequest(reason="Error de datos")
        assert req.reason == "Error de datos"

    def test_reason_max_length_enforced(self) -> None:
        """reason exceeding 500 characters must raise ValidationError."""
        with pytest.raises(ValidationError):
            VoidInvoiceRequest(reason="x" * 501)


# =============================================================================
# InvoiceResponse (from_attributes)
# =============================================================================


class _FakePayment:
    """Minimal Payment ORM stub for from_attributes testing."""

    def __init__(self) -> None:
        self.id = str(uuid4())
        self.stripe_payment_intent_id = "pi_test_123"
        self.stripe_charge_id = None
        self.amount_eur = Decimal("72.60")
        self.fee_eur = None
        self.status = "succeeded"
        self.failure_reason = None
        self.created_at = datetime.now(timezone.utc)


class _FakeInvoice:
    """Minimal Invoice ORM stub for from_attributes testing."""

    def __init__(self) -> None:
        self.id = str(uuid4())
        self.invoice_number = "MSI-2025-01-001"
        self.year = 2025
        self.month = 1
        self.maintenance_amount_eur = Decimal("50.00")
        self.token_amount_eur = Decimal("10.00")
        self.subtotal_eur = Decimal("60.00")
        self.iva_rate = Decimal("21.00")
        self.iva_amount_eur = Decimal("12.60")
        self.total_eur = Decimal("72.60")
        self.status = "issued"
        self.stripe_invoice_id = None
        self.pdf_path = None
        self.due_date = date(2025, 2, 1)
        self.issued_at = datetime.now(timezone.utc)
        self.paid_at = None
        self.notes = None
        self.payments: list[_FakePayment] = []
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class TestInvoiceResponse:
    """InvoiceResponse must support from_attributes validation."""

    def test_model_validate_from_attributes(self) -> None:
        """InvoiceResponse.model_validate must work with ORM-like objects."""
        fake = _FakeInvoice()
        resp = InvoiceResponse.model_validate(fake)
        assert resp.invoice_number == "MSI-2025-01-001"
        assert resp.year == 2025
        assert resp.month == 1
        assert resp.status == "issued"

    def test_payments_default_empty_list(self) -> None:
        """InvoiceResponse.payments defaults to empty list."""
        fake = _FakeInvoice()
        resp = InvoiceResponse.model_validate(fake)
        assert resp.payments == []

    def test_status_literal_accepts_valid_values(self) -> None:
        """InvoiceResponse accepts all valid status Literal values."""
        for status in ("draft", "issued", "paid", "overdue", "void"):
            fake = _FakeInvoice()
            fake.status = status
            resp = InvoiceResponse.model_validate(fake)
            assert resp.status == status

    def test_monetary_fields_are_decimal(self) -> None:
        """Monetary fields on InvoiceResponse must be Decimal."""
        fake = _FakeInvoice()
        resp = InvoiceResponse.model_validate(fake)
        assert isinstance(resp.total_eur, Decimal)
        assert isinstance(resp.subtotal_eur, Decimal)
        assert isinstance(resp.iva_amount_eur, Decimal)


# =============================================================================
# PaymentResponse (from_attributes)
# =============================================================================


class TestPaymentResponse:
    """PaymentResponse must support from_attributes validation."""

    def test_model_validate_from_attributes(self) -> None:
        """PaymentResponse.model_validate must work with ORM-like objects."""
        fake = _FakePayment()
        resp = PaymentResponse.model_validate(fake)
        assert resp.status == "succeeded"
        assert resp.amount_eur == Decimal("72.60")
        assert resp.stripe_charge_id is None


# =============================================================================
# CurrentEstimateResponse
# =============================================================================


class TestCurrentEstimateResponse:
    """CurrentEstimateResponse monetary fields must be strings."""

    def test_monetary_fields_are_strings(self) -> None:
        """All monetary fields in CurrentEstimateResponse must be str."""
        resp = CurrentEstimateResponse(
            year=2025,
            month=4,
            maintenance_eur="50.00",
            token_eur="12.34",
            subtotal_eur="62.34",
            iva_rate="21.00",
            iva_amount_eur="13.09",
            total_eur="75.43",
            input_tokens=100_000,
            output_tokens=50_000,
        )
        assert isinstance(resp.maintenance_eur, str)
        assert isinstance(resp.token_eur, str)
        assert isinstance(resp.subtotal_eur, str)
        assert isinstance(resp.iva_rate, str)
        assert isinstance(resp.iva_amount_eur, str)
        assert isinstance(resp.total_eur, str)

    def test_token_fields_are_int(self) -> None:
        """input_tokens and output_tokens must be int."""
        resp = CurrentEstimateResponse(
            year=2025,
            month=4,
            maintenance_eur="50.00",
            token_eur="0.00",
            subtotal_eur="50.00",
            iva_rate="21.00",
            iva_amount_eur="10.50",
            total_eur="60.50",
            input_tokens=0,
            output_tokens=0,
        )
        assert isinstance(resp.input_tokens, int)
        assert isinstance(resp.output_tokens, int)


# =============================================================================
# FiscalDetailsResponse
# =============================================================================


class TestFiscalDetailsResponse:
    """FiscalDetailsResponse must nest two FiscalPartyResponse objects."""

    def test_structure(self) -> None:
        """FiscalDetailsResponse must have company and client parties."""
        resp = FiscalDetailsResponse(
            company=FiscalPartyResponse(
                name="MSI Automotive SL",
                nif="B12345678",
                address="Calle Mayor 1, Madrid",
            ),
            client=FiscalPartyResponse(
                name="Cliente SA",
                nif="A87654321",
                address="Avenida Real 2, Barcelona",
            ),
        )
        assert resp.company.name == "MSI Automotive SL"
        assert resp.client.nif == "A87654321"

    def test_fiscal_party_required_fields(self) -> None:
        """FiscalPartyResponse must require name, nif, and address."""
        with pytest.raises(ValidationError):
            FiscalPartyResponse(name="Only Name")  # type: ignore[call-arg]


# =============================================================================
# InvoiceListResponse
# =============================================================================


class TestInvoiceListResponse:
    """InvoiceListResponse must include pagination metadata."""

    def test_pagination_fields(self) -> None:
        """InvoiceListResponse must expose total, page, page_size."""
        resp = InvoiceListResponse(
            invoices=[],
            total=0,
            page=1,
            page_size=10,
        )
        assert resp.total == 0
        assert resp.page == 1
        assert resp.page_size == 10
        assert resp.invoices == []
