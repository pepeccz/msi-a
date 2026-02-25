# Plan: Fix Critical Agent Bugs from Conversation 3 (2026-02-25)

> **Status**: ✅ Completed  
> **Created**: 2026-02-25  
> **Updated**: 2026-02-25  
> **Priority**: 🔴 High

---

## Resumen Ejecutivo

During a real customer conversation about homologating a solar panel on a motorhome (autocaravana), **4 critical bugs** were identified. The most severe is the **documentation hallucination** — the LLM invents documentation requirements because tariff/doc data is lost between turns. Additionally, the LLM bypasses `confirmar_presupuesto()` tool for EXPEDIENTE transition, invents variant options not in the database, and state resets unexpectedly mid-conversation. This plan addresses all 4 root causes with surgical fixes focused on the agent layer.

---

## Problema

### Contexto

A customer asked about homologating a placa solar (solar panel) on their autocaravana. The agent correctly identified the element and calculated the price, but subsequent turns exhibited:

1. **Invented documentation** — The LLM fabricated documentation requirements like "foto instalada y homologación original" that don't exist in the database
2. **No tool call for transition** — When user said "sí quiero iniciarlo" to start expediente, the LLM generated a text response asking for personal data WITHOUT calling `confirmar_presupuesto()`, so no Case was created and no mode transition occurred
3. **Invented variant option** — The LLM presented 3 options (A/B/C) for a variant question that only has 2 database-defined options
4. **State reset** — Between turns, mode reverted from PRESUPUESTO_MODE to START, causing re-identification with a different category

### Pain Points

- **P1**: Customer receives WRONG documentation instructions — compliance risk, trust damage
- **P2**: Customer data collected without expediente → data LOST forever (no Case in DB)
- **P3**: Customer chooses non-existent option C → agent confused, flow breaks
- **P4**: Customer has to repeat information after state reset → frustration, double pricing

### Requisitos de Negocio

- Agent must ONLY describe documentation from database fields (`documentacion.base`, `documentacion.elementos`, `imagenes_ejemplo[].descripcion`)
- Agent must call `confirmar_presupuesto()` before collecting expediente data
- Agent must present EXACTLY the variant options from the database (no more, no less)
- State must not reset mid-conversation without clear error handling

---

## Solución Propuesta

### Enfoque General

**4 targeted fixes**, all in the agent layer (no database or API changes needed):

| Fix | Root Cause | Approach | Files Changed |
|-----|-----------|----------|---------------|
| **Fix 1** | Doc data lost between turns | Persist documentation summary in `format_mode_context()` | `agent/prompts/loader.py` |
| **Fix 2** | LLM skips confirmar_presupuesto | Add constraint + prompt reinforcement | `agent/prompts/modes/presupuesto_mode.md`, `agent/services/constraint_service.py` |
| **Fix 3** | LLM invents variant options | Inject exact options into mode context | `agent/prompts/loader.py` |
| **Fix 4** | State reset mid-conversation | Add defensive logging + state recovery | `agent/graph/conversation_graph.py`, `agent/state/checkpointer.py` |

### Alternativas Consideradas

| Opción | Pros | Contras | Decisión |
|--------|------|---------|----------|
| **A: Fix `format_mode_context()` to include doc data** | Minimal change, data already in mode_context, permanent fix | Adds ~200 tokens to system prompt | ✅ Selected for Fix 1 |
| B: Store tool results in message history | Would fix all context loss | Massive token cost, compress_tool_result already truncates, complex refactor | ❌ Rejected |
| C: Create separate `obtener_documentacion_elemento` tool call per turn | Data always fresh from DB | Extra DB + LLM roundtrip per turn, agent may forget to call it | ❌ Rejected |
| **A: Add regex constraint for expediente transition** | Deterministic, already has constraint infra | New constraint type, needs DB seed | ✅ Selected for Fix 2 |
| B: Prompt-only reinforcement | No code change | LLM still free to ignore | ❌ Insufficient alone (but combined with A) |
| **A: Include exact variant options in mode context** | Deterministic, no LLM discretion on options | Slightly longer context | ✅ Selected for Fix 3 |
| B: Post-validate variant count | Catches error after the fact | UX damage already done (user sees wrong options) | ❌ Rejected |

### Decisiones Arquitectónicas

- **No new tools needed** — All fixes leverage existing data flows
- **No DB migration needed** — All data already exists, just not surfaced to LLM correctly
- **Constraint system reuse** — Fix 2 uses the existing `ResponseConstraint` mechanism
- **Token budget**: Fixes 1+3 add ~250 tokens to PRESUPUESTO_MODE context — acceptable given 4K context window

---

## Servicios Afectados

- [x] **Agent** (`agent/`) — Prompts, loader, constraint service, graph
- [ ] ~~API~~ — No changes
- [ ] ~~Admin Panel~~ — No changes
- [ ] ~~Database~~ — No migrations (constraint seed via script only)
- [ ] ~~Shared~~ — No changes

---

## Tareas por Servicio

### Agent → **agent-dev**

**Responsable**: agent-dev  
**Prioridad**: 1 (only service affected)

---

#### Fix 1: Persist Documentation Data in Mode Context (ROOT CAUSE 1 — CRITICAL)

**Problem**: `format_mode_context()` in `loader.py:189-193` only extracts the PRICE from `tarifa_calculada`, discarding ALL documentation data. On subsequent turns, the LLM has zero documentation context and hallucinates.

**Root code path**:
```
calcular_tarifa_con_elementos → returns {documentacion: {base: [...], elementos: [...]}, imagenes_ejemplo: [...]}
  → stored in mode_context["tarifa_calculada"] (line 756, presupuesto_mode.py)
    → format_mode_context() reads tarifa_calculada BUT only extracts precio (line 189-193, loader.py)
      → LLM sees "PRECIO: 59€ +IVA" — NO documentation info
        → LLM invents documentation on next turn
```

**Fix**: Modify `format_mode_context()` in `agent/prompts/loader.py` to extract and format documentation data from `tarifa_calculada`.

- [ ] **1a.** In `format_mode_context()` PRESUPUESTO_MODE section (after line 193), add extraction of `documentacion.base` and `documentacion.elementos` from `tarifa_calculada`
- [ ] **1b.** Format as compact text block: `DOCUMENTACIÓN BASE: [items]` + `DOCUMENTACIÓN POR ELEMENTO: [element]: [desc]`
- [ ] **1c.** Also extract `imagenes_ejemplo[].descripcion` to provide image descriptions (so LLM knows what photos exist without inventing)
- [ ] **1d.** Cap total documentation context at ~200 tokens to avoid bloating system prompt

**Implementation detail** for `agent/prompts/loader.py` (after line 193):

```python
# Documentation from tariff calculation (prevents hallucination)
tarifa = context.get("tarifa_calculada")
if tarifa and isinstance(tarifa, dict):
    # Extract base documentation
    doc = tarifa.get("documentacion", {})
    if isinstance(doc, dict):
        base_docs = doc.get("base", [])
        if base_docs:
            base_items = []
            for d in base_docs:
                if isinstance(d, dict):
                    base_items.append(d.get("nombre", d.get("name", str(d))))
                elif isinstance(d, str):
                    base_items.append(d)
            if base_items:
                parts.append(f"DOCUMENTACIÓN BASE REQUERIDA: {', '.join(base_items)}")
        
        elem_docs = doc.get("elementos", [])
        if elem_docs:
            parts.append("DOCUMENTACIÓN POR ELEMENTO:")
            for ed in elem_docs:
                if isinstance(ed, dict):
                    code = ed.get("codigo", ed.get("code", "?"))
                    desc = ed.get("descripcion", ed.get("description", "Foto del elemento con matrícula visible"))
                    parts.append(f"  - {code}: {desc}")
    
    # Image descriptions (so LLM knows what photos are available)
    imgs = tarifa.get("imagenes_ejemplo", [])
    if imgs:
        img_descs = []
        for img in imgs:
            if isinstance(img, dict):
                desc = img.get("descripcion", img.get("description", ""))
                if desc:
                    img_descs.append(desc)
        if img_descs:
            parts.append(f"FOTOS DE EJEMPLO DISPONIBLES: {'; '.join(img_descs)}")

    # Explicit anti-hallucination signal
    if doc or imgs:
        parts.append("⚠️ USA SOLO la documentación listada arriba. NO inventes requisitos adicionales.")
```

**Files**:
- `agent/prompts/loader.py` — Modify `format_mode_context()` (lines 189-193)

---

#### Fix 2: Force `confirmar_presupuesto()` for Expediente Transition (ROOT CAUSE 2)

**Problem**: When user confirms they want to proceed ("sí quiero iniciarlo"), the LLM generates a text response asking for personal data WITHOUT calling `confirmar_presupuesto()`. No Case is created in DB, no mode transition to EXPEDIENTE_MODE occurs, and all subsequently collected data is lost.

**Two-layer fix** (belt AND suspenders):

##### Layer A: Prompt Reinforcement

- [ ] **2a.** In `agent/prompts/modes/presupuesto_mode.md`, add explicit anti-pattern section near the transition rules:

```markdown
## TRANSICIÓN A EXPEDIENTE (OBLIGATORIO)

Cuando el usuario confirma que quiere proceder con el expediente:
- "Sí", "Quiero iniciarlo", "Dale", "Adelante", "Venga", "Opción B"

**DEBES** llamar a `confirmar_presupuesto()` ANTES de pedir datos personales.

### ❌ PROHIBIDO:
```
User: "Sí, quiero iniciarlo"
Bot: "¡Perfecto! Vamos a necesitar tus datos personales: nombre completo..."
```
↑ NUNCA pidas datos sin llamar a confirmar_presupuesto()

### ✅ CORRECTO:
```
User: "Sí, quiero iniciarlo"
→ confirmar_presupuesto()  ← PRIMERO
Bot: "¡Perfecto! Vamos a iniciar el expediente..."
```
```

**Files**:
- `agent/prompts/modes/presupuesto_mode.md` — Add transition anti-pattern section

##### Layer B: Constraint-Based Detection

- [ ] **2b.** Add a new constraint type `expediente_requires_tool` to detect when the LLM is asking for personal data (nombre, DNI, dirección, etc.) without having called `confirmar_presupuesto()` first
- [ ] **2c.** Add detection regex pattern: `(?:nombre completo|DNI|NIE|dirección|domicilio|datos personales|ficha técnica|permiso de circulación).*(?:necesit|proporcion|facilit|enví)`
- [ ] **2d.** Register constraint in the `_REGEX_ONLY_CONSTRAINTS` set (high precision regex, skip LLM confirmation)
- [ ] **2e.** Add skip condition: when `mode_context.get("current_mode") == "EXPEDIENTE_MODE"` (already transitioned, asking for data is correct)

**Implementation** in `agent/services/constraint_service.py`:

```python
# Add to _REGEX_ONLY_CONSTRAINTS:
_REGEX_ONLY_CONSTRAINTS: set[str] = {"price_requires_tool", "expediente_requires_tool"}

# Add skip condition in _should_skip_constraint():
if constraint_type == "expediente_requires_tool":
    # Skip if already in EXPEDIENTE mode (data collection is legitimate)
    if fsm_state.get("current_mode", "").startswith("EXPEDIENTE"):
        return True
    # Skip if confirmar_presupuesto was called this turn
    if "confirmar_presupuesto" in (fsm_state.get("tools_called_this_turn", []) or []):
        return True
```

- [ ] **2f.** Seed the constraint via a one-time script (no migration needed — ResponseConstraint already exists):

```python
# Script to add constraint (run manually or via seed)
constraint = ResponseConstraint(
    constraint_type="expediente_requires_tool",
    detection_pattern=r"(?:nombre completo|DNI|NIE|NIF|direcci[oó]n|domicilio|datos personales|ficha t[eé]cnica|permiso de circulaci[oó]n|necesitamos? tus datos).*",
    required_tool="confirmar_presupuesto",
    error_injection="ERROR: Debes llamar a confirmar_presupuesto() ANTES de pedir datos personales al usuario. El usuario ha confirmado que quiere proceder, llama a la herramienta ahora.",
    priority=90,
    is_active=True,
    category_id=None,  # Global constraint
)
```

**Files**:
- `agent/services/constraint_service.py` — Add constraint type + skip logic
- `database/seeds/` — Add seed script for new constraint (or inline in existing seeder)

---

#### Fix 3: Inject Exact Variant Options into Mode Context (ROOT CAUSE 3)

**Problem**: When `identificar_y_resolver_elementos` returns variant questions, the `question_hint` contains the question text but the LLM reformulates it and INVENTS additional options (e.g., Option C when only A and B exist in database).

**Fix**: In `format_mode_context()`, when rendering `pending_variants`, include the EXACT options from the database so the LLM must reproduce them verbatim.

- [ ] **3a.** Modify the pending variants section in `format_mode_context()` to include each variant's options (from `preguntas_variantes` or similar field):

```python
# Current (line 212-217):
variants = context.get("pending_variants", [])
if variants:
    parts.append("⚠️ VARIANTES PENDIENTES:")
    for v in variants:
        parts.append(f"  - {v.get('codigo_base', '?')}: {v.get('pregunta', '?')}")
    parts.append("USA seleccionar_variante_por_respuesta(), NO identificar_y_resolver_elementos()")

# New — include exact options:
variants = context.get("pending_variants", [])
if variants:
    parts.append("⚠️ VARIANTES PENDIENTES (reproduce las opciones EXACTAMENTE como aparecen):")
    for v in variants:
        code = v.get('codigo_base', '?')
        question = v.get('pregunta', '?')
        parts.append(f"  - {code}: {question}")
        # Include exact options from variant data
        opciones = v.get('opciones', [])
        if opciones:
            for i, opt in enumerate(opciones):
                label = chr(65 + i)  # A, B, C...
                nombre = opt.get('nombre', opt.get('name', str(opt)))
                parts.append(f"    Opción {label}: {nombre}")
            parts.append(f"    (SOLO {len(opciones)} opciones — NO inventes opciones adicionales)")
    parts.append("USA seleccionar_variante_por_respuesta(), NO identificar_y_resolver_elementos()")
```

- [ ] **3b.** Verify that `pending_variants` entries include option data. Check `_extract_context_from_tool()` in `presupuesto_mode.py` for the `identificar_y_resolver_elementos` handler — ensure variant options are stored, not just the question.

- [ ] **3c.** If variant options are NOT currently stored in `pending_variants`, modify `_extract_context_from_tool()` to include them from the tool result's `preguntas_variantes[].opciones` field.

**Files**:
- `agent/prompts/loader.py` — Modify `format_mode_context()` pending variants section
- `agent/modes/presupuesto_mode.py` — Possibly modify `_extract_context_from_tool()` to store variant options

---

#### Fix 4: State Reset Diagnosis + Defensive Recovery (ROOT CAUSE 4)

**Problem**: Between two turns (~90 seconds apart), the mode reset from PRESUPUESTO_MODE to START, causing the agent to re-identify elements with a potentially different category. Root cause is unclear — could be checkpointer failure, conversation_id mismatch, or Redis TTL issue.

**Approach**: Add defensive logging first to capture the root cause if it happens again, plus a lightweight recovery mechanism.

- [ ] **4a.** In `conversation_graph.py` `router_node()`, add logging when `current_mode` is empty/START but `mode_context` has data (indicates unexpected reset):

```python
# In router_node(), after reading state:
current_mode = state.get("current_mode", "")
mode_context = state.get("mode_context", {})

if (not current_mode or current_mode == "START") and mode_context:
    logger.warning(
        "unexpected_state_reset_detected",
        conversation_id=state.get("conversation_id"),
        mode_context_keys=list(mode_context.keys()),
        has_tarifa=bool(mode_context.get("tarifa_calculada")),
        has_categoria=bool(mode_context.get("categoria_slug")),
        message_count=state.get("message_count", 0),
    )
```

- [ ] **4b.** In `checkpointer.py`, add error logging when checkpoint read fails or returns empty (currently silent):

```python
# In get() method, log when checkpoint is None but conversation should have state:
async def get(self, config):
    thread_id = config["configurable"]["thread_id"]
    data = await self.redis.get(f"checkpoint:{thread_id}")
    if data is None:
        logger.info("checkpoint_miss", thread_id=thread_id)
    return ... 
```

- [ ] **4c.** Consider adding a lightweight state recovery: if `current_mode` is empty but `mode_context` contains `tarifa_calculada` and `categoria_slug`, auto-restore to PRESUPUESTO_MODE instead of falling to START. This is a safety net, not a fix for the underlying issue.

```python
# In router_node(), recovery attempt:
if (not current_mode or current_mode == "START") and mode_context:
    if mode_context.get("tarifa_calculada") and mode_context.get("categoria_slug"):
        logger.warning("auto_recovering_to_presupuesto", ...)
        current_mode = "PRESUPUESTO_MODE"
        # Return updated state
```

**Files**:
- `agent/graph/conversation_graph.py` — Add detection + recovery in `router_node()`
- `agent/state/checkpointer.py` — Add miss/error logging

---

## Dependencias entre Tareas

```
Fix 1 (doc context)  ─────────┐
Fix 3 (variant options) ──────┤─── All independent, can parallelize
Fix 2 (constraint) ───────────┤
Fix 4 (state reset logging) ──┘
```

**All 4 fixes are INDEPENDENT** — they modify different code paths and can be implemented in parallel. Suggested order by impact:

1. **Fix 1** (Documentation hallucination) — Highest impact, most customer-facing
2. **Fix 2** (Expediente transition) — Data loss risk
3. **Fix 3** (Variant options) — UX confusion
4. **Fix 4** (State reset) — Diagnostic + safety net

---

## Tests Requeridos

### Unit Tests

- [ ] **Fix 1**: Test `format_mode_context("PRESUPUESTO_MODE", context_with_tarifa)` includes documentation lines
- [ ] **Fix 1**: Test documentation extraction handles missing/empty/malformed `documentacion` field
- [ ] **Fix 2**: Test `_should_skip_constraint("expediente_requires_tool", ...)` returns True when in EXPEDIENTE_MODE
- [ ] **Fix 2**: Test constraint detects "necesito tus datos personales: nombre completo..." pattern
- [ ] **Fix 3**: Test `format_mode_context()` with pending_variants including `opciones` field renders exact options
- [ ] **Fix 3**: Test option count annotation ("SOLO 2 opciones") is present
- [ ] **Fix 4**: Test state recovery logic when mode="" but mode_context has tarifa data

### Integration Tests

- [ ] **Fix 1**: Simulate two-turn conversation: turn 1 calculates tarifa, turn 2 asks about documentation → verify LLM context contains doc data
- [ ] **Fix 2**: Simulate "sí quiero iniciarlo" after price → verify `confirmar_presupuesto` is enforced

### Criterios de Aceptación

- [ ] Coverage >90% for modified functions
- [ ] All existing tests pass
- [ ] Manual test: reproduce conversation 3 scenario → all 4 bugs resolved

---

## Criterios de Aceptación

### Funcional

- [ ] **CA-1**: When LLM describes documentation after price calculation, it ONLY uses data from `tarifa_calculada.documentacion` — NEVER invents requirements
- [ ] **CA-2**: When user confirms wanting to start expediente, agent calls `confirmar_presupuesto()` and transitions to EXPEDIENTE_MODE before asking for personal data
- [ ] **CA-3**: Variant questions present EXACTLY the options from the database (e.g., 2 options → only A and B, never C)
- [ ] **CA-4**: If state resets unexpectedly, agent auto-recovers to PRESUPUESTO_MODE when tarifa data exists in mode_context

### No Funcional

- [ ] **Performance**: System prompt size increases by ≤250 tokens for PRESUPUESTO_MODE
- [ ] **Security**: No new external data flows introduced
- [ ] **Reliability**: Constraint system fail-open behavior preserved (agent not blocked if constraint check fails)

---

## Checklist de Verificación Pre-Deploy

### Agent

- [ ] `format_mode_context()` tested with real tarifa_calculada data from aseicars-prof PLACA_SOLAR
- [ ] Constraint `expediente_requires_tool` seeded in production DB
- [ ] Prompt `presupuesto_mode.md` updated with anti-pattern for transition
- [ ] Pending variants format verified with real PLACA_SOLAR variant data
- [ ] State recovery logic has proper logging (not silent)
- [ ] All existing constraint tests still pass

### General

- [ ] ADR not needed (no architectural change, just data flow fix)
- [ ] Coding standards followed
- [ ] Skills updated if needed (`/sync-docs`) — likely NOT needed (bug fixes, no new patterns)

---

## Rollback Plan

### If Fix Breaks Agent

All fixes are in the agent service only:
1. **Immediate**: `docker-compose restart agent`
2. **Code**: Revert commits for specific fix
3. **Constraint**: Deactivate constraint via `UPDATE response_constraints SET is_active = false WHERE constraint_type = 'expediente_requires_tool'`
4. **Verify**: Check agent logs for normal operation

**Risk**: LOW — all fixes are additive (adding context data, adding constraints), not changing existing logic flow.

---

## Monitoreo Post-Deploy

### Métricas a Observar

- [ ] Agent logs for `unexpected_state_reset_detected` events
- [ ] Agent logs for `checkpoint_miss` events
- [ ] Constraint violation logs for `expediente_requires_tool`
- [ ] Token usage per turn in PRESUPUESTO_MODE (should increase by ≤250 tokens)

### Success Criteria (72h post-deploy)

- [ ] Zero documentation hallucination reports in new conversations
- [ ] All expediente transitions go through `confirmar_presupuesto()`
- [ ] No variant questions with incorrect option count
- [ ] State reset events logged (if any) with full diagnostic data

---

## Notas Adicionales

### References

- Conversation 3 (2026-02-25) — Source of all 4 bugs
- ADR-005: Tool-driven state management — Related pattern
- `docs/plans/active/fix-message-history-persistence.md` — Related (broader context loss issue)

### Riesgos Identificados

| Riesgo | Impacto | Probabilidad | Mitigación |
|--------|---------|--------------|------------|
| Documentation context too long → prompt overflow | Medium | Low | Cap at ~200 tokens, use compact format |
| Constraint false positive (detects legit doc question) | Medium | Low | Regex tuned for personal data keywords specifically |
| State recovery masks underlying bug | Low | Medium | Recovery logs WARNING, root cause investigation continues |
| Variant option format varies between categories | Medium | Low | Use defensive extraction with fallbacks |

### Deprioritized Items (NOT in this plan)

- **aseicars-part seed data** (PLACA_SOLAR missing variants) — Sergio confirmed this is not a priority, testing with aseicars-prof
- **Message history persistence** (broader issue) — Separate plan exists at `fix-message-history-persistence.md`
- **compress_tool_result truncation** — Systemic issue, separate scope

---

---

## Fix 5 — Documentation Query Routing (Added 2026-02-25)

**Issue**: Preguntas de documentación de un elemento específico sin presupuesto previo (e.g., "¿Qué documentación necesito para homologar mi placa solar?") eran clasificadas como `CONSULTA_GENERAL` → `CONSULTA_MODE`, que carece de las herramientas necesarias (`obtener_documentacion_elemento`, `calcular_tarifa_con_elementos`).

**Fix**: Añadido patrón keyword en `agent/router/intent_router.py` con confidence 0.85 (> 0.80 del broad catch de `CONSULTA_GENERAL`) para enrutar directamente a `PRESUPUESTO_DIRECTO` → `PRESUPUESTO_MODE`.

**Pattern**: `(qué documentación|qué documentos|qué fotos|qué requisitos) + (necesito|hay que|se requieren|hace falta)`

**LLM Prompt**: Actualizado `CLASSIFICATION_SYSTEM_PROMPT` para que el LLM también route documentación de elementos específicos → `PRESUPUESTO_DIRECTO`.

**File modified**: `agent/router/intent_router.py`

---

**Plan creado por**: Zanovix (architect mode)  
**Revisado por**: Pending  
**Aprobado por**: Pending  
**Completado**: 2026-02-25
**Completado**: —
