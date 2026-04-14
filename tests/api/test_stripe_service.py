"""
Unit tests for StripeService — async wrapper for the Stripe Python SDK.

Coverage:
  - _run_sync wraps calls in executor
  - verify_webhook with valid event
  - verify_webhook raises ValueError on invalid signature
  - has_payment_method returns correct dict with/without payment methods
  - create_invoice calls create → InvoiceItem → finalize → pay in order
  - Stripe errors are caught and re-raised as HTTPException(502)

Import strategy:
  - Inject stripe stub into sys.modules BEFORE loading the service
  - Load api.services.stripe_service via importlib.util.spec_from_file_location
    to bypass api/services/__init__.py which pulls heavy transitive deps
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Minimal stripe stub — avoids requiring the real stripe SDK
# ---------------------------------------------------------------------------

def _make_stripe_stub() -> ModuleType:
    """Build a minimal stripe module stub for unit testing."""
    stub = ModuleType("stripe")

    # error namespace
    error_ns = ModuleType("stripe.error")
    stub.StripeError = type("StripeError", (Exception,), {})
    error_ns.StripeError = stub.StripeError
    stub.error = error_ns

    # Resource stubs
    stub.PaymentMethod = MagicMock()
    stub.Invoice = MagicMock()
    stub.InvoiceItem = MagicMock()
    stub.Webhook = MagicMock()

    # checkout.Session
    checkout_ns = ModuleType("stripe.checkout")
    checkout_ns.Session = MagicMock()
    stub.checkout = checkout_ns

    stub.api_key = None
    return stub


# Inject stubs BEFORE the service module is loaded
_stripe_stub = _make_stripe_stub()
sys.modules.setdefault("stripe", _stripe_stub)
sys.modules.setdefault("stripe.error", _stripe_stub.error)
sys.modules.setdefault("stripe.checkout", _stripe_stub.checkout)

if "structlog" not in sys.modules:
    _structlog_stub = ModuleType("structlog")
    _structlog_stub.get_logger = lambda *a, **kw: MagicMock()
    sys.modules["structlog"] = _structlog_stub

# ---------------------------------------------------------------------------
# Load service directly, bypassing api/services/__init__.py heavy imports
# ---------------------------------------------------------------------------

_SERVICE_PATH = Path(__file__).parent.parent.parent / "api" / "services" / "stripe_service.py"
_spec = importlib.util.spec_from_file_location("api.services.stripe_service", _SERVICE_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["api.services.stripe_service"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

StripeService = _mod.StripeService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service() -> StripeService:
    """Instantiate StripeService with a patched get_settings."""
    settings = MagicMock()
    settings.STRIPE_SECRET_KEY = "sk_test_dummy"
    # Patch on the module object directly (avoids dotted-path resolution issues
    # when api/services/__init__.py is not fully loaded)
    with patch.object(_mod, "get_settings", return_value=settings):
        return StripeService()


def _pm_dict(last4: str = "1234", bank_name: str = "BBVA") -> dict:
    """Return a minimal payment method dict."""
    return {
        "id": "pm_test",
        "type": "sepa_debit",
        "sepa_debit": {"last4": last4, "bank_name": bank_name},
    }


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestStripeServiceInit:
    def test_sets_api_key_from_settings(self) -> None:
        settings = MagicMock()
        settings.STRIPE_SECRET_KEY = "sk_live_abc"
        with patch.object(_mod, "get_settings", return_value=settings):
            StripeService()
        assert _stripe_stub.api_key == "sk_live_abc"

    def test_logs_warning_when_key_empty(self) -> None:
        settings = MagicMock()
        settings.STRIPE_SECRET_KEY = ""
        mock_logger = MagicMock()
        with (
            patch.object(_mod, "get_settings", return_value=settings),
            patch.object(_mod, "logger", mock_logger),
        ):
            StripeService()
        mock_logger.warning.assert_called_once()
        call_kwargs = mock_logger.warning.call_args
        assert "stripe_secret_key_missing" in call_kwargs[0]


# ---------------------------------------------------------------------------
# _run_sync
# ---------------------------------------------------------------------------


class TestRunSync:
    @pytest.mark.asyncio
    async def test_run_sync_uses_executor(self) -> None:
        """_run_sync must call run_in_executor, not the func directly."""
        svc = _make_service()

        fake_result = object()
        mock_executor = AsyncMock(return_value=fake_result)

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_loop.run_in_executor = mock_executor
            mock_get_loop.return_value = mock_loop

            result = await svc._run_sync(lambda x: x, 42)

        mock_executor.assert_awaited_once()
        assert result is fake_result

    @pytest.mark.asyncio
    async def test_run_sync_passes_kwargs(self) -> None:
        """_run_sync must forward kwargs via functools.partial."""
        svc = _make_service()
        captured: list = []

        def _spy_func(**kwargs: object) -> str:
            captured.append(kwargs)
            return "ok"

        result = await svc._run_sync(_spy_func, customer="cus_123", type="sepa_debit")

        assert result == "ok"
        assert captured == [{"customer": "cus_123", "type": "sepa_debit"}]


# ---------------------------------------------------------------------------
# verify_webhook
# ---------------------------------------------------------------------------


class TestVerifyWebhook:
    def test_returns_event_on_valid_signature(self) -> None:
        svc = _make_service()
        fake_event = {"type": "invoice.paid", "id": "evt_001"}
        _stripe_stub.Webhook.construct_event.return_value = fake_event

        result = svc.verify_webhook(b"payload", "sig_header", "whsec_secret")

        _stripe_stub.Webhook.construct_event.assert_called_once_with(
            b"payload", "sig_header", "whsec_secret"
        )
        assert result == fake_event

    def test_raises_value_error_on_invalid_signature(self) -> None:
        svc = _make_service()
        _stripe_stub.Webhook.construct_event.side_effect = ValueError("Invalid signature")

        with pytest.raises(ValueError, match="Invalid signature"):
            svc.verify_webhook(b"bad_payload", "bad_sig", "whsec_secret")

    def test_is_synchronous(self) -> None:
        """verify_webhook must not be a coroutine (no I/O)."""
        svc = _make_service()
        # Reset any side_effect left by previous tests in this class
        _stripe_stub.Webhook.construct_event.side_effect = None
        _stripe_stub.Webhook.construct_event.return_value = {}
        result = svc.verify_webhook(b"p", "s", "k")
        assert not asyncio.iscoroutine(result)


# ---------------------------------------------------------------------------
# has_payment_method
# ---------------------------------------------------------------------------


class TestHasPaymentMethod:
    @pytest.mark.asyncio
    async def test_returns_true_when_method_exists(self) -> None:
        svc = _make_service()
        pm = _pm_dict(last4="9999", bank_name="Santander")

        with patch.object(svc, "get_payment_methods", AsyncMock(return_value=[pm])):
            result = await svc.has_payment_method("cus_test")

        assert result == {
            "has_payment_method": True,
            "payment_method_type": "sepa_debit",
            "last4": "9999",
            "bank_name": "Santander",
        }

    @pytest.mark.asyncio
    async def test_returns_false_when_no_methods(self) -> None:
        svc = _make_service()

        with patch.object(svc, "get_payment_methods", AsyncMock(return_value=[])):
            result = await svc.has_payment_method("cus_empty")

        assert result == {
            "has_payment_method": False,
            "payment_method_type": None,
            "last4": None,
            "bank_name": None,
        }

    @pytest.mark.asyncio
    async def test_uses_first_method_only(self) -> None:
        """Only the first payment method in the list is used."""
        svc = _make_service()
        pm1 = _pm_dict(last4="1111", bank_name="BBVA")
        pm2 = _pm_dict(last4="2222", bank_name="CaixaBank")

        with patch.object(svc, "get_payment_methods", AsyncMock(return_value=[pm1, pm2])):
            result = await svc.has_payment_method("cus_multi")

        assert result["last4"] == "1111"
        assert result["bank_name"] == "BBVA"

    @pytest.mark.asyncio
    async def test_handles_missing_sepa_debit_fields(self) -> None:
        """sepa_debit subdict may be absent — must not raise."""
        svc = _make_service()
        pm = {"id": "pm_no_sepa", "type": "sepa_debit", "sepa_debit": {}}

        with patch.object(svc, "get_payment_methods", AsyncMock(return_value=[pm])):
            result = await svc.has_payment_method("cus_partial")

        assert result["has_payment_method"] is True
        assert result["last4"] == ""
        assert result["bank_name"] == ""


# ---------------------------------------------------------------------------
# create_invoice — call order
# ---------------------------------------------------------------------------


class TestCreateInvoice:
    @pytest.mark.asyncio
    async def test_calls_create_then_item_then_finalize_then_pay(self) -> None:
        """create_invoice must call: Invoice.create → InvoiceItem.create → finalize → pay."""
        svc = _make_service()

        call_order: list[str] = []

        fake_inv = MagicMock()
        fake_inv.id = "in_123"

        fake_finalized = MagicMock()
        fake_finalized.id = "in_123"

        fake_paid = MagicMock()
        fake_paid.id = "in_123"
        fake_paid.status = "paid"
        fake_paid.to_dict.return_value = {"id": "in_123", "status": "paid"}

        async def fake_run_sync(func: object, *args: object, **kwargs: object) -> object:
            name = getattr(func, "__name__", str(func))
            # Identify calls by the underlying Stripe resource method
            if func is _stripe_stub.Invoice.create:
                call_order.append("Invoice.create")
                return fake_inv
            if func is _stripe_stub.InvoiceItem.create:
                call_order.append("InvoiceItem.create")
                item_mock = MagicMock()
                return item_mock
            if func is _stripe_stub.Invoice.finalize_invoice:
                call_order.append("Invoice.finalize_invoice")
                return fake_finalized
            if func is _stripe_stub.Invoice.pay:
                call_order.append("Invoice.pay")
                return fake_paid
            raise AssertionError(f"Unexpected Stripe call: {func}")

        with patch.object(svc, "_run_sync", side_effect=fake_run_sync):
            result = await svc.create_invoice(
                customer_id="cus_abc",
                line_items=[{"description": "Mantenimiento", "amount_cents": 5000}],
                tax_rate_id="txr_21",
            )

        assert call_order == [
            "Invoice.create",
            "InvoiceItem.create",
            "Invoice.finalize_invoice",
            "Invoice.pay",
        ]
        assert result == {"id": "in_123", "status": "paid"}

    @pytest.mark.asyncio
    async def test_creates_one_invoice_item_per_line_item(self) -> None:
        svc = _make_service()
        item_calls: list[dict] = []

        fake_inv = MagicMock()
        fake_inv.id = "in_multi"
        fake_paid = MagicMock()
        fake_paid.id = "in_multi"
        fake_paid.status = "paid"
        fake_paid.to_dict.return_value = {"id": "in_multi", "status": "paid"}

        async def fake_run_sync(func: object, *args: object, **kwargs: object) -> object:
            if func is _stripe_stub.Invoice.create:
                return fake_inv
            if func is _stripe_stub.InvoiceItem.create:
                item_calls.append(kwargs)
                return MagicMock()
            if func is _stripe_stub.Invoice.finalize_invoice:
                return MagicMock()
            if func is _stripe_stub.Invoice.pay:
                return fake_paid
            raise AssertionError(f"Unexpected: {func}")

        with patch.object(svc, "_run_sync", side_effect=fake_run_sync):
            await svc.create_invoice(
                customer_id="cus_multi",
                line_items=[
                    {"description": "Item A", "amount_cents": 1000},
                    {"description": "Item B", "amount_cents": 2000},
                ],
            )

        assert len(item_calls) == 2
        assert item_calls[0]["description"] == "Item A"
        assert item_calls[1]["description"] == "Item B"

    @pytest.mark.asyncio
    async def test_no_tax_rates_when_tax_rate_id_is_none(self) -> None:
        svc = _make_service()
        item_calls: list[dict] = []

        fake_inv = MagicMock()
        fake_inv.id = "in_notax"
        fake_paid = MagicMock()
        fake_paid.id = "in_notax"
        fake_paid.status = "paid"
        fake_paid.to_dict.return_value = {"id": "in_notax", "status": "paid"}

        async def fake_run_sync(func: object, *args: object, **kwargs: object) -> object:
            if func is _stripe_stub.Invoice.create:
                return fake_inv
            if func is _stripe_stub.InvoiceItem.create:
                item_calls.append(kwargs)
                return MagicMock()
            if func is _stripe_stub.Invoice.finalize_invoice:
                return MagicMock()
            if func is _stripe_stub.Invoice.pay:
                return fake_paid
            raise AssertionError(f"Unexpected: {func}")

        with patch.object(svc, "_run_sync", side_effect=fake_run_sync):
            await svc.create_invoice(
                customer_id="cus_notax",
                line_items=[{"description": "Fee", "amount_cents": 500}],
                tax_rate_id=None,
            )

        assert item_calls[0]["tax_rates"] == []


# ---------------------------------------------------------------------------
# Stripe error → HTTPException(502)
# ---------------------------------------------------------------------------


class TestStripeErrorHandling:
    @pytest.mark.asyncio
    async def test_get_payment_methods_raises_502_on_stripe_error(self) -> None:
        from fastapi import HTTPException

        svc = _make_service()
        stripe_err = _stripe_stub.error.StripeError("card_error")

        async def fake_run_sync(func: object, *args: object, **kwargs: object) -> object:
            raise stripe_err

        with patch.object(svc, "_run_sync", side_effect=fake_run_sync):
            with pytest.raises(HTTPException) as exc_info:
                await svc.get_payment_methods("cus_bad")

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "Error en Stripe"

    @pytest.mark.asyncio
    async def test_create_setup_session_raises_502_on_stripe_error(self) -> None:
        from fastapi import HTTPException

        svc = _make_service()
        stripe_err = _stripe_stub.error.StripeError("rate_limit")

        async def fake_run_sync(func: object, *args: object, **kwargs: object) -> object:
            raise stripe_err

        with patch.object(svc, "_run_sync", side_effect=fake_run_sync):
            with pytest.raises(HTTPException) as exc_info:
                await svc.create_setup_session("cus_err", "http://ok", "http://cancel")

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "Error en Stripe"

    @pytest.mark.asyncio
    async def test_create_invoice_raises_502_on_stripe_error(self) -> None:
        from fastapi import HTTPException

        svc = _make_service()
        stripe_err = _stripe_stub.error.StripeError("api_error")

        async def fake_run_sync(func: object, *args: object, **kwargs: object) -> object:
            raise stripe_err

        with patch.object(svc, "_run_sync", side_effect=fake_run_sync):
            with pytest.raises(HTTPException) as exc_info:
                await svc.create_invoice(
                    customer_id="cus_fail",
                    line_items=[{"description": "X", "amount_cents": 100}],
                )

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "Error en Stripe"

    @pytest.mark.asyncio
    async def test_void_invoice_raises_502_on_stripe_error(self) -> None:
        from fastapi import HTTPException

        svc = _make_service()
        stripe_err = _stripe_stub.error.StripeError("invalid_request")

        async def fake_run_sync(func: object, *args: object, **kwargs: object) -> object:
            raise stripe_err

        with patch.object(svc, "_run_sync", side_effect=fake_run_sync):
            with pytest.raises(HTTPException) as exc_info:
                await svc.void_invoice("in_voiderr")

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "Error en Stripe"
