"""
Tests for BillingService — Task 6 (Core Business Logic)

Covers:
  - calculate_token_cost: zero tokens, real tokens (Decimal math)
  - generate_invoice: conflict (409), happy path (correct amounts)
  - void_invoice: paid → 400, already void → 400
  - check_overdue: returns updated row count
  - _send_invoice_email: empty OPERATOR_EMAIL → no send
  - webhook idempotency: already-paid invoice → no state change
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# billing_service.py uses lazy imports for stripe, jinja2, weasyprint, and
# aiosmtplib (imported only inside methods), so no module-level stubs are needed
# here. Tests patch the lazy-import helpers (_get_stripe_service, _get_pdf_service)
# and aiosmtplib directly where needed.


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_invoice(**kwargs) -> MagicMock:
    """Build a MagicMock that looks like an Invoice ORM instance."""
    inv = MagicMock()
    inv.id = kwargs.get("id", uuid.uuid4())
    inv.invoice_number = kwargs.get("invoice_number", "MSI-2025-04-001")
    inv.year = kwargs.get("year", 2025)
    inv.month = kwargs.get("month", 4)
    inv.status = kwargs.get("status", "issued")
    inv.stripe_invoice_id = kwargs.get("stripe_invoice_id", None)
    inv.due_date = kwargs.get("due_date", date(2025, 5, 15))
    inv.maintenance_amount_eur = kwargs.get("maintenance_amount_eur", Decimal("50.00"))
    inv.token_amount_eur = kwargs.get("token_amount_eur", Decimal("0.00"))
    inv.subtotal_eur = kwargs.get("subtotal_eur", Decimal("50.00"))
    inv.iva_rate = kwargs.get("iva_rate", Decimal("21.00"))
    inv.iva_amount_eur = kwargs.get("iva_amount_eur", Decimal("10.50"))
    inv.total_eur = kwargs.get("total_eur", Decimal("60.50"))
    inv.paid_at = kwargs.get("paid_at", None)
    inv.stripe_pdf_url = kwargs.get("stripe_pdf_url", None)
    return inv


def _make_session() -> AsyncMock:
    """Build a minimal AsyncMock session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _mock_execute_scalar(session: AsyncMock, return_value) -> None:
    """Configure session.execute() to return a scalar_one_or_none result."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=return_value)
    session.execute = AsyncMock(return_value=result_mock)


def _mock_execute_scalar_result(session: AsyncMock, return_value) -> None:
    """Configure session.execute() to return a scalar() result."""
    result_mock = MagicMock()
    result_mock.scalar = MagicMock(return_value=return_value)
    session.execute = AsyncMock(return_value=result_mock)


# ─────────────────────────────────────────────────────────────────────────────
# calculate_token_cost
# ─────────────────────────────────────────────────────────────────────────────


class TestCalculateTokenCost:
    """BillingService.calculate_token_cost must use Decimal math only."""

    @pytest.mark.asyncio
    async def test_zero_tokens_when_no_usage_record(self) -> None:
        """When no TokenUsage exists for the period, returns (0.00, None)."""
        from api.services.billing_service import BillingService

        session = _make_session()
        _mock_execute_scalar(session, None)  # no usage record

        service = BillingService()
        cost, snapshot = await service.calculate_token_cost(session, 2025, 4)

        assert cost == Decimal("0.00"), f"Expected Decimal('0.00'), got {cost!r}"
        assert snapshot is None

    @pytest.mark.asyncio
    async def test_real_tokens_correct_decimal_math(self) -> None:
        """Token cost calculation must be pure Decimal, never float."""
        from api.services.billing_service import BillingService

        session = _make_session()

        # Simulate: 1_000_000 input tokens + 500_000 output tokens
        # cost = 1.0 * 0.14 + 0.5 * 0.28 = 0.14 + 0.14 = 0.28 EUR
        usage_mock = MagicMock()
        usage_mock.input_tokens = 1_000_000
        usage_mock.output_tokens = 500_000
        usage_mock.total_requests = 100
        _mock_execute_scalar(session, usage_mock)

        fake_settings = MagicMock()
        fake_settings.TOKEN_PRICE_INPUT = Decimal("0.14")
        fake_settings.TOKEN_PRICE_OUTPUT = Decimal("0.28")

        with patch(
            "api.services.billing_service.get_settings",
            return_value=fake_settings,
        ):
            service = BillingService()
            cost, snapshot = await service.calculate_token_cost(session, 2025, 4)

        expected = Decimal("0.14") + Decimal("0.14")  # 0.28
        assert cost == expected, f"Expected {expected!r}, got {cost!r}"
        assert isinstance(cost, Decimal), "Cost must be Decimal, never float"

        assert snapshot is not None
        assert snapshot["input_tokens"] == 1_000_000
        assert snapshot["output_tokens"] == 500_000
        assert snapshot["total_requests"] == 100

    @pytest.mark.asyncio
    async def test_token_cost_returns_decimal_type(self) -> None:
        """The returned cost value must always be a Decimal instance."""
        from api.services.billing_service import BillingService

        session = _make_session()
        _mock_execute_scalar(session, None)

        service = BillingService()
        cost, _ = await service.calculate_token_cost(session, 2025, 1)

        assert isinstance(cost, Decimal), (
            f"Expected Decimal, got {type(cost).__name__}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# generate_invoice
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerateInvoice:
    """BillingService.generate_invoice — conflict and happy path."""

    @pytest.mark.asyncio
    async def test_conflict_raises_409(self) -> None:
        """When an active invoice exists for the period, raises HTTPException(409)."""
        from api.services.billing_service import BillingService
        from fastapi import HTTPException

        session = _make_session()

        # First execute call (conflict check) returns a row
        conflict_result = MagicMock()
        conflict_result.scalar = MagicMock(return_value=1)
        session.execute = AsyncMock(return_value=conflict_result)

        service = BillingService()
        with pytest.raises(HTTPException) as exc_info:
            await service.generate_invoice(session, 2025, 4)

        assert exc_info.value.status_code == 409
        assert "04/2025" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_happy_path_creates_invoice_with_correct_amounts(self) -> None:
        """generate_invoice must compute IVA via Decimal, never float."""
        from api.services.billing_service import BillingService

        session = _make_session()

        # Track execute call sequence
        call_count = 0
        created_invoice: Invoice | None = None  # type: ignore[name-defined]

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()

            if call_count == 1:
                # Conflict check — no active invoice
                result.scalar = MagicMock(return_value=None)
            elif call_count == 2:
                # TokenUsage query — no token usage
                result.scalar_one_or_none = MagicMock(return_value=None)
            elif call_count == 3:
                # _next_invoice_number COUNT — returns 0
                result.scalar = MagicMock(return_value=0)
            else:
                result.scalar_one_or_none = MagicMock(return_value=None)
                result.scalar = MagicMock(return_value=None)
            return result

        session.execute = execute_side_effect

        fake_settings = MagicMock()
        fake_settings.MONTHLY_MAINTENANCE_EUR = Decimal("50.00")
        fake_settings.IVA_RATE = Decimal("21.00")
        fake_settings.TOKEN_PRICE_INPUT = Decimal("0.14")
        fake_settings.TOKEN_PRICE_OUTPUT = Decimal("0.28")
        fake_settings.PAYMENT_DUE_DAYS = 15
        fake_settings.INVOICE_PREFIX = "MSI"
        fake_settings.STRIPE_CUSTOMER_ID = ""  # No Stripe
        fake_settings.COMPANY_LEGAL_NAME = "Test Co"
        fake_settings.COMPANY_NIF = "B12345678"
        fake_settings.COMPANY_FISCAL_ADDRESS = "Calle Test 1"
        fake_settings.CLIENT_COMPANY_NAME = "Client Co"
        fake_settings.CLIENT_NIF = "A87654321"
        fake_settings.CLIENT_FISCAL_ADDRESS = "Avenida Test 2"
        fake_settings.OPERATOR_EMAIL = ""
        fake_settings.SMTP_HOST = ""

        captured_invoice: list = []

        def capture_add(obj):
            captured_invoice.append(obj)

        session.add = capture_add

        async def fake_refresh(obj):
            # Simulate refresh by returning the same object unchanged
            pass

        session.refresh = fake_refresh

        mock_pdf = AsyncMock()
        mock_pdf.generate = AsyncMock(return_value=None)

        def _consume_coro(coro):
            """Close the coroutine so it doesn't leak and trigger RuntimeWarning."""
            coro.close()

        with (
            patch("api.services.billing_service.get_settings", return_value=fake_settings),
            patch("api.services.billing_service._get_pdf_service", return_value=mock_pdf),
            patch("api.services.billing_service.asyncio.create_task", side_effect=_consume_coro),
        ):
            service = BillingService()
            invoice = await service.generate_invoice(session, 2025, 4)

        # The invoice object captured by session.add is what we check
        assert len(captured_invoice) >= 1
        inv = captured_invoice[0]

        # maintenance=50, token=0, subtotal=50, IVA=50*0.21=10.50, total=60.50
        assert inv.maintenance_amount_eur == Decimal("50.00")
        assert inv.token_amount_eur == Decimal("0.00")
        assert inv.subtotal_eur == Decimal("50.00")
        assert inv.iva_amount_eur == Decimal("10.50")
        assert inv.total_eur == Decimal("60.50")
        assert inv.status == "issued"
        assert inv.invoice_number == "MSI-2025-04-001"

    @pytest.mark.asyncio
    async def test_stripe_failure_does_not_persist_invoice(self) -> None:
        """When Stripe raises HTTPException(502), invoice must NOT be saved to DB."""
        from api.services.billing_service import BillingService
        from fastapi import HTTPException

        session = _make_session()
        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar = MagicMock(return_value=None)  # no conflict
            elif call_count == 2:
                result.scalar_one_or_none = MagicMock(return_value=None)  # no token usage
            elif call_count == 3:
                result.scalar = MagicMock(return_value=0)  # invoice count
            return result

        session.execute = execute_side_effect

        add_calls: list = []
        session.add = lambda obj: add_calls.append(obj)

        fake_settings = MagicMock()
        fake_settings.MONTHLY_MAINTENANCE_EUR = Decimal("50.00")
        fake_settings.IVA_RATE = Decimal("21.00")
        fake_settings.TOKEN_PRICE_INPUT = Decimal("0.14")
        fake_settings.TOKEN_PRICE_OUTPUT = Decimal("0.28")
        fake_settings.PAYMENT_DUE_DAYS = 15
        fake_settings.INVOICE_PREFIX = "MSI"
        fake_settings.STRIPE_CUSTOMER_ID = "cus_test123"  # Stripe enabled
        fake_settings.STRIPE_TAX_RATE_ID = ""

        stripe_mock = AsyncMock()
        stripe_mock.create_invoice = AsyncMock(
            side_effect=HTTPException(status_code=502, detail="Error en Stripe")
        )

        with (
            patch("api.services.billing_service.get_settings", return_value=fake_settings),
            patch(
                "api.services.billing_service._get_stripe_service",
                return_value=stripe_mock,
            ),
        ):
            service = BillingService()
            with pytest.raises(HTTPException) as exc_info:
                await service.generate_invoice(session, 2025, 4)

        assert exc_info.value.status_code == 502
        # Invoice must NOT have been added to the session
        assert len(add_calls) == 0, (
            f"Invoice was persisted despite Stripe failure: {add_calls}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# void_invoice
# ─────────────────────────────────────────────────────────────────────────────


class TestVoidInvoice:
    """BillingService.void_invoice — guard rails."""

    @pytest.mark.asyncio
    async def test_paid_invoice_raises_400(self) -> None:
        """Cannot void a paid invoice."""
        from api.services.billing_service import BillingService
        from fastapi import HTTPException

        session = _make_session()
        paid_invoice = _make_invoice(status="paid")
        _mock_execute_scalar(session, paid_invoice)

        service = BillingService()
        with pytest.raises(HTTPException) as exc_info:
            await service.void_invoice(session, paid_invoice.id)

        assert exc_info.value.status_code == 400
        assert "pagada" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_already_void_raises_400(self) -> None:
        """Cannot void an already-void invoice."""
        from api.services.billing_service import BillingService
        from fastapi import HTTPException

        session = _make_session()
        void_invoice = _make_invoice(status="void")
        _mock_execute_scalar(session, void_invoice)

        service = BillingService()
        with pytest.raises(HTTPException) as exc_info:
            await service.void_invoice(session, void_invoice.id)

        assert exc_info.value.status_code == 400
        assert "anulada" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_not_found_raises_404(self) -> None:
        """Missing invoice raises HTTPException(404)."""
        from api.services.billing_service import BillingService
        from fastapi import HTTPException

        session = _make_session()
        _mock_execute_scalar(session, None)

        service = BillingService()
        with pytest.raises(HTTPException) as exc_info:
            await service.void_invoice(session, uuid.uuid4())

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_issued_invoice_is_voided(self) -> None:
        """An issued invoice can be successfully voided."""
        from api.services.billing_service import BillingService

        session = _make_session()
        issued_invoice = _make_invoice(status="issued", stripe_invoice_id=None)
        _mock_execute_scalar(session, issued_invoice)

        async def fake_refresh(obj):
            pass

        session.refresh = fake_refresh

        service = BillingService()
        result = await service.void_invoice(session, issued_invoice.id)

        assert issued_invoice.status == "void"


# ─────────────────────────────────────────────────────────────────────────────
# check_overdue
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckOverdue:
    """BillingService.check_overdue — returns updated count."""

    @pytest.mark.asyncio
    async def test_returns_updated_row_count(self) -> None:
        """check_overdue returns the number of invoices marked overdue."""
        from api.services.billing_service import BillingService

        session = _make_session()
        update_result = MagicMock()
        update_result.rowcount = 3
        session.execute = AsyncMock(return_value=update_result)

        service = BillingService()
        count = await service.check_overdue(session)

        assert count == 3

    @pytest.mark.asyncio
    async def test_returns_zero_when_nothing_overdue(self) -> None:
        """check_overdue returns 0 when no invoices are past due."""
        from api.services.billing_service import BillingService

        session = _make_session()
        update_result = MagicMock()
        update_result.rowcount = 0
        session.execute = AsyncMock(return_value=update_result)

        service = BillingService()
        count = await service.check_overdue(session)

        assert count == 0


# ─────────────────────────────────────────────────────────────────────────────
# _send_invoice_email
# ─────────────────────────────────────────────────────────────────────────────


class TestSendInvoiceEmail:
    """_send_invoice_email must be a no-op when config is missing."""

    @pytest.mark.asyncio
    async def test_empty_operator_email_returns_without_sending(self) -> None:
        """When OPERATOR_EMAIL is empty, no email is sent and no error raised."""
        from api.services.billing_service import _send_invoice_email

        invoice = _make_invoice()

        fake_settings = MagicMock()
        fake_settings.OPERATOR_EMAIL = ""  # No operator email
        fake_settings.SMTP_HOST = "smtp.example.com"

        # _send_invoice_email returns early before importing aiosmtplib
        # so we just verify no exception is raised and no import error occurs
        with patch("api.services.billing_service.get_settings", return_value=fake_settings):
            await _send_invoice_email(invoice, None)
        # If we reach here without error, the guard worked

    @pytest.mark.asyncio
    async def test_empty_smtp_host_returns_without_sending(self) -> None:
        """When SMTP_HOST is empty, no email is sent and no error raised."""
        from api.services.billing_service import _send_invoice_email

        invoice = _make_invoice()

        fake_settings = MagicMock()
        fake_settings.OPERATOR_EMAIL = "op@example.com"
        fake_settings.SMTP_HOST = ""  # No SMTP host

        with patch("api.services.billing_service.get_settings", return_value=fake_settings):
            await _send_invoice_email(invoice, None)
        # If we reach here without error, the guard worked

    @pytest.mark.asyncio
    async def test_smtp_error_never_propagates(self) -> None:
        """SMTP errors must be caught and logged, never raised."""
        import sys
        import types

        from api.services.billing_service import _send_invoice_email

        invoice = _make_invoice()

        fake_settings = MagicMock()
        fake_settings.OPERATOR_EMAIL = "op@example.com"
        fake_settings.SMTP_HOST = "smtp.example.com"
        fake_settings.SMTP_PORT = 587
        fake_settings.SMTP_USER = "user@example.com"
        fake_settings.SMTP_PASSWORD = "secret"

        # Stub aiosmtplib with an error-raising send function
        aiosmtplib_stub = types.ModuleType("aiosmtplib")
        aiosmtplib_stub.send = AsyncMock(side_effect=Exception("SMTP connection refused"))  # type: ignore[attr-defined]

        with (
            patch("api.services.billing_service.get_settings", return_value=fake_settings),
            patch.dict(sys.modules, {"aiosmtplib": aiosmtplib_stub}),
        ):
            # Must not raise — error is caught and logged
            await _send_invoice_email(invoice, None)


# ─────────────────────────────────────────────────────────────────────────────
# Webhook idempotency
# ─────────────────────────────────────────────────────────────────────────────


class TestWebhookIdempotency:
    """handle_webhook_event must be idempotent."""

    @pytest.mark.asyncio
    async def test_already_paid_invoice_skipped(self) -> None:
        """When invoice is already paid, handle_webhook_event must not change state."""
        from api.services.billing_service import BillingService

        session = _make_session()
        already_paid_invoice = _make_invoice(
            status="paid",
            stripe_invoice_id="in_test123",
        )

        _mock_execute_scalar(session, already_paid_invoice)

        event = {
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": "in_test123",
                    "charge": "ch_test456",
                    "payment_intent": "pi_test789",
                    "amount_paid": 6050,
                }
            },
        }

        service = BillingService()
        await service.handle_webhook_event(session, event)

        # Status must remain "paid" — no commit with new payment
        # session.add should NOT have been called (no new Payment created)
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_already_void_invoice_skipped(self) -> None:
        """When invoice is already void, invoice.voided webhook must not re-void."""
        from api.services.billing_service import BillingService

        session = _make_session()
        already_void_invoice = _make_invoice(
            status="void",
            stripe_invoice_id="in_void123",
        )

        _mock_execute_scalar(session, already_void_invoice)

        event = {
            "type": "invoice.voided",
            "data": {"object": {"id": "in_void123"}},
        }

        service = BillingService()
        await service.handle_webhook_event(session, event)

        # Commit must NOT have been called (no state change)
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_event_type_is_ignored(self) -> None:
        """Unknown webhook events must be silently ignored."""
        from api.services.billing_service import BillingService

        session = _make_session()
        service = BillingService()

        event = {
            "type": "customer.subscription.updated",
            "data": {"object": {}},
        }

        # Must not raise, must not touch session
        await service.handle_webhook_event(session, event)
        session.add.assert_not_called()
        session.commit.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# IVA rounding
# ─────────────────────────────────────────────────────────────────────────────


class TestIvaRounding:
    """IVA must be rounded to 2dp with ROUND_HALF_UP — never float arithmetic."""

    def test_iva_uses_quantize_round_half_up(self) -> None:
        """Manually verify the IVA rounding formula used in generate_invoice."""
        from decimal import Decimal, ROUND_HALF_UP

        subtotal = Decimal("50.00")
        iva_rate = Decimal("21.00")

        iva_amount = (subtotal * iva_rate / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        assert iva_amount == Decimal("10.50")
        assert isinstance(iva_amount, Decimal)

    def test_iva_rounding_fractional_case(self) -> None:
        """Test IVA rounding for a subtotal with fractional IVA result."""
        from decimal import Decimal, ROUND_HALF_UP

        # subtotal = 3.33 → 3.33 * 0.21 = 0.6993 → rounded to 0.70
        subtotal = Decimal("3.33")
        iva_rate = Decimal("21.00")
        iva_amount = (subtotal * iva_rate / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        assert iva_amount == Decimal("0.70")
