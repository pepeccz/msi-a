---
titulo: Panel admin — billing
ambito: ui
ultima_verificacion_fecha: 2026-04-17
ultima_verificacion_commit:
---

# Panel admin — billing

## Resumen

El área de billing muestra al admin el historial de facturas del operador (MSI Automotive) con su ciclo de vida completo, permite descargar los PDFs de cada factura y visualizar el estado de pago. Este archivo documenta exclusivamente la experiencia en el panel (UX). Las reglas de negocio de facturación — ciclo de vida de facturas, Stripe SEPA, webhooks, estados — están en [`../../modulos/facturacion/flujo.md`](../../modulos/facturacion/flujo.md).

## Escenarios

### 13. Admin gestiona facturación mensual
- CUANDO abre **Billing** (ruta bajo `/billing` o sección Settings)
- ENTONCES ve historial de facturas con estado (draft → issued → paid / overdue / void), puede descargar PDF, ver monto y período.
- Click en "Descargar PDF" → el navegador inicia la descarga del PDF de la factura correspondiente.
- El estado de la factura se muestra con badge de color acorde: draft (gris), issued (azul), paid (verde), overdue (naranja), void (rojo).
- No hay acciones de edición desde el panel: las transiciones de estado las gatilla el backend vía Stripe webhooks o acción manual del API.

## Reglas duras

Ver "Reglas compartidas (aplican a todo el panel)" en [conversaciones.md](./conversaciones.md) para las 13 reglas base del panel.

Reglas propias de billing:

- El panel de billing es solo lectura: no permite crear ni editar facturas desde la UI. Las operaciones de escritura son exclusivas del backend.
- La descarga de PDF se hace vía link firmado o endpoint de descarga del API — nunca exponiendo la URL directa del archivo en storage.
- Para las reglas de negocio completas (cálculo de monto, período de facturación, reintentos de cobro, estados válidos y transiciones), ver [`../../modulos/facturacion/flujo.md`](../../modulos/facturacion/flujo.md).

## Mapeo al código

| Ruta | Archivo | Qué hace |
|------|---------|----------|
| `/billing` | `admin-panel/src/app/(authenticated)/billing/page.tsx` | Historial de facturas, descarga PDF |
| `GET /api/billing/*` | `api/routes/billing.py` | 10 endpoints: historial, PDF, estado, Stripe |

## Fuera de alcance

- `api/**` — `api/routes/billing.py`, lógica de negocio de facturación, integración Stripe SEPA
- `database/**` — modelo ORM de facturas, estados de pago
- `shared/**` — librerías compartidas
- Reglas de negocio del ciclo de facturación — ver `modulos/facturacion/flujo.md`
