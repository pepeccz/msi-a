# Plan: Fix Tool Flags Bug (CRITICAL)

**Fecha**: 2026-02-06  
**Severidad**: CRÍTICA  
**Impacto**: Rompe protección PRECIO_BEFORE_IMAGES  
**Tiempo estimado**: 1h 20min

---

## Resumen Ejecutivo

**Problema**: `_apply_tool_flags()` recibe STRING (JSON) en vez de DICT, causando que los flags internos (`precio_comunicado`, `imagenes_enviadas`) nunca se apliquen correctamente.

**Causa raíz**: `_execute_and_log_tool()` retorna STRING (vía `_execute_tool()` → `json.dumps()`), pero `_apply_tool_flags()` espera DICT con método `.get()`.

**Alcance**: 
- ✅ **presupuesto_mode.py** - USO CONFIRMADO en línea 312
- ❌ **consulta_mode.py** - NO USA `_apply_tool_flags()`
- ❌ **expediente_mode.py** - NO USA `_apply_tool_flags()`
- ✅ **Tests existentes** - `test_tool_flag_contract.py` (249 líneas)

---

## Fase 1: Investigación (15 min)

### 1.1 Confirmar Alcance Exacto
**Tiempo**: 5 min  
**Objetivo**: Verificar qué archivos están afectados

- [x] Buscar todos los usos de `_apply_tool_flags()` ✅ Solo en presupuesto_mode.py
- [x] Buscar todos los usos de `_execute_and_log_tool()` ✅ En 3 modos (consulta, expediente, presupuesto)
- [x] Verificar si otros modos tienen helpers similares ✅ NO tienen
- [x] Buscar patrón `json.loads(result)` en otros modos ✅ Encontrado en presupuesto_mode.py (2 lugares) y expediente_mode.py (2 lugares)

**Resultado**: 
- Bug SOLO afecta `presupuesto_mode.py` línea 312
- Otros modos NO usan `_apply_tool_flags()` → NO afectados
- Patrón `json.loads(result)` ya existe en `_extract_context_from_tool()` → solución conocida

### 1.2 Verificar Retorno de `_execute_and_log_tool()`
**Tiempo**: 5 min  
**Objetivo**: Confirmar que retorna STRING

```python
# agent/modes/base_mode.py:361
async def _execute_and_log_tool(...) -> str:  # ← RETORNA STRING
    start = _time.time()
    result = await self._execute_tool(tool_name, tool_args, tools)  # ← Ya es STRING
    elapsed_ms = int((_time.time() - start) * 1000)
    
    # ... logging ...
    
    return result  # ← STRING (porque _execute_tool retorna STRING)
```

```python
# agent/modes/base_mode.py:315
# En _execute_tool():
return _json.dumps(result, ensure_ascii=False)  # ← Convierte a STRING
```

**Confirmación**: `_execute_and_log_tool()` retorna STRING (JSON serializado).

### 1.3 Revisar Tests Existentes
**Tiempo**: 5 min  
**Objetivo**: Verificar cobertura de tool flags

```bash
# Buscar tests de tool flags
rg "test.*flag" tests/ --type py -l

# Ejecutar tests existentes
pytest tests/unit/test_tool_flag_contract.py -v
```

**Archivos a revisar**:
- `tests/unit/test_tool_flag_contract.py` (249 líneas)

**Resultado esperado**: 
- ✅ Tests existen pero PASAN porque usan DICT directamente
- ❌ NO cubren el caso real (STRING desde `_execute_and_log_tool()`)

**Comandos de verificación**:
```bash
cd /home/autohomologacion/msi-a
pytest tests/unit/test_tool_flag_contract.py::test_precio_comunicado_set_via_tool_flags -xvs
```

---

## Fase 2: Fix Inmediato (30 min)

### 2.1 Fix en `presupuesto_mode.py`
**Tiempo**: 10 min  
**Archivo**: `agent/modes/presupuesto_mode.py`  
**Líneas afectadas**: 312, 98

**Cambios**:

```python
# ANTES (línea 312):
result = await self._execute_and_log_tool(...)  # STRING
_apply_tool_flags(mode_context, result, self._logger)  # ❌ Falla porque result es STRING

# DESPUÉS (línea 312):
result = await self._execute_and_log_tool(...)  # STRING
result_dict = json.loads(result) if isinstance(result, str) else result  # Parse JSON
_apply_tool_flags(mode_context, result_dict, self._logger)  # ✅ Ahora es DICT
```

**Alternativa defensive en `_apply_tool_flags()`**:

```python
# ANTES (línea 95-98):
def _apply_tool_flags(
    mode_context: dict,
    tool_result: dict,  # ❌ Type hint dice DICT pero recibe STRING
    logger: Any,
) -> None:
    if not isinstance(tool_result, dict):
        return
    
    flags = tool_result.get("_internal_flags", {})  # ❌ STRING no tiene .get()

# DESPUÉS (línea 95-98):
def _apply_tool_flags(
    mode_context: dict,
    tool_result: dict | str,  # ✅ Acepta ambos tipos
    logger: Any,
) -> None:
    # Parse JSON if needed
    if isinstance(tool_result, str):
        try:
            tool_result = json.loads(tool_result)
        except json.JSONDecodeError:
            logger.warning("apply_tool_flags_invalid_json", tool_result=tool_result[:100])
            return
    
    if not isinstance(tool_result, dict):
        return
    
    flags = tool_result.get("_internal_flags", {})  # ✅ Ahora tool_result es DICT
```

**Decisión**: Aplicar AMBOS cambios (defensive programming):
1. Parse en el caller (línea 312) → explicit
2. Parse en la función (línea 95-110) → defensive

**Criterio de éxito**:
```bash
# Test manual
python -c "
from agent.modes.presupuesto_mode import _apply_tool_flags
import structlog
import json

logger = structlog.get_logger()
mode_context = {'precio_comunicado': False}

# Simular STRING (caso real)
tool_result_str = json.dumps({
    'success': True,
    'precio_final': 410.0,
    '_internal_flags': {'precio_comunicado': True}
})

_apply_tool_flags(mode_context, tool_result_str, logger)
assert mode_context['precio_comunicado'] is True, 'Flag NOT applied!'
print('✅ Flag applied correctly from STRING')
"
```

### 2.2 Agregar Type Hints Explícitos
**Tiempo**: 5 min  
**Archivo**: `agent/modes/presupuesto_mode.py`

```python
# Importar typing si no existe
from typing import Any
import json

# Actualizar firma de _apply_tool_flags
def _apply_tool_flags(
    mode_context: dict[str, Any],
    tool_result: dict[str, Any] | str,  # ✅ Acepta ambos
    logger: Any,
) -> None:
    """
    Apply _internal_flags from tool result to mode_context.
    
    This is the NEW pattern for explicit state management:
    - Tools declare state changes in their return value
    - Mode applies those changes atomically
    - Changes are persisted via ConversationState
    
    Args:
        mode_context: Current mode context (will be modified in-place)
        tool_result: Tool return value with optional _internal_flags.
                     Can be dict or JSON string (will be parsed).
        logger: Logger instance for debugging
    """
```

**Criterio de éxito**: Mypy no reporta errores de tipo.

```bash
mypy agent/modes/presupuesto_mode.py --ignore-missing-imports
```

### 2.3 Verificar Otros Usos de `_extract_context_from_tool()`
**Tiempo**: 10 min  
**Objetivo**: Confirmar que otros modos usan el patrón correcto

**Archivos a revisar**:
- `agent/modes/presupuesto_mode.py` líneas 491, 575
- `agent/modes/expediente_mode.py` líneas 597, 663

```python
# Patrón CORRECTO ya existente:
data = json.loads(result) if isinstance(result, str) else result

# Verificar que se usa en todos los lugares
```

**Comandos de verificación**:
```bash
rg "json\.loads\(result\)" agent/modes/ -A 2 -B 2
rg "_extract_context_from_tool" agent/modes/ -A 5 -B 2
```

**Criterio de éxito**: 
- ✅ Todos los usos de `_extract_context_from_tool()` parsean el resultado
- ✅ No hay otros lugares donde se pase STRING esperando DICT

### 2.4 Documentar el Patrón
**Tiempo**: 5 min  
**Archivo**: `agent/modes/presupuesto_mode.py`

**Agregar comentario en línea 312**:

```python
# REFACTOR-001 Phase 2: Parse tool result before applying flags
# _execute_and_log_tool() returns STRING (JSON serialized)
# but _apply_tool_flags() expects DICT
result = await self._execute_and_log_tool(...)
result_dict = json.loads(result) if isinstance(result, str) else result
_apply_tool_flags(mode_context, result_dict, self._logger)
```

**Agregar a docstring de `_apply_tool_flags()`**:

```python
def _apply_tool_flags(...) -> None:
    """
    ...
    
    NOTE: This function accepts both dict and JSON string for tool_result.
    If a string is passed, it will be parsed as JSON automatically.
    This defensive approach prevents bugs when _execute_and_log_tool()
    returns serialized JSON instead of a dict object.
    
    Example:
        # Both work:
        _apply_tool_flags(ctx, {"_internal_flags": {"precio_comunicado": True}}, logger)
        _apply_tool_flags(ctx, '{"_internal_flags": {"precio_comunicado": true}}', logger)
    """
```

---

## Fase 3: Prevención (20 min)

### 3.1 Crear Test de Integración
**Tiempo**: 10 min  
**Archivo**: `tests/unit/test_tool_flag_contract.py`

**Agregar test nuevo**:

```python
@pytest.mark.asyncio
@pytest.mark.unit
async def test_apply_tool_flags_accepts_json_string():
    """
    REGRESSION TEST: Verify _apply_tool_flags handles JSON string input.
    
    This test prevents the bug where _execute_and_log_tool() returns STRING
    but _apply_tool_flags() expects DICT.
    
    Bug context:
    - _execute_and_log_tool() → calls _execute_tool() → json.dumps() → STRING
    - _apply_tool_flags() → expects DICT with .get() method
    - Result: flags never applied, precio_comunicado stays False
    
    Fix: _apply_tool_flags() now parses JSON strings automatically.
    """
    from agent.modes.presupuesto_mode import _apply_tool_flags
    import structlog
    import json
    
    logger = structlog.get_logger()
    
    # Setup: mode_context with precio_comunicado=False
    mode_context = {
        "precio_comunicado": False,
        "imagenes_enviadas": False,
        "conversation_id": "test-123",
    }
    
    # Simulate REAL scenario: tool result as JSON STRING
    # (this is what _execute_and_log_tool() actually returns)
    tool_result_string = json.dumps({
        "success": True,
        "precio_final": 410.0,
        "_internal_flags": {
            "precio_comunicado": True,
            "imagenes_enviadas": False,
        }
    })
    
    # Apply flags (should parse JSON automatically)
    _apply_tool_flags(mode_context, tool_result_string, logger)
    
    # VERIFY: Flags were applied despite STRING input
    assert mode_context["precio_comunicado"] is True, \
        "precio_comunicado should be set even when tool_result is JSON string"
    assert mode_context["imagenes_enviadas"] is False, \
        "imagenes_enviadas should be set even when tool_result is JSON string"
    
    print("✅ _apply_tool_flags correctly handles JSON string input")
    print("   - Parsed JSON string automatically")
    print("   - Applied flags to mode_context")
    print("   - REGRESSION BUG PREVENTED")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_apply_tool_flags_handles_invalid_json():
    """
    EDGE CASE: Verify _apply_tool_flags handles malformed JSON gracefully.
    """
    from agent.modes.presupuesto_mode import _apply_tool_flags
    import structlog
    
    logger = structlog.get_logger()
    
    mode_context = {"precio_comunicado": False}
    
    # Invalid JSON
    invalid_json = "not a valid json string"
    
    # Should not crash
    _apply_tool_flags(mode_context, invalid_json, logger)
    
    # Should not modify context
    assert mode_context["precio_comunicado"] is False, \
        "Invalid JSON should not modify context"
    
    print("✅ _apply_tool_flags handles invalid JSON gracefully")
```

**Criterio de éxito**:
```bash
pytest tests/unit/test_tool_flag_contract.py::test_apply_tool_flags_accepts_json_string -xvs
pytest tests/unit/test_tool_flag_contract.py::test_apply_tool_flags_handles_invalid_json -xvs
```

### 3.2 Documentar en ADR
**Tiempo**: 5 min  
**Archivo**: `docs/decisions/005-tool-driven-state-management.md`

**Agregar sección "Known Issues & Fixes"**:

```markdown
## Known Issues & Fixes

### Issue 1: _apply_tool_flags receives STRING instead of DICT (Fixed 2026-02-06)

**Problem**: `_execute_and_log_tool()` returns JSON string, but `_apply_tool_flags()` 
expected dict, causing flags to never be applied.

**Impact**: CRITICAL - `precio_comunicado` and `imagenes_enviadas` flags were never set,
breaking the PRECIO_BEFORE_IMAGES protection.

**Root cause**: 
- `_execute_and_log_tool()` → `_execute_tool()` → `json.dumps()` → STRING
- `_apply_tool_flags()` → `tool_result.get("_internal_flags")` → CRASH (str has no .get())

**Fix**: Made `_apply_tool_flags()` defensive:
1. Accept `dict | str` type hint
2. Auto-parse JSON if string
3. Gracefully handle invalid JSON

**Prevention**: Added regression test `test_apply_tool_flags_accepts_json_string()`

**Files changed**:
- `agent/modes/presupuesto_mode.py` (lines 95-112, 312)
- `tests/unit/test_tool_flag_contract.py` (new tests added)
```

### 3.3 Actualizar AGENTS.md
**Tiempo**: 5 min  
**Archivo**: `agent/AGENTS.md`

**Actualizar sección "Critical Rules"**:

```markdown
## Critical Rules

1. **NEVER re-identify after variant question** — Use `seleccionar_variante_por_respuesta()`, not `identificar_y_resolver_elementos()`
2. **PRICE BEFORE IMAGES** — `enviar_imagenes_ejemplo` blocks if price not mentioned first
3. **Skip validation after ID** — Always use `skip_validation=True` in `calcular_tarifa_con_elementos()` after identification
4. **Exact field_key** — Use exact `field_key` from `obtener_campos_elemento()` in `guardar_datos_elemento()`
5. **No hardcoded flow** — LLM decides, system prompt guides (not Python logic)
6. **Async everywhere** — All I/O operations use `async def`
7. **Mode context updates** — Tools return updates, nodes apply them to `mode_context`
8. **Tool flags explicit** — Tools declare state changes via `_internal_flags`, NOT pattern matching (REFACTOR-001)
9. **NEW: Parse tool results** — `_execute_and_log_tool()` returns STRING (JSON), always parse with `json.loads()` before using as dict
```

**Agregar sección "Tool Result Parsing Pattern"**:

```markdown
## Tool Result Parsing Pattern

`_execute_and_log_tool()` returns **JSON string**, not dict. Always parse before use:

```python
# ✅ CORRECT
result = await self._execute_and_log_tool(...)  # → STRING
result_dict = json.loads(result) if isinstance(result, str) else result
_apply_tool_flags(mode_context, result_dict, logger)  # → DICT

# ❌ WRONG
result = await self._execute_and_log_tool(...)  # → STRING
_apply_tool_flags(mode_context, result, logger)  # → CRASH (str.get() fails)
```

**Defensive helper**:
`_apply_tool_flags()` now auto-parses JSON strings, but explicit parsing at call site is preferred for clarity.
```

---

## Fase 4: Verificación (15 min)

### 4.1 Test Unitario
**Tiempo**: 5 min

```bash
cd /home/autohomologacion/msi-a

# Run all tool flag tests
pytest tests/unit/test_tool_flag_contract.py -xvs

# Expected output:
# ✅ test_calcular_tarifa_returns_internal_flags PASSED
# ✅ test_extraction_handles_missing_internal_flags PASSED
# ✅ test_precio_comunicado_set_via_tool_flags PASSED
# ✅ test_internal_flags_schema PASSED
# ✅ test_tarifa_actual_content_requirements PASSED
# ✅ test_apply_tool_flags_accepts_json_string PASSED (NEW)
# ✅ test_apply_tool_flags_handles_invalid_json PASSED (NEW)
```

### 4.2 Test de Integración con Conversación Real
**Tiempo**: 5 min

**Objetivo**: Verificar que los flags se aplican correctamente en una conversación real.

```bash
# Start agent in test mode
python -c "
import asyncio
from agent.modes.presupuesto_mode import PresupuestoModeNode
from agent.state.conversation_state import ConversationState

async def test_real_conversation():
    mode = PresupuestoModeNode()
    
    state = {
        'conversation_id': 'test-real-123',
        'current_mode': 'PRESUPUESTO_MODE',
        'mode_context': {
            'categoria_slug': 'motos-part',
            'precio_comunicado': False,
            'imagenes_enviadas': False,
        },
        'messages': [
            {'role': 'user', 'content': 'Quiero homologar el escape de mi moto'}
        ],
    }
    
    # Process message (this will call tools and apply flags)
    result = await mode.process(state)
    
    # Verify flags were applied
    mode_context = result.get('mode_context', {})
    print(f'precio_comunicado: {mode_context.get(\"precio_comunicado\")}')
    print(f'imagenes_enviadas: {mode_context.get(\"imagenes_enviadas\")}')
    
    assert mode_context.get('precio_comunicado') is True, 'Flag NOT applied!'
    print('✅ Flags applied correctly in real conversation')

asyncio.run(test_real_conversation())
"
```

### 4.3 Verificar Checkpoints en Redis
**Tiempo**: 5 min

**Objetivo**: Confirmar que los flags persisten en Redis.

```bash
# Connect to Redis
docker-compose exec redis redis-cli

# Find conversation checkpoint
KEYS langgraph:*test-real-123*

# Get checkpoint data
GET langgraph:checkpoint:test-real-123

# Should contain:
# {
#   "mode_context": {
#     "precio_comunicado": true,
#     "imagenes_enviadas": false
#   }
# }
```

**Alternativa con script Python**:

```python
import asyncio
from agent.state.checkpointer import get_redis_checkpointer

async def verify_checkpoint():
    checkpointer = get_redis_checkpointer()
    
    # Get checkpoint for test conversation
    checkpoint = await checkpointer.aget({
        'configurable': {'thread_id': 'test-real-123'}
    })
    
    if checkpoint:
        mode_context = checkpoint.get('channel_values', {}).get('mode_context', {})
        print(f'precio_comunicado: {mode_context.get("precio_comunicado")}')
        print(f'imagenes_enviadas: {mode_context.get("imagenes_enviadas")}')
        
        assert mode_context.get('precio_comunicado') is True
        print('✅ Checkpoint persisted correctly')
    else:
        print('❌ Checkpoint not found')

asyncio.run(verify_checkpoint())
```

---

## Criterios de Éxito Global

### Must Have (Bloqueantes)
- [ ] `_apply_tool_flags()` acepta STRING y lo parsea correctamente
- [ ] `_apply_tool_flags()` acepta DICT directamente (backward compat)
- [ ] Tests unitarios PASAN (incluyendo nuevos tests de regresión)
- [ ] Type hints actualizados (`dict | str`)
- [ ] Flags se aplican correctamente en conversación real
- [ ] Flags persisten en Redis checkpoint

### Should Have (Recomendados)
- [ ] Documentación actualizada en ADR-005
- [ ] AGENTS.md actualizado con nuevo patrón
- [ ] Comentarios explicativos en código

### Nice to Have (Opcionales)
- [ ] Test de integración con Chatwoot (end-to-end)
- [ ] Verificar que NO hay otros usos de pattern matching para flags

---

## Rollout Plan

### Desarrollo
1. **Aplicar fix** en presupuesto_mode.py
2. **Ejecutar tests** localmente
3. **Commit** con mensaje: `fix(agent): parse tool result before applying flags`

### Testing
4. **Ejecutar tests** en CI/CD (si existe)
5. **Test manual** con conversación real
6. **Verificar** checkpoints en Redis

### Producción
7. **Deploy** a producción con precaución
8. **Monitor** logs para errores de `apply_tool_flags_invalid_json`
9. **Verificar** métricas de `precio_comunicado` flag (debe ser > 0%)

---

## Comandos de Verificación Rápida

```bash
# 1. Verificar fix está aplicado
rg "_apply_tool_flags" agent/modes/presupuesto_mode.py -A 3 -B 3

# 2. Ejecutar tests
pytest tests/unit/test_tool_flag_contract.py -xvs

# 3. Verificar type hints
mypy agent/modes/presupuesto_mode.py --ignore-missing-imports

# 4. Buscar otros usos problemáticos
rg "tool_result\.get\(" agent/modes/ -B 5

# 5. Verificar documentación
rg "_internal_flags" docs/decisions/005-tool-driven-state-management.md
```

---

## Timeline

| Fase | Tiempo | Acumulado |
|------|--------|-----------|
| 1. Investigación | 15 min | 15 min |
| 2. Fix inmediato | 30 min | 45 min |
| 3. Prevención | 20 min | 1h 5min |
| 4. Verificación | 15 min | 1h 20min |

**Total**: 1 hora 20 minutos

---

## Notas Finales

### Por Qué Ocurrió Este Bug

1. **Type hints engañosos**: `_apply_tool_flags()` declaraba `tool_result: dict` pero recibía `str`
2. **No defensive programming**: No validaba el tipo del input
3. **Tests pasaban**: Usaban DICT directamente, no simulaban el caso real (STRING)
4. **Documentación incompleta**: No mencionaba que `_execute_and_log_tool()` retorna STRING

### Lecciones Aprendidas

1. ✅ **SIEMPRE parsear** resultados de `_execute_and_log_tool()` antes de usar como dict
2. ✅ **Defensive programming**: Validar tipos en funciones críticas
3. ✅ **Tests realistas**: Simular el caso real (STRING), no el ideal (DICT)
4. ✅ **Type hints precisos**: `dict | str` si se aceptan ambos
5. ✅ **Documentar contratos**: Especificar qué retorna cada función

### Patrón Correcto a Seguir

```python
# PATRÓN RECOMENDADO (explicit parsing)
result = await self._execute_and_log_tool(...)  # → STRING
result_dict = json.loads(result) if isinstance(result, str) else result  # → DICT
_apply_tool_flags(mode_context, result_dict, logger)  # ✅ Seguro

# PATRÓN ALTERNATIVO (defensive helper)
result = await self._execute_and_log_tool(...)  # → STRING
_apply_tool_flags(mode_context, result, logger)  # ✅ Auto-parsea internamente
```

**Recomendación**: Usar PATRÓN RECOMENDADO (explicit parsing) para clarity.

---

## Checklist de Implementación

### Investigación
- [x] Buscar todos los usos de `_apply_tool_flags()`
- [x] Buscar todos los usos de `_execute_and_log_tool()`
- [x] Verificar patrón en otros modos
- [x] Revisar tests existentes

### Fix Inmediato
- [ ] Fix en `presupuesto_mode.py` línea 312 (explicit parsing)
- [ ] Fix en `_apply_tool_flags()` líneas 95-110 (defensive)
- [ ] Actualizar type hints
- [ ] Verificar otros usos de `_extract_context_from_tool()`
- [ ] Documentar patrón en comentarios

### Prevención
- [ ] Crear test de regresión `test_apply_tool_flags_accepts_json_string`
- [ ] Crear test de edge case `test_apply_tool_flags_handles_invalid_json`
- [ ] Actualizar ADR-005 con "Known Issues & Fixes"
- [ ] Actualizar AGENTS.md con nuevo patrón

### Verificación
- [ ] Ejecutar tests unitarios
- [ ] Test de integración con conversación real
- [ ] Verificar checkpoints en Redis
- [ ] Monitor logs en producción

---

**Creado por**: Zanovix  
**Fecha**: 2026-02-06  
**Prioridad**: P0 (CRÍTICA)  
**Bloqueante**: Sí (rompe protección PRECIO_BEFORE_IMAGES)
