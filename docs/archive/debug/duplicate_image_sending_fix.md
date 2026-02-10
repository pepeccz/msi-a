# Duplicate Image Sending Fix - COLLECT_BASE_DOCS Phase

**Date**: 2026-01-31  
**Issue**: Agent sent base documentation example images twice in same turn  
**Root Cause**: LLM confusion between IDLE and COLLECT_BASE_DOCS prompts + missing guards  
**Status**: Fixed with 3-layer defense

---

## Problem Statement

### User Report

User "Pepe Cabeza Cruz" experienced duplicate image sending during COLLECT_BASE_DOCS phase:

**Turn 1**: User asks for examples
- User: "Me puedes ejemplos de las imagenes que te tengo que enviar ahora?"
- FSM State: `COLLECT_BASE_DOCS` (expediente already open)
- Agent calls: `enviar_imagenes_ejemplo(tipo="documentacion_base", categoria="motos-part")`
- Agent sends: 2 images (ficha técnica + permiso)
- **Follow-up message**: "¿Quieres que te abra el expediente para gestionar la homologación?" ← **WRONG**

**Turn 2**: User says "Si"
- User: "Si"
- FSM State: Still `COLLECT_BASE_DOCS`
- **LLM confusion**: Interprets "Si" as confirmation to open expediente (but it's already open!)
- Agent calls: `enviar_imagenes_ejemplo(tipo="documentacion_base", categoria="motos-part")` **AGAIN**
- Agent sends: Same 2 images again
- No FSM state change, conversation recovers

### Impact

- User confusion (saw same images twice)
- UX friction (unnecessary back-and-forth)
- Potential infinite loop if user keeps saying "yes"

---

## Root Cause Analysis

### Timeline Reconstruction

**Turn 1 Analysis**:
```
1. User asks for examples
2. LLM calls enviar_imagenes_ejemplo(tipo="documentacion_base")
3. Tool returns: {"success": True, "_pending_images": {...}}
4. Node extracts images, sends them
5. PROBLEM: Tool or LLM adds follow_up_message: "¿Quieres que abra expediente?"
   - This message makes NO SENSE in COLLECT_BASE_DOCS (expediente already open)
   - Likely LLM "mixed" IDLE prompt instructions with COLLECT_BASE_DOCS
```

**Turn 2 Analysis**:
```
1. User says "Si" (responding to confusing follow_up message)
2. LLM sees: COLLECT_BASE_DOCS + user said "si" + previous message asked about expediente
3. LLM confusion: Should I open expediente? But prompt says I'm in base docs phase...
4. LLM decides: Send images again (maybe user wants to see them again?)
5. Calls enviar_imagenes_ejemplo(tipo="documentacion_base") again
6. NO GUARD: Tool doesn't block duplicate call
7. Same images sent again
```

### Root Causes Identified

| # | Issue | Evidence | Layer Failed |
|---|-------|----------|--------------|
| 1 | **LLM prompt confusion** | IDLE prompt (line 104) says `follow_up_message="Quieres que abra expediente?"` for presupuesto type. LLM applied this to documentacion_base type. | Prompt (Layer 1) |
| 2 | **Missing FSM guard in tool** | `enviar_imagenes_ejemplo` didn't validate that `tipo="documentacion_base"` only callable from `COLLECT_BASE_DOCS`. | Tool guard (Layer 3) |
| 3 | **Missing duplicate prevention** | `tipo="documentacion_base"` had no duplicate send check (unlike `tipo="presupuesto"` which has `images_sent_for_current_quote`). | Tool logic |
| 4 | **No follow_up_message sanitization** | Tool accepted `follow_up_message` containing "expediente" even in COLLECT_BASE_DOCS phase. | Tool logic |

---

## Solution Implemented (3-Layer Defense)

### Layer 1: Tool Guard - FSM Phase Validation

**File**: `agent/tools/image_tools.py` (line ~420)

**Change**: Added FSM phase guard for `tipo="documentacion_base"`

```python
elif tipo == "documentacion_base":
    # FSM Guard: Only callable from COLLECT_BASE_DOCS (defense-in-depth)
    if state:
        fsm_state = state.get("fsm_state")
        current_step = get_current_step(fsm_state)
        if current_step != CollectionStep.COLLECT_BASE_DOCS:
            logger.warning(...)
            return tool_error_response(
                message="No puedes enviar imágenes de documentación base fuera de la fase de recolección.",
                error_category=ErrorCategory.FSM_STATE_ERROR,
                error_code="FSM_WRONG_PHASE_FOR_BASE_DOCS",
                guidance="Estás en '{current_step.value}'. Solo puedes enviar documentación base durante COLLECT_BASE_DOCS.",
            )
```

**Impact**: Blocks calls to `enviar_imagenes_ejemplo(tipo="documentacion_base")` from wrong phases (e.g., IDLE, COLLECT_PERSONAL).

---

### Layer 2: Tool Logic - follow_up_message Sanitization

**File**: `agent/tools/image_tools.py` (line ~435)

**Change**: Block inappropriate `follow_up_message` containing "expediente"

```python
# Sanitize follow_up_message: Block inappropriate messages about "expediente"
# The case is already open in COLLECT_BASE_DOCS, so asking about opening it is confusing
if follow_up_message and "expediente" in follow_up_message.lower():
    logger.warning(
        "[enviar_imagenes_ejemplo] Blocking inappropriate follow_up_message in COLLECT_BASE_DOCS",
        extra={"conversation_id": conversation_id, "blocked_message": follow_up_message}
    )
    follow_up_message = None  # Clear inappropriate message
```

**Impact**: Even if LLM passes a confusing follow_up, it gets stripped before sending to user.

---

### Layer 3: Duplicate Prevention - State Flag

**File**: `agent/tools/image_tools.py` (line ~450)

**Change**: Added duplicate prevention flag (like `images_sent_for_current_quote`)

```python
# PROTECTION: Check if base docs images were already sent (prevent duplicates)
if state and state.get("base_docs_images_sent"):
    logger.warning(...)
    return {
        "success": False,
        "message": (
            "Las imágenes de documentación base ya fueron enviadas anteriormente. "
            "NO las envíes de nuevo - el usuario ya las vio. "
            "Si el usuario dice 'listo', usa confirmar_documentacion_base()."
        ),
    }
```

**File**: `agent/nodes/conversational_agent.py` (line ~1210)

**Change**: Set flag after sending images

```python
elif tipo == "documentacion_base":
    state["base_docs_images_sent"] = True
    logger.info(
        f"[{tool_name}] Set base_docs_images_sent=True",
        extra={"conversation_id": conversation_id}
    )
```

**File**: `agent/nodes/conversational_agent.py` (line ~1555)

**Change**: Reset flag when entering COLLECT_BASE_DOCS phase

```python
# Reset image sent flags when entering certain phases
if new_step == "collect_base_docs":
    state["base_docs_images_sent"] = False
    logger.info(
        f"Reset base_docs_images_sent on phase transition to COLLECT_BASE_DOCS",
        extra={"conversation_id": conversation_id}
    )
```

**Impact**: Second call to `enviar_imagenes_ejemplo(tipo="documentacion_base")` returns error instead of sending images.

---

### Layer 4: Prompt Clarification

**File**: `agent/prompts/phases/collect_base_docs.md` (line ~20)

**Change**: Added explicit rule against `follow_up_message`

```markdown
**REGLA CRITICA: NO uses follow_up_message**

# ✅ CORRECTO
enviar_imagenes_ejemplo(tipo="documentacion_base", categoria="motos-part")

# ❌ INCORRECTO
enviar_imagenes_ejemplo(
    tipo="documentacion_base", 
    categoria="motos-part",
    follow_up_message="¿Quieres que abra expediente?"  # ❌ NUNCA
)

**¿Por qué?** El expediente ya está abierto. Preguntar confunde al usuario y al sistema.
```

**Impact**: Guides LLM to not add confusing follow_up messages in this phase.

---

## Defense Layer Summary

| Layer | Mechanism | File | Effectiveness |
|-------|-----------|------|---------------|
| **Prompt** | Explicit rule: NO follow_up_message | `collect_base_docs.md` | Soft (guides LLM) |
| **Tool Guard** | FSM phase check | `image_tools.py` | **Hard (blocks wrong phase)** |
| **Sanitization** | Strip "expediente" from follow_up | `image_tools.py` | **Hard (prevents confusion)** |
| **Duplicate Prevention** | `base_docs_images_sent` flag | `image_tools.py` + `conversational_agent.py` | **Hard (blocks duplicates)** |

**Total**: 4 defense layers (1 soft + 3 hard)

---

## Testing Recommendations

### Test Case 1: Duplicate Call (Same Turn)

**Setup**: FSM in COLLECT_BASE_DOCS, no images sent yet

**Actions**:
1. Call `enviar_imagenes_ejemplo(tipo="documentacion_base", categoria="motos-part")` → SUCCESS
2. Immediately call again → **BLOCKED**

**Expected**:
```json
{
  "success": false,
  "message": "Las imágenes de documentación base ya fueron enviadas anteriormente..."
}
```

### Test Case 2: Wrong Phase Call

**Setup**: FSM in IDLE (quotation phase)

**Actions**:
1. Call `enviar_imagenes_ejemplo(tipo="documentacion_base", categoria="motos-part")`

**Expected**:
```json
{
  "success": false,
  "error_category": "fsm_state_error",
  "error_code": "FSM_WRONG_PHASE_FOR_BASE_DOCS",
  "message": "No puedes enviar imágenes de documentación base fuera de la fase de recolección.",
  "guidance": "Estás en 'idle'. Solo puedes enviar documentación base durante COLLECT_BASE_DOCS."
}
```

### Test Case 3: follow_up_message Sanitization

**Setup**: FSM in COLLECT_BASE_DOCS

**Actions**:
1. Call `enviar_imagenes_ejemplo(tipo="documentacion_base", categoria="motos-part", follow_up_message="¿Quieres que abra expediente?")`

**Expected**:
- `follow_up_message` is **cleared** (set to None)
- Images sent without confusing follow-up
- Log warning: "Blocking inappropriate follow_up_message"

### Test Case 4: Flag Reset on Phase Transition

**Setup**: FSM in COLLECT_ELEMENT_DATA (last element)

**Actions**:
1. Complete last element → FSM transitions to COLLECT_BASE_DOCS
2. Call `enviar_imagenes_ejemplo(tipo="documentacion_base", ...)` → SUCCESS (flag was reset)

**Expected**:
- Images sent successfully (no "already sent" error)
- `base_docs_images_sent` set to True after sending

---

## Monitoring Queries

### Check Duplicate Image Sends

```sql
-- Find cases where enviar_imagenes_ejemplo was called multiple times with tipo=documentacion_base
SELECT 
  conversation_id,
  COUNT(*) as call_count,
  array_agg(created_at ORDER BY created_at) as timestamps
FROM tool_call_logs
WHERE tool_name = 'enviar_imagenes_ejemplo'
  AND parameters::text LIKE '%documentacion_base%'
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY conversation_id
HAVING COUNT(*) > 1
ORDER BY call_count DESC;
```

### Check Blocked Duplicate Calls (Success)

```sql
-- Count how many duplicate calls were successfully blocked
SELECT 
  COUNT(*) as blocked_count,
  COUNT(*) * 100.0 / NULLIF((
    SELECT COUNT(*) 
    FROM tool_call_logs 
    WHERE tool_name = 'enviar_imagenes_ejemplo'
      AND parameters::text LIKE '%documentacion_base%'
      AND created_at > NOW() - INTERVAL '7 days'
  ), 0) as block_rate_percentage
FROM tool_call_logs
WHERE tool_name = 'enviar_imagenes_ejemplo'
  AND parameters::text LIKE '%documentacion_base%'
  AND result_summary LIKE '%already sent%'
  AND created_at > NOW() - INTERVAL '7 days';
```

**Alert threshold**: If `call_count > 1` for same conversation_id AND block_rate < 80%, investigate prompt confusion.

---

## Changelog

| Date | File | Change | Lines |
|------|------|--------|-------|
| 2026-01-31 | `image_tools.py` | Add FSM guard for tipo=documentacion_base | +16 |
| 2026-01-31 | `image_tools.py` | Add follow_up_message sanitization | +10 |
| 2026-01-31 | `image_tools.py` | Add duplicate prevention check | +15 |
| 2026-01-31 | `conversational_agent.py` | Set base_docs_images_sent flag after send | +8 |
| 2026-01-31 | `conversational_agent.py` | Reset flag on phase transition | +6 |
| 2026-01-31 | `collect_base_docs.md` | Add follow_up_message warning | +17 |

**Total**: ~72 lines across 3 files

---

## Relationship to Phase 3 Fix

**Question**: Was this fixed by the Phase 3 FSM enforcement?

**Answer**: NO. Phase 3 (commit `273eff1`) addressed different issues:
- `COMPLETED` state tool mapping
- `iniciar_expediente` FSM guard
- `cancelar_expediente` availability in REVIEW_SUMMARY
- Dedicated COMPLETED phase prompt

**This fix addresses**:
- `enviar_imagenes_ejemplo` duplicate sends
- Wrong-phase calls for `tipo="documentacion_base"`
- Inappropriate `follow_up_message` sanitization

**Overlap**: Both use the same defense-in-depth pattern (Prompt + Tool Manager + Tool Guard), but protect different attack vectors.

---

**Generated by**: Root Cause Analysis Session  
**Reviewed by**: Architecture Team  
**Approved for**: Production Deployment  
**Risk Level**: Low (defensive guards, no breaking changes)
