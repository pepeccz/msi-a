# Plan: Fix Escalation System & Expediente Case Creation Stubs

**Date**: 2026-02-14
**Status**: PROPOSED
**Priority**: CRITICAL (production broken — escalations silently fail)
**Trigger**: Conversation 1 on 2026-02-14 — user "Pepe Cabeza Cruz" escalated to human but nobody was notified

---

## Executive Summary

During the v1→v2 migration, three critical systems were replaced with **non-functional stubs**:
1. `escalar_a_humano` tool — logs a message but does NOTHING (no Chatwoot, no DB)
2. `escalation_node` in the graph — returns a farewell message but does NOTHING
3. `_auto_create_case` — creates a Case but SKIPS critical initialization steps

All the **infrastructure** needed is already in place (Chatwoot client methods, `Escalation` DB model, `CaseElementData` model). The stubs just need to be replaced with real implementations, porting the battle-tested v1 code adapted to v2's architecture.

---

## Root Causes (5)

### RC-1: `escalar_a_humano` is a stub (CRITICAL)
- **File**: `agent/tools/shared_tools.py` (100 lines)
- **What it does**: Logs the call, returns a string "Escalación registrada correctamente"
- **What it should do** (from v1 at `archive/agent-v1/tools/tarifa_tools.py:222-488`):
  1. Duplicate escalation prevention (5-min window check)
  2. Disable bot in Chatwoot (`update_conversation_attributes(atencion_automatica=False)`)
  3. Add labels to Chatwoot conversation ("escalado", optionally "error-tecnico")
  4. Add private note in Chatwoot with context (type, reason, user, timestamp)
  5. Attempt team assignment in Chatwoot
  6. Save `Escalation` record to PostgreSQL
  7. Return `escalation_triggered=True` + `terminate_processing=True`

### RC-2: `escalation_node` is a stub
- **File**: `agent/graph/conversation_graph.py:415-443`
- **What it does**: Returns a farewell message, sets flags (`escalation_triggered`, etc.)
- **What it should do**: Actually trigger Chatwoot integration + save DB record
- **Impact**: When `FallbackAction.ESCALATE_TO_HUMAN` fires or panic button triggers, user sees "Espera un momento..." but nobody is notified.

### RC-3: `_auto_create_case` is incomplete
- **File**: `agent/modes/expediente_mode.py:281-445`
- **What it does**: Creates a `Case` row in DB with basic data
- **What it SKIPS compared to `iniciar_expediente` (case_tools.py:393-731)**:
  - ❌ Does NOT validate element codes against the category
  - ❌ Does NOT initialize `fsm_state` via `update_case_fsm_state()`
  - ❌ Does NOT obtain `base_doc_descriptions` from tarifa_service
  - ❌ Does NOT create `CaseElementData` rows (table is EMPTY for this case)
  - ❌ Does NOT return `fsm_state_update` that downstream tools expect
  - ❌ Does NOT provide imperative instructions message for the LLM

### RC-4: `iniciar_expediente` missing from EXPEDIENTE_MODE toolset
- **File**: `agent/modes/expediente_mode.py:1220-1254`
- **Impact**: When the LLM enters `collect_element_data` sub-mode and tries to call `iniciar_expediente` (because it doesn't know the case was auto-created), it gets "herramienta no encontrada" → escalation
- **Root issue**: `_auto_create_case` was supposed to make `iniciar_expediente` unnecessary, but it doesn't provide the same context/initialization

### RC-5: `FallbackAction.ESCALATE_TO_HUMAN` routes to stub `escalation_node`
- **File**: `agent/fallback/fallback_handler.py:356-368`
- **Impact**: When retry limits are exceeded, sets `current_mode: "ESCALATION"` which routes to the stub. No real escalation happens.
- **Fix**: Depends on fixing RC-2 (escalation_node)

---

## Solution Architecture

### Design Decisions

**D1: Centralize escalation logic in a shared service, not in tools or nodes**

Why: Both `escalar_a_humano` (tool) and `escalation_node` (graph node) need the same 5-step Chatwoot+DB logic. Duplicating it is a maintenance nightmare.

```
agent/services/escalation_service.py (NEW)
    ├── perform_escalation(conversation_id, user_id, reason, source, is_technical)
    │   ├── Step 1: Duplicate check (5-min window)
    │   ├── Step 2: Disable bot in Chatwoot
    │   ├── Step 3: Add labels
    │   ├── Step 4: Add private note
    │   ├── Step 5: Attempt team assignment
    │   └── Step 6: Save Escalation to DB
    │
    └── Used by:
        ├── escalar_a_humano tool (shared_tools.py)
        ├── escalation_node (conversation_graph.py)
        └── fallback_handler (indirectly via escalation_node)
```

**D2: Eliminate `_auto_create_case` — use `iniciar_expediente` properly**

Why: `_auto_create_case` is a half-baked copy. Instead of patching it, we should:
1. Keep `_auto_create_case` but make it **call `iniciar_expediente` internally** as a function (not as an LLM tool call)
2. Or: inject sufficient context into `mode_context` so the LLM knows the case exists and doesn't try to call `iniciar_expediente`

**Chosen approach**: Option 2 — enhance `_auto_create_case` to produce the SAME output as `iniciar_expediente`, including:
- `fsm_state` initialization via `update_case_fsm_state()`
- `base_doc_descriptions` from tarifa_service
- `CaseElementData` row creation
- Imperative instruction message in `mode_context["case_instructions"]`

Why not Option 1: `iniciar_expediente` has LLM-specific guards (phase check, state completeness) that don't apply when auto-creating internally. Calling it as a function would require bypassing those guards, which is fragile.

**D3: Don't add `iniciar_expediente` to `_get_element_data_tools()`**

Why: The case is already created by the time we reach `collect_element_data`. Adding `iniciar_expediente` would let the LLM try to create a SECOND case. Instead, we ensure `mode_context` contains enough context that the LLM knows the case exists and what to do next.

---

## Implementation Plan

### Phase 1: Escalation Service (CRITICAL — fixes RC-1, RC-2, RC-5)

**Priority**: HIGHEST — This is the "nobody gets notified" problem

#### Step 1.1: Create `agent/services/escalation_service.py`

Port from `archive/agent-v1/tools/tarifa_tools.py:222-488`, adapted to v2:

```python
# agent/services/escalation_service.py

async def perform_escalation(
    conversation_id: str,
    user_id: str | None,
    user_phone: str,
    reason: str,
    source: str = "tool_call",  # tool_call | auto | fallback | panic
    is_technical_error: bool = False,
) -> dict[str, Any]:
    """
    Execute the full 6-step escalation flow.
    
    Returns:
        Dict with success, escalation_id, message, duplicate_prevented
    """
```

**6 steps** (same as v1, adapted):
1. **Duplicate check**: Query `escalations` table for same `conversation_id` in last 5 minutes
2. **Disable bot**: `ChatwootClient().update_conversation_attributes(conv_id, {"atencion_automatica": False})`
3. **Add labels**: `ChatwootClient().add_labels(conv_id, ["escalado"])` (+ "error-tecnico" if applicable)
4. **Private note**: `ChatwootClient().add_private_note(conv_id, note_content)`
5. **Team assignment**: `ChatwootClient().assign_to_team(conv_id, team_id)` (best-effort)
6. **DB record**: Create `Escalation(id, conversation_id, user_id, reason, source, status="pending", metadata_={...})`

**Error handling**: Each step is independent. Steps 1-2 are critical (continue even if 3-5 fail). Step 6 is important but non-blocking.

**Dependencies**: 
- `shared/chatwoot_client.py` — methods already exist (verified: lines 284, 823, 876, 925)
- `database/models.py` — `Escalation` model exists (verified: line 2329)
- `shared/config.py` — `CHATWOOT_TEAM_GROUP_ID` setting exists

#### Step 1.2: Replace `escalar_a_humano` stub in `shared_tools.py`

Replace the current 100-line stub with a real implementation that calls `escalation_service.perform_escalation()`.

**Key changes**:
- Import and call `perform_escalation()` from the service
- Use `get_current_state()` to get `conversation_id`, `user_id`, `user_phone` (same pattern as v1)
- Return `escalation_triggered=True` and `terminate_processing=True`
- Keep the existing `EscalarAHumanoInput` Pydantic schema (it's good)

#### Step 1.3: Replace `escalation_node` stub in `conversation_graph.py`

Replace the current stub (lines 415-443) with a real implementation that calls `escalation_service.perform_escalation()`.

**Key changes**:
- Extract `conversation_id`, `user_id`, `user_phone` from state
- Extract `escalation_reason` from state (set by fallback handler or tool)
- Call `perform_escalation()` with `source="auto"` (or `source="fallback"` / `source="panic"`)
- Return existing state updates (`escalation_triggered`, `current_mode`, etc.) PLUS the service result

#### Step 1.4: Verify `fallback_handler.py` integration

The fallback handler (line 356-368) already sets `current_mode: "ESCALATION"` which routes to `escalation_node`. Once step 1.3 is done, this path works automatically. No code changes needed here.

**Verify**: The `escalation_reason` set by fallback (`retry_limit_X`) reaches `escalation_node` via state.

---

### Phase 2: Fix Case Auto-Creation (fixes RC-3, RC-4)

**Priority**: HIGH — This is the "LLM gets confused and escalates" problem

#### Step 2.1: Enhance `_auto_create_case` in `expediente_mode.py`

Add the missing initialization that `iniciar_expediente` provides:

**Missing pieces to add**:

1. **Element code validation** (optional, since these come from PRESUPUESTO which already validated):
   - Skip full validation but log a warning if codes look suspicious

2. **`fsm_state` initialization** via `update_case_fsm_state()`:
   ```python
   from agent.utils.fsm_compat import update_case_fsm_state, initialize_element_data_status
   
   new_fsm_state = update_case_fsm_state(state.get("fsm_state"), {
       "step": "collect_element_data",
       "case_id": str(case_id),
       "category_slug": categoria_slug,
       "category_id": category_id,
       "element_codes": element_codes,
       "current_element_index": 0,
       "element_phase": "photos",
       "element_data_status": initialize_element_data_status(element_codes),
       "base_docs_received": False,
       "base_doc_descriptions": base_doc_descriptions,
       "received_images": [],
       "tariff_tier_id": tier_id,
       "tariff_amount": tarifa_amount,
       "taller_propio": None,
       "taller_data": None,
       "retry_count": 0,
   })
   ```

3. **`base_doc_descriptions`** from tarifa_service:
   ```python
   from agent.services.tarifa_service import get_tarifa_service
   tarifa_service = get_tarifa_service()
   category_data = await tarifa_service.get_category_data(categoria_slug)
   base_doc_descriptions = []
   if category_data and category_data.get("base_documentation"):
       base_doc_descriptions = [bd["description"] for bd in category_data["base_documentation"]]
   ```

4. **`CaseElementData` row creation** (per element):
   ```python
   from database.models import CaseElementData
   for code in element_codes:
       element_data = CaseElementData(
           id=uuid.uuid4(),
           case_id=case_id,
           element_code=code,
           status="pending_photos",
           field_values={},
       )
       session.add(element_data)
   ```

5. **Imperative instructions** in `mode_context["case_instructions"]`:
   ```python
   context["case_instructions"] = (
       f"EXPEDIENTE CREADO AUTOMÁTICAMENTE. "
       f"Empezamos con el primer elemento: {first_element}.\n\n"
       "INSTRUCCIONES OBLIGATORIAS:\n"
       "1. Pregunta al usuario si quiere ver imágenes de ejemplo\n"
       "2. SOLO usa enviar_imagenes_ejemplo() si el usuario PIDE ver ejemplos\n"
       "3. Pide al usuario que envíe las fotos del elemento\n"
       "4. Cuando diga 'listo', usa confirmar_fotos_elemento()\n"
       "5. Luego recoge los datos técnicos con guardar_datos_elemento()\n"
       "6. Usa completar_elemento_actual() para pasar al siguiente\n\n"
       f"ELEMENTO ACTUAL: {first_element}\n"
       f"TOTAL ELEMENTOS: {len(element_codes)}"
   )
   ```

6. **Return `fsm_state` update** in the context dict so it propagates to graph state

#### Step 2.2: Inject `case_instructions` into the LLM prompt

In `_run_llm_loop` (or in the prompt assembly), check for `mode_context["case_instructions"]` and prepend it to the system prompt or user message so the LLM knows what to do.

**Where**: `expediente_mode.py` `_run_llm_loop` method, between building `system_prompt` and creating `llm_messages`.

#### Step 2.3: Ensure `_process_message` propagates `fsm_state` updates

When `_auto_create_case` returns the new context with `fsm_state`, this must be propagated to the graph state. Check that `_process_message` includes `fsm_state` in its return dict.

---

### Phase 3: Cleanup & Verification

#### Step 3.1: Remove "In production this will..." comments

Files to clean:
- `agent/tools/shared_tools.py` — remove stub comments (lines 73-77)
- `agent/graph/conversation_graph.py` — remove "(In production: triggers Chatwoot assignment)" comment (line 423)

#### Step 3.2: Add ADR

Create `docs/decisions/006-restore-escalation-integration.md`:
- Context: v2 migration left escalation as stubs
- Decision: Centralized `escalation_service.py` + restore full Chatwoot integration
- Consequences: All 3 escalation paths now functional

#### Step 3.3: Integration testing checklist

Manual verification needed (production system):

1. **Tool path**: Send "quiero hablar con una persona" → verify:
   - [ ] Escalation record created in `escalations` table
   - [ ] Chatwoot conversation has "escalado" label
   - [ ] Chatwoot conversation has private note
   - [ ] Bot disabled (`atencion_automatica=False`)

2. **Fallback path**: Trigger retry limit exceeded → verify same as above

3. **Auto-case creation**: User accepts budget → verify:
   - [ ] Case created in `cases` table
   - [ ] `CaseElementData` rows created
   - [ ] `fsm_state` properly initialized
   - [ ] LLM asks for photos of first element (doesn't try to call `iniciar_expediente`)

---

## Files to Modify

| File | Action | Lines affected |
|------|--------|---------------|
| `agent/services/escalation_service.py` | **CREATE** | ~150 lines (new file) |
| `agent/tools/shared_tools.py` | **REWRITE** | 100→120 lines (replace stub with real impl) |
| `agent/graph/conversation_graph.py` | **MODIFY** | Lines 415-443 (escalation_node) |
| `agent/modes/expediente_mode.py` | **MODIFY** | Lines 281-445 (_auto_create_case) + ~630 (_run_llm_loop) |
| `docs/decisions/006-restore-escalation-integration.md` | **CREATE** | ~50 lines |

### Files NOT modified (already correct)

| File | Why it's fine |
|------|---------------|
| `agent/fallback/fallback_handler.py` | Routes to `escalation_node` which we're fixing |
| `shared/chatwoot_client.py` | All 4 methods exist and work |
| `database/models.py` | `Escalation` model is complete |
| `agent/tools/case_tools.py` | `iniciar_expediente` stays as-is (used for manual case creation) |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Chatwoot API changes since v1 | Low | Medium | Methods are already in shared/chatwoot_client.py and used elsewhere |
| `update_conversation_attributes` fails | Medium | High | Step 2 is critical but service continues on failure (same pattern as v1) |
| Team assignment fails | High | Low | Expected — bot token may lack permission. Best-effort (same as v1) |
| `fsm_state` propagation breaks tools | Medium | High | Test with a real conversation after deploy |
| LLM still tries to call `iniciar_expediente` | Low | Medium | `case_instructions` in prompt explicitly tells LLM case is created |

---

## Execution Order

```
Phase 1 (CRITICAL — do first):
  1.1 Create escalation_service.py
  1.2 Replace shared_tools.py stub
  1.3 Replace escalation_node stub
  1.4 Verify fallback integration

Phase 2 (HIGH — do second):
  2.1 Enhance _auto_create_case
  2.2 Inject case_instructions into prompt
  2.3 Ensure fsm_state propagation

Phase 3 (CLEANUP — do last):
  3.1 Remove stub comments
  3.2 Create ADR-006
  3.3 Integration testing
```

**Estimated effort**: ~4 hours (2h Phase 1, 1.5h Phase 2, 0.5h Phase 3)

---

## Delegation Map

| Phase | Agent | Files |
|-------|-------|-------|
| 1.1-1.3 | **agent-dev** | `escalation_service.py`, `shared_tools.py`, `conversation_graph.py` |
| 2.1-2.3 | **agent-dev** | `expediente_mode.py` |
| 3.2 | **zanovix** | `docs/decisions/006-restore-escalation-integration.md` |
| 3.3 | **qa-dev** | Integration test checklist |

---

## Success Criteria

1. ✅ `escalar_a_humano` tool creates `Escalation` DB record
2. ✅ `escalar_a_humano` tool disables bot in Chatwoot
3. ✅ `escalar_a_humano` tool adds labels + private note in Chatwoot
4. ✅ `escalation_node` performs same Chatwoot+DB operations
5. ✅ `_auto_create_case` creates `CaseElementData` rows
6. ✅ `_auto_create_case` initializes `fsm_state` via `update_case_fsm_state()`
7. ✅ `_auto_create_case` obtains `base_doc_descriptions`
8. ✅ LLM in EXPEDIENTE_MODE knows case is created (doesn't call `iniciar_expediente`)
9. ✅ `escalations` table has records after escalation
10. ✅ No stub comments remain ("In production this will...")
11. ✅ Zero duplicate logic between `escalar_a_humano` tool and `escalation_node`
