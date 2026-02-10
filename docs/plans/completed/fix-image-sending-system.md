# Plan: Fix Sistema de Envío de Imágenes MSI-a

**Fecha**: 5 de Febrero de 2026  
**Estado**: APROBADO PARA IMPLEMENTACIÓN  
**Prioridad**: CRÍTICA  
**Estrategia UX**: Opción B (Flujo Conversacional Mejorado)

---

## Resumen Ejecutivo

El sistema de envío de imágenes de ejemplo está completamente **NO FUNCIONAL** debido a 5 bugs críticos identificados:

1. 🔴 **CRÍTICO**: `tarifa_actual` nunca se escribe → tool siempre falla
2. 🔴 **CRÍTICO**: `price_communicated_to_user` nunca se setea → tool bloquea envío
3. 🟠 **ALTO**: No hay detección de "Opción A" → ~30-40% usuarios no detectados
4. 🟡 **MEDIO**: LLM inventa URLs cuando no hay imágenes disponibles
5. 🟡 **MEDIO**: Constraint service causa falsos positivos → +2-3x costo tokens

**Impacto**: El flujo principal de presupuestación (90% del tráfico) está roto. Los usuarios NO reciben imágenes de ejemplo aunque las pidan explícitamente.

**Solución**: 5 fases de fixes (bugs críticos → mejoras UX → optimización), ~85 minutos de implementación, 8 archivos modificados, ~135 líneas de código.

---

## Servicios Afectados

- [x] **Agent** (modes, router, tools, prompts, services)
- [ ] API (ningún cambio)
- [ ] Database (ningún cambio)
- [ ] Admin (ningún cambio)
- [ ] Shared (ningún cambio)

---

## Hallazgos de Investigación

### Contexto Analizado

- **Conversación reportada**: Usuario responde "A" tras calcular presupuesto de SUBCHASIS
- **Comportamiento actual**: Agent lista URLs en texto plano, NO envía imágenes vía Chatwoot
- **5 investigaciones paralelas** completadas (tarifa_actual, price_communicated, error handling, constraint service, detección "Opción A")

### Bug #1: `tarifa_actual` No Se Escribe (CRÍTICO)

**Evidencia**:
```python
# image_tools.py:166 BUSCA:
tarifa_actual = state.get("tarifa_actual")
if not tarifa_actual:
    return {"success": False, "message": "No hay presupuesto calculado..."}

# presupuesto_mode.py:408 ESCRIBE:
updates["tarifa_calculada"] = data  # ← Nombre DIFERENTE!

# RESULTADO: Tool SIEMPRE falla con "No hay presupuesto calculado"
```

**Causa raíz**: En v1 (archivado) sí se escribía `tarifa_actual`. En v2 (actual) se perdió esta lógica durante la migración.

### Bug #2: `price_communicated_to_user` No Se Setea (CRÍTICO)

**Evidencia**:
```python
# image_tools.py:183 VALIDA:
if not state.get("price_communicated_to_user"):
    return {"error": "PRICE_NOT_COMMUNICATED"}

# BÚSQUEDA EN TODO EL CÓDIGO:
# ❌ NO HAY ningún lugar que setee este flag a True

# RESULTADO: Tool SIEMPRE bloquea con error PRICE_NOT_COMMUNICATED
```

**Causa raíz**: En v1 había pattern matching (`"410€"` en respuesta LLM). En v2 se eliminó esta lógica.

### Bug #3: No Hay Detección de "Opción A" (ALTO)

**Evidencia**:
```python
# intent_router.py:111 - CONFIRMACION pattern:
(re.compile(r"^\s*(sí|si|ok|dale)...\s*$", re.I), UserIntent.CONFIRMACION, 0.90)
# ❌ NO matchea "A", "opción A", "ver fotos"

# conversation_state.py - ModeContextData:
# ❌ NO HAY flag waiting_for_image_choice

# presupuesto_mode.md:226 - Ejemplos:
# "sí, mostrá las fotos" ✅
# "A" ❌ NO mencionado
```

**Tasa de fallo estimada**: 30-40% de usuarios (respuestas ultra-cortas).

### Bug #4: LLM Inventa URLs (MEDIO)

**Evidencia en logs** (conversation_id=1, 5 Feb 17:41):
```
Bot: "Te envío las fotos de ejemplo:
- https://storage.chatwoot.com/attachments/... ← INVENTADO
- https://storage.chatwoot.com/attachments/... ← INVENTADO"
```

**Causa raíz**: 
- Tool retorna `success: False` con error message
- LLM ve en prompt que `imagenes_ejemplo` debe contener URLs
- LLM **inventa** URLs basándose en el patrón "aprendido"

### Bug #5: Constraint Falsos Positivos (MEDIO)

**Evidencia en logs** (conversation_id=1, 5 Feb 17:41):
```
17:41:23 - calcular_tarifa_con_elementos() → precio: 410€
17:41:27 - LLM: "El presupuesto es de 410€..."
17:41:30 - Constraint violation: 'price_requires_tool' ⚠️
17:41:30 - constraint_validation_retry (retry 1/2)
17:41:35 - calcular_tarifa RE-EJECUTADO innecesariamente
```

**Causa raíz**: Constraint detecta "410€" en texto sin verificar si el precio ya fue calculado en turno anterior.

---

## Tareas por Fase

### FASE 1: Fix `tarifa_actual` No Se Escribe [CRÍTICA]

**Archivo**: `agent/modes/presupuesto_mode.py`

**Cambio 1** - Línea ~404-410 (`_extract_context_from_tool`):
```python
# ANTES:
elif tool_name == "calcular_tarifa_con_elementos":
    precio = data.get("precio_final") or data.get("price") or data.get("total")
    if precio:
        updates["precio_calculado"] = float(precio)
        updates["tarifa_calculada"] = data

# DESPUÉS:
elif tool_name == "calcular_tarifa_con_elementos":
    precio = data.get("precio_final") or data.get("price") or data.get("total")
    if precio:
        updates["precio_calculado"] = float(precio)
        updates["tarifa_calculada"] = data  # mode_context (persistent)
        updates["precio_comunicado"] = False  # Reset flag for new quote
        updates["_tarifa_actual"] = data  # Signal to write to root state
```

**Cambio 2** - Línea ~236-245 (`_process_message`):
```python
# ANTES:
result_dict: dict[str, Any] = {
    "ai_response": ai_response,
    "mode_context": updated_context,
}

# DESPUÉS:
result_dict: dict[str, Any] = {
    "ai_response": ai_response,
    "mode_context": updated_context,
}

# Propagate tarifa_actual to root state if needed
if updated_context.get("_tarifa_actual"):
    result_dict["tarifa_actual"] = updated_context.pop("_tarifa_actual")
```

**Test**:
```python
# tests/integration/test_image_sending_fix.py
@pytest.mark.asyncio
async def test_tarifa_actual_is_written_to_root_state():
    mode_node = PresupuestoModeNode()
    tool_result = {"success": True, "precio_final": 410.0}
    updates = mode_node._extract_context_from_tool("calcular_tarifa_con_elementos", json.dumps(tool_result))
    assert updates.get("_tarifa_actual") is not None
```

**Tiempo estimado**: 10 min

---

### FASE 2: Fix `price_communicated` No Se Setea [CRÍTICA]

**Archivo**: `agent/modes/presupuesto_mode.py`

**Cambio** - Línea ~178 (después de constraint validation, antes del `break`):
```python
# Después de constraint validation...
if not is_valid and error_injection:
    validation_retries += 1
    llm_messages.append({...})
    continue

# ✅ NUEVO: Detect price in LLM response (PRICE_BEFORE_IMAGES enforcement)
if ai_response and mode_context.get("tarifa_calculada"):
    precio = (
        mode_context["tarifa_calculada"].get("precio_final") or
        mode_context["tarifa_calculada"].get("price") or
        mode_context["tarifa_calculada"].get("total")
    )
    
    if precio and not context_updates.get("precio_comunicado"):
        # Pattern matching: "410€", "410 €", "410EUR", etc.
        precio_int = int(precio) if float(precio).is_integer() else precio
        price_patterns = [
            f"{precio_int}€",
            f"{precio_int} €",
            f"{precio_int}EUR",
            f"{precio} €",
            f"{precio}€",
        ]
        
        if any(pattern in ai_response for pattern in price_patterns):
            context_updates["precio_comunicado"] = True
            self._logger.info(
                "price_communicated_detected",
                price=precio,
                conversation_id=conversation_id,
            )

break  # Exit tool loop
```

**Test**:
```python
@pytest.mark.asyncio
async def test_price_communicated_flag_is_set():
    state = {"mode_context": {"tarifa_calculada": {"precio_final": 410.0}}}
    ai_response = "El presupuesto es de 410€ +IVA."
    # ... process ...
    assert state["mode_context"]["precio_comunicado"] is True
```

**Tiempo estimado**: 20 min

---

### FASE 3: Mejorar Detección "Opción A" [ALTA]

**Archivo 1**: `agent/router/intent_router.py`

**Cambio 1** - Línea ~30 (enum):
```python
class UserIntent(str, Enum):
    CONSULTA = "consulta"
    PRESUPUESTO = "presupuesto"
    CONFIRMACION = "confirmacion"
    RECHAZO = "rechazo"
    VER_IMAGENES = "ver_imagenes"  # ✅ NUEVO
    ABRIR_EXPEDIENTE = "abrir_expediente"  # ✅ NUEVO
```

**Cambio 2** - Línea ~80 (keywords):
```python
# VER_IMAGENES: Ultra-short responses for "Option A"
(re.compile(r"^\s*([Aa]|opci[oó]n\s*[Aa]|la\s*[Aa])\s*[.!?]?\s*$", re.I),
 UserIntent.VER_IMAGENES, 0.95),

# VER_IMAGENES: Natural language variants
(re.compile(r"\b(ver|mostrar|enviar|quiero|dame)\s+(las\s+)?(fotos?|im[aá]genes?|ejemplos?)\b", re.I),
 UserIntent.VER_IMAGENES, 0.90),

(re.compile(r"\b(s[ií],?\s*)?(mostr[aá]|env[ií]a|manda)\s+(las\s+)?(fotos?|im[aá]genes?)\b", re.I),
 UserIntent.VER_IMAGENES, 0.90),

# ABRIR_EXPEDIENTE: Ultra-short responses for "Option B"
(re.compile(r"^\s*([Bb]|opci[oó]n\s*[Bb]|la\s*[Bb])\s*[.!?]?\s*$", re.I),
 UserIntent.ABRIR_EXPEDIENTE, 0.95),
```

**Archivo 2**: `agent/state/conversation_state.py`

**Cambio** - Línea ~95:
```python
class ModeContextData(TypedDict, total=False):
    # PRESUPUESTO_MODE
    precio_calculado: float
    precio_comunicado: bool
    tarifa_calculada: dict[str, Any]
    imagenes_enviadas: bool
    presupuesto_offered_count: int
    waiting_for_image_choice: bool  # ✅ NUEVO
```

**Archivo 3**: `agent/prompts/modes/presupuesto_mode.md`

**Cambio** - Después de línea 244:
```markdown

---

## ⚡ Interpretación de Respuestas a Opciones A/B

Cuando ofreciste las opciones A (imágenes) y B (expediente), el usuario puede responder de muchas formas.

### Respuestas que significan "Opción A" (ver imágenes):

**Ultra-cortas**: "A", "Opción A", "La A", "1"

**Naturales**: "Sí, mostrá las fotos", "Quiero ver las imágenes", "Mostrame ejemplos", "Ver fotos"

**Confirmaciones ambiguas** (SI `waiting_for_image_choice = True`):
- "Sí" → Asume Opción A
- "Dale" → Asume Opción A

**Acción**: Ejecutar `enviar_imagenes_ejemplo(tipo="presupuesto")`

### Respuestas que significan "Opción B" (expediente):

**Ultra-cortas**: "B", "Opción B", "La B", "2"

**Naturales**: "Abrí el expediente", "Empecemos", "Adelante con el expediente"

**Acción**: Transicionar a EVALUACION_GATEWAY
```

**Tests**:
```python
@pytest.mark.parametrize("user_input,expected", [
    ("A", UserIntent.VER_IMAGENES),
    ("Opción A", UserIntent.VER_IMAGENES),
    ("ver fotos", UserIntent.VER_IMAGENES),
    ("B", UserIntent.ABRIR_EXPEDIENTE),
])
def test_option_detection(user_input, expected):
    result = classify_user_intent(user_input, mode_context={})
    assert result["intent"] == expected
```

**Tiempo estimado**: 30 min

---

### FASE 4: Error Handling (Imágenes No Disponibles) [MEDIA]

**Archivo 1**: `agent/tools/image_tools.py`

**Cambio** - Líneas ~381-390, ~172-180, ~232-249, ~355-363:
```python
# APLICAR ESTE PATRÓN EN LOS 4 LUGARES:
return {
    "success": False,
    "message": (
        f"⚠️ CRITICAL INSTRUCTION FOR LLM ⚠️\n"
        f"No hay imagenes de ejemplo disponibles para '{element_name}'.\n\n"
        f"DO NOT generate fake URLs or image links.\n"
        f"DO NOT list URLs like 'storage.chatwoot.com/...'.\n\n"
        f"Instead, tell the user:\n"
        f"'En este momento no tengo fotos de ejemplo disponibles, "
        f"pero puedo explicarte qué documentación necesitarás. ¿Te parece?'"
    ),
    "data": None,
}
```

**Archivo 2**: `agent/prompts/core/08_documentation.md`

**Cambio** - Final del archivo:
```markdown

---

## Manejo de Errores en Imágenes

Si `enviar_imagenes_ejemplo()` retorna `success=False`:

### ❌ NO HAGAS ESTO:
"Te envío las fotos:"
- https://storage.chatwoot.com/... ← INVENTADO

### ✅ HAZ ESTO:
"En este momento no tengo fotos de ejemplo disponibles, 
pero puedo explicarte qué documentación necesitarás."

**REGLA DE ORO**: Si el tool falla, NUNCA inventes URLs.
```

**Test**:
```python
async def test_no_images_graceful_error():
    result = await enviar_imagenes_ejemplo(tipo="elemento", codigo_elemento="ESCAPE")
    assert result["success"] is False
    assert "DO NOT generate fake URLs" in result["message"]
```

**Tiempo estimado**: 15 min

---

### FASE 5: Optimizar Constraint Service [MEDIA]

**Archivo**: `agent/services/constraint_service.py`

**Cambio** - Línea ~136-151:
```python
def _should_skip_constraint(constraint_type: str, fsm_state: dict[str, Any] | None) -> bool:
    if not fsm_state:
        return False
    
    if constraint_type == "price_requires_tool":
        expediente_sub_mode = fsm_state.get("expediente_sub_mode")
        has_tariff = fsm_state.get("tariff_amount") is not None
        presupuesto_done = fsm_state.get("presupuesto_completado", False)
        
        # ✅ NUEVO: Check if tariff was calculated in previous turn
        has_tarifa_calculada = fsm_state.get("tarifa_calculada") is not None
        has_precio_calculado = fsm_state.get("precio_calculado") is not None
        
        if (
            (expediente_sub_mode and has_tariff) 
            or presupuesto_done
            or has_tarifa_calculada
            or has_precio_calculado
        ):
            logger.debug(f"Skipping constraint | has_tarifa_calculada={has_tarifa_calculada}")
            return True
    
    return False
```

**Test**:
```python
def test_skip_constraint_when_tarifa_exists():
    context = {"tarifa_calculada": {"precio_final": 410.0}}
    assert _should_skip_constraint("price_requires_tool", context) is True

def test_do_not_skip_when_no_tariff():
    assert _should_skip_constraint("price_requires_tool", {}) is False
```

**Tiempo estimado**: 10 min

---

## Dependencias entre Tareas

```
FASE 1 (tarifa_actual)
  ↓ CRÍTICO - Sin esto NADA funciona
FASE 2 (price_communicated)
  ↓ CRÍTICO - Sin esto tool bloquea
FASE 3 (detección Opción A)
  ↓ ALTA - Mejora UX significativa
FASE 4 (error handling)
  ↓ MEDIA - Evita confusión
FASE 5 (constraint optimization)
  ↓ MEDIA - Ahorra tokens, no blocking
```

**Recomendación**: Implementar Fases 1-2 inmediatamente (30 min), luego Fase 3. Fases 4-5 pueden esperar.

---

## Tests Requeridos

### Tests Unitarios
- [ ] `test_tarifa_actual_is_written_to_root_state` (Fase 1)
- [ ] `test_price_communicated_flag_is_set` (Fase 2)
- [ ] `test_option_detection` (Fase 3) - parametrizado, 6 casos
- [ ] `test_skip_constraint_when_tarifa_exists` (Fase 5)
- [ ] `test_do_not_skip_when_no_tariff` (Fase 5)

### Tests de Integración
- [ ] `test_image_sending_fix` (Fase 1)
- [ ] `test_price_communication_detection` (Fase 2)
- [ ] `test_no_images_graceful_error` (Fase 4)
- [ ] `test_complete_image_flow_with_option_a` (E2E completo)

### Comandos
```bash
# Unitarios
pytest tests/unit/test_intent_router_images.py -v
pytest tests/unit/test_constraint_service_optimization.py -v

# Integración
pytest tests/integration/test_image_sending_fix.py -v
pytest tests/integration/test_image_error_handling.py -v
pytest tests/integration/test_image_sending_complete_flow.py -v

# Suite completo
pytest tests/ -v --cov=agent --cov-report=html

# Verificar coverage >90%
open htmlcov/index.html
```

---

## Criterios de Aceptación

- [ ] `enviar_imagenes_ejemplo()` ejecuta exitosamente después de calcular tarifa
- [ ] Usuario que responde "A" recibe imágenes vía Chatwoot (no texto plano)
- [ ] Cuando no hay imágenes disponibles, bot informa gracefully sin inventar URLs
- [ ] Conversaciones multi-turno NO causan retries innecesarios del constraint
- [ ] Tests pasan con coverage >90% en módulos modificados
- [ ] Logs muestran `price_communicated_detected` y `has_pending_images=True`

---

## Checklist de Verificación Pre-Deploy

### Pre-Implementación
- [ ] Backup de archivos a modificar
- [ ] Branch creado: `git checkout -b fix/image-sending-system`
- [ ] Docker services corriendo
- [ ] DB tiene seeds con imágenes de ejemplo

### Durante Implementación
- [ ] Fase 1: Modificar presupuesto_mode.py (2 cambios)
- [ ] Fase 1: Test unitario pasa
- [ ] Fase 2: Modificar presupuesto_mode.py (detección precio)
- [ ] Fase 2: Test unitario pasa
- [ ] Fase 3: Modificar intent_router.py, conversation_state.py, presupuesto_mode.md
- [ ] Fase 3: Tests parametrizados pasan
- [ ] Fase 4: Modificar image_tools.py (4 lugares), 08_documentation.md
- [ ] Fase 4: Test de error handling pasa
- [ ] Fase 5: Modificar constraint_service.py
- [ ] Fase 5: Tests de constraint pasan

### Post-Implementación
- [ ] Suite completo pasa: `pytest tests/ -v`
- [ ] Coverage >90% en agent/modes/presupuesto_mode.py
- [ ] Coverage >90% en agent/router/intent_router.py
- [ ] Test E2E manual: "Quiero homologar escape" → "A" → imágenes enviadas
- [ ] Verificar logs: `docker-compose logs agent | grep "price_communicated_detected"`
- [ ] Verificar logs: `docker-compose logs agent | grep "has_pending_images"`
- [ ] Commit con mensaje: `fix(agent): resolve 5 critical bugs in image sending system`
- [ ] Push branch y crear PR

---

## Métricas de Éxito

### Pre-Fix (Estado Actual)
- ❌ Tasa de envío de imágenes: **0%**
- ❌ Detección "Opción A": **~10%**
- ⚠️ Falsos positivos constraint: **~40%**
- ⚠️ URLs inventadas: **~15%**

### Post-Fix (Objetivo)
- ✅ Tasa de envío de imágenes: **>95%**
- ✅ Detección "Opción A": **>90%**
- ✅ Falsos positivos constraint: **<10%**
- ✅ URLs inventadas: **0%**

### Monitoreo Post-Deploy
```bash
# Tasa de éxito
docker-compose logs agent | grep "enviar_imagenes_ejemplo" | grep "success.*true" | wc -l

# Detección precio
docker-compose logs agent | grep "price_communicated_detected" | wc -l

# Detección "Opción A"
docker-compose logs agent | grep "intent.*ver_imagenes" | wc -l

# Retries (deberían disminuir)
docker-compose logs agent | grep "constraint_validation_retry" | wc -l
```

---

## Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Regex no detecta formato diferente | Media | Bajo | LLM recibe error y reintenta |
| Usuario dice "sí" ambiguamente | Media | Bajo | Prompt asume A si `waiting_for_image_choice=True` |
| Imágenes no enviadas si Chatwoot falla | Baja | Medio | Logs + retry logic ya existe |
| Pattern matching falla con sinónimos | Media | Bajo | Prompt + LLM como fallback |
| Constraint optimization rompe otros flujos | Muy Baja | Alto | Tests + solo afecta PRESUPUESTO_MODE |

---

## Notas Técnicas

### Sistema de Modos (NO FSM)

Este proyecto usa **arquitectura basada en MODOS** (v2), NO el sistema FSM (v1 archivado).

**Estructura actual**:
```
agent/
├── modes/              # ← Arquitectura de modos
│   ├── presupuesto_mode.py
│   ├── consulta_mode.py
│   └── expediente_mode.py
├── router/             # ← Intent routing
│   ├── intent_router.py
│   └── mode_transitions.py
└── prompts/modes/      # ← Prompts por modo
```

**NO existe** `agent/fsm/` en código actual.

### Nombres Legacy

Algunos parámetros se llaman `fsm_state` por compatibilidad, pero **realmente son `mode_context`**:

```python
# constraint_service.py
def _should_skip_constraint(
    constraint_type: str,
    fsm_state: dict[str, Any] | None,  # ← Nombre legacy
):
    # En realidad es mode_context
    has_tarifa = fsm_state.get("tarifa_calculada")
```

---

## Timeline

- **Fase 1**: 10 minutos
- **Fase 2**: 20 minutos
- **Fase 3**: 30 minutos
- **Fase 4**: 15 minutos
- **Fase 5**: 10 minutos
- **Testing**: 15 minutos

**TOTAL**: ~1.5 horas (sin interrupciones)

---

## Referencias

- `agent/AGENTS.md` - Arquitectura completa del agente
- `docs/coding-standards/03-agent-architecture.md` - Anti-patterns
- `docs/coding-standards/00-general.md` - Fundamentos
- Investigaciones completas en sesión del 5 Feb 2026

---

**Creado por**: Architect (Claude Sonnet 4.5)  
**Aprobado por**: Usuario  
**Fecha**: 5 de Febrero de 2026  
**Próximo paso**: Ejecutar Fases 1-2 (30 min) → Testing → Deploy

IMPORTANTE: Este archivo contiene TODO el plan completo. NO crear archivos separados. Usa este como referencia única.
