---
titulo: Facturación y pagos
ambito: billing
ultima_verificacion_commit:
ultima_verificacion_fecha: 2026-04-17
---

# Facturación y pagos

## Resumen

MSI-a factura mensualmente al cliente (MSI Automotive) de forma automática: al final de cada mes, el admin genera la factura del período desde el panel, el sistema calcula cuánto costó el mantenimiento fijo más el consumo de tokens de IA, emite la factura en PDF, la registra en Stripe y cobra vía débito SEPA configurado previamente.

El cliente no necesita hacer nada: si tiene un método de pago SEPA activo en Stripe, el cobro ocurre automáticamente. Si el pago falla, Stripe notifica vía webhook y la factura pasa a estado `overdue`. El admin puede consultar, descargar y anular facturas desde el panel de administración (`/settings/billing`). La factura también se envía por email al operador como notificación.

## Escenarios

### 1. Generación automática de factura mensual

- DADO que terminó el mes de marzo 2025 y existe consumo de tokens registrado
- CUANDO el admin abre el panel en `/settings/billing` y hace click en "Generar factura"
- ENTONCES: el sistema calcula el coste de mantenimiento fijo (configurable via `MONTHLY_MAINTENANCE_EUR`) + coste de tokens (input/output del mes, vía `TokenUsage`) → aplica IVA (`IVA_RATE`) → crea factura con número correlativo `{PREFIX}-2025-03-001` → la persiste en BD con `status="issued"` → crea factura en Stripe → genera PDF → envía email al operador → la factura aparece en el listado del panel.
- Si ya existe una factura activa para ese período → error 409, no se crea duplicado.

### 2. Pago exitoso vía Stripe (débito SEPA)

- DADO que la factura `MSI-2025-03-001` tiene `status="issued"` y el cliente tiene SEPA configurado
- CUANDO Stripe procesa el débito exitosamente (normalmente en 3-5 días bancarios)
- ENTONCES: Stripe envía webhook `invoice.payment_succeeded` → nuestro endpoint `/api/billing/stripe/webhook` lo verifica por firma → `BillingService.handle_webhook_event()` actualiza la factura a `status="paid"`, registra `paid_at` y crea un registro `Payment` con `status="succeeded"` → la factura aparece como "Pagada" en el panel.
- Idempotente: si el webhook llega dos veces, la segunda es ignorada silenciosamente.

### 3. Pago fallido → escalado a overdue

- DADO que la factura `MSI-2025-03-001` está en `status="issued"` y el SEPA falla
- CUANDO Stripe envía webhook `invoice.payment_failed` con motivo "insufficient_funds"
- ENTONCES: el sistema registra un `Payment` con `status="failed"` y `failure_reason="insufficient_funds"` → si la fecha de vencimiento ya pasó, la factura pasa a `status="overdue"` → el admin ve la factura marcada en rojo en el panel y debe gestionar manualmente con el cliente.
- El sistema NO reintenta automáticamente (Stripe puede hacerlo según su configuración de reintentos).

### 4. Admin consulta facturas del mes en el panel

- DADO que el admin está logueado en el panel de administración
- CUANDO navega a `/settings/billing`
- ENTONCES: el panel llama a `GET /api/billing/invoices` → obtiene listado paginado ordenado por período (más reciente primero) → puede ver estado, importe total, fecha de vencimiento y si hay pagos registrados → puede descargar el PDF con `GET /api/billing/invoices/{id}/pdf` → puede ver estimación del mes en curso con `GET /api/billing/current-estimate` (sin generar factura).

## Reglas duras

1. **Una sola factura activa por período**: antes de crear una factura, `generate_invoice()` ejecuta un chequeo `SELECT 1 FROM invoices WHERE year=:year AND month=:month AND status != 'void' LIMIT 1`. Si hay resultado → error 409. No es un bloqueo de fila (no usa `FOR UPDATE`): bajo dos peticiones concurrentes teóricamente podrían pasar las dos validaciones antes del `commit`. La protección real es que esta operación es disparada solo desde el panel admin por un único operador, por lo que la carrera no ocurre en práctica. (`api/services/billing_service.py:131-140`)

2. **Stripe no bloquea la persistencia de la factura**: si `STRIPE_CUSTOMER_ID` no está configurado, la factura se genera igualmente sin Stripe. Si Stripe falla, la factura NO se persiste (la HTTPException(502) se propaga antes del `session.commit()`). (`api/services/billing_service.py:163-181`)

3. **PDF se genera después de persistir**: el PDF se genera tras el commit de la factura. Si el PDF falla, la factura queda igualmente en BD con `pdf_path=None`. El endpoint de descarga devuelve 404 si el PDF no existe. (`api/services/billing_service.py:218-222`)

4. **No se puede anular una factura pagada**: `void_invoice()` lanza error 400 si `status="paid"`. Solo se pueden anular facturas en `status="issued"` o `status="overdue"`. (`api/services/billing_service.py:293-298`)

5. **Webhook verificado por firma Stripe**: el endpoint `/api/billing/stripe/webhook` NO tiene autenticación JWT (es llamado por Stripe). La verificación se hace con `stripe.Webhook.construct_event()` usando `STRIPE_WEBHOOK_SECRET`. Firma inválida → 400. (`api/routes/billing.py:316-322`)

6. **Todos los montos en Decimal, nunca float**: `maintenance_amount_eur`, `token_amount_eur`, `iva_amount_eur`, `total_eur` son todos `Decimal` con rounding `ROUND_HALF_UP`. Usar float en cálculos financieros es un error. (`api/services/billing_service.py:148-153`)

7. **El email es fire-and-forget**: `_send_invoice_email()` se lanza como `asyncio.create_task()` y NUNCA propaga excepciones. Si el SMTP falla, se loguea el error pero la generación de factura no falla. (`api/services/billing_service.py:225`)

## Mapeo al código

| Archivo | Qué hace |
|---------|----------|
| `api/routes/billing.py` | Router `/api/billing` con 9 endpoints: listar/obtener/generar/anular facturas, descargar PDF, estimación actual, datos fiscales, setup SEPA, estado Stripe, webhook |
| `api/services/billing_service.py` | Lógica principal: `generate_invoice()` (crea factura completa), `current_estimate()` (lectura), `void_invoice()`, `handle_webhook_event()` (dispatcher), `check_overdue()` |
| `api/services/stripe_service.py` | Wrapper async del SDK Stripe: `create_invoice()`, `void_invoice()`, `create_setup_session()`, `has_payment_method()`, `verify_webhook()` |
| `api/services/pdf_service.py` | Generación de PDF con Jinja2 + WeasyPrint. Recibe dict de datos de `_build_invoice_data()`, devuelve path del archivo |
| `api/models/billing.py` | Pydantic schemas: `InvoiceResponse`, `GenerateInvoiceRequest`, `StripeSetupSessionResponse`, `CurrentEstimateResponse`, `FiscalDetailsResponse`, `PaymentResponse` |
| `database/models.py` | ORM: `Invoice` (número, año/mes, importes, status, Stripe IDs, pdf_path), `Payment` (intent_id, charge_id, monto, status, failure_reason) |

### Estados de una factura (`Invoice.status`)

| Estado | Descripción | Transición siguiente |
|--------|-------------|----------------------|
| `issued` | Emitida, pendiente de cobro | → `paid` (webhook) / → `overdue` (vencida) / → `void` (anulada) |
| `paid` | Cobrada exitosamente | Terminal (no se puede anular) |
| `overdue` | Vencida sin pago | → `void` (anulada manualmente) |
| `void` | Anulada | Terminal |

### Endpoints (todos bajo `/api/billing`, requieren rol `admin` salvo webhook)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/invoices` | Listado paginado de facturas |
| `GET` | `/invoices/{id}` | Detalle de una factura |
| `POST` | `/invoices/generate` | Genera factura para un período |
| `POST` | `/invoices/{id}/void` | Anula una factura |
| `GET` | `/invoices/{id}/pdf` | Descarga PDF |
| `GET` | `/current-estimate` | Estimación mes en curso (sin persistir) |
| `GET` | `/fiscal-details` | Datos fiscales proveedor/cliente |
| `POST` | `/stripe/setup-session` | URL para configurar SEPA en Stripe |
| `GET` | `/stripe/status` | Comprueba si hay método de pago SEPA |
| `POST` | `/stripe/webhook` | Webhook de Stripe (sin JWT, firma Stripe) |

## Fuera de alcance

- **Facturación a clientes finales** — este sistema factura de MSI-a (sistema) al operador (MSI Automotive). No cubre facturas al usuario final de WhatsApp.
- **Múltiples clientes Stripe** — un solo `STRIPE_CUSTOMER_ID` por instancia. No hay multitenancy de facturación.
- **Automatización de generación** — la generación de factura es manual (admin hace click). No hay cron job que la genere automáticamente al fin de mes.
- **Pasarela de pago para usuarios finales** — los usuarios de WhatsApp no pagan a través del sistema; el sistema factura solo el servicio de IA al operador.
- **Panel de cliente** — el cliente (MSI Automotive) no tiene acceso al panel. El admin es el equipo técnico de MSI-a.
- `admin-panel/src/` — componentes frontend del panel (otro scope)
- `database/alembic/` — migraciones (otro scope)
