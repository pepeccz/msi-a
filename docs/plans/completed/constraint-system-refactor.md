# Plan: Constraint System Refactor — Validación Híbrida + Fixes Arquitectónicos

**Fecha**: 13 de Febrero de 2026  
**Estado**: PENDIENTE APROBACIÓN  
**Prioridad**: ALTA (bloquea el sales funnel en producción)  
**Rama**: `master` (hotfix incremental)  
**Depende de**: Transition Hardening completado (✅)

---

## Motivación

El sistema de constraints anti-alucinación (4 regexes en BD) produce **falsos positivos** que:
1. **Bloquean el sales funnel**: Session 1 del test E2E → usuario recibió "Disculpa, he tenido un problema..." en vez del mensaje de transición a Gateway
2. **Causan retries innecesarios**: +2-3s de latencia cloud por cada falso positivo
3. **Se parchean caso por caso**: Ya existe `_should_skip_constraint()` como parche para `price_requires_tool`, pero es frágil y crece con cada edge case

### Causa Raíz (3 problemas interrelacionados)

| # | Problema | Impacto |
|---|----------|---------|
| **P1** | LLM loop no corta cuando un tool señala `_transition_to` → LLM genera texto extra que dispara constraints | Bloquea transiciones |
| **P2** | Constraint validation usa `state` stale (del inicio del turno), no el `mode_context` actualizado → `_should_skip_constraint` no puede hacer skip | Falsos positivos |
| **P3** | Regex patterns no entienden CONTEXTO (un resumen legítimo que menciona precio matchea igual que una alucinación) | Falsos positivos estructurales |
| **P4** | Cache invalidation cross-container rota → admin desactiva constraint pero agente tarda 5 min en enterarse | Operación imposible |
| **P5** | Retry exhaustion sin protección → si 2 retries fallan, respuesta alucinada se envía al usuario | Riesgo UX |

---

## Solución Propuesta: 4 Fases

### Fase 1: Fix Quirúrgico del Loop + State (P1 + P2)
**Objetivo**: Desbloquear el sales funnel inmediatamente.

### Fase 2: Validación Híbrida (Regex pre-filter + LLM confirma) (P3)
**Objetivo**: Eliminar falsos positivos de raíz usando el LLM hybrid system.

### Fase 3: Redis Pub/Sub para Cache Invalidation (P4)
**Objetivo**: Los cambios de constraints desde admin se aplican instantáneamente.

### Fase 4: Hardening del Constraint System (P5 + cleanup)
**Objetivo**: Retry fallback seguro, consistencia entre modos, tests.

---

## Fase 1: Fix Quirúrgico del Loop + State

**Archivos**: `presupuesto_mode.py`, `expediente_mode.py`, `base_mode.py`, `consulta_mode.py`  
**Riesgo**: BAJO  
**Estimación**: ~40 líneas cambiadas

### 1A: Fast-Path Break en Transición

**Qué**: Cuando `_apply_tool_flags()` detecta `_transition_to`, el loop debe hacer `break` inmediato. El campo `message` del tool result se usa como `ai_response`.

**Dónde**: 
- `presupuesto_mode.py` — después de `_apply_tool_flags()` + `mode_context.update()` (~línea 396)
- `expediente_mode.py` — después de `_apply_tool_flags()` + `mode_context.update()` (~línea 777)

**Tools afectados** (3 total):
| Tool | Archivo | Target |
|------|---------|--------|
| `confirmar_presupuesto` | `transition_tools.py` | EVALUACION_GATEWAY |
| `finalizar_expediente` | `expediente_mode.py` (via `_extract_context_from_tool`) | COMPLETED |
| `cancelar_expediente` | `expediente_mode.py` (via `_extract_context_from_tool`) | PRESUPUESTO_MODE |

**Lógica**:
```
Después de _apply_tool_flags + mode_context.update(context_updates):
  if mode_context.get("_transition_to"):
    1. Extraer message del tool result como ai_response
    2. Añadir tool result a llm_messages (para checkpoint consistente)
    3. Set transition_break = True
    4. break del inner loop (tool_calls)
    
En el outer loop (iteraciones):
  if transition_break:
    break (sale sin hacer otra iteración LLM)
```

**NO afecta**: `consulta_mode.py` (no tiene tools de transición), `evaluacion_gateway.py` (no tiene LLM loop).

### 1B: Pasar mode_context Actualizado a Constraint Validation

**Qué**: Añadir parámetro `current_mode_context` a `_validate_response_constraints()` para que use el mode_context del turno actual (no el stale del state original).

**Dónde**:
- `base_mode.py:_validate_response_constraints()` — nuevo param opcional `current_mode_context`
- Los 3 modos que llaman constraints: pasar `mode_context` local

**Impacto**: Cuando `tarifa_calculada` se calcula en el mismo turno, `_should_skip_constraint` ahora SÍ lo ve → no dispara `price_requires_tool` innecesariamente.

### Verificación Fase 1
- Test: Simular `confirmar_presupuesto` → verificar loop para en la iteración correcta
- Test: Simular `calcular_tarifa` en mismo turno → verificar skip de `price_requires_tool`
- Deploy: `docker compose restart agent` → test E2E del funnel completo

---

## Fase 2: Validación Híbrida (Regex + LLM)

**Archivos**: `constraint_service.py`, `shared/llm_router.py`, `shared/config.py`  
**Riesgo**: BAJO (aditivo, fallback a regex si falla)  
**Estimación**: ~120 líneas nuevas

### Concepto

```
Paso 1: Regex rápido (0ms)
  → Si NO match → VÁLIDO (skip LLM) [~70% de casos]
  → Si MATCH → Paso 2

Paso 2: LLM Tier 1 qwen2.5:3b (200ms)
  → Confirma o descarta el match del regex
  → Si Ollama caído → Paso 3

Paso 3: Fallback a regex puro
  → Usar resultado del regex (NO escalar a cloud)
```

### Por Qué Híbrido (no LLM puro)

| Approach | Latencia media | Falsos positivos | Dependencia Ollama |
|----------|---------------|-----------------|-------------------|
| Regex puro (actual) | 0ms + 2.5s×FP_rate | ~5-10% | Ninguna |
| **Híbrido (propuesto)** | **~60ms** (0.7×0 + 0.3×200) | **~0%** | **Solo cuando regex matchea** |
| LLM puro | 200ms fijo | ~0% | Total |

### 2A: Nuevo TaskType.VALIDATION en LLM Router

**`shared/llm_router.py`**:
- Añadir `VALIDATION = "validation"` a `TaskType` enum
- Mapear a `ModelTier.LOCAL_FAST` (qwen2.5:3b)
- **IMPORTANTE**: Override de fallback — NUNCA escalar a cloud. Si Ollama cae → return None (regex decide).

**`shared/config.py`**:
- Añadir `USE_LOCAL_CONSTRAINT_VALIDATION: bool = True`
- Añadir `CONSTRAINT_VALIDATION_MODEL: str = "qwen2.5:3b"`

### 2B: Función `validate_with_llm()` en constraint_service

**Prompt de validación** (~200 tokens, structured JSON output):

```
Eres un validador de respuestas para un agente de homologación de vehículos.
Analiza si la RESPUESTA del agente contiene información que SOLO debería venir de herramientas.

HERRAMIENTAS LLAMADAS EN ESTE TURNO: {tools_called}
TIPO DE VIOLACIÓN DETECTADA POR REGEX: {constraint_type}
RESPUESTA DEL AGENTE: {response_text[:300]}

REGLAS:
- Si el agente RESUME o CONFIRMA información previamente calculada → VÁLIDO
- Si el agente INVENTA precios, variantes, o documentación sin tool → INVÁLIDO
- Si el agente menciona datos que vinieron del resultado de un tool en este turno → VÁLIDO

Responde SOLO con JSON:
{"valid": true}
o
{"valid": false, "reason": "breve explicación"}
```

**Características**:
- Input truncado a 300 chars (suficiente para detectar el patrón)
- `temperature=0` para máximo determinismo
- Timeout: 2s (si tarda más → fallback a regex)
- ~280 tokens total → ~200ms con qwen2.5:3b

### 2C: Integración en `validate_response()`

Modificar el flujo actual en `constraint_service.py`:

```python
# ANTES: regex match → VIOLATION
if re.search(pattern, response, IGNORECASE):
    if required_tool not in tools_called:
        return (False, error_injection)

# DESPUÉS: regex match → LLM confirma → VIOLATION (o false positive descartado)
if re.search(pattern, response, IGNORECASE):
    if required_tool not in tools_called:
        # Paso 2: LLM confirmation
        is_false_positive = await validate_with_llm(
            response, tools_called, constraint_type
        )
        if is_false_positive:
            logger.info("constraint_false_positive_discarded", ...)
            continue  # Skip this constraint
        return (False, error_injection)
```

### Verificación Fase 2
- Test unitario: Regex matchea + LLM dice "valid" → constraint NO dispara
- Test unitario: Regex matchea + LLM dice "invalid" → constraint SÍ dispara
- Test unitario: Ollama caído → fallback a regex puro
- Test E2E: `confirmar_presupuesto` genera resumen con precio → no se bloquea

---

## Fase 3: Redis Pub/Sub para Cache Invalidation

**Archivos**: `api/routes/constraints.py`, `agent/main.py`, nuevo `agent/services/cache_subscriber.py`  
**Riesgo**: BAJO  
**Estimación**: ~70 líneas nuevas

### Infraestructura Existente (ya funciona)

- `shared/redis_client.py` tiene `publish_to_channel()` → listo para publicar
- `agent/main.py` tiene patrón de background tasks con `shutdown_event` → listo para subscriber
- API y Agent comparten la misma instancia Redis via `msia-network`

### 3A: Publisher (API side)

**`api/routes/constraints.py`** — reemplazar `_invalidate_constraint_cache()`:

```python
# ANTES (roto en Docker):
def _invalidate_constraint_cache():
    try:
        from agent.services.constraint_service import invalidate_cache
        invalidate_cache()
    except Exception:
        pass

# DESPUÉS:
async def _invalidate_constraint_cache():
    await publish_to_channel(
        "msia:cache:invalidate:constraints",
        {"action": "invalidate_all", "timestamp": datetime.now(UTC).isoformat()}
    )
```

### 3B: Subscriber (Agent side)

**Nuevo `agent/services/cache_subscriber.py`**:

```python
async def cache_invalidation_subscriber(shutdown_event: asyncio.Event):
    """Subscribe to cache invalidation messages from API."""
    redis = get_redis_client()
    pubsub = redis.pubsub()
    await pubsub.subscribe("msia:cache:invalidate:constraints")
    
    while not shutdown_event.is_set():
        message = await pubsub.get_message(timeout=1.0)
        if message and message["type"] == "message":
            invalidate_cache()  # Borra _constraints_cache inmediatamente
    
    await pubsub.unsubscribe()
```

**`agent/main.py`** — añadir como tercera background task:

```python
cache_task = asyncio.create_task(
    cache_invalidation_subscriber(shutdown_event)
)
```

### Canal Naming Convention

```
msia:cache:invalidate:constraints   → Constraints cache
msia:cache:invalidate:tariffs       → (futuro) Tariffs cache
msia:cache:invalidate:settings      → (futuro) Settings cache
```

### Verificación Fase 3
- Test: Publicar mensaje en canal → verificar que `_constraints_cache` se vacía
- Test manual: Desactivar constraint desde admin → verificar que agente lo aplica en < 1s

---

## Fase 4: Hardening del Constraint System

**Archivos**: Todos los modos, `constraint_service.py`, tests  
**Riesgo**: BAJO  
**Estimación**: ~80 líneas

### 4A: Retry Exhaustion Safety Net

**Qué**: Cuando los 2 retries de constraint se agotan, en vez de enviar la respuesta alucinada, generar un mensaje genérico seguro.

**En los 3 modos** (presupuesto, consulta, expediente):
```python
# DESPUÉS de que validation_retries >= MAX_VALIDATION_RETRIES:
if validation_retries >= MAX_VALIDATION_RETRIES:
    logger.warning("constraint_retries_exhausted", ...)
    ai_response = "Disculpa, déjame reformularte la respuesta."
    # Resetear y dejar que el safety net de base_mode actúe
    break
```

### 4B: Unificar Rol de Mensaje Inyectado

**Qué**: Todos los modos usan `"role": "system"` (no `"user"`) para la inyección de constraint error. Añadir la instrucción "IMPORTANT: You MUST call the required tools" en todos.

| Modo | Antes | Después |
|------|-------|---------|
| PRESUPUESTO | `role: "system"` + IMPORTANT | Sin cambio |
| CONSULTA | `role: "user"` sin IMPORTANT | `role: "system"` + IMPORTANT |
| EXPEDIENTE | `role: "user"` sin IMPORTANT | `role: "system"` + IMPORTANT |

### 4C: Reactivar `variant_requires_tool` constraint

**Qué**: Después de que la validación híbrida esté funcionando, reactivar el constraint que desactivamos. Con el LLM confirmando, no debería producir falsos positivos.

```sql
UPDATE response_constraints 
SET is_active = true 
WHERE constraint_type = 'variant_requires_tool';
```

### 4D: Tests de Regresión

Nuevos tests en `tests/unit/test_constraint_refactor.py`:

1. **Fast-path break**: `confirmar_presupuesto` → loop para en iteración correcta, `ai_response` = tool message
2. **State actualizado**: `calcular_tarifa` en mismo turno → skip de `price_requires_tool`
3. **Híbrido regex+LLM**: Regex matchea resumen legítimo → LLM descarta → no violation
4. **Híbrido regex+LLM**: Regex matchea alucinación real → LLM confirma → violation
5. **Fallback a regex**: Ollama caído → regex decide
6. **Pub/Sub**: Publicar invalidación → caché se vacía
7. **Retry exhaustion**: 2 retries fallidos → mensaje seguro (no alucinación)
8. **Rol unificado**: Todos los modos inyectan como `role: "system"`

---

## Orden de Implementación y Deploy

| Fase | Qué | Deploy | Test E2E |
|------|-----|--------|----------|
| **1** | Fix loop + state stale | `docker compose restart agent` | Funnel completo: PRESUPUESTO → "sí" → GATEWAY → EXPEDIENTE |
| **2** | Validación híbrida | `docker compose restart agent` | Repetir test con `variant_requires_tool` reactivado |
| **3** | Redis Pub/Sub | `docker compose restart agent api` | Desactivar/reactivar constraint desde admin → verificar efecto inmediato |
| **4** | Hardening + tests | `docker compose restart agent` | Test de retry exhaustion, verificar mensaje seguro |

### Cada fase es independientemente deployable
- Fase 1 sola ya desbloquea el funnel
- Fase 2 sola ya elimina falsos positivos
- Fase 3 sola ya arregla operación admin
- Fase 4 cierra deuda técnica

---

## Riesgos y Mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|-------------|-----------|
| Fast-path break pierde respuesta personalizada del LLM | BAJA | El `message` del tool ya es adecuado. El Gateway genera su propio mensaje después. |
| LLM de validación (qwen2.5:3b) es demasiado permisivo | BAJA | El regex pre-filtra, el LLM solo confirma/descarta. Tarea binaria simple. Si el LLM falla → regex decide. |
| Ollama caído durante validación | BAJA | Fallback a regex puro. No peor que el estado actual. NUNCA escalar a cloud. |
| Redis Pub/Sub pierde mensajes | BAJA | TTL de 5 min sigue como fallback. Los mensajes perdidos se resuelven en la próxima expiración. |
| Meta-hallucination (LLM validando LLM) | MUY BAJA | El LLM solo decide "¿es resumen o invención?". No genera contenido. `temperature=0`. |

---

## Archivos Afectados (Resumen)

| Archivo | Fase | Cambio |
|---------|------|--------|
| `agent/modes/presupuesto_mode.py` | 1, 4 | Fast-path break + state fix + rol unificado |
| `agent/modes/expediente_mode.py` | 1, 4 | Fast-path break + state fix + rol unificado |
| `agent/modes/consulta_mode.py` | 1, 4 | State fix + rol unificado |
| `agent/modes/base_mode.py` | 1 | Nuevo param `current_mode_context` en `_validate_response_constraints()` |
| `agent/services/constraint_service.py` | 2 | `validate_with_llm()` + integración híbrida |
| `shared/llm_router.py` | 2 | `TaskType.VALIDATION` + routing |
| `shared/config.py` | 2 | Settings para constraint validation |
| `api/routes/constraints.py` | 3 | Publisher Redis Pub/Sub |
| `agent/main.py` | 3 | Background task subscriber |
| `agent/services/cache_subscriber.py` | 3 | **NUEVO** — Pub/Sub subscriber |
| `tests/unit/test_constraint_refactor.py` | 4 | **NUEVO** — Tests de regresión |

**Total estimado**: ~310 líneas nuevas/modificadas, 11 archivos (1 nuevo + 1 test nuevo)

---

## Criterios de Éxito

1. ✅ El funnel PRESUPUESTO → "sí" → GATEWAY → EXPEDIENTE funciona sin mensajes de error
2. ✅ `variant_requires_tool` reactivado y sin falsos positivos
3. ✅ Desactivar constraint desde admin se aplica en < 1s en el agente
4. ✅ Si Ollama está caído, el sistema funciona igual que ahora (regex puro)
5. ✅ Retry exhaustion produce mensaje seguro, no alucinación
6. ✅ Todos los tests pasan (52 existentes + ~8 nuevos)

---

## Pregunta Abierta

¿Quieres que también mueva los 4 constraints de la migración 027 al sistema de seeds con UUIDs determinísticos? Actualmente están hardcodeados en la migración y si alguien los borra desde admin, se pierden permanentemente. Esto sería un fix menor (~50 líneas extra) pero no es bloqueante.
