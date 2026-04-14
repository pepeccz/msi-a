"""Billing service — invoice generation, cost calculation, payment lifecycle."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Invoice, Payment, TokenUsage
from shared.config import get_settings

# Lazy imports to avoid polluting the test environment with heavy optional deps
# (stripe SDK, weasyprint, jinja2). These are imported inside methods where they
# are actually used, so stubs/patches are straightforward.
if TYPE_CHECKING:
    from api.services.stripe_service import StripeService
    from api.services.pdf_service import PdfService

logger = structlog.get_logger(__name__)


def _get_stripe_service() -> "StripeService":
    """Lazy-import StripeService to avoid stripe SDK at module level."""
    from api.services.stripe_service import StripeService  # noqa: PLC0415
    return StripeService()


def _get_pdf_service() -> "PdfService":
    """Lazy-import PdfService to avoid jinja2/weasyprint at module level."""
    from api.services.pdf_service import PdfService  # noqa: PLC0415
    return PdfService()


class BillingService:
    """Core billing orchestrator: invoice generation, cost calculation, payment lifecycle."""

    # -------------------------------------------------------------------------
    # Token Cost Calculation
    # -------------------------------------------------------------------------

    async def calculate_token_cost(
        self,
        session: AsyncSession,
        year: int,
        month: int,
    ) -> tuple[Decimal, dict | None]:
        """Calculate token cost for a given billing period.

        Returns:
            Tuple of (cost_in_eur, snapshot_dict). snapshot_dict is None when
            no TokenUsage record exists for the period.
        """
        settings = get_settings()

        result = await session.execute(
            select(TokenUsage).where(
                TokenUsage.year == year,
                TokenUsage.month == month,
            )
        )
        usage = result.scalar_one_or_none()

        if not usage:
            return (Decimal("0.00"), None)

        input_tokens = Decimal(str(usage.input_tokens))
        output_tokens = Decimal(str(usage.output_tokens))

        input_cost = (input_tokens / Decimal("1000000")) * settings.TOKEN_PRICE_INPUT
        output_cost = (output_tokens / Decimal("1000000")) * settings.TOKEN_PRICE_OUTPUT
        total_cost = input_cost + output_cost

        snapshot = {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_requests": usage.total_requests,
        }

        return (total_cost, snapshot)

    # -------------------------------------------------------------------------
    # Invoice Number Generation
    # -------------------------------------------------------------------------

    async def _next_invoice_number(
        self,
        session: AsyncSession,
        year: int,
        month: int,
    ) -> str:
        """Generate the next sequential invoice number for the given year.

        Uses FOR UPDATE to prevent concurrent duplicates.
        """
        settings = get_settings()

        result = await session.execute(
            text("SELECT COUNT(*) FROM invoices WHERE year = :year FOR UPDATE").bindparams(
                year=year
            )
        )
        count: int = result.scalar() or 0

        return f"{settings.INVOICE_PREFIX}-{year}-{month:02d}-{count + 1:03d}"

    # -------------------------------------------------------------------------
    # Generate Invoice
    # -------------------------------------------------------------------------

    async def generate_invoice(
        self,
        session: AsyncSession,
        year: int,
        month: int,
    ) -> Invoice:
        """Generate a monthly invoice for the given period.

        Raises:
            HTTPException(409): An active (non-void) invoice already exists.
            HTTPException(502): Stripe call failed — invoice is NOT persisted.
        """
        settings = get_settings()

        # 1. Conflict check — no active invoice for this period
        conflict_result = await session.execute(
            text(
                "SELECT 1 FROM invoices WHERE year = :year AND month = :month "
                "AND status != 'void' LIMIT 1"
            ).bindparams(year=year, month=month)
        )
        if conflict_result.scalar() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Ya existe una factura activa para el período {month:02d}/{year}",
            )

        # 2. Token cost + snapshot
        token_cost, snapshot = await self.calculate_token_cost(session, year, month)

        # 3. Amounts — ALL Decimal, NEVER float
        maintenance = settings.MONTHLY_MAINTENANCE_EUR
        subtotal = maintenance + token_cost
        iva_amount = (subtotal * settings.IVA_RATE / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total = subtotal + iva_amount

        # 4. Invoice number (row-level lock)
        invoice_number = await self._next_invoice_number(session, year, month)

        # 5. Stripe (optional — only when customer ID is configured)
        stripe_invoice_id: str | None = None
        stripe_hosted_invoice_url: str | None = None
        stripe_pdf_url: str | None = None

        if settings.STRIPE_CUSTOMER_ID:
            line_items = [
                {
                    "description": "Honorarios de mantenimiento mensual",
                    "amount_cents": int(maintenance * 100),
                },
                {
                    "description": f"Consumo de IA — {month:02d}/{year}",
                    "amount_cents": int(token_cost * 100),
                },
            ]
            tax_rate_id = settings.STRIPE_TAX_RATE_ID or None
            # If Stripe raises HTTPException(502) it propagates — invoice NOT saved
            stripe_result = await _get_stripe_service().create_invoice(
                settings.STRIPE_CUSTOMER_ID, line_items, tax_rate_id
            )
            stripe_invoice_id = stripe_result.get("id")
            stripe_hosted_invoice_url = stripe_result.get("hosted_invoice_url")
            stripe_pdf_url = stripe_result.get("invoice_pdf")

        # 6. Persist invoice
        invoice = Invoice(
            invoice_number=invoice_number,
            year=year,
            month=month,
            maintenance_amount_eur=maintenance,
            token_amount_eur=token_cost,
            subtotal_eur=subtotal,
            iva_rate=settings.IVA_RATE,
            iva_amount_eur=iva_amount,
            total_eur=total,
            status="issued",
            stripe_invoice_id=stripe_invoice_id,
            stripe_hosted_invoice_url=stripe_hosted_invoice_url,
            stripe_pdf_url=stripe_pdf_url,
            due_date=date.today() + timedelta(days=settings.PAYMENT_DUE_DAYS),
            issued_at=datetime.now(timezone.utc),
            token_usage_snapshot=snapshot,
        )
        session.add(invoice)
        await session.commit()
        await session.refresh(invoice)

        # 7. Payment record when Stripe returned data
        if stripe_invoice_id:
            payment = Payment(
                invoice_id=invoice.id,
                stripe_payment_intent_id=stripe_invoice_id,
                amount_eur=total,
                status="pending",
            )
            session.add(payment)
            await session.commit()

        # 8. Generate PDF
        pdf_data = self._build_invoice_data(invoice, settings)
        pdf_path = await _get_pdf_service().generate(pdf_data)
        if pdf_path is not None:
            invoice.pdf_path = pdf_path
            await session.commit()

        # 9. Fire-and-forget email
        asyncio.create_task(_send_invoice_email(invoice, pdf_path))

        logger.info(
            "invoice_generated",
            invoice_number=invoice.invoice_number,
            year=year,
            month=month,
            total_eur=str(total),
            status=invoice.status,
        )

        return invoice

    # -------------------------------------------------------------------------
    # Current Estimate (read-only)
    # -------------------------------------------------------------------------

    async def current_estimate(self, session: AsyncSession) -> dict:
        """Return a read-only cost estimate for the current billing period."""
        settings = get_settings()
        now = datetime.now(timezone.utc)
        year, month = now.year, now.month

        token_cost, snapshot = await self.calculate_token_cost(session, year, month)

        maintenance = settings.MONTHLY_MAINTENANCE_EUR
        subtotal = maintenance + token_cost
        iva_amount = (subtotal * settings.IVA_RATE / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total = subtotal + iva_amount

        return {
            "year": year,
            "month": month,
            "maintenance_eur": f"{maintenance:.2f}",
            "token_eur": f"{token_cost:.2f}",
            "subtotal_eur": f"{subtotal:.2f}",
            "iva_rate": f"{settings.IVA_RATE:.2f}",
            "iva_amount_eur": f"{iva_amount:.2f}",
            "total_eur": f"{total:.2f}",
            "input_tokens": snapshot["input_tokens"] if snapshot else 0,
            "output_tokens": snapshot["output_tokens"] if snapshot else 0,
        }

    # -------------------------------------------------------------------------
    # Void Invoice
    # -------------------------------------------------------------------------

    async def void_invoice(
        self,
        session: AsyncSession,
        invoice_id: Any,
    ) -> Invoice:
        """Void an issued invoice.

        Raises:
            HTTPException(404): Invoice not found.
            HTTPException(400): Invoice is paid (cannot void) or already void.
            HTTPException(502): Stripe void call failed.
        """
        result = await session.execute(
            select(Invoice).where(Invoice.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()
        if invoice is None:
            raise HTTPException(status_code=404, detail="Factura no encontrada")

        if invoice.status == "paid":
            raise HTTPException(
                status_code=400, detail="No se puede anular una factura pagada"
            )
        if invoice.status == "void":
            raise HTTPException(status_code=400, detail="La factura ya está anulada")

        if invoice.stripe_invoice_id:
            await _get_stripe_service().void_invoice(invoice.stripe_invoice_id)

        invoice.status = "void"
        await session.commit()
        await session.refresh(invoice)

        logger.info("invoice_voided", invoice_number=invoice.invoice_number)
        return invoice

    # -------------------------------------------------------------------------
    # Check Overdue
    # -------------------------------------------------------------------------

    async def check_overdue(self, session: AsyncSession) -> int:
        """Mark issued invoices past due date as overdue.

        Returns:
            Number of invoices transitioned to overdue status.
        """
        today = date.today()
        result = await session.execute(
            text(
                "UPDATE invoices SET status = 'overdue', updated_at = now() "
                "WHERE status = 'issued' AND due_date < :today"
            ).bindparams(today=today)
        )
        count: int = result.rowcount
        await session.commit()

        if count:
            logger.info("invoices_marked_overdue", count=count)

        return count

    # -------------------------------------------------------------------------
    # Webhook Event Handler
    # -------------------------------------------------------------------------

    async def handle_webhook_event(
        self,
        session: AsyncSession,
        event: dict,
    ) -> None:
        """Dispatch Stripe webhook events to billing state transitions.

        Idempotent: already-transitioned invoices are silently skipped.
        """
        event_type: str = event.get("type", "")
        data_object: dict = event.get("data", {}).get("object", {})
        stripe_invoice_id: str | None = data_object.get("id")

        logger.debug("webhook_event_received", event_type=event_type)

        if event_type == "invoice.payment_succeeded":
            await self._handle_invoice_paid(session, stripe_invoice_id, data_object)
        elif event_type == "invoice.payment_failed":
            await self._handle_payment_failed(session, stripe_invoice_id, data_object)
        elif event_type == "invoice.voided":
            await self._handle_invoice_voided(session, stripe_invoice_id)
        else:
            logger.debug("webhook_event_ignored", event_type=event_type)

    async def _find_invoice_by_stripe_id(
        self, session: AsyncSession, stripe_invoice_id: str | None
    ) -> Invoice | None:
        if not stripe_invoice_id:
            return None
        result = await session.execute(
            select(Invoice).where(Invoice.stripe_invoice_id == stripe_invoice_id)
        )
        return result.scalar_one_or_none()

    async def _handle_invoice_paid(
        self,
        session: AsyncSession,
        stripe_invoice_id: str | None,
        data_object: dict,
    ) -> None:
        invoice = await self._find_invoice_by_stripe_id(session, stripe_invoice_id)
        if invoice is None:
            logger.warning("webhook_invoice_not_found", stripe_invoice_id=stripe_invoice_id)
            return

        # Idempotency: already paid → skip
        if invoice.status == "paid":
            logger.debug("webhook_invoice_already_paid", invoice_id=str(invoice.id))
            return

        invoice.status = "paid"
        invoice.paid_at = datetime.now(timezone.utc)

        # Capture Stripe PDF URL if available
        if data_object.get("invoice_pdf"):
            invoice.stripe_pdf_url = data_object["invoice_pdf"]

        # Dedup payments by stripe_charge_id
        stripe_charge_id: str | None = data_object.get("charge")
        if stripe_charge_id:
            existing_payment_result = await session.execute(
                select(Payment).where(Payment.stripe_charge_id == stripe_charge_id)
            )
            if existing_payment_result.scalar_one_or_none() is not None:
                await session.commit()
                return

        payment = Payment(
            invoice_id=invoice.id,
            stripe_payment_intent_id=data_object.get("payment_intent"),
            stripe_charge_id=stripe_charge_id,
            amount_eur=Decimal(str(data_object.get("amount_paid", 0))) / Decimal("100"),
            status="succeeded",
        )
        session.add(payment)
        await session.commit()

        logger.info("invoice_paid_via_webhook", invoice_number=invoice.invoice_number)

    async def _handle_payment_failed(
        self,
        session: AsyncSession,
        stripe_invoice_id: str | None,
        data_object: dict,
    ) -> None:
        invoice = await self._find_invoice_by_stripe_id(session, stripe_invoice_id)
        if invoice is None:
            logger.warning(
                "webhook_invoice_not_found_for_failure",
                stripe_invoice_id=stripe_invoice_id,
            )
            return

        failure_reason: str | None = None
        if data_object.get("last_payment_error"):
            failure_reason = data_object["last_payment_error"].get("message")

        payment = Payment(
            invoice_id=invoice.id,
            stripe_payment_intent_id=data_object.get("payment_intent"),
            amount_eur=Decimal(str(data_object.get("amount_due", 0))) / Decimal("100"),
            status="failed",
            failure_reason=failure_reason,
        )
        session.add(payment)

        # Escalate to overdue if past due date
        if invoice.due_date and invoice.due_date < date.today():
            invoice.status = "overdue"

        await session.commit()
        logger.warning(
            "invoice_payment_failed_via_webhook",
            invoice_number=invoice.invoice_number,
            failure_reason=failure_reason,
        )

    async def _handle_invoice_voided(
        self,
        session: AsyncSession,
        stripe_invoice_id: str | None,
    ) -> None:
        invoice = await self._find_invoice_by_stripe_id(session, stripe_invoice_id)
        if invoice is None:
            logger.warning("webhook_invoice_not_found_for_void", stripe_invoice_id=stripe_invoice_id)
            return

        if invoice.status == "void":
            logger.debug("webhook_invoice_already_void", invoice_id=str(invoice.id))
            return

        invoice.status = "void"
        await session.commit()
        logger.info("invoice_voided_via_webhook", invoice_number=invoice.invoice_number)

    # -------------------------------------------------------------------------
    # Invoice Data Builder (for PDF)
    # -------------------------------------------------------------------------

    def _build_invoice_data(self, invoice: Invoice, settings: Any) -> dict:
        """Build the dict expected by PdfService.generate()."""
        return {
            "invoice_number": invoice.invoice_number,
            "issued_at": invoice.issued_at,
            "due_date": invoice.due_date,
            "company_name": settings.COMPANY_LEGAL_NAME,
            "company_nif": settings.COMPANY_NIF,
            "company_address": settings.COMPANY_FISCAL_ADDRESS,
            "client_name": settings.CLIENT_COMPANY_NAME,
            "client_nif": settings.CLIENT_NIF,
            "client_address": settings.CLIENT_FISCAL_ADDRESS,
            "line_items": [
                {
                    "description": "Honorarios de mantenimiento mensual",
                    "amount": f"{invoice.maintenance_amount_eur:.2f}",
                },
                {
                    "description": f"Consumo de IA — {invoice.month:02d}/{invoice.year}",
                    "amount": f"{invoice.token_amount_eur:.2f}",
                },
            ],
            "subtotal": f"{invoice.subtotal_eur:.2f}",
            "iva_rate": f"{invoice.iva_rate:.2f}",
            "iva_amount": f"{invoice.iva_amount_eur:.2f}",
            "total": f"{invoice.total_eur:.2f}",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Email (fire-and-forget — NEVER raises)
# ─────────────────────────────────────────────────────────────────────────────


async def _send_invoice_email(invoice: Invoice, pdf_path: str | None) -> None:
    """Send invoice notification email to the operator.

    All errors are caught and logged. This function NEVER propagates exceptions.
    """
    settings = get_settings()

    if not settings.OPERATOR_EMAIL:
        logger.warning("invoice_email_skipped_no_operator_email")
        return

    if not settings.SMTP_HOST:
        logger.warning("invoice_email_skipped_no_smtp_host")
        return

    try:
        import aiosmtplib  # noqa: PLC0415 — lazy import (optional dependency)

        msg = MIMEMultipart()
        msg["Subject"] = f"Factura {invoice.invoice_number} — MSI Automotive"
        msg["From"] = settings.SMTP_USER
        msg["To"] = settings.OPERATOR_EMAIL

        body = (
            f"Período: {invoice.month:02d}/{invoice.year}\n"
            f"Total (IVA incluido): {invoice.total_eur} €\n"
            f"Vencimiento: {invoice.due_date}"
        )
        msg.attach(MIMEText(body, "plain"))

        if pdf_path and Path(pdf_path).exists():
            with open(pdf_path, "rb") as f:
                pdf_part = MIMEApplication(f.read(), _subtype="pdf")
                pdf_part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=f"{invoice.invoice_number}.pdf",
                )
                msg.attach(pdf_part)

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )

        logger.info(
            "invoice_email_sent",
            invoice_number=invoice.invoice_number,
            recipient=settings.OPERATOR_EMAIL,
        )

    except Exception:  # noqa: BLE001 — intentional blanket catch
        logger.warning(
            "invoice_email_failed",
            invoice_number=invoice.invoice_number,
            exc_info=True,
        )
