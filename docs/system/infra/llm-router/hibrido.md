---
titulo: LLM router — 2-tier Ollama + OpenRouter
ambito: infra
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Sistema LLM híbrido de 2 tiers

## Resumen

MSI-a implementa un **sistema LLM de 2 tiers** para optimizar latencia, costo y confiabilidad:

- **Tier 1 (Local)**: **Ollama + gemma4:e4b** (~4.9B params, 10GB VRAM) — tareas simples, rápidas: clasificación de vehículo, extracción de secciones, validación de restricciones. Latencia ~200-500ms, gratis.
- **Tier 2 (Cloud)**: **OpenRouter + deepseek/deepseek-chat** — razonamiento complejo, conversación agente, tool calling. Latencia ~1-3s, costo variable.

**Fallback automático**: si Tier 1 falla (Ollama offline), ruta a Tier 2. Si Tier 2 falla y el task es cloud-only (ej. tool calling), error fatal. Si Tier 2 falla y task tiene Tier 1, fallback a Local.

**TaskType enum dicta routing**: 8 task types → `CLASSIFICATION, EXTRACTION, RAG_COMPLEX, CONVERSATION, TOOL_CALLING, SUMMARIZATION, TRANSLATION, CONSTRAINT_VALIDATION`. Cada uno mapeado a Tier vía `TASK_TO_TIER` dict. El código **nunca hardcodea modelo**, siempre usa `LLMRouter.invoke(task_type=...)`.

## Escenarios

### 1. Clasificación simple de vehículo (Tier 1 local)
- CUANDO el agent recibe "Tengo una moto Yamaha YZF-R1"
- ENTONCES router detecta `task=CLASSIFICATION` → Tier 1 (gemma4:e4b) → Ollama latencia ~300ms → respuesta "moto deportiva". Metrics: `fallback_used=False, tier="local_fast"`.

### 2. Conversación compleja (Tier 2 cloud)
- CUANDO el agent entra a PRE_EXPEDIENTE y el cliente pregunta detalles técnicos
- ENTONCES `task=CONVERSATION` → Tier 2 (deepseek-chat vía OpenRouter) → latencia ~2s → respuesta multi-párrafo. Metrics: `fallback_used=False, tier="cloud_standard"`.

### 3. Ollama offline, fallback Local → Cloud
- CUANDO Ollama container está down (network issue, OOM killed)
- ENTONCES el agent intenta Tier 1 classification → httpx timeout/connection error → fallback disparado a Tier 2 (deepseek) → éxito → `fallback_used=True, original_tier="local_fast"`. El agent sigue funcionando, la conversación no se rompe.

### 4. Tool calling heavy (force Tier 2)
- CUANDO el agent ejecuta `confirmar_presupuesto` o `escalar_a_humano` (tool_calling)
- ENTONCES LLMRouter ve `tools=[...]` argument → `force_tier=CLOUD_STANDARD` independientemente de task_type (local no soporta tool calling bien) → respuesta JSON estructurada.

### 5. Extracción estructurada local
- CUANDO el agent necesita mapear "suspensión delantera/trasera" de texto libre
- ENTONCES `task=EXTRACTION` → Tier 1 (gemma4:e4b) → prompt pide JSON output → respuesta rápida, local ~400ms. `variant_interpretation_service` llama LLMRouter con `task=EXTRACTION`.

### 6. Validación de restricción (`CONSTRAINT_VALIDATION`, NEVER cloud)
- CUANDO `response_constraint` validator ejecuta regex check y quiere confirmación LLM
- ENTONCES `task=CONSTRAINT_VALIDATION, disable_fallback=True` → DEBE usar Tier 1 local → si Ollama offline, error (no fallback permitido) → previene cloud leakage de datos sensibles.

### 7. Cloud falla, task tiene Tier 1 fallback
- CUANDO deepseek-chat retorna 500 error (API down)
- ENTONCES `task=SUMMARIZATION` (default=Tier1). `TASK_TO_TIER[SUMMARIZATION]=LOCAL_FAST`, así que el error solo ocurre si local también falla.

### 8. Resiliencia completa: ambos tiers activos
- CUANDO sistema en producción con Ollama healthy + OpenRouter healthy
- ENTONCES clasificaciones/extracciones usan local (fast, free), conversaciones complejas usan cloud (capable), fallback chain permite one-off failures. SLO target: 99.9% uptime.

## Reglas duras

1. **TaskType enum dicta routing, no business logic**: nunca código como `if element_code == "ESCAPE" then use cloud`. Siempre `router.invoke(task_type=CLASSIFICATION, ...)`. TaskType es source of truth.

2. **`TASK_TO_TIER` dict inmutable en runtime**: no cambiar mappings dinámicamente. Cambios vía config/env rebuild.

3. **Fallback chain**: LOCAL_FAST → CLOUD_STANDARD → LOCAL_FAST (bidireccional). Si A falla, intenta B con `disable_fallback=True` para evitar loops. Solo ONE fallback attempt.

4. **`CONSTRAINT_VALIDATION` NEVER cloud**: `disable_fallback=True` mandatory. Si Ollama offline, error esperado (no call cloud). Protege datos sensibles.

5. **Tool calling fuerza CLOUD_STANDARD**: si `tools=[...]` present, tier override a CLOUD_STANDARD automáticamente, sin importar task_type.

6. **Timeouts a nivel HTTP**: `httpx.AsyncClient(timeout=120.0)` para Ollama y OpenRouter. Si sobrepasa, exception → fallback chain.

7. **Metrics buffering**: `_record_metrics()` guarda en `_metrics_buffer` (in-memory), se envían a BD async (batch persistence). Permite tracking sin bloqueo.

8. **No hardcodeo de modelos en business code**: todos los modelos definidos en `shared/config.py` (`LOCAL_FAST_MODEL="gemma4:e4b"`, `LLM_MODEL="deepseek/deepseek-chat"`).

9. **Ollama graceful degradation**: si Ollama offline, agent sigue funcionando (fallback a cloud). Si OpenRouter offline, solo tasks que soportan Tier 1 siguen.

10. **`LLMResponse` fields ALWAYS populated** (excepto error cases): `content`, `provider`, `model`, `tier`, `latency_ms`, `success` siempre presentes. Fallback y error responses tienen `fallback_used=True`, `original_tier=`.

## Mapeo al código

### Router central
- `shared/llm_router.py:1-433` — `LLMRouter` class, singleton
  - `TaskType` enum (37-47): CLASSIFICATION, EXTRACTION, RAG_COMPLEX, CONVERSATION, TOOL_CALLING, SUMMARIZATION, TRANSLATION, CONSTRAINT_VALIDATION
  - `ModelTier` enum (49-54): LOCAL_FAST, CLOUD_STANDARD, CLOUD_ADVANCED
  - `TASK_TO_TIER` dict (95-104)
  - `FALLBACK_CHAIN` dict (107-111)
  - `invoke()` (135-272): entry point, tier selection, call chain, fallback handling
  - `_call_ollama()` (274-302): httpx POST a Ollama `/api/chat`
  - `_call_openrouter()` (304-341): httpx POST a OpenRouter `/v1/chat/completions`
  - `health_check()` (381-420): ping both providers

### Configuration
- `shared/config.py:154-294`
  - `OPENROUTER_API_KEY`, `LLM_MODEL` ("deepseek/deepseek-chat"), `USE_HYBRID_LLM`
  - `LOCAL_FAST_MODEL` ("gemma4:e4b"), `OLLAMA_BASE_URL` ("http://ollama:11434")
  - Timeouts: `LLM_REQUEST_TIMEOUT_SECONDS`, `AGENT_TURN_TIMEOUT_SECONDS`

### Consumers del Router
- `agent/services/variant_interpretation_service.py` — `task=EXTRACTION`
- `agent/services/vehicle_classification_service.py` — `task=CLASSIFICATION`
- `agent/modes/base_mode.py` — LLM calls en tool loops
- `agent/modes/*/node.py` — cada node puede invocar router

### Metrics & Tracking
- `shared/llm_router.py:79-92` — `LLMMetrics` dataclass
- `shared/llm_router.py:343-379` — `_record_metrics()`, buffering
- `database/models.py` — `LLMUsageMetric` table (persiste métricas)

### Docker Orchestration
- `docker-compose.yml:82-134` — Ollama service (gemma4:e4b pull on startup), GPU support (nvidia docker)
- `docker-compose.yml:149` — Agent deps: Ollama optional

## Fuera de alcance

- `agent/modes/**` — business logic de modos (otro scope)
- `agent/prompts/**` — prompts (otro scope)
- `agent/tools/**` — tool definitions (otro scope)
- Database schema (usar migrations) — `LLMUsageMetric` existe, no editar models.py
- `api/routes/**` — API endpoints (otro scope)
- Frontend `admin-panel/src` — UI (otro scope)
- `shared/config.py` excepto para agregar NEW LLM settings
- Test suite `tests/` — scope distinto
