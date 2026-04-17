---
titulo: Telemetría y costes de LLM
ambito: infraestructura
ultima_verificacion_commit:
ultima_verificacion_fecha: 2026-04-17
---

# Telemetría y costes de LLM

## Resumen

MSI-a tiene dos capas de observabilidad para el uso del LLM:

1. **Turn Telemetry** (`agent/services/turn_telemetry.py`) — envelope por turno emitido como log estructurado JSON en tiempo real. Cubre latencia, tools usadas, tier LLM, violaciones de constraints, y motivo de salida del loop.
2. **Token Tracking** (`agent/services/token_tracking.py`) — persistencia mensual en PostgreSQL de tokens consumidos y costes calculados. Acumulado mes a mes vía UPSERT atómico.

Además, el sistema de validación tiene sus propias métricas accesibles vía API.

---

## Turn Telemetry

**Fuente**: `agent/services/turn_telemetry.py`

### Qué es un "turn"

Un turno es un ciclo completo: el usuario envía un mensaje → el agente procesa (incluyendo el tool loop) → el agente emite su respuesta. Cada turno genera exactamente un `TurnTelemetryEnvelope`.

### Campos del envelope

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `conversation_id` | `str` | ID de conversación (hilo de WhatsApp) |
| `turn_id` | `str` | UUID único por turno |
| `mode` | `str` | Modo activo: `PRE_EXPEDIENTE_MODE`, `EXPEDIENTE_MODE`, etc. |
| `sub_mode` | `str \| None` | Sub-modo en EXPEDIENTE (ej. `collect_personal`) |
| `latency_ms` | `float` | Latencia total del turno en ms (desde entrada hasta respuesta) |
| `prompt_tokens_estimate` | `int \| None` | Estimación de tokens de prompt |
| `completion_tokens` | `int \| None` | Tokens reales de completion (cuando el LLM los reporta) |
| `tool_iterations` | `int` | Cuántas iteraciones hizo el tool loop |
| `tools_called` | `list[str]` | Nombres de las herramientas invocadas en el turno |
| `fallback_used` | `bool` | True si hubo fallback de tier LLM (cloud → local o viceversa) |
| `original_tier` | `str \| None` | Tier LLM intentado originalmente (Tier 1 / Tier 2) |
| `final_tier` | `str \| None` | Tier LLM que efectivamente respondió |
| `constraint_violations` | `int` | Cuántas violations de constraints se detectaron en el turno |
| `llm_validations_skipped` | `int` | Cuántas validaciones LLM se saltaron |
| `state_warnings` | `list[str]` | Warnings de contrato de state (ej. "mode_context key missing") |
| `exit_reason` | `str \| None` | Por qué terminó el tool loop: `no_tool_calls`, `max_iterations`, `validation_abort`, `error` |
| `error` | `str \| None` | Descripción de error si el turno falló |

### Cómo se usa

El `BaseModeNode` (o cada nodo de modo) llama:

```python
from agent.services.turn_telemetry import start_turn, complete_turn, emit_turn_telemetry

envelope = start_turn(conversation_id, mode="PRE_EXPEDIENTE_MODE")
# ... loop de herramientas y LLM ...
envelope.tool_iterations = iteration_count
envelope.tools_called = list(tools_called)
complete_turn(envelope)       # Calcula latency_ms
emit_turn_telemetry(envelope)  # Emite structlog INFO "turn_telemetry"
```

### Dónde se persiste

**No se persiste en base de datos directamente** — se emite como log estructurado JSON via `structlog` a nivel `INFO`. El log aparece en la salida del contenedor `agent` con el evento `"turn_telemetry"`.

Para leerlos en producción:

```bash
docker compose logs agent | grep turn_telemetry
# O filtrar en el sistema de logs (Docker log driver, Loki, CloudWatch, etc.)
```

### Relación con el admin panel

> **Estado (2026-04-17)**: `api/routes/llm_metrics.py` **no existe en el repositorio** — fue eliminado junto con el stack RAG. Lo que sí existe es `api/routes/token_usage.py` para consultar tokens y costes.

El panel no tiene una sección "LLM Metrics" operativa actualmente. Para métricas de tokens y costes, el admin puede usar los endpoints de `token_usage.py` (ver sección Token Tracking).

---

## Token Tracking (persistencia mensual)

**Fuente**: `agent/services/token_tracking.py`

### Qué persiste

Una fila por mes en la tabla `TokenUsage` (PostgreSQL). UPSERT atómico: si ya existe la fila del mes actual, incrementa `input_tokens`, `output_tokens`, `total_requests`. Si no existe, la crea.

```
TokenUsage:
  id           UUID (PK)
  year         int
  month        int          ← constraint UNIQUE (year, month)
  input_tokens int          ← acumulado del mes (prompt tokens)
  output_tokens int         ← acumulado del mes (completion tokens)
  total_requests int        ← número de requests LLM en el mes
  created_at   timestamptz
  updated_at   timestamptz
```

### Cómo se registra

Cada vez que el LLM responde, el servicio llama:

```python
await record_token_usage(input_tokens=..., output_tokens=...)
```

Este método usa `INSERT ... ON CONFLICT DO UPDATE SET input_tokens = input_tokens + ...` — operación atómica que garantiza no perder datos en concurrencia.

**Tokens con valor 0 o negativo no se registran** (guarda que evita contaminación con valores de fallback o errores).

**Fallos no se propagan**: si PostgreSQL falla, el error se logua a `ERROR` pero el agente continúa respondiendo. El token tracking nunca debe romper la conversación.

### Endpoints de consulta

Todos bajo `api/routes/token_usage.py` (`/api/token-usage`), requieren JWT + rol admin:

| Endpoint | Qué devuelve |
|----------|-------------|
| `GET /api/token-usage` | Últimos 12 meses, orden desc. |
| `GET /api/token-usage/current` | Mes actual con **costes calculados en EUR** (usando `TOKEN_PRICE_INPUT` y `TOKEN_PRICE_OUTPUT` de Settings) |
| `GET /api/token-usage/pricing` | Configuración actual de precios por millón de tokens |

### Cálculo de costes

```
cost_input_eur  = (input_tokens  / 1_000_000) * TOKEN_PRICE_INPUT
cost_output_eur = (output_tokens / 1_000_000) * TOKEN_PRICE_OUTPUT
cost_total_eur  = cost_input_eur + cost_output_eur
```

Los precios `TOKEN_PRICE_INPUT` y `TOKEN_PRICE_OUTPUT` se leen de `get_settings()` (Pydantic Settings) — configurables por variable de entorno, sin restart del servicio.

---

## Métricas de validación

**Fuente**: `agent/utils/validation_metrics.py` + `api/routes/validation_metrics.py`

El sistema de validación del agente (que verifica que las respuestas del LLM cumplan constraints) mantiene contadores en memoria:

- Intentos totales de validación
- Fallos por herramienta y por capa
- Tasa de éxito en reintento
- Tasa de escalación tras fallos

Estos contadores son **en memoria** — se resetean al reiniciar el contenedor. Se acceden vía:

| Endpoint | Auth | Descripción |
|----------|------|-------------|
| `GET /api/validation-metrics` | admin | Snapshot de todos los contadores |
| `POST /api/validation-metrics/reset` | admin | Reset de contadores (nueva ventana de medición) |

Para leer desde el panel: Settings → Validación (si la ruta existe en el frontend) o via `curl` directo.

---

## Costes aproximados del LLM

| Capa | Modelo | Uso | Coste típico |
|------|--------|-----|-------------|
| **Tier 1 (local)** | Ollama `gemma4:e4b` | Clasificación, extracción, tasks simples | Casi cero (CPU/GPU del servidor) |
| **Tier 2 (cloud)** | OpenRouter `deepseek/deepseek-chat` | Conversación, razonamiento complejo | Varía por tokens — ver `/api/token-usage/current` para coste real |
| **Fallback** | Cloud → Local | Si el cloud falla, se intenta local | Depende del modelo de fallback disponible |

El sistema híbrido minimiza costes usando el tier local siempre que sea posible (clasificaciones, extracciones de entidades, queries RAG simples). El cloud se usa para la generación de respuestas conversacionales y para queries RAG complejas.

El coste mensual real se consulta en el panel admin en **Settings → Uso de Tokens** (`/settings/usage`).

---

## Escenarios

### Operador detecta latencia alta en un modo
- CUANDO los logs muestran `turn_telemetry` con `latency_ms > 8000`
- ENTONCES revisar `tool_iterations` (si alto → el tool loop iteró mucho) y `final_tier` (si cloud → latencia de red)
- Y revisar `exit_reason` — si es `max_iterations` → el LLM nunca cerró el loop limpiamente

### Admin consulta coste del mes
- CUANDO abre `/settings/usage` o llama `GET /api/token-usage/current`
- ENTONCES ve input_tokens, output_tokens, total_requests, y `cost_total_eur` calculado
- Si el coste es inesperadamente alto → revisar si `fallback_used=True` frecuente en logs (indica problemas de disponibilidad del tier local)

### Detectar spike de escalaciones por validación
- CUANDO `GET /api/validation-metrics` muestra `escalation_rate` > umbral esperado
- ENTONCES revisar logs con evento `validation_abort` en `exit_reason` del turn_telemetry
- Resetear con `POST /api/validation-metrics/reset` después de investigar para empezar nueva ventana limpia

---

## Reglas duras

- **Token tracking nunca debe romper el agente**: errores de DB en `record_token_usage()` se loguean y se ignoran.
- **Turn telemetry siempre se emite**: incluso en turnos con error, `emit_turn_telemetry()` debe llamarse (con `error` seteado en el envelope).
- **Los precios de tokens son configurables**: `TOKEN_PRICE_INPUT` y `TOKEN_PRICE_OUTPUT` en Settings. Actualizar cuando cambie el proveedor o el modelo.
- **Métricas de validación son en memoria**: al reiniciar el `agent` container, los contadores se pierden. No usar para SLAs a largo plazo sin un sistema externo de agregación.
- **LLM Metrics eliminado**: `api/routes/llm_metrics.py` no existe en el repositorio actual. Si se reimplementa, tener en cuenta si agregar auth o dejarlo sin auth (métricas no sensibles).

---

## Mapeo al código

| Componente | Archivo | Notas |
|-----------|---------|-------|
| `TurnTelemetryEnvelope` | `agent/services/turn_telemetry.py` | Dataclass, todos los campos |
| `start_turn` / `complete_turn` / `emit_turn_telemetry` | `agent/services/turn_telemetry.py` | Funciones de ciclo de vida del envelope |
| `record_token_usage` | `agent/services/token_tracking.py` | UPSERT mensual en DB |
| `get_current_month_usage` | `agent/services/token_tracking.py` | Lectura del mes actual |
| Token API endpoints | `api/routes/token_usage.py` | 3 endpoints bajo `/api/token-usage` |
| ~~LLM Metrics endpoints~~ | ~~`api/routes/llm_metrics.py`~~ | **ELIMINADO** — no existe en el repo |
| Validation Metrics endpoints | `api/routes/validation_metrics.py` | 2 endpoints, admin only |
| `get_validation_metrics()` | `agent/utils/validation_metrics.py` | Singleton en memoria |
| `TokenUsage` model | `database/models.py` | ORM + constraint `uq_token_usage_year_month` |
| Precio tokens | `shared/config.py` → `TOKEN_PRICE_INPUT`, `TOKEN_PRICE_OUTPUT` | Pydantic Settings |

---

## Fuera de alcance

- Exportación de logs a servicios externos (Loki, CloudWatch, Datadog) — depende del log driver de Docker configurado en el servidor
- Alertas automáticas en umbral de coste — no implementado; se haría a nivel de infraestructura externa
- Telemetría de la capa API (FastAPI) — no tiene turn telemetry propio; usa logging estándar de FastAPI
- El sistema de billing para el operador (Stripe, facturas) — ver `docs/system/04-reglas-negocio/facturacion.md`
