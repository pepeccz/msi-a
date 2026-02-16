# Plan: Fix Agent Mode Transitions & State Management

**Date**: 2026-02-09
**Status**: PROPOSED
**Priority**: CRITICAL — Production is broken
**Estimated effort**: ~400 lines of code changes across 8 files

---

## Executive Summary

The agent's core business flow (PRESUPUESTO → EVALUACION_GATEWAY → EXPEDIENTE) is **completely broken in production**. Users can get a price quote but **cannot proceed to open a formal case**. The root causes are:

1. **No mechanism exists** to transition from PRESUPUESTO_MODE to any other mode
2. **State race condition** corrupts `precio_comunicado` flag, causing repeated pricing
3. **Dual state management** (REFACTOR-001 `_internal_flags` vs legacy `_extract_context_from_tool`) creates conflicts
4. **Dead code** (3 ContextVars, VIABILIDAD_MODE reference) adds confusion

This plan addresses ALL issues with **root-cause fixes**, not patches.

---

## Problems Confirmed by Investigation

### P1: PRESUPUESTO → EVALUACION_GATEWAY transition is UNREACHABLE (CRITICAL)
- **Confirmed by**: investigator-dev agent (3 independent traces)
- **Root cause**: `presupuesto_mode._process_message()` NEVER returns `current_mode` in its result dict. No tool, no flag, no conditional edge can trigger this transition.
- **Impact**: 100% of users who want to open an expediente get stuck in an infinite loop
- **Compounding issue**: `iniciar_expediente` tool IS available in PRESUPUESTO and creates orphan Cases in DB without transitioning mode

### P2: `precio_comunicado` resets to False via stale `context_updates` (CRITICAL)
- **Confirmed by**: investigator-dev agent (line-by-line trace of data flow)
- **Root cause**: `context_updates` dict accumulates across all tool calls in a turn. When `identificar_y_resolver_elementos` sets `precio_comunicado=False`, that value persists in `context_updates` even after `calcular_tarifa_con_elementos` sets it to `True` via `_internal_flags`. The final merge `{**mode_context, **context_updates}` (line 428) overwrites True with stale False.
- **Impact**: Price recalculated every turn, extra latency, wasted tokens

### P3: `imagenes_enviadas` has TRIPLE write (HIGH)
- **Confirmed by**: audit agent
- Written in: (1) `_apply_tool_flags`, (2) hardcoded line 405, (3) `_extract_context_from_tool`
- Currently converges to correct value but fragile

### P4: EVALUACION_GATEWAY is dead code (MEDIUM)
- **Confirmed by**: All 3 agents independently
- Gateway works correctly internally but is never reached
- Will be activated by fixing P1

### P5: EXPEDIENTE_MODE doesn't process `_internal_flags` (MEDIUM)
- **Confirmed by**: audit agent
- Missing `_apply_tool_flags()` call means flags from tools are silently ignored

### P6: 3 ContextVars are dead code (LOW)
- `context_precio_comunicado`, `context_imagenes_enviadas`, `context_waiting_for_image_choice`
- Set in `_sync_contextvars_from_mode_context()` but NEVER read anywhere
- "Temporary during migration" comment — migration is done, cleanup forgotten

### P7: VIABILIDAD_MODE reference in digression_manager (LOW)
- Dead reference to removed mode in `digression_manager.py` line 69

---

## Architectural Decision: How Should Transitions Work?

### Decision: Tool-Driven Transition Signals + Mode Propagation

**Chosen approach**: Tools signal desired transitions via `_internal_flags`, and modes propagate them.

**Rationale**:
- Aligns with ADR-005 (tool-driven state management)
- Keeps transition validation in `mode_transitions.py` (whitelist respected)
- No new tools needed — existing tools get `_transition_to` flag
- Modes already have the propagation point (result dict)

**Rejected alternatives**:
- ❌ Router re-classification for active modes — Too complex, blurs responsibility
- ❌ New `solicitar_expediente()` tool — Adds tool proliferation without benefit
- ❌ Conditional edges in graph — LangGraph design says mode nodes → END (by design)

---

## Implementation Plan

### Phase 1: Unify State Management (Fix P2, P3, P6) — FOUNDATION

**Goal**: Eliminate the dual-write conflict. Single source of truth for flags.

**Principle**: `_internal_flags` from tools are the ONLY mechanism for flag management. `_extract_context_from_tool()` handles STRUCTURAL context (elements, categories, tariffs). Flags (`precio_comunicado`, `imagenes_enviadas`, etc.) are EXCLUSIVELY managed via `_internal_flags`.

#### Step 1.1: Remove flag writes from `_extract_context_from_tool()` in presupuesto_mode.py

**File**: `agent/modes/presupuesto_mode.py`

In `_extract_context_from_tool()`:
- For `identificar_y_resolver_elementos` (line 581): REMOVE `updates["precio_comunicado"] = False` and `updates["imagenes_enviadas"] = False`
- These resets should be done via `_internal_flags` in the tool itself

#### Step 1.2: Add `_internal_flags` to `identificar_y_resolver_elementos`

**File**: `agent/tools/element_tools.py`

The tool should return `_internal_flags` that resets pricing state when re-identifying:
```python
"_internal_flags": {
    "precio_comunicado": False,
    "imagenes_enviadas": False,
    "waiting_for_image_choice": False,
}
```

This makes the intent EXPLICIT in the tool itself (not hidden in mode logic).

#### Step 1.3: Remove triple-write for `imagenes_enviadas` in presupuesto_mode.py

**File**: `agent/modes/presupuesto_mode.py`

- REMOVE hardcoded `context_updates["imagenes_enviadas"] = True` on line 405
- REMOVE `updates["imagenes_enviadas"] = True` from `_extract_context_from_tool()` for `enviar_imagenes_ejemplo` (line 639)
- `enviar_imagenes_ejemplo` already returns `_internal_flags: {imagenes_enviadas: True}` — that's sufficient

#### Step 1.4: Give `_internal_flags` FINAL authority in the merge

**File**: `agent/modes/presupuesto_mode.py`

In `_process_message()`, accumulate all applied flags during the turn:
```python
# Before the loop (around line 258):
all_applied_flags: dict[str, Any] = {}

# Inside the loop, after _apply_tool_flags (around line 388):
flags = result_dict.get("_internal_flags", {})
all_applied_flags.update(flags)

# After the loop, FINAL merge (replace line 428):
updated_context = {**mode_context, **context_updates}
# Flags ALWAYS win over stale context_updates
for key in all_applied_flags:
    if key in updated_context:
        updated_context[key] = all_applied_flags[key]
```

This is a belt-and-suspenders fix: even if some stale value leaks into `context_updates`, the flags from tools have final authority.

#### Step 1.5: Remove dead ContextVars and sync function

**File**: `agent/state/conversation_state.py`
- REMOVE `context_precio_comunicado`, `context_imagenes_enviadas`, `context_waiting_for_image_choice` (lines 31-39)

**File**: `agent/modes/presupuesto_mode.py`
- REMOVE `_sync_contextvars_from_mode_context()` function (lines 52-74)
- REMOVE all calls to `_sync_contextvars_from_mode_context()` (lines 139, 409)
- REMOVE import of context vars from conversation_state (line 62-66)

**File**: `agent/tools/image_tools.py`
- Verify it reads from `_current_state` ContextVar (the full state), NOT from the dedicated ContextVars — CONFIRMED, no changes needed

#### Step 1.6: Remove VIABILIDAD_MODE reference

**File**: `agent/router/digression_manager.py`
- Remove "VIABILIDAD_MODE" from any target mode references (line 69)

---

### Phase 2: Implement Mode Transition Mechanism (Fix P1, P4) — CORE FIX

**Goal**: Enable PRESUPUESTO_MODE to transition to EVALUACION_GATEWAY, and EVALUACION_GATEWAY to transition to EXPEDIENTE_MODE.

#### Step 2.1: Add `_transition_to` support in `_apply_tool_flags()`

**File**: `agent/modes/presupuesto_mode.py`

Modify `_apply_tool_flags()` to recognize `_transition_to` as a special flag:
```python
def _apply_tool_flags(mode_context, tool_result, logger):
    # ... existing parsing ...
    flags = tool_result.get("_internal_flags", {})
    
    # Separate transition signal from context flags
    transition_to = flags.pop("_transition_to", None)
    if transition_to:
        mode_context["_transition_to"] = transition_to
        logger.info("transition_signal_received", target=transition_to)
    
    # Apply remaining flags
    mode_context.update(flags)
    # ... existing sync ...
```

#### Step 2.2: Propagate `_transition_to` in `_process_message()` result

**File**: `agent/modes/presupuesto_mode.py`

After the tool loop, in the result building section (around line 430):
```python
result_dict: dict[str, Any] = {
    "ai_response": ai_response,
    "mode_context": updated_context,
    "retry_state": retry_state,
}

# Propagate mode transition if signaled by a tool
transition_target = updated_context.pop("_transition_to", None)
if transition_target:
    # Validate transition
    from agent.router.mode_transitions import validate_transition
    allowed, reason = validate_transition("PRESUPUESTO_MODE", transition_target)
    if allowed:
        result_dict["current_mode"] = transition_target
        self._logger.info(
            "mode_transition_from_tool",
            target=transition_target,
            conversation_id=conversation_id,
        )
    else:
        self._logger.warning(
            "mode_transition_blocked",
            target=transition_target,
            reason=reason,
        )
```

#### Step 2.3: Remove `iniciar_expediente` from PRESUPUESTO_MODE tools

**File**: `agent/modes/presupuesto_mode.py`

In `_get_presupuesto_tools()` (line 720):
- REMOVE `iniciar_expediente` from the tool list
- This tool should ONLY be available in EXPEDIENTE_MODE (where it belongs)
- The prompt already says "❌ NO inicies expediente directamente — pasa por EVALUACION_GATEWAY"

**Reasoning**: The `iniciar_expediente` tool creates a Case in the DB, which should only happen AFTER the user confirms in EVALUACION_GATEWAY and the agent transitions to EXPEDIENTE_MODE. Having it in PRESUPUESTO creates orphan cases.

#### Step 2.4: Add transition-signaling tool `confirmar_presupuesto`

**File**: `agent/tools/element_tools.py` (or new file `agent/tools/transition_tools.py`)

Create a lightweight tool that signals the transition:
```python
@tool
async def confirmar_presupuesto() -> dict[str, Any]:
    """
    Confirma que el usuario quiere proceder con el presupuesto y abrir expediente.
    
    Usa esta herramienta cuando el usuario diga que quiere iniciar el expediente,
    abrir el caso, o confirme el presupuesto con palabras como "dale", "sí", 
    "adelante", "perfecto", etc.
    
    Returns:
        Dict con confirmación y señal de transición.
    """
    state = get_current_state()
    mode_context = state.get("mode_context", {}) if state else {}
    
    # Verify price was communicated
    if not mode_context.get("precio_comunicado"):
        return {
            "success": False,
            "message": "No se puede iniciar expediente sin haber comunicado el precio primero.",
            "error": "PRICE_NOT_COMMUNICATED",
        }
    
    tarifa = mode_context.get("tarifa_calculada", {})
    element_codes = mode_context.get("element_codes", [])
    
    return {
        "success": True,
        "message": (
            "Perfecto, vamos a iniciar el expediente. "
            "Te voy a pedir confirmación antes de empezar."
        ),
        "tarifa_resumen": {
            "precio": tarifa.get("datos", {}).get("price") if isinstance(tarifa, dict) else None,
            "elementos": element_codes,
        },
        "_internal_flags": {
            "_transition_to": "EVALUACION_GATEWAY",
        },
    }
```

#### Step 2.5: Add `confirmar_presupuesto` to PRESUPUESTO_MODE tools

**File**: `agent/modes/presupuesto_mode.py`

In `_get_presupuesto_tools()`:
- ADD `confirmar_presupuesto` (replaces `iniciar_expediente`)

#### Step 2.6: Update PRESUPUESTO_MODE prompt

**File**: `agent/prompts/modes/presupuesto_mode.md`

Update the prompt to instruct the LLM:
- When user confirms they want to proceed → call `confirmar_presupuesto()`
- DO NOT call `iniciar_expediente` (it's no longer available)
- The gateway will handle the formal confirmation

#### Step 2.7: Verify EVALUACION_GATEWAY → EXPEDIENTE_MODE works

**File**: `agent/modes/evaluacion_gateway.py`

ALREADY WORKS — `_handle_yes()` returns `{"current_mode": "EXPEDIENTE_MODE"}` (line 186).
`BaseModeNode.process()` propagates this to state.

**Verify**: That `BaseModeNode.process()` correctly propagates `current_mode` from mode result to graph state. 
Read base_mode.py `process()` method to confirm.

#### Step 2.8: Ensure context preservation through transitions

**File**: `agent/router/mode_transitions.py`

Already has `CONTEXT_PRESERVE_RULES` for PRESUPUESTO → EVALUACION_GATEWAY and EVALUACION_GATEWAY → EXPEDIENTE_MODE. Verify these keys are correct:
- `elementos_confirmados`, `element_codes`, `tarifa_calculada`, `categoria_slug`

**Also verify**: That `transition_mode()` in `conversation_state.py` correctly applies these rules.

---

### Phase 3: Fix EXPEDIENTE_MODE Gaps (Fix P5) — HARDENING

**Goal**: Ensure EXPEDIENTE_MODE correctly processes tool flags and handles transitions.

#### Step 3.1: Add `_apply_tool_flags()` to EXPEDIENTE_MODE

**File**: `agent/modes/expediente_mode.py`

Import and use `_apply_tool_flags` in the tool processing loop (same pattern as PRESUPUESTO_MODE).

#### Step 3.2: Add `_transition_to` propagation to EXPEDIENTE_MODE

**File**: `agent/modes/expediente_mode.py`

Same pattern as Phase 2, Step 2.2 — check for `_transition_to` in mode_context and propagate to result dict.

#### Step 3.3: Handle unprocessed tool results in `_extract_context_from_tool()`

**File**: `agent/modes/expediente_mode.py`

Add handlers for:
- `editar_expediente` → could signal transition to PRESUPUESTO_MODE
- `finalizar_expediente` → should signal COMPLETED state

---

### Phase 4: Clean Orphan Cases — DATA FIX

**Goal**: Clean up Cases created by `iniciar_expediente` that never progressed.

#### Step 4.1: SQL cleanup query

```sql
-- Find orphan cases (created but never progressed past "collecting" with no data)
SELECT id, conversation_id, created_at, status
FROM cases 
WHERE status = 'collecting' 
AND metadata_->>'started_at' IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM case_images WHERE case_images.case_id = cases.id
)
ORDER BY created_at DESC;

-- Mark as cancelled (soft delete)
UPDATE cases SET status = 'cancelled', updated_at = NOW()
WHERE id IN (/* orphan IDs from above */);
```

---

### Phase 5: Testing — VERIFICATION

#### Step 5.1: Unit tests for state management

**File**: `tests/test_presupuesto_state.py` (new)

Test scenarios:
1. `identificar` + `calcular_tarifa` in same turn → `precio_comunicado` must be True
2. `calcular_tarifa` alone → `precio_comunicado` must be True
3. `identificar` alone → `precio_comunicado` must be False
4. `enviar_imagenes_ejemplo` → `imagenes_enviadas` must be True (single source)

#### Step 5.2: Integration tests for mode transitions

**File**: `tests/test_mode_transitions.py` (new)

Test scenarios:
1. PRESUPUESTO → `confirmar_presupuesto()` → state has `current_mode: "EVALUACION_GATEWAY"`
2. EVALUACION_GATEWAY + "dale" → state has `current_mode: "EXPEDIENTE_MODE"`
3. EVALUACION_GATEWAY + "no" → state has `current_mode: "PRESUPUESTO_MODE"`
4. PRESUPUESTO without price → `confirmar_presupuesto()` returns error

#### Step 5.3: End-to-end conversation test

**File**: `tests/test_e2e_presupuesto_to_expediente.py` (new)

Simulate the full flow:
1. "Quiero homologar el subchasis de mi moto"
2. Agent identifies element, calculates price
3. User says "Dale" (or "Opción B")
4. Agent transitions to EVALUACION_GATEWAY
5. Gateway asks confirmation
6. User says "Sí"
7. Agent transitions to EXPEDIENTE_MODE
8. Verify case created correctly

---

## File Change Summary

| File | Changes | Phase |
|------|---------|-------|
| `agent/modes/presupuesto_mode.py` | Remove flag writes from `_extract_context_from_tool`, add `all_applied_flags`, remove ContextVar sync, add transition propagation, remove `iniciar_expediente` from tools, add `confirmar_presupuesto` | 1, 2 |
| `agent/tools/element_tools.py` | Add `_internal_flags` to `identificar_y_resolver_elementos`, add `confirmar_presupuesto` tool | 1, 2 |
| `agent/state/conversation_state.py` | Remove 3 dead ContextVars | 1 |
| `agent/tools/image_tools.py` | Verify no reads from dead ContextVars (no changes expected) | 1 |
| `agent/router/digression_manager.py` | Remove VIABILIDAD_MODE reference | 1 |
| `agent/prompts/modes/presupuesto_mode.md` | Update instructions for `confirmar_presupuesto` | 2 |
| `agent/modes/expediente_mode.py` | Add `_apply_tool_flags()`, add transition propagation | 3 |
| `tests/test_presupuesto_state.py` | New — state management tests | 5 |
| `tests/test_mode_transitions.py` | New — transition tests | 5 |
| `tests/test_e2e_presupuesto_to_expediente.py` | New — e2e flow test | 5 |

---

## Execution Order

```
Phase 1 (Foundation) ──→ Phase 2 (Core Fix) ──→ Phase 3 (Hardening) ──→ Phase 4 (Data) ──→ Phase 5 (Tests)
     ↑                         ↑                        ↑
 MUST be first           Depends on Phase 1       Independent
 (fixes state bugs       (uses unified flags     (can be parallel
  that Phase 2 needs)     for transitions)        with Phase 4)
```

**Phases 1+2 are the MINIMUM viable fix.** Phases 3-5 are important but can follow.

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Removing `iniciar_expediente` from PRESUPUESTO breaks LLM behavior | LLM tries to call removed tool → error | Update system prompt FIRST, test with new prompt |
| `confirmar_presupuesto` tool not called by LLM | User can't proceed | Make tool description very clear, test with real conversations |
| EVALUACION_GATEWAY too many questions | UX friction (extra turn) | Gateway is lightweight (~1s), provides useful confirmation |
| Context lost during PRESUPUESTO → GATEWAY transition | Missing price/elements in EXPEDIENTE | Verify `CONTEXT_PRESERVE_RULES` has all needed keys |
| Orphan Cases in DB cause confusion | Duplicate expedientes | Phase 4 cleanup + add guard in `iniciar_expediente` |

---

## ADR Required

This plan should be documented as:
- **ADR-006: Unify tool-driven state management and mode transitions**
- Key decisions: Single flag management via `_internal_flags`, `_transition_to` pattern for mode changes, removal of dead ContextVars

---

## Success Criteria

1. ✅ User says "Quiero homologar X" → gets price → says "Dale" → reaches EVALUACION_GATEWAY
2. ✅ In EVALUACION_GATEWAY, user says "Sí" → transitions to EXPEDIENTE_MODE
3. ✅ `precio_comunicado` remains True after `calcular_tarifa` (verified by test)
4. ✅ No orphan Cases created (iniciar_expediente removed from PRESUPUESTO)
5. ✅ Images not re-sent after confirmation
6. ✅ No dead ContextVars in codebase
7. ✅ All tests pass
