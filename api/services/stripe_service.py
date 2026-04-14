"""Stripe payment gateway service — async wrapper for sync SDK."""
import asyncio
import functools
from typing import Any

import stripe
import structlog
from fastapi import HTTPException

from shared.config import get_settings

logger = structlog.get_logger(__name__)


class StripeService:
    """Async wrapper around the synchronous Stripe Python SDK.

    All Stripe SDK calls are wrapped in run_in_executor to avoid blocking
    the asyncio event loop.
    """

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.STRIPE_SECRET_KEY:
            logger.warning("stripe_secret_key_missing", detail="STRIPE_SECRET_KEY is empty — Stripe calls will fail")
        stripe.api_key = settings.STRIPE_SECRET_KEY

    async def _run_sync(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a synchronous Stripe SDK call in a thread pool executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, functools.partial(func, *args, **kwargs)
        )

    async def get_payment_methods(self, customer_id: str) -> list[dict]:
        """List SEPA payment methods for a Stripe customer."""
        try:
            result = await self._run_sync(
                stripe.PaymentMethod.list,
                customer=customer_id,
                type="sepa_debit",
            )
            return [pm.to_dict() for pm in result.data]
        except stripe.error.StripeError as exc:
            logger.error(
                "stripe_get_payment_methods_error",
                customer_id=customer_id,
                error=str(exc),
            )
            raise HTTPException(status_code=502, detail="Error en Stripe") from exc

    async def has_payment_method(self, customer_id: str) -> dict:
        """Check if customer has a SEPA payment method configured.

        Returns dict with: has_payment_method, payment_method_type, last4, bank_name.
        """
        methods = await self.get_payment_methods(customer_id)
        if methods:
            pm = methods[0]
            sepa = pm.get("sepa_debit", {})
            return {
                "has_payment_method": True,
                "payment_method_type": "sepa_debit",
                "last4": sepa.get("last4", ""),
                "bank_name": sepa.get("bank_name", ""),
            }
        return {
            "has_payment_method": False,
            "payment_method_type": None,
            "last4": None,
            "bank_name": None,
        }

    async def create_setup_session(
        self, customer_id: str, success_url: str, cancel_url: str
    ) -> str:
        """Create a Stripe Checkout session for SEPA mandate setup.

        Returns the session URL for redirect.
        """
        try:
            session = await self._run_sync(
                stripe.checkout.Session.create,
                customer=customer_id,
                payment_method_types=["sepa_debit"],
                mode="setup",
                success_url=success_url,
                cancel_url=cancel_url,
            )
            return session.url
        except stripe.error.StripeError as exc:
            logger.error(
                "stripe_create_setup_session_error",
                customer_id=customer_id,
                error=str(exc),
            )
            raise HTTPException(status_code=502, detail="Error en Stripe") from exc

    async def create_invoice(
        self,
        customer_id: str,
        line_items: list[dict],
        tax_rate_id: str | None = None,
    ) -> dict:
        """Create, populate, finalize, and pay a Stripe invoice.

        line_items: list of {"description": str, "amount_cents": int}
        Returns the finalized and paid Stripe invoice as a dict.
        """
        try:
            # 1. Create draft invoice
            inv = await self._run_sync(
                stripe.Invoice.create,
                customer=customer_id,
                collection_method="charge_automatically",
                auto_advance=False,
            )

            # 2. Add line items
            for item in line_items:
                tax_rates = [tax_rate_id] if tax_rate_id else []
                await self._run_sync(
                    stripe.InvoiceItem.create,
                    customer=customer_id,
                    invoice=inv.id,
                    amount=item["amount_cents"],
                    currency="eur",
                    description=item["description"],
                    tax_rates=tax_rates,
                )

            # 3. Finalize (moves from draft → open)
            await self._run_sync(stripe.Invoice.finalize_invoice, inv.id)

            # 4. Pay (triggers SEPA charge)
            paid = await self._run_sync(stripe.Invoice.pay, inv.id)

            logger.info(
                "stripe_invoice_created",
                stripe_invoice_id=paid.id,
                status=paid.status,
            )
            return paid.to_dict()

        except stripe.error.StripeError as exc:
            logger.error(
                "stripe_create_invoice_error",
                customer_id=customer_id,
                error=str(exc),
            )
            raise HTTPException(status_code=502, detail="Error en Stripe") from exc

    async def void_invoice(self, stripe_invoice_id: str) -> None:
        """Void a Stripe invoice."""
        try:
            await self._run_sync(stripe.Invoice.void_invoice, stripe_invoice_id)
            logger.info("stripe_invoice_voided", stripe_invoice_id=stripe_invoice_id)
        except stripe.error.StripeError as exc:
            logger.error(
                "stripe_void_invoice_error",
                stripe_invoice_id=stripe_invoice_id,
                error=str(exc),
            )
            raise HTTPException(status_code=502, detail="Error en Stripe") from exc

    def verify_webhook(
        self, payload: bytes, sig_header: str, secret: str
    ) -> dict:
        """Verify and construct a Stripe webhook event.

        Synchronous — no I/O involved.
        Raises ValueError on invalid signature (caller handles it).
        """
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
        return event
