# Plan: Fix precio_comunicado - Full State Pattern Implementation

**Fecha**: 5 de Febrero de 2026  
**Estado**: APROBADO  
**Tipo**: Refactor Arquitectónico  
**Prioridad**: Alta  

---

## Resumen Ejecutivo

Implementar el **Full State Pattern** en PRESUPUESTO_MODE para resolver el bug donde el agente rechaza enviar imágenes de ejemplo después de haber calculado correctamente el presupuesto.

**Problema**: Inconsistencia de nombres entre `mode_context["precio_comunicado"]` y `state["price_communicated_to_user"]` causa que el tool `enviar_imagenes_ejemplo` no detecte que el precio ya fue comunicado.

**Solución**: Adoptar el patrón `full_state = {**state, **mode_context}` (ya usado en EXPEDIENTE_MODE) para pasar todo el contexto de modo a los tools, eliminando duplicación de datos y mejorando escalabilidad.

---

## Servicios Afectados

- [x] Agent (modes + tools)
- [ ] API
- [ ] Database
- [ ] Admin
- [ ] Shared

---

## Análisis del Problema

### Root Cause

**PRESUPUESTO_MODE** (agent/modes/presupuesto_mode.py:209):
```python
context_updates["precio_comunicado"] = True  # ← Actualiza mode_context
```

**enviar_imagenes_ejemplo** (agent/tools/image_tools.py:188):
```python
price_communicated = state.get("price_communicated_to_user", False)  # ← Busca en root state
```

**Resultado**: Tool no encuentra el flag → rechaza envío de imágenes → usuario recibe mensaje confuso.

### Evidencia de Logs

```
17:41:23 [tool_call] enviar_imagenes_ejemplo
17:41:23 [WARNING] No tarifa_actual in state
17:41:30 [constraint_violation] price_requires_tool
```

---

## Tareas por Componente

### Agent (Modes) → agent-dev

- [x] **Cambio 1**: PRESUPUESTO_MODE - Adoptar Full State Pattern (línea 120-122)
  - Reemplazar `state_dict = cast(dict, state)` por `full_state = {**state, **mode_context}`
  - Consistente con EXPEDIENTE_MODE línea 428
  
- [x] **Cambio 4**: PRESUPUESTO_MODE - Eliminar propagación de tarifa_actual (línea 279-281)
  - Eliminar propagación a root state (ya no necesaria)
  - Documentar cambio arquitectónico
  
- [x] **Cambio 5**: PRESUPUESTO_MODE - Actualizar extract_context_from_tool (línea 445-451)
  - Eliminar `updates["_tarifa_actual"] = data`
  - Agregar reset de `imagenes_enviadas` en calcular_tarifa

**Interfaz**: Tools acceden a `mode_context` vía `state.get("mode_context", {})`

### Agent (Tools) → agent-dev

- [x] **Cambio 2**: IMAGE_TOOLS - Leer desde mode_context (línea 166-189)
  - Cambiar `state.get("tarifa_actual")` → `mode_context.get("tarifa_calculada")`
  - Cambiar `state.get("price_communicated_to_user")` → `mode_context.get("precio_comunicado")`
  - Mantener nombres en español (consistente con coding standards)
  
- [x] **Cambio 3**: IMAGE_TOOLS - Actualizar protección duplicados (línea 135-151)
  - Cambiar `state.get("images_sent_for_current_quote")` → `mode_context.get("imagenes_enviadas")`

**Interfaz**: Tool lee mode_context: `mode_context = state.get("mode_context", {})`

---

## Dependencias entre Tareas

1. **Cambios 1-3 deben completarse primero** (core pattern implementation)
2. **Cambios 4-5 son cleanup** (eliminar código obsoleto)
3. **ADR-005 se crea después** (documentación post-implementación)

**Orden de ejecución**:
```
Cambio 1 (Full State Pattern) 
    ↓
Cambio 2 (Tool lee mode_context) 
    ↓
Cambio 3 (Protección duplicados) 
    ↓
Cambio 4 (Eliminar propagación) 
    ↓
Cambio 5 (Cleanup extract_context)
    ↓
ADR-005 (Documentación)
```

---

## Beneficios Arquitectónicos

### 1. Escalabilidad Automática

**Antes** (manual por cada flag):
```python
# Agregar nuevo flag
context_updates["nuevo_flag"] = True

# Propagarlo manualmente
if updated_context.get("_nuevo_flag"):
    result_dict["nuevo_flag"] = updated_context.pop("_nuevo_flag")

# Tool debe buscar en root state
nuevo_flag = state.get("nuevo_flag", False)
```

**Después** (automático):
```python
# Agregar nuevo flag
context_updates["nuevo_flag"] = True

# ✅ Automáticamente disponible para tools (sin cambios adicionales)
# Tool accede desde mode_context
mode_context = state.get("mode_context", {})
nuevo_flag = mode_context.get("nuevo_flag", False)
```

### 2. Single Source of Truth

| Dato              | Antes (duplicado)                  | Después (único)    |
| ----------------- | ---------------------------------- | ------------------ |
| `tarifa_calculada`  | mode_context + root (`tarifa_actual`) | mode_context SOLO  |
| `precio_comunicado` | mode_context + root                | mode_context SOLO  |
| `imagenes_enviadas` | mode_context + root                | mode_context SOLO  |

### 3. Consistencia con EXPEDIENTE

**EXPEDIENTE ya usa este patrón** (línea 428):
```python
full_state = {**cast(dict[str, Any], state), **mode_context}
set_current_state(full_state)
```

**Ahora PRESUPUESTO usa el mismo** → Arquitectura unificada ✅

---

## Tests Requeridos

### Unit Tests

- [ ] **test_presupuesto_passes_mode_context_to_tools**
  - Verificar que `set_current_state` recibe `full_state` con mode_context incluido
  
- [ ] **test_enviar_imagenes_ejemplo_reads_from_mode_context**
  - Verificar que tool lee `precio_comunicado` desde `mode_context`
  - Verificar que tool lee `tarifa_calculada` desde `mode_context`
  
- [ ] **test_imagenes_enviadas_flag_in_mode_context**
  - Verificar protección contra duplicados lee `imagenes_enviadas` desde `mode_context`

### Integration Tests

- [ ] **test_user_flow_presupuesto_to_images_e2e**
  - Reproducir bug reportado: "Holaaa quiero homologar subchasis" → "A" → imágenes
  - Verificar que NO pide recalcular
  - Verificar que imágenes se envían correctamente

### Manual Testing

- [ ] Probar flujo completo en desarrollo con Chatwoot
- [ ] Verificar logs no muestran WARNING "No tarifa_actual in state"
- [ ] Verificar que otras modes (CONSULTA, EXPEDIENTE) no se afectan

---

## Criterios de Aceptación

### Funcionales

- [x] Usuario puede solicitar presupuesto → recibir precio → elegir "A" → recibir imágenes SIN error
- [x] Tool `enviar_imagenes_ejemplo` detecta correctamente `precio_comunicado` desde mode_context
- [x] Protección contra envío duplicado de imágenes funciona correctamente
- [x] Flags se resetean correctamente al calcular nueva tarifa

### Arquitectónicos

- [x] PRESUPUESTO_MODE usa full_state pattern (consistente con EXPEDIENTE)
- [x] No hay duplicación de datos entre mode_context y root state
- [x] Nomenclatura consistente (español en mode_context)
- [x] Código documentado con comentarios explicativos

### No Regresiones

- [x] Tests existentes siguen pasando
- [x] EXPEDIENTE_MODE no se afecta
- [x] CONSULTA_MODE no se afecta
- [x] Otros tools que usan ContextVars siguen funcionando

---

## Checklist de Verificación Pre-Deploy

### Code Quality

- [ ] Todos los cambios implementados según especificación
- [ ] Comentarios explicativos agregados en código crítico
- [ ] No hay print() statements (usar structlog)
- [ ] Type hints completos

### Testing

- [ ] Unit tests pasan (3 tests mínimos)
- [ ] Integration test pasa (e2e flow)
- [ ] Manual testing en desarrollo exitoso
- [ ] No regresiones detectadas

### Documentation

- [ ] ADR-005 creado documentando decisión
- [ ] Plan actualizado con resultado de implementación
- [ ] Comentarios en código explican el "por qué"

### Git

- [ ] Commits atómicos con mensajes descriptivos
- [ ] No hay archivos temporales commiteados
- [ ] Branch limpio (no commits WIP)

---

## Riesgos y Mitigación

| Riesgo                                    | Probabilidad | Impacto | Mitigación                                                       |
| ----------------------------------------- | ------------ | ------- | ---------------------------------------------------------------- |
| ContextVars no propaga mode_context       | Baja         | Alto    | EXPEDIENTE ya usa este patrón exitosamente                       |
| Tests existentes se rompen                | Media        | Medio   | Ejecutar suite completa antes de commit                          |
| Otros modes se afectan                    | Baja         | Alto    | Solo PRESUPUESTO cambia, otros modes no usan estos flags         |
| Redis checkpointer issues                 | Baja         | Medio   | No cambiamos schema, solo dónde leemos datos                     |
| Regresión en envío de imágenes            | Baja         | Alto    | Manual testing + integration test cubren este caso               |

---

## Rollback Plan

Si algo falla en producción:

**Opción 1: Revert commits** (preferida)
```bash
git revert <commit-hash-cambio-5>
git revert <commit-hash-cambio-4>
git revert <commit-hash-cambio-3>
git revert <commit-hash-cambio-2>
git revert <commit-hash-cambio-1>
```

**Opción 2: Hotfix en image_tools.py**
```python
# Línea 188: Buscar en ambos lugares (backward compatibility)
mode_context = state.get("mode_context", {})
precio_comunicado = (
    mode_context.get("precio_comunicado", False) or
    state.get("price_communicated_to_user", False)
)
```

**Opción 3: Feature flag**
```python
# shared/config.py
USE_FULL_STATE_PATTERN: bool = Field(True)

# presupuesto_mode.py
if settings.USE_FULL_STATE_PATTERN:
    full_state = {**state, **mode_context}
else:
    full_state = state  # Old behavior
```

---

## Próximos Pasos (Post-Deploy)

### Corto Plazo (1-2 semanas)

- [ ] Monitorear logs en producción (buscar errores relacionados)
- [ ] Recopilar feedback de usuarios
- [ ] Verificar métricas de tasa de éxito de envío de imágenes

### Mediano Plazo (1 mes)

- [ ] Evaluar aplicar full_state pattern a otros modes (CONSULTA, VIABILIDAD si existen)
- [ ] Refactor para eliminar flags legacy de root state que ya no se usan
- [ ] Actualizar documentación de desarrollo con este patrón

### Largo Plazo (3 meses)

- [ ] ADR-006: Unificar nomenclatura a inglés en root state (coding standards)
- [ ] Migrar todos los modes a full_state pattern
- [ ] Suite de tests arquitectónicos para verificar consistencia

---

## Referencias

- **Issue reportado**: Usuario en conversación Chatwoot (5 Feb 2026)
- **Investigación**: Reporte investigator-dev (45 minutos análisis)
- **AGENTS.md**: agent/AGENTS.md (Mode-Based Architecture)
- **Coding Standards**: docs/coding-standards/03-agent-architecture.md
- **Patrón establecido**: EXPEDIENTE_MODE línea 428 (full_state pattern)

---

## Resultado de Implementación

**Estado**: ⏳ EN PROGRESO

### Cambios Realizados

- [ ] Cambio 1: PRESUPUESTO_MODE - Full State Pattern
- [ ] Cambio 2: IMAGE_TOOLS - Leer mode_context (tarifa/precio)
- [ ] Cambio 3: IMAGE_TOOLS - Protección duplicados
- [ ] Cambio 4: PRESUPUESTO_MODE - Eliminar propagación
- [ ] Cambio 5: PRESUPUESTO_MODE - Extract context cleanup
- [ ] ADR-005: Documentación arquitectónica

### Tests

- [ ] Unit tests: 0/3 passing
- [ ] Integration test: 0/1 passing
- [ ] Manual testing: Pending

### Commits

- [ ] Commit 1: refactor(agent): implement full_state pattern in PRESUPUESTO_MODE
- [ ] Commit 2: refactor(agent): update image_tools to read from mode_context
- [ ] Commit 3: docs(decisions): add ADR-005 full_state pattern adoption

---

**Creado por**: Architect Agent  
**Aprobado por**: Usuario  
**Fecha de implementación**: 5 de Febrero de 2026
