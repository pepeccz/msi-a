---
titulo: Workers — image, lifecycle, billing, doc_processor
ambito: infra
ultima_verificacion_commit:
ultima_verificacion_fecha: 2026-04-17
---

# Workers en background

## Resumen

MSI-a tiene **3 workers activos** que corren en segundo plano: dos dentro del proceso `agent` y uno dentro del proceso `api`. Ninguno es un proceso separado: se arrancan como `asyncio.create_task` al inicio del servidor correspondiente y viven durante todo el ciclo de vida del contenedor.

> **Nota**: existe un cuarto worker (`document_processor_worker`) diseñado para RAG, pero su código fue eliminado del repositorio (`api/workers/document_processor_worker.py` no existe). `docker/Dockerfile.worker` también fue eliminado (era el único archivo que lo referenciaba y nunca estuvo en docker-compose.yml). Ver sección correspondiente.

| Worker | Proceso | Propósito | Intervalo |
|--------|---------|-----------|-----------|
| `image_batch_confirmation_worker` | `agent` | CTA de confirmación de fotos por timeout | Polling 3s, actúa tras N segundos de inactividad |
| `case_lifecycle_worker` | `agent` | Recordatorios a casos inactivos; marca como abandoned | Configurable via settings (default: scan cada X min) |
| ~~`document_processor_worker`~~ | `api` | **ELIMINADO del codebase** — diseñado para procesar PDFs vía Redis Streams → Qdrant; ni `api/workers/document_processor_worker.py` ni `docker/Dockerfile.worker` existen en el repo actual | — |
| `billing_worker` | `api` | Genera facturas mensuales; detecta facturas vencidas | Disparos cronometrados: 1° de mes 02:00 UTC + diario 03:00 UTC |

---

## Workers del servicio `agent`

Ambos se arrancan en `agent/main.py:1958-1967` como tasks de asyncio y se cancelan en el `finally` del shutdown:

```python
batch_task = asyncio.create_task(image_batch_confirmation_worker(shutdown_event, checkpointer))
lifecycle_task = asyncio.create_task(case_lifecycle_worker(shutdown_event, chatwoot))
```

Ambos reciben un `asyncio.Event` de shutdown y lo usan con `asyncio.wait_for(..., timeout=interval)` para salir limpiamente en lugar de `sleep()`.

### `image_batch_confirmation_worker`

**Fuente**: `agent/services/image_handling.py:1696`

**Qué hace**: Supervisa los batches de imágenes en Redis (clave `IMAGE_BATCH_KEY_PREFIX*`). Cuando un batch lleva más de `IMAGE_BATCH_TIMEOUT_SECONDS` inactivo, asume que el usuario terminó de subir fotos y:
1. Corre reconciliación (`reconcile_conversation_images`) para recuperar imágenes cuyo webhook se perdió.
2. Envía un mensaje CTA al usuario vía Chatwoot ("¿Confirmás que ya enviaste todas las fotos?").
3. Almacena el conteo confirmado para `reconcile_on_completion`.

**Polling**: cada 3 segundos (`check_interval = 3`). Escanea todas las claves en Redis con `SCAN`.

**Relación con Redis**: lee hashes de batch (`hgetall`), no usa Streams. Los batches los crean los webhooks de Chatwoot en tiempo real.

**Relación con estado**: lee `mode_context` del checkpointer de LangGraph para saber en qué sub-modo está la conversación (necesita confirmar que está en `COLLECT_ELEMENT_DATA` o `COLLECT_BASE_DOCS` antes de enviar la CTA).

**Comportamiento ante fallos**: errores por batch están aislados (un batch malo no bloquea los demás). El loop general sigue corriendo.

---

### `case_lifecycle_worker`

**Fuente**: `agent/services/case_lifecycle_worker.py`

**Qué hace**: Dos fases en cada ciclo:
1. **Recordatorio (~20h inactividad)**: llama `get_reminder_candidates(reminder_hours)`, para cada caso encontrado envía un WhatsApp via `chatwoot.send_message()` usando la plantilla `CASE_REMINDER_MESSAGE_TEMPLATE`, luego marca `Case.reminder_sent_at = now()`.
2. **Abandono (~4 días inactividad)**: llama `mark_cases_abandoned(abandon_days)`, que actualiza masivamente los casos a `status="abandoned"`. Estos casos son luego recuperables por el usuario via `reactivar_expediente_abandonado`.

**Timing**: Lee configuración de `get_settings()` en cada ciclo (sin restart para aplicar cambios):
- `CASE_REMINDER_HOURS` — horas de inactividad antes de recordatorio
- `CASE_ABANDON_DAYS` — días de inactividad antes de marcar abandoned
- `CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES` — intervalo entre ciclos

**Errores**: fallos por caso individual están aislados. Excepciones del ciclo completo se loguean a nivel ERROR y el loop continúa tras el intervalo.

**Relación con `reactivar_expediente_abandonado`**: este worker MARCA los casos como `abandoned`. La herramienta del agente los REACTIVA cuando el usuario vuelve. Son las dos puntas del mismo flujo.

---

## Worker del servicio `api`: `document_processor_worker` — ELIMINADO

> **Estado (2026-04-17)**: El archivo `api/workers/document_processor_worker.py` **no existe en el repositorio**. Fue eliminado junto con el resto del stack RAG (`api/services/qdrant_service.py`, `rag_service.py`, etc.). `docker/Dockerfile.worker` también fue eliminado (era el único archivo que lo referenciaba y nunca estuvo en docker-compose.yml). Las migraciones de BD para RAG sí existen (`007_rag_system.py`, `008_fix_rag_queries_fk.py`) pero las tablas están sin poblar.

**Qué hacía** (documentado para contexto futuro): Consumía la cola Redis Streams (`document_workers` consumer group) para procesar PDFs subidos vía el admin panel. Pipeline: PDF Extraction → Semantic Chunking → Section Mapping → Embedding Generation → Qdrant Indexing → DB Persistence. Soportaba multi-instancia con crash recovery (reclama mensajes idle >30s).

Para reactivar el pipeline RAG completo se necesita: restaurar los archivos de servicio eliminados + agregar Qdrant al docker-compose + crear un nuevo `Dockerfile.worker` (el anterior fue eliminado).

---

## Worker del servicio `api`: `billing_worker`

**Fuente**: `api/workers/billing_worker.py`

**Qué hace**: Dos loops en paralelo (`asyncio.gather`):

1. **`_monthly_invoice_loop`**: Corre el día 1 de cada mes a las 02:00 UTC. Llama `BillingService.generate_invoice(session, prev_year, prev_month)`. Si la factura ya existe (HTTP 409) lo logua a INFO, no ERROR.

2. **`_overdue_check_loop`**: Corre diariamente a las 03:00 UTC. Llama `BillingService.check_overdue(session)` y logua cuántas facturas quedaron vencidas.

**Timing**: Usa `_seconds_until(target_hour, target_minute, target_day)` — calcula segundos exactos hasta el próximo disparo, sin polling. Duerme con `asyncio.wait_for(shutdown_event.wait(), timeout=seconds)` para poder salir limpiamente.

**Arranque**: El `api/main.py` llama `billing_worker.run()` en el startup event. El `shutdown()` setea el evento global `_shutdown_event`.

**Relación con el sistema de facturación**: ver [`docs/system/modulos/facturacion/flujo.md`](../../modulos/facturacion/flujo.md) para el contrato completo de facturación (Stripe, PDF, estados).

---

## Escenarios

### Usuario sube fotos y el bot no responde de inmediato
- CUANDO el usuario envía 3 fotos por WhatsApp en COLLECT_ELEMENT_DATA
- ENTONCES los webhooks actualizan el batch hash en Redis, `last_update` se refresca con cada foto
- CUANDO `image_batch_confirmation_worker` detecta que el batch lleva `IMAGE_BATCH_TIMEOUT_SECONDS` sin actividad
- ENTONCES envía CTA de confirmación, el usuario confirma, el flujo avanza a datos técnicos

### Expediente inactivo durante 20h
- CUANDO `case_lifecycle_worker` corre su ciclo y encuentra un `Case` con `last_activity_at` hace >20h y `reminder_sent_at` nulo
- ENTONCES envía WhatsApp de recordatorio usando la plantilla configurada, marca `reminder_sent_at`
- El caso sigue activo — solo es un recordatorio amistoso

### Expediente abandonado tras 4 días
- CUANDO `case_lifecycle_worker` detecta caso con >4 días de inactividad
- ENTONCES `mark_cases_abandoned()` setea `status="abandoned"`, `abandoned_at=now()`
- Si el usuario vuelve: `conversation_graph.py` detecta `pending_abandoned_case` en state → bot ofrece retomar → usuario confirma → `reactivar_expediente_abandonado` lo reactiva

### PDF subido al admin panel
- CUANDO admin sube PDF vía `/api/admin/regulatory-documents`
- ENTONCES API crea `RegulatoryDocument` con `status="pending"` y publica en Redis Streams
- `document_processor_worker` consume el mensaje, procesa el PDF, actualiza progreso al 10%→20%→...→100%
- Admin puede ver progreso vía polling en el panel (si Qdrant disponible); actualmente termina en error en paso de indexación

---

## Reglas duras

- **Workers no se deben arrancar localmente** — corren en Docker dentro del servicio correspondiente. Ver CLAUDE.md `Do NOT start services locally`.
- **Fallos por item son aislados**: un case fallido, un batch fallido, o un documento fallido no bloquea el worker. Solo se logua el error a nivel ERROR/WARNING.
- **Shutdown limpio**: todos los workers reciben un `asyncio.Event` y lo esperan en lugar de hacer `time.sleep()`. Responden a SIGTERM en <intervalo de polling>.
- **`billing_worker`**: si el ciclo mensual ya generó la factura del mes (HTTP 409), NO es un error — es idempotencia correcta. No relanzar ni alarmar.
- **`document_processor_worker`**: ACK siempre, incluso en fallo. No dejar mensajes en estado pendiente que bloqueen la cola.

---

## Mapeo al código

| Componente | Archivo | Notas |
|-----------|---------|-------|
| `image_batch_confirmation_worker` | `agent/services/image_handling.py:1696` | Batch timeout, CTA, reconciliación |
| `case_lifecycle_worker` | `agent/services/case_lifecycle_worker.py` | Reminder + abandon loop |
| `billing_worker` | `api/workers/billing_worker.py` | Monthly invoice + overdue check |
| ~~`document_processor_worker`~~ | ~~`api/workers/document_processor_worker.py`~~ | **ELIMINADO** — no existe |
| Arranque agent workers | `agent/main.py:1958-1967` | `asyncio.create_task` |
| Helpers lifecycle | `agent/services/case_helpers.py` | `get_reminder_candidates`, `mark_cases_abandoned` |

---

## Fuera de alcance

- La lógica de facturación de Stripe (ver `facturacion.md`)
- El pipeline RAG completo (ver `docs/system/modulos/rag-regulatorio/pipeline.md`)
- Configuración de timeouts — se hacen via variables de entorno, ver `shared/config.py`
- Logs de workers — van a stdout en formato JSON estructurado (structlog), capturados por Docker
