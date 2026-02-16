# Plan: Transition Hardening — Bases Sólidas para Transiciones de Modo

**Fecha**: 12 de Febrero de 2026
**Estado**: ✅ COMPLETADO (12 Feb 2026)
**Prioridad**: ALTA
**Rama**: `master` (hotfix incremental)

---

## Motivación

Investigación exhaustiva (19 puntos de transición auditados, 10+ archivos, 4,588 líneas) revela un **problema sistémico de diseño** en las transiciones de modo del agente MSI-a:

- Solo **2 de 19** transiciones (17%) usan `transition_mode()`
- `merge_dicts` reducer es **append-only** → keys nunca se eliminan de `mode_context`
- Fallback resets son **NO-OPs** (vacío + merge = sin efecto)
- `draft_contexts.pop()` es inefectivo por el mismo reducer
- 3 modos tienen escalation sin `current_mode: "ESCALATION"`
- EXPEDIENTE sub-modos no reciben contexto en el prompt (bug en loader)
- `expediente_completed`/`expediente_cancelled` flags se setean pero no desencadenan transición

### LangGraph `Overwrite` — La Solución

LangGraph 1.0.8 (nuestra versión) soporta `Overwrite()` que bypasea el reducer y REEMPLAZA el valor. Esto permite limpiar `mode_context` en transiciones sin cambiar el reducer.

---

## Arquitectura Objetivo

### Estado Actual (Roto)

```
mode_node returns {"current_mode": "EXPEDIENTE_MODE", "mode_context": {**all_garbage, ...new_keys}}
    ↓
merge_dicts reducer: {**checkpoint_context, **returned_context} = BASURA ACUMULADA
    ↓
mode_context crece indefinidamente, retry_state no reseteado, previous_mode stale
```

### Estado Objetivo (Limpio)

```
mode_node llama transition_mode() que retorna:
    {"mode_context": Overwrite(clean_context), "previous_mode": X, "retry_state": empty, ...}
    ↓
Overwrite bypasea merge_dicts → mode_context es EXACTAMENTE clean_context
    ↓
Cada modo empieza con SOLO las keys que necesita
```

### Principios de Diseño

1. **`transition_mode()` es la ÚNICA forma de cambiar de modo** — todas las transiciones pasan por ella
2. **`Overwrite` para context limpio** — cada transición empieza con un context sin basura
3. **Contratos explícitos** — cada modo declara qué keys necesita recibir y cuáles produce
4. **`draft_contexts` funcional** — guardar y restaurar context al cambiar de modo (para volver de GATEWAY a PRESUPUESTO, o de EXPEDIENTE cancelado a PRESUPUESTO)
5. **Safety nets** — si algo falla, el usuario siempre recibe respuesta

---

## Fases de Implementación

### Fase 0: Tests de Regresión de Transiciones (PRIMERO)

**Objetivo**: Tener tests que validen el comportamiento ACTUAL antes de tocar nada.

**Archivos a crear**:
- `tests/test_transitions.py`

**Tests a escribir**:

| Test | Qué valida |
|------|-----------|
| `test_gateway_yes_transitions_to_expediente` | Gateway YES → current_mode=EXPEDIENTE_MODE, keys críticas preservadas |
| `test_gateway_no_transitions_to_presupuesto` | Gateway NO → current_mode=PRESUPUESTO_MODE |
| `test_gateway_ambiguous_retries` | Ambiguous responses incrementan attempts, max → PRESUPUESTO |
| `test_presupuesto_to_gateway_via_tool` | Tool `confirmar_presupuesto` → current_mode=EVALUACION_GATEWAY |
| `test_transition_mode_preserves_keys` | `transition_mode()` con preserve_keys copia correctamente |
| `test_transition_mode_saves_draft` | `transition_mode()` guarda draft del modo actual |
| `test_transition_mode_restores_draft` | `transition_mode()` restaura draft si existe |
| `test_fallback_reset_clears_context` | Fallback RESET_TO_MODE_START realmente limpia context |
| `test_fallback_escalate_sets_mode` | Fallback ESCALATE establece current_mode=ESCALATION |
| `test_expediente_initialization_has_required_keys` | EXPEDIENTE recibe case_id, element_codes, categoria_slug |
| `test_context_keys_not_leaked` | Después de transición, keys del modo anterior NO están en context |

**Estrategia de testing**: Unit tests con state dicts mockeados. NO requieren DB ni LLM. Testean `transition_mode()`, `_handle_yes()`, `_handle_no()`, `execute_fallback()` como funciones puras.

**Estimación**: ~200 líneas, ~2h

---

### Fase 1: `transition_mode()` con `Overwrite` + Contratos de Keys

**Objetivo**: Hacer que `transition_mode()` use `Overwrite` y definir contratos explícitos de qué keys necesita cada modo.

**Archivos a modificar**:
- `agent/state/conversation_state.py`

**Cambios**:

#### 1a. Añadir `Overwrite` a `transition_mode()`

```python
from langgraph.types import Overwrite

def transition_mode(
    state: ConversationState,
    new_mode: ConversationMode,
    *,
    preserve_keys: list[str] | None = None,
    new_context: ModeContextData | None = None,
) -> dict[str, Any]:
    # ... existing draft save logic ...

    # Build clean target context (same logic as before)
    # ...

    return {
        "current_mode": new_mode,
        "previous_mode": current_mode,
        "mode_history": history,
        "mode_context": Overwrite(target_context),  # ← REEMPLAZO LIMPIO
        "draft_contexts": Overwrite(draft_contexts), # ← Fix H4: pop() ahora funciona
        "retry_state": create_empty_retry_state(),
        "mode_message_count": 0,
        "updated_at": now,
        "last_activity_at": now,
    }
```

#### 1b. Definir contratos de keys por transición

```python
# En mode_transitions.py — ampliar CONTEXT_PRESERVE_RULES
CONTEXT_PRESERVE_RULES: dict[str, dict[str, list[str]]] = {
    "PRESUPUESTO_MODE": {
        "EVALUACION_GATEWAY": [
            "element_codes",
            "tarifa_calculada",
            "categoria_slug",
            "precio_comunicado",       # Gateway necesita saber si se comunicó precio
        ],
    },
    "EVALUACION_GATEWAY": {
        "EXPEDIENTE_MODE": [
            "element_codes",
            "tarifa_calculada",
            "categoria_slug",
        ],
        "PRESUPUESTO_MODE": [          # NUEVO: para cuando usuario dice NO
            "element_codes",
            "tarifa_calculada",
            "categoria_slug",
            "precio_comunicado",
            "imagenes_enviadas",
        ],
    },
    "EXPEDIENTE_MODE": {
        "PRESUPUESTO_MODE": [          # NUEVO: expediente cancelado → volver
            "element_codes",
            "tarifa_calculada",
            "categoria_slug",
        ],
    },
}
```

**Estimación**: ~40 líneas de cambio, ~1h

**Verificación**: Ejecutar tests de Fase 0. Todos deben PASAR (los que testean el nuevo comportamiento con Overwrite) y los de backward compat deben adaptarse.

---

### Fase 2: Migrar Gateway a `transition_mode()`

**Objetivo**: Que `evaluacion_gateway.py` use `transition_mode()` en lugar de transiciones manuales.

**Archivos a modificar**:
- `agent/modes/evaluacion_gateway.py`

**Cambios**:

#### 2a. `_handle_yes()` — Usar `transition_mode()`

```python
def _handle_yes(self, state, mode_context):
    from agent.state.conversation_state import transition_mode
    from agent.router.mode_transitions import get_preserve_keys

    self._logger.info("gateway_confirmed")

    preserve = get_preserve_keys("EVALUACION_GATEWAY", "EXPEDIENTE_MODE")
    updates = transition_mode(state, "EXPEDIENTE_MODE", preserve_keys=preserve)

    updates["ai_response"] = (
        "¡Perfecto! Vamos a iniciar el expediente. "
        "Te voy a ir pidiendo la información paso a paso."
    )

    return updates
```

#### 2b. `_handle_no()` — Usar `transition_mode()` + draft restore

```python
def _handle_no(self, state, mode_context):
    from agent.state.conversation_state import transition_mode
    from agent.router.mode_transitions import get_preserve_keys

    self._logger.info("gateway_declined")

    preserve = get_preserve_keys("EVALUACION_GATEWAY", "PRESUPUESTO_MODE")
    updates = transition_mode(state, "PRESUPUESTO_MODE", preserve_keys=preserve)

    updates["ai_response"] = (
        "Sin problema. El presupuesto queda guardado "
        "por si lo quieres retomar más adelante. "
        "¿Hay algo más en lo que te pueda ayudar?"
    )

    return updates
```

#### 2c. `_handle_ambiguous()` max retries — Igual que `_handle_no()`

```python
if attempts >= MAX_GATEWAY_RETRIES:
    preserve = get_preserve_keys("EVALUACION_GATEWAY", "PRESUPUESTO_MODE")
    updates = transition_mode(state, "PRESUPUESTO_MODE", preserve_keys=preserve)
    updates["ai_response"] = "Entiendo que todavía no estás seguro..."
    return updates
```

**Estimación**: ~50 líneas de cambio, ~1h

**Verificación**: Tests de Fase 0 para gateway. E2E manual por WhatsApp: PRESUPUESTO → "sí" → verificar que EXPEDIENTE se inicia con context limpio.

---

### Fase 3: Migrar Tool-Signaled Transitions (Presupuesto + Expediente)

**Objetivo**: Que las transiciones disparadas por tools (`_transition_to` en `_internal_flags`) también usen `transition_mode()`.

**Archivos a modificar**:
- `agent/modes/presupuesto_mode.py` (~L425-440)
- `agent/modes/expediente_mode.py` (~L810-825)

**Cambio en ambos** (mismo patrón):

```python
# ANTES (manual):
transition_target = updated_context.pop("_transition_to", None)
if transition_target:
    allowed, reason = validate_transition(current_mode, transition_target)
    if allowed:
        result_dict["current_mode"] = transition_target

# DESPUÉS (via transition_mode):
transition_target = updated_context.pop("_transition_to", None)
if transition_target:
    allowed, reason = validate_transition(self.mode_name, transition_target)
    if allowed:
        from agent.state.conversation_state import transition_mode
        from agent.router.mode_transitions import get_preserve_keys

        preserve = get_preserve_keys(self.mode_name, transition_target)
        transition_updates = transition_mode(
            state, transition_target, preserve_keys=preserve
        )
        result_dict.update(transition_updates)
        # Mantener ai_response del mode node (no sobrescribir)
        result_dict["ai_response"] = ai_response
```

**Nota importante**: `transition_mode()` devuelve `mode_context: Overwrite(clean)`. Necesitamos asegurar que el `ai_response` generado por el LLM loop NO se pierde.

**Estimación**: ~30 líneas de cambio por archivo, ~1.5h

**Verificación**: Tests de Fase 0 para tool transitions. E2E: PRESUPUESTO → `confirmar_presupuesto` → verificar transición a GATEWAY limpia.

---

### Fase 4: Fix Fallback Resets + Escalation

**Objetivo**: Que fallback resets realmente limpien context, y que escalation siempre establezca `current_mode`.

**Archivos a modificar**:
- `agent/fallback/fallback_handler.py`
- `agent/modes/consulta_mode.py` (~L263)
- `agent/modes/presupuesto_mode.py` (~L354)
- `agent/modes/expediente_mode.py` (~L735)

**Cambios**:

#### 4a. Fallback resets usan `Overwrite`

```python
# RESET_TO_MODE_START
if action == FallbackAction.RESET_TO_MODE_START:
    return {
        "ai_response": "Empecemos de nuevo...",
        "retry_state": create_empty_retry_state(),
        "mode_context": Overwrite({}),  # ← REALMENTE limpia
    }

# RESET_TO_CONSULTA — usar transition_mode()
if action == FallbackAction.RESET_TO_CONSULTA:
    updates = transition_mode(state, "CONSULTA_MODE")
    updates["ai_response"] = "Parece que nos hemos trabado..."
    return updates

# SAVE_DRAFT_AND_EXIT — usar transition_mode() (guarda draft automáticamente)
if action == FallbackAction.SAVE_DRAFT_AND_EXIT:
    updates = transition_mode(state, "CONSULTA_MODE")
    updates["ai_response"] = "He guardado tu progreso como borrador..."
    updates["draft_quote"] = state.get("mode_context", {}).get("tarifa_calculada")
    return updates
```

#### 4b. Validation escalation incluye `current_mode`

En los 3 archivos (consulta, presupuesto, expediente), donde se hace escalation por validation retries:

```python
# ANTES:
return {
    "ai_response": "...",
    "escalation_triggered": True,
    "escalation_reason": "max_validation_retries",
    "mode_context": mode_context,
}

# DESPUÉS:
return {
    "ai_response": "...",
    "current_mode": "ESCALATION",       # ← FIX H1
    "escalation_triggered": True,
    "escalation_reason": "max_validation_retries",
    "mode_context": mode_context,
}
```

**Estimación**: ~60 líneas de cambio, ~1.5h

**Verificación**: Tests de Fase 0 para fallback. Verificar en logs que escalation establece ESCALATION mode.

---

### Fase 5: Fix EXPEDIENTE Completion/Cancellation + Prompt Context

**Objetivo**: Que `finalizar_expediente` y `cancelar_expediente` desencadenen transición, y que los sub-modos de EXPEDIENTE reciban contexto en el prompt.

**Archivos a modificar**:
- `agent/modes/expediente_mode.py` (~L917-925) — extract_context completion/cancellation
- `agent/prompts/loader.py` (~L209) — format_mode_context para sub-modos
- `agent/router/mode_transitions.py` — añadir transiciones EXPEDIENTE → COMPLETED

**Cambios**:

#### 5a. Completion/Cancellation desencadenan transición

```python
# En _extract_context_from_tool():

# finalizar_expediente
if tool_name == "finalizar_expediente" and data.get("success"):
    updates["expediente_completed"] = True
    updates["_transition_to"] = "COMPLETED"  # ← NUEVO

# cancelar_expediente
if tool_name == "cancelar_expediente" and data.get("success"):
    updates["expediente_cancelled"] = True
    updates["_transition_to"] = "PRESUPUESTO_MODE"  # ← NUEVO (volver con context)
```

Añadir a `ALLOWED_TRANSITIONS`:
```python
"EXPEDIENTE_MODE": [
    "PRESUPUESTO_MODE",  # From review or cancellation
    "COMPLETED",          # ← NUEVO
    "ESCALATION",
],
```

Añadir a `CONTEXT_PRESERVE_RULES`:
```python
"EXPEDIENTE_MODE": {
    "PRESUPUESTO_MODE": [
        "element_codes",
        "tarifa_calculada",
        "categoria_slug",
    ],
    # COMPLETED no necesita preserve keys
},
```

#### 5b. Fix prompt context para sub-modos de EXPEDIENTE

```python
# En format_mode_context():

# ANTES:
elif mode == "EXPEDIENTE_MODE":
    ...

# DESPUÉS:
elif mode == "EXPEDIENTE_MODE" or mode.startswith("EXPEDIENTE_"):
    # Sub-modos de EXPEDIENTE también reciben contexto
    ...
```

**Estimación**: ~50 líneas de cambio, ~1.5h

**Verificación**: Tests para completion transition. Manual: completar expediente → verificar que no re-entra en EXPEDIENTE al siguiente mensaje. Verificar que sub-modos tienen contexto en prompt.

---

### Fase 6: Cleanup Dead Code + Ghost Keys

**Objetivo**: Eliminar código muerto y keys fantasma.

**Archivos a modificar**:
- `agent/state/conversation_state.py` — Eliminar `elementos_confirmados` y `quote_accepted` de ModeContextData (ghost keys nunca escritos)
- `agent/router/mode_transitions.py` — Eliminar `elementos_confirmados` de CONTEXT_PRESERVE_RULES
- `agent/modes/evaluacion_gateway.py` — Eliminar lectura de `precio_exacto` (nunca escrito)
- `agent/router/digression_manager.py` — Fix `sub_modo` → `expediente_sub_mode` en preserve keys

**Estimación**: ~20 líneas, ~30min

**Verificación**: Tests pasan. Grep confirma que las keys eliminadas no se usan en ningún otro lugar.

---

### Fase 7: ADR + Documentación

**Objetivo**: Documentar la decisión arquitectónica y actualizar AGENTS.md.

**Archivos a crear/modificar**:
- `docs/decisions/006-overwrite-transitions.md` — ADR
- `agent/AGENTS.md` — Actualizar sección de transiciones
- `docs/coding-standards/03-agent-architecture.md` — Añadir patrón de transición obligatorio

**Contenido del ADR**:
- Context: merge_dicts append-only, 17% de transiciones consistentes
- Decision: Usar `Overwrite` + `transition_mode()` para TODAS las transiciones
- Consequences: Context limpio, draft_contexts funcional, debugging más fácil

**Estimación**: ~1h

---

## Resumen de Fases

| Fase | Qué | Archivos | Líneas est. | Tiempo est. | Riesgo |
|------|-----|----------|-------------|-------------|--------|
| **0** | Tests de regresión | 1 nuevo | ~200 | 2h | NINGUNO |
| **1** | `Overwrite` en `transition_mode()` + contratos | 2 | ~40 | 1h | BAJO |
| **2** | Migrar Gateway | 1 | ~50 | 1h | MEDIO |
| **3** | Migrar Tool transitions | 2 | ~60 | 1.5h | MEDIO |
| **4** | Fix Fallback + Escalation | 4 | ~60 | 1.5h | BAJO |
| **5** | Fix Completion + Prompt context | 3 | ~50 | 1.5h | BAJO |
| **6** | Cleanup dead code | 4 | ~20 | 0.5h | BAJO |
| **7** | ADR + docs | 3 | ~100 | 1h | NINGUNO |
| **TOTAL** | | **~14 archivos** | **~580 líneas** | **~10h** | **MEDIO** |

---

## Orden de Ejecución

```
Fase 0 (tests) → Commit & verify
    ↓
Fase 1 (Overwrite) → Commit & run tests
    ↓
Fase 2 (Gateway) → Commit & deploy & E2E test
    ↓
Fase 3 (Tool transitions) → Commit & deploy & E2E test
    ↓
Fase 4 (Fallback + Escalation) → Commit & deploy
    ↓
Fase 5 (Completion + Prompts) → Commit & deploy & E2E test
    ↓
Fase 6 (Cleanup) → Commit
    ↓
Fase 7 (Docs) → Commit
    ↓
Git push (all phases)
```

**Cada fase es independiente y deployable** — si algo sale mal en Fase 3, podemos parar y las fases 0-2 siguen funcionando.

---

## Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|-----------|
| `Overwrite` rompe algo inesperado en LangGraph | BAJA | ALTO | Fase 0 tests lo detectan. Rollback = revert commit |
| Key faltante en preserve_rules rompe flujo | MEDIA | ALTO | Tests de Fase 0 validan keys esperadas. Audit completo de keys ya hecho |
| `transition_mode()` desde mode node causa conflicto con base_mode.process() | BAJA | MEDIO | base_mode.process() merge retry_state DESPUÉS de _process_message(). transition_mode() incluye retry_state. Necesario asegurar que transition_mode updates ganan |
| draft_contexts con Overwrite no persiste correctamente | BAJA | MEDIO | Test explícito en Fase 0 |
| EXPEDIENTE prompt context cambia comportamiento LLM | BAJA | BAJO | El contexto que se inyecta es factual (case_id, element_index). No cambia instrucciones |

---

## Criterios de Éxito

1. ✅ **100% de transiciones** pasan por `transition_mode()`
2. ✅ **mode_context limpio** después de cada transición (solo keys del modo destino + preservadas)
3. ✅ **draft_contexts funcional** — volver de GATEWAY a PRESUPUESTO restaura context
4. ✅ **Fallback resets efectivos** — RESET_TO_MODE_START realmente limpia
5. ✅ **Escalation completa** — siempre establece current_mode=ESCALATION
6. ✅ **EXPEDIENTE completion** — transiciona a COMPLETED
7. ✅ **Tests de regresión** — todos pasan después de cada fase
8. ✅ **E2E funcional** — flujo WhatsApp completo funciona
9. ✅ **ADR documentado** — decisión registrada para futuros desarrolladores

---

## Dependencias

- **LangGraph 1.0.8**: `Overwrite` confirmado disponible ✅
- **Redis checkpointer**: Compatible con `Overwrite` (LangGraph lo gestiona internamente) ✅
- **No requiere migración de DB**: Solo cambia lógica de Python ✅
- **No requiere cambios en admin panel**: Solo afecta al agente ✅

---

## Bugs Encontrados Durante Investigación (para referencia)

| ID | Bug | Severidad | Fase que lo arregla |
|----|-----|-----------|-------------------|
| C1 | mode_context append-only (merge_dicts) | CRÍTICO | Fase 1 (Overwrite) |
| C2 | Fallback reset es NO-OP | CRÍTICO | Fase 4 |
| C3 | Gateway bypass transition_mode() | CRÍTICO | Fase 2 |
| H1 | Escalation sin current_mode en 3 modos | ALTO | Fase 4 |
| H3 | expediente_completed/cancelled sin transición | ALTO | Fase 5 |
| H4 | draft_contexts.pop() inefectivo | ALTO | Fase 1 (Overwrite en draft_contexts) |
| H5 | mode_history deduplica (append_unique_list) | MEDIO | No se arregla ahora (minor) |
| M4 | digression preserva `sub_modo` en vez de `expediente_sub_mode` | MEDIO | Fase 6 |
| NEW | EXPEDIENTE sub-modos sin contexto en prompt | MEDIO | Fase 5 |
| NEW | `elementos_confirmados` ghost key (nunca escrito) | BAJO | Fase 6 |
| NEW | `quote_accepted` ghost key (nunca escrito) | BAJO | Fase 6 |
| NEW | `precio_exacto` leído pero nunca escrito | BAJO | Fase 6 |
