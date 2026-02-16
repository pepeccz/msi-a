# Plan: Fix FSM Compat State Propagation

**Estado**: PENDIENTE APROBACIÓN  
**Fecha**: 13 de Febrero de 2026  
**Prioridad**: CRÍTICA — Bloquea flujo de expedientes en producción  
**Autor**: Zanovix (arquitectura) + 4 investigadores

---

## Resumen Ejecutivo

La auditoría exhaustiva del agente MSI-a ha revelado un **problema sistémico** en la capa de compatibilidad entre los tools v1 (FSM-based) y la arquitectura v2 (Mode-based). El resultado: las actualizaciones de estado de los tools NO se propagan correctamente al `mode_context`, causando regresiones de estado, loops infinitos, y validaciones rotas.

**No es un bug aislado — son 12 puntos de fallo identificados en 4 archivos.**

---

## Problemas Identificados (Inventario Completo)

### GRUPO A: `update_case_fsm_state()` pierde datos en cadena (fsm_compat.py)

**Causa raíz**: La función IGNORA su parámetro `fsm_state` y siempre crea un dict nuevo. Cuando se encadenan dos llamadas, la segunda SOBREESCRIBE la primera.

```python
# fsm_compat.py L262-265 — BUG
def update_case_fsm_state(fsm_state, updates):
    return {"case_collection": updates}  # ← fsm_state IGNORADO
```

| #  | Tool afectado | Campos perdidos en cadena | Impacto |
|----|---------------|---------------------------|---------|
| A1 | `confirmar_fotos_elemento` (all done, no fields) | `step` (COLLECT_BASE_DOCS) | 🔴 CRÍTICO: Transición perdida |
| A2 | `completar_elemento_actual` (all done) | `step` (COLLECT_BASE_DOCS) | 🔴 CRÍTICO: Transición perdida |
| A3 | `confirmar_documentacion_base` (enough images) | `base_docs_received` | 🟡 ALTO: Flag perdido |
| A4 | `confirmar_documentacion_base` (user confirms) | `base_docs_received` | 🟡 ALTO: Flag perdido |
| A5 | `actualizar_datos_expediente` (personal) | `personal_data` | 🟡 MEDIO: Datos en mode_context stale |
| A6 | `actualizar_datos_expediente` (vehículo) | `vehicle_data` | 🟡 MEDIO: Datos en mode_context stale |
| A7 | `actualizar_datos_taller` (MSI) | `taller_propio` | 🟡 MEDIO: Flag perdido |
| A8 | `actualizar_datos_taller` (propio válido) | `taller_data` | 🟡 MEDIO: Datos perdidos |

### GRUPO B: `_extract_context_from_tool()` no desempaqueta `fsm_state_update` (expediente_mode.py)

**Causa raíz**: El extractor busca `case_collection` en el nivel raíz del resultado, pero los tools lo anidan dentro de `fsm_state_update`.

```python
# El tool retorna:
{"fsm_state_update": {"case_collection": {"element_phase": "data"}}}

# El extractor busca:
data["case_collection"]  → NO EXISTE (está 1 nivel más abajo)
data["element_phase"]    → NO EXISTE (está 2 niveles más abajo)
```

| #  | Campo no extraído | Impacto |
|----|-------------------|---------|
| B1 | `element_phase` ("photos" → "data") | 🔴 CRÍTICO: Bug reportado por el usuario |
| B2 | `element_data_status` (progreso por elemento) | 🟡 ALTO: Tracking desincronizado |
| B3 | `current_element_index` (vía fsm_compat) | 🟡 MEDIO: Índice stale |

### GRUPO C: `_extract_context_from_tool()` busca parámetro `seccion` que no existe (expediente_mode.py)

**Causa raíz**: El extractor asume que `actualizar_datos_expediente` tiene un parámetro `seccion`, pero la tool usa `datos_personales` / `datos_vehiculo` como parámetros separados.

| #  | Transición rota | Impacto |
|----|-----------------|---------|
| C1 | COLLECT_PERSONAL → COLLECT_VEHICLE | 🟡 ALTO: Sub-mode no se actualiza |
| C2 | COLLECT_VEHICLE → COLLECT_WORKSHOP | 🟡 ALTO: Sub-mode no se actualiza |

### GRUPO D: Handler faltante para `editar_expediente` (expediente_mode.py)

| #  | Tool sin handler | Impacto |
|----|------------------|---------|
| D1 | `editar_expediente` → COLLECT_PERSONAL/VEHICLE/WORKSHOP/BASE_DOCS | 🟡 MEDIO: Sub-mode no se actualiza al editar |

### GRUPO E: `Case.is_active` no existe (constraint_service.py)

**Causa raíz**: El modelo `Case` usa `status: str` con 7 valores, no `is_active: bool`.

| #  | Error | Impacto |
|----|-------|---------|
| E1 | `Case.is_active` en query L602 | 🟡 ALTO: validate_case_id() SIEMPRE falla silenciosamente |
| E2 | `User.is_active` en docstrings de pagination.py | ℹ️ BAJO: Documentación errónea |

---

## Plan de Implementación

### NIVEL 1 — Fix Inmediato (Resuelve los bugs activos)

**Estimación**: 2-3 horas  
**Riesgo**: BAJO (cambios quirúrgicos, aditivos)  
**Agente**: `agent-dev`

#### Tarea 1.1: Fix `update_case_fsm_state()` para hacer MERGE

**Archivo**: `agent/utils/fsm_compat.py` L262-265

**Cambio**:
```python
# ANTES (bug):
def update_case_fsm_state(fsm_state, updates):
    return {"case_collection": updates}

# DESPUÉS (fix):
def update_case_fsm_state(
    fsm_state: dict[str, Any] | None,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """
    Update case collection FSM state with MERGE semantics.
    
    Merges new updates with existing case_collection data,
    so chained calls accumulate instead of overwriting.
    """
    existing: dict[str, Any] = {}
    if isinstance(fsm_state, dict) and "case_collection" in fsm_state:
        existing = dict(fsm_state["case_collection"])
    existing.update(updates)
    return {"case_collection": existing}
```

**Impacto**: Resuelve TODOS los bugs del GRUPO A (A1-A8). Las llamadas encadenadas ahora acumulan datos en vez de sobreescribirse.

**Tests necesarios**: Verificar que `transition_to()` + `update_case_fsm_state()` acumulan campos.

---

#### Tarea 1.2: Fix `_extract_context_from_tool()` para desempaquetar `fsm_state_update`

**Archivo**: `agent/modes/expediente_mode.py` — método `_extract_context_from_tool()`

**Cambio**: Después de la sección actual de `case_collection` (L986-996), añadir:

```python
# Unpack fsm_state_update.case_collection (v1 tools compatibility layer)
# Tools wrap their state updates in: {"fsm_state_update": {"case_collection": {...}}}
# We need to unwrap both levels to extract the actual updates.
if "fsm_state_update" in data:
    fsm_update = data["fsm_state_update"]
    if isinstance(fsm_update, dict):
        case_coll = fsm_update.get("case_collection", {})
        if isinstance(case_coll, dict):
            updates.update(case_coll)
            logger.debug(
                "applied_fsm_state_update",
                tool_name=tool_name,
                keys=list(case_coll.keys()),
            )
```

**Impacto**: Resuelve TODOS los bugs del GRUPO B (B1-B3). Los campos `element_phase`, `element_data_status`, `current_element_index` ahora se propagan correctamente.

**Tests necesarios**: Verificar que `confirmar_fotos_elemento` propaga `element_phase: "data"` al mode_context.

---

#### Tarea 1.3: Fix `validate_case_id()` — `Case.is_active` → `Case.status`

**Archivo**: `agent/services/constraint_service.py` L596-616

**Cambio**:
```python
async def validate_case_id(case_id: str) -> tuple[bool, str | None]:
    """Validate that a case ID exists and is active."""
    ...
    ACTIVE_STATUSES = ["collecting", "pending_images", "pending_review", "in_progress"]

    async def query():
        async with get_async_session() as session:
            from database.models import Case
            result = await session.execute(
                select(Case.id, Case.status).where(Case.id == uuid_obj)
            )
            row = result.one_or_none()
            if not row:
                return {"exists": False, "status": None}
            return {"exists": True, "status": row.status}

    result = await cached_db_lookup(cache_key, query, ttl=60)

    if not result["exists"]:
        return (False, f"El expediente '{case_id}' no existe")
    elif result["status"] not in ACTIVE_STATUSES:
        return (False, f"El expediente '{case_id}' está {result['status']}")
    else:
        return (True, None)
```

**Impacto**: Resuelve GRUPO E1. La validación semántica de case IDs ahora funciona.

---

### NIVEL 2 — Defensa en Profundidad (Previene recurrencia)

**Estimación**: 4-6 horas  
**Riesgo**: BAJO-MEDIO  
**Agente**: `agent-dev`

#### Tarea 2.1: Fix `actualizar_datos_expediente` handler — `seccion` → detección por `next_step`

**Archivo**: `agent/modes/expediente_mode.py` — `_extract_context_from_tool()`

**Cambio**: Reemplazar el handler de `actualizar_datos_expediente` (L947-960):

```python
# ANTES (bug — busca parámetro "seccion" que no existe):
elif tool_name == "actualizar_datos_expediente":
    seccion = tool_args.get("seccion")
    if data.get("success") and seccion == "datos_personales":
        ...

# DESPUÉS (fix — detecta por next_step del resultado):
elif tool_name == "actualizar_datos_expediente":
    if data.get("success"):
        next_step = data.get("next_step")
        STEP_TO_SUBMODE = {
            "collect_vehicle": COLLECT_VEHICLE,
            "collect_workshop": COLLECT_WORKSHOP,
        }
        if next_step in STEP_TO_SUBMODE:
            updates["expediente_sub_mode"] = STEP_TO_SUBMODE[next_step]
            logger.info(
                "expediente_sub_mode_transition",
                tool=tool_name,
                new_sub_mode=STEP_TO_SUBMODE[next_step],
            )
```

**Impacto**: Resuelve GRUPO C (C1-C2).

---

#### Tarea 2.2: Añadir handler para `editar_expediente`

**Archivo**: `agent/modes/expediente_mode.py` — `_extract_context_from_tool()`

**Cambio**: Añadir nuevo handler:

```python
elif tool_name == "editar_expediente":
    if data.get("success"):
        next_step = data.get("next_step")
        STEP_TO_SUBMODE = {
            "collect_personal": COLLECT_PERSONAL,
            "collect_vehicle": COLLECT_VEHICLE,
            "collect_workshop": COLLECT_WORKSHOP,
            "collect_base_docs": COLLECT_BASE_DOCS,
        }
        if next_step in STEP_TO_SUBMODE:
            updates["expediente_sub_mode"] = STEP_TO_SUBMODE[next_step]
            updates["editing_from_review"] = True
```

**Impacto**: Resuelve GRUPO D (D1).

---

#### Tarea 2.3: Redundancia — Tools devuelven campos clave también en nivel raíz

**Archivos**: `agent/tools/element_data_tools.py`, `agent/tools/case_tools.py`

**Cambio**: En cada tool que usa `update_case_fsm_state()`, TAMBIÉN devolver los campos críticos en el nivel raíz del resultado:

```python
# En confirmar_fotos_elemento (element_data_tools.py):
response = {
    "success": True,
    "element_phase": "data",              # ← REDUNDANCIA en raíz
    "element_data_status": element_data_status,  # ← REDUNDANCIA en raíz
    "current_element_index": current_idx,  # ← REDUNDANCIA en raíz
    "fsm_state_update": new_fsm_state,    # ← FSM compat (ya existente)
    ...
}
```

**Tools a modificar**:
- `confirmar_fotos_elemento` (3 paths: has_fields, all_done, more_elements)
- `completar_elemento_actual` (2 paths: all_done, more_elements)
- `confirmar_documentacion_base` (2 paths)
- `actualizar_datos_expediente` (2 paths: personal, vehículo)
- `actualizar_datos_taller` (3 paths)

**Impacto**: Defensa en profundidad. Si el extractor `fsm_state_update` fallara, los campos siguen disponibles en raíz.

---

#### Tarea 2.4: Corregir docstrings y comentarios incorrectos

**Archivos**:
- `agent/modes/expediente_mode.py` L484: Eliminar referencia a `seccion="datos_personales"`
- `agent/modes/expediente_mode.py` L506: Eliminar referencia a `seccion="datos_vehiculo"`
- `api/utils/pagination.py` L62, L114: Cambiar `User.is_active` a `Element.is_active`

---

### NIVEL 3 — Estabilización Arquitectónica (Elimina deuda técnica)

**Estimación**: 1-2 días (puede hacerse incrementalmente)  
**Riesgo**: MEDIO (cambio más amplio, necesita tests exhaustivos)  
**Agente**: `agent-dev` + `qa-dev`

#### Tarea 3.1: Contrato formal para tool → mode_context updates

**Nuevo archivo**: `agent/utils/tool_context_contract.py`

Crear un helper que estandarice CÓMO los tools devuelven actualizaciones de contexto, eliminando la ambigüedad del doble-wrapping:

```python
"""
Standard contract for tools to declare mode_context updates.

Usage in tools:
    from agent.utils.tool_context_contract import context_update

    return {
        "success": True,
        "message": "...",
        **context_update(
            element_phase="data",
            element_data_status=updated_status,
            expediente_sub_mode="collect_base_docs",
        ),
    }

The context_update() function places all updates in a standard
`_context_updates` key that _extract_context_from_tool() reads.
"""

def context_update(**kwargs) -> dict[str, Any]:
    """Wrap context updates in standard format for mode nodes."""
    return {"_context_updates": kwargs}
```

Y en `_extract_context_from_tool()`:
```python
# Standard contract (new tools)
if "_context_updates" in data:
    ctx = data["_context_updates"]
    if isinstance(ctx, dict):
        updates.update(ctx)
```

**Impacto**: Los nuevos tools usarán un formato limpio y explícito. Los tools v1 siguen funcionando via los fixes del Nivel 1-2.

---

#### Tarea 3.2: Reconciliación de estado con la DB al inicio de cada turno

**Archivo**: `agent/modes/expediente_mode.py` — `_process_message()`

Después de leer `mode_context`, verificar contra la DB los campos críticos:

```python
async def _reconcile_state_with_db(
    self, 
    mode_context: dict, 
    case_id: str,
) -> dict:
    """
    Reconcile mode_context with DB state as safety net.
    
    If mode_context has stale data, correct it from the DB
    (source of truth). Log warnings for every correction.
    """
    corrections = {}
    
    async with get_async_session() as session:
        case = await session.get(Case, uuid.UUID(case_id))
        if not case:
            return corrections
        
        # Check element_phase against actual element status
        current_element = mode_context.get("current_element_code")
        if current_element:
            elem_data = await _get_case_element_data(case_id, current_element)
            if elem_data:
                if elem_data.status == "pending_data" and mode_context.get("element_phase") == "photos":
                    corrections["element_phase"] = "data"
                    logger.warning(
                        "state_reconciled",
                        field="element_phase",
                        stale="photos",
                        corrected="data",
                    )
    
    return corrections
```

**Impacto**: Safety net definitivo. Si cualquier mecanismo de propagación falla, el siguiente turno se auto-corrige.

---

#### Tarea 3.3: Migración progresiva de tools a `_context_updates` y `_internal_flags`

No se hace de golpe. Se crea un ticket por cada tool para migrar gradualmente:

**Fase 1** (tools de expediente críticos):
- `confirmar_fotos_elemento`
- `completar_elemento_actual`
- `confirmar_documentacion_base`
- `actualizar_datos_expediente`
- `actualizar_datos_taller`

**Fase 2** (tools restantes):
- `iniciar_expediente`
- `finalizar_expediente`
- `cancelar_expediente`
- `editar_expediente`

Cada migración:
1. Añade `_context_updates` al return del tool
2. Mantiene `fsm_state_update` por compatibilidad
3. Tests verifican que ambos mecanismos producen el mismo resultado
4. Cuando todos los tools están migrados, deprecar `fsm_state_update`

---

## Orden de Ejecución

```
NIVEL 1 (inmediato):
  ├── 1.1: Fix update_case_fsm_state merge    ← Resuelve GRUPO A (8 bugs)
  ├── 1.2: Fix extractor fsm_state_update     ← Resuelve GRUPO B (3 bugs)  
  └── 1.3: Fix Case.is_active → Case.status   ← Resuelve GRUPO E (1 bug)
  
NIVEL 2 (defensa en profundidad):
  ├── 2.1: Fix handler seccion → next_step    ← Resuelve GRUPO C (2 bugs)
  ├── 2.2: Añadir handler editar_expediente   ← Resuelve GRUPO D (1 bug)
  ├── 2.3: Redundancia campos en raíz tools   ← Defensa en profundidad
  └── 2.4: Fix docstrings y comentarios       ← Limpieza

NIVEL 3 (estabilización):
  ├── 3.1: Contrato formal _context_updates   ← Nuevo estándar
  ├── 3.2: Reconciliación state ↔ DB          ← Safety net definitivo
  └── 3.3: Migración progresiva de tools      ← Elimina deuda técnica
```

---

## Tests Necesarios

### Tests del Nivel 1

```python
# test_fsm_compat_merge.py
class TestUpdateCaseFSMState:
    def test_single_call(self):
        """Single call wraps correctly."""
        result = update_case_fsm_state(None, {"element_phase": "data"})
        assert result == {"case_collection": {"element_phase": "data"}}
    
    def test_chained_calls_accumulate(self):
        """Chained calls accumulate, not overwrite."""
        step1 = transition_to(None, CollectionStep.COLLECT_BASE_DOCS)
        step2 = update_case_fsm_state(step1, {"element_data_status": {"SUBCHASIS": "complete"}})
        
        case_coll = step2["case_collection"]
        assert "step" in case_coll, "step from transition_to must survive"
        assert "element_data_status" in case_coll, "element_data_status must be added"
        assert case_coll["step"] == "collect_base_docs"

# test_extract_context.py
class TestExtractContextFromTool:
    def test_fsm_state_update_unwrapped(self):
        """fsm_state_update.case_collection is properly unwrapped."""
        data = {
            "success": True,
            "fsm_state_update": {
                "case_collection": {
                    "element_phase": "data",
                    "element_data_status": {"SUBCHASIS": "photos_done"},
                }
            }
        }
        updates = _extract_context_from_tool("confirmar_fotos_elemento", {}, json.dumps(data), {})
        assert updates.get("element_phase") == "data"
        assert "element_data_status" in updates
    
    def test_actualizar_datos_by_next_step(self):
        """actualizar_datos_expediente transitions by next_step, not seccion."""
        data = {"success": True, "next_step": "collect_vehicle"}
        updates = _extract_context_from_tool("actualizar_datos_expediente", {}, json.dumps(data), {})
        assert updates.get("expediente_sub_mode") == COLLECT_VEHICLE

# test_validate_case_id.py
class TestValidateCaseId:
    async def test_active_case(self, session):
        """Active case passes validation."""
        case = Case(status="collecting", ...)
        # ...
        valid, msg = await validate_case_id(str(case.id))
        assert valid is True
    
    async def test_cancelled_case(self, session):
        """Cancelled case fails validation."""
        case = Case(status="cancelled", ...)
        # ...
        valid, msg = await validate_case_id(str(case.id))
        assert valid is False
        assert "cancelled" in msg
```

### Tests del Nivel 2

```python
# test_tool_redundancy.py
class TestToolRedundancy:
    def test_confirmar_fotos_returns_element_phase_at_root(self):
        """confirmar_fotos_elemento returns element_phase at both levels."""
        result = await confirmar_fotos_elemento("SUBCHASIS")
        data = json.loads(result) if isinstance(result, str) else result
        
        # Root level (for direct extraction)
        assert "element_phase" in data
        
        # FSM compat level (for case_collection extraction)
        fsm = data.get("fsm_state_update", {}).get("case_collection", {})
        assert "element_phase" in fsm
        
        # Both must agree
        assert data["element_phase"] == fsm["element_phase"]
```

### Tests del Nivel 3

```python
# test_state_reconciliation.py
class TestStateReconciliation:
    async def test_corrects_stale_element_phase(self, session):
        """Reconciliation corrects stale element_phase from DB."""
        # Setup: DB says pending_data, mode_context says photos
        mode_context = {"element_phase": "photos", "case_id": str(case.id)}
        
        corrections = await _reconcile_state_with_db(mode_context, str(case.id))
        
        assert corrections.get("element_phase") == "data"
```

---

## Archivos Afectados (Resumen)

| Archivo | Nivel | Cambio |
|---------|-------|--------|
| `agent/utils/fsm_compat.py` | 1 | Fix merge en `update_case_fsm_state()` |
| `agent/modes/expediente_mode.py` | 1+2 | Fix extractor + handlers |
| `agent/services/constraint_service.py` | 1 | Fix `Case.is_active` → `Case.status` |
| `agent/tools/element_data_tools.py` | 2 | Redundancia campos en raíz |
| `agent/tools/case_tools.py` | 2 | Redundancia campos en raíz |
| `api/utils/pagination.py` | 2 | Fix docstrings |
| `agent/utils/tool_context_contract.py` | 3 | Nuevo archivo: contrato |
| `tests/test_fsm_compat.py` | 1 | Tests del fix merge |
| `tests/test_expediente_state.py` | 1+2 | Tests del extractor |
| `tests/test_constraint_service.py` | 1 | Tests validate_case_id |

---

## Métricas de Éxito

1. **El bug reportado desaparece**: Usuario dice "listo" → datos técnicos → datos se guardan (no regresión a fotos)
2. **Todos los sub-mode transitions funcionan**: COLLECT_ELEMENT_DATA → BASE_DOCS → PERSONAL → VEHICLE → WORKSHOP → REVIEW
3. **validate_case_id funciona**: No más `AttributeError` silencioso en logs
4. **element_data_status persiste entre turnos**: Tracking de progreso por elemento se mantiene correcto
5. **Tests pasan**: Coverage >90% para los archivos modificados

---

## Riesgo y Rollback

| Nivel | Riesgo | Plan de Rollback |
|-------|--------|-----------------|
| 1 | BAJO | Revertir 3 archivos. Los cambios son aditivos y quirúrgicos. |
| 2 | BAJO | Revertir handlers. Los existentes no se eliminan, solo se corrigen. |
| 3 | MEDIO | Nuevo código aditivo. Si falla, se desactiva sin afectar v1 tools. |

---

## ADR Asociado

Si se aprueba, se creará `docs/decisions/006-fix-fsm-compat-state-propagation.md` documentando:
- La decisión de hacer merge en `update_case_fsm_state()`
- El contrato `_context_updates` para tools nuevos
- La reconciliación state ↔ DB como safety net

---

**Estado**: ⏳ PENDIENTE APROBACIÓN DEL USUARIO
