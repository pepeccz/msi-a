"""
MSI Automotive - Billing API routes.

Provides endpoints for invoice management, current cost estimates,
Stripe payment setup, and fiscal information.
Protected by admin authentication (except webhook).
"""

import structlog
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select, desc

from api.models.billing import (
    CurrentEstimateResponse,
    FiscalDetailsResponse,
    FiscalPartyResponse,
    GenerateInvoiceRequest,
    InvoiceListResponse,
    InvoiceResponse,
    PaymentResponse,
    StripeSetupSessionResponse,
    StripeStatusResponse,
    VoidInvoiceRequest,
)
from api.routes.admin import require_role
from api.services.billing_service import BillingService
from database.connection import get_async_session
from database.models import AdminUser, Invoice
from shared.config import get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


# =============================================================================
# Helpers
# =============================================================================


def _invoice_to_response(invoice: Invoice) -> InvoiceResponse:
    """Convert an Invoice ORM instance to InvoiceResponse schema."""
    payments = [
        PaymentResponse(
            id=str(p.id),
            stripe_payment_intent_id=p.stripe_payment_intent_id,
            stripe_charge_id=p.stripe_charge_id,
            amount_eur=p.amount_eur,
            fee_eur=p.fee_eur,
            status=p.status,
            failure_reason=p.failure_reason,
            created_at=p.created_at,
        )
        for p in (invoice.payments or [])
    ]
    return InvoiceResponse(
        id=str(invoice.id),
        invoice_number=invoice.invoice_number,
        year=invoice.year,
        month=invoice.month,
        maintenance_amount_eur=invoice.maintenance_amount_eur,
        token_amount_eur=invoice.token_amount_eur,
        subtotal_eur=invoice.subtotal_eur,
        iva_rate=invoice.iva_rate,
        iva_amount_eur=invoice.iva_amount_eur,
        total_eur=invoice.total_eur,
        status=invoice.status,
        stripe_invoice_id=invoice.stripe_invoice_id,
        pdf_path=invoice.pdf_path,
        due_date=invoice.due_date,
        issued_at=invoice.issued_at,
        paid_at=invoice.paid_at,
        notes=getattr(invoice, "notes", None),
        payments=payments,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/invoices",
    response_model=InvoiceListResponse,
    summary="Listar facturas",
    description="Devuelve la lista paginada de facturas ordenadas por período. Admin only.",
)
async def list_invoices(
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(10, ge=1, le=100, description="Elementos por página"),
    _: AdminUser = Depends(require_role("admin")),
) -> InvoiceListResponse:
    """List invoices with pagination, ordered by year DESC, month DESC."""
    async with get_async_session() as session:
        # Total count
        count_result = await session.execute(select(func.count(Invoice.id)))
        total = count_result.scalar() or 0

        # Paginated results
        offset = (page - 1) * page_size
        result = await session.execute(
            select(Invoice)
            .order_by(desc(Invoice.year), desc(Invoice.month))
            .offset(offset)
            .limit(page_size)
        )
        invoices = result.scalars().all()

        return InvoiceListResponse(
            invoices=[_invoice_to_response(inv) for inv in invoices],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get(
    "/invoices/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Obtener factura",
    description="Devuelve una factura por su ID. Admin only.",
)
async def get_invoice(
    invoice_id: str,
    _: AdminUser = Depends(require_role("admin")),
) -> InvoiceResponse:
    """Get a single invoice by ID."""
    async with get_async_session() as session:
        result = await session.execute(
            select(Invoice).where(Invoice.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()

        if invoice is None:
            raise HTTPException(status_code=404, detail="Factura no encontrada")

        return _invoice_to_response(invoice)


@router.post(
    "/invoices/generate",
    response_model=InvoiceResponse,
    status_code=201,
    summary="Generar factura",
    description="Genera una nueva factura para el período indicado. Admin only.",
)
async def generate_invoice(
    body: GenerateInvoiceRequest,
    _: AdminUser = Depends(require_role("admin")),
) -> InvoiceResponse:
    """Generate a monthly invoice for the given year/month."""
    async with get_async_session() as session:
        invoice = await BillingService().generate_invoice(session, body.year, body.month)
        return _invoice_to_response(invoice)


@router.get(
    "/current-estimate",
    response_model=CurrentEstimateResponse,
    summary="Estimación del período actual",
    description="Devuelve la estimación de costes del mes en curso. Admin only.",
)
async def current_estimate(
    _: AdminUser = Depends(require_role("admin")),
) -> CurrentEstimateResponse:
    """Return a read-only cost estimate for the current billing period."""
    async with get_async_session() as session:
        data = await BillingService().current_estimate(session)
        return CurrentEstimateResponse(**data)


@router.get(
    "/invoices/{invoice_id}/pdf",
    summary="Descargar PDF de factura",
    description="Devuelve el PDF generado de la factura. Admin only.",
)
async def download_pdf(
    invoice_id: str,
    _: AdminUser = Depends(require_role("admin")),
) -> FileResponse:
    """Download the PDF for a given invoice."""
    async with get_async_session() as session:
        result = await session.execute(
            select(Invoice).where(Invoice.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()

        if invoice is None:
            raise HTTPException(status_code=404, detail="Factura no encontrada")

        if not invoice.pdf_path or not Path(invoice.pdf_path).exists():
            raise HTTPException(status_code=404, detail="PDF no disponible")

        return FileResponse(
            invoice.pdf_path,
            media_type="application/pdf",
            filename=f"{invoice.invoice_number}.pdf",
        )


@router.post(
    "/invoices/{invoice_id}/void",
    response_model=InvoiceResponse,
    summary="Anular factura",
    description="Anula una factura emitida. Admin only.",
)
async def void_invoice(
    invoice_id: str,
    body: VoidInvoiceRequest | None = None,
    _: AdminUser = Depends(require_role("admin")),
) -> InvoiceResponse:
    """Void an issued invoice."""
    async with get_async_session() as session:
        invoice = await BillingService().void_invoice(session, invoice_id)
        return _invoice_to_response(invoice)


@router.get(
    "/fiscal-details",
    response_model=FiscalDetailsResponse,
    summary="Datos fiscales",
    description="Devuelve los datos fiscales del proveedor y cliente. Admin only.",
)
async def fiscal_details(
    _: AdminUser = Depends(require_role("admin")),
) -> FiscalDetailsResponse:
    """Return fiscal details for the company and client from settings."""
    settings = get_settings()
    return FiscalDetailsResponse(
        company=FiscalPartyResponse(
            name=settings.COMPANY_LEGAL_NAME,
            nif=settings.COMPANY_NIF,
            address=settings.COMPANY_FISCAL_ADDRESS,
        ),
        client=FiscalPartyResponse(
            name=settings.CLIENT_COMPANY_NAME,
            nif=settings.CLIENT_NIF,
            address=settings.CLIENT_FISCAL_ADDRESS,
        ),
    )


@router.post(
    "/stripe/setup-session",
    response_model=StripeSetupSessionResponse,
    summary="Crear sesión de configuración de Stripe",
    description="Crea una sesión de Checkout para configurar el método de pago SEPA. Admin only.",
)
async def create_stripe_setup_session(
    request: Request,
    _: AdminUser = Depends(require_role("admin")),
) -> StripeSetupSessionResponse:
    """Create a Stripe Checkout session for SEPA payment method setup."""
    from api.services.stripe_service import StripeService  # noqa: PLC0415

    settings = get_settings()
    if not settings.STRIPE_CUSTOMER_ID:
        raise HTTPException(status_code=503, detail="Stripe no configurado")

    success_url = f"{request.base_url}settings/billing?setup=success"
    cancel_url = f"{request.base_url}settings/billing?setup=cancel"

    session_url = await StripeService().create_setup_session(
        settings.STRIPE_CUSTOMER_ID, success_url, cancel_url
    )
    return StripeSetupSessionResponse(session_url=session_url)


@router.get(
    "/stripe/status",
    response_model=StripeStatusResponse,
    summary="Estado de Stripe",
    description="Comprueba si hay un método de pago SEPA configurado en Stripe. Admin only.",
)
async def stripe_status(
    _: AdminUser = Depends(require_role("admin")),
) -> StripeStatusResponse:
    """Check Stripe payment method status for the configured customer."""
    from api.services.stripe_service import StripeService  # noqa: PLC0415

    settings = get_settings()
    if not settings.STRIPE_CUSTOMER_ID:
        return StripeStatusResponse(
            has_payment_method=False,
            payment_method_type=None,
            last4=None,
            bank_name=None,
        )

    data = await StripeService().has_payment_method(settings.STRIPE_CUSTOMER_ID)
    return StripeStatusResponse(**data)


@router.post(
    "/stripe/webhook",
    summary="Webhook de Stripe",
    description="Endpoint de webhook para eventos de Stripe. Verificado por firma.",
    include_in_schema=True,
)
async def stripe_webhook(request: Request) -> dict:
    """Handle incoming Stripe webhook events.

    No auth dependency — verification is done via Stripe signature.
    """
    from api.services.stripe_service import StripeService  # noqa: PLC0415

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    settings = get_settings()

    try:
        event = StripeService().verify_webhook(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Firma de webhook inválida")

    async with get_async_session() as session:
        await BillingService().handle_webhook_event(session, event)

    return {"received": True}
