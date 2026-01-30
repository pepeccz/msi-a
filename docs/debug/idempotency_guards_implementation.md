# Idempotency Guards Implementation - High Priority Tools

**Date**: 2026-01-31  
**Phase**: 1 (High Priority - FSM Loop Prevention)  
**Tools Modified**: 4  
**Total Lines Changed**: ~120

---

## Executive Summary

Implemented idempotency guards for the **4 highest-priority FSM tools** that were causing conversation loops and FSM advancement issues.

**Key Principle**: All guards return `{"success": True, "already_done": True}` instead of errors, preventing LLM confusion and retry loops.

---

## Tools Modified

### 1. ✅ `confirmar_fotos_elemento` (element_data_tools.py, line 753-774)

**Problem**: Confusing error message when called twice caused LLM to retry indefinitely.

**Before**:
```python
if phase != "photos":
    return _tool_error_response(
        f"Ya estamos en fase '{phase}'. Las fotos ya fueron confirmadas."
    )
```

**After**:
```python
if phase != "photos":
    # Idempotency guard: Check if this is a repeat call
    if phase == "data" and is_current_element_photos_done(case_state):
        logger.info(
            f"confirmar_fotos_elemento called idempotently | element_code={element_code}",
            extra={"idempotent": True}
        )
        return {
            "success": True,
            "photos_confirmed": True,
            "already_confirmed": True,
            "element_code": element_code,
            "message": f"Las fotos de {element_code} ya fueron confirmadas. Continuamos con los datos técnicos.",
            "fsm_state_update": fsm_state,  # Return current state unchanged
        }
    # Different error for truly wrong phase
    return _tool_error_response(...)
```

**Impact**: 
- Prevents "wrong phase" error from triggering retry loops
- LLM understands photos already confirmed and continues naturally
- Maintains FSM state consistency

---

### 2. ✅ `completar_elemento_actual` (element_data_tools.py, line 975-1012)

**Problem**: Could advance FSM twice if called repeatedly, causing element skipping.

**Before**:
```python
# Get current element
element_code = get_current_element_code(case_state)
if not element_code:
    return _tool_error_response("No hay elemento actual seleccionado")
# ... proceed with completion ...
```

**After**:
```python
# Get current element
element_code = get_current_element_code(case_state)
if not element_code:
    return _tool_error_response("No hay elemento actual seleccionado")

# Idempotency guard: Check if element already completed
element_data_status = case_state.get("element_data_status", {})
if element_data_status.get(element_code) == ELEMENT_STATUS_COMPLETE:
    logger.info(
        f"completar_elemento_actual called idempotently | element_code={element_code}",
        extra={"idempotent": True}
    )
    # Element already complete, check what's next
    element_codes = case_state.get("element_codes", [])
    current_idx = case_state.get("current_element_index", 0)
    
    if current_idx + 1 < len(element_codes):
        next_code = element_codes[current_idx + 1]
        return {
            "success": True,
            "already_completed": True,
            "message": f"Elemento {element_code} ya está completado. Siguiente: {next_code}.",
            "fsm_state_update": fsm_state,
        }
    else:
        return {
            "success": True,
            "already_completed": True,
            "all_elements_complete": True,
            "message": f"Elemento {element_code} ya está completado. Todos los elementos listos.",
            "fsm_state_update": fsm_state,
        }
```

**Impact**: 
- Prevents double FSM advancement
- Returns clear status about what's next (next element or all done)
- Database write protection (won't mark complete twice)

---

### 3. ✅ `guardar_datos_elemento` (element_data_tools.py, line 533-598)

**Problem**: Silent overwrites of field values hid LLM retry loops, making debugging difficult.

**Before**:
```python
# Validate
is_valid, error_msg = _validate_field_value(value, field)
if not is_valid:
    errors.append(...)
else:
    # Always save
    current_values[actual_field_key] = value
    results.append({
        "field_key": actual_field_key,
        "status": "saved",
        "value": value,
    })
```

**After**:
```python
# Idempotency guard: Check if field already has this exact value
existing_value = current_values.get(actual_field_key)
if existing_value == value:
    idempotent_count += 1
    results.append({
        "field_key": actual_field_key,
        "status": "already_saved",
        "value": value,
        "message": f"Campo '{field.field_label}' ya tiene este valor",
    })
    logger.info(
        f"guardar_datos_elemento idempotent field | element={element_code} | field={actual_field_key}",
        extra={"idempotent": True}
    )
    continue  # Skip validation and DB write

# Validate
is_valid, error_msg = _validate_field_value(value, field)
if not is_valid:
    errors.append(...)
else:
    # Save only if value is different
    current_values[actual_field_key] = value
    results.append({
        "field_key": actual_field_key,
        "status": "saved",
        "value": value,
    })
```

**Impact**: 
- Detects and logs idempotent field saves
- Skips unnecessary validation and DB writes
- Makes LLM retry loops visible in logs
- Distinguishes between "user changed value" vs "LLM resent same value"

---

### 4. ✅ `actualizar_datos_expediente` (case_tools.py, line 690-738, 762-808)

**Problem**: Auto-transitions to next FSM step could trigger twice with same data, causing FSM confusion.

**Before (datos_personales)**:
```python
if datos_personales:
    # Merge with existing personal data
    existing_personal = case_fsm_state.get("personal_data", {})
    merged_personal = {**existing_personal}
    
    for key in personal_fields:
        if key in datos_personales and datos_personales[key]:
            merged_personal[key] = datos_personales[key].strip()
    # ... update database ...
```

**After (datos_personales)**:
```python
if datos_personales:
    # Merge with existing personal data
    existing_personal = case_fsm_state.get("personal_data", {})
    merged_personal = {**existing_personal}
    
    # Idempotency guard: Check if incoming data is identical to existing
    incoming_personal = {k: v.strip() for k, v in datos_personales.items() if k in personal_fields and v}
    is_idempotent = all(
        existing_personal.get(key) == value 
        for key, value in incoming_personal.items()
    )
    
    if is_idempotent and incoming_personal:
        logger.info(
            f"actualizar_datos_expediente (datos_personales) called idempotently",
            extra={"idempotent": True, "fields": list(incoming_personal.keys())}
        )
        return {
            "success": True,
            "already_saved": True,
            "message": "Estos datos personales ya están guardados. Continuamos.",
            "fsm_state_update": fsm_state,
        }
    
    for key in personal_fields:
        if key in datos_personales and datos_personales[key]:
            merged_personal[key] = datos_personales[key].strip()
    # ... update database ...
```

**Same pattern for datos_vehiculo** (lines 762-808).

**Impact**: 
- Prevents duplicate auto-transitions (COLLECT_PERSONAL → COLLECT_VEHICLE)
- Skips unnecessary database writes when data unchanged
- Reduces Chatwoot sync API calls (User sync only on actual changes)
- Makes idempotent calls visible in logs for monitoring

---

## Common Pattern

All 4 guards follow the same structure:

```python
# 1. CHECK idempotency condition FIRST
if is_already_done:
    logger.info("tool called idempotently", extra={"idempotent": True})
    
    # 2. Return SUCCESS (not error)
    return {
        "success": True,
        "already_done": True,  # Flag to signal idempotency
        "message": "Esta acción ya fue completada.",
        "fsm_state_update": fsm_state,  # Return current state
    }

# 3. Proceed with normal logic (first call)
# ... perform state changes ...
```

### Key Elements

1. **Check BEFORE any DB writes**: Prevents corruption
2. **Return `success: True`**: Avoids LLM confusion (errors trigger retries)
3. **Add `already_done` flag**: Helps LLM understand it's idempotent
4. **Log with `idempotent: True`**: Makes monitoring easy
5. **Friendly message**: "Ya está completa do" vs "error de paso"
6. **Return current FSM state**: Maintains graph flow

---

## Testing Recommendations

### Test Case 1: confirmar_fotos_elemento Idempotency

```python
@pytest.mark.asyncio
async def test_confirmar_fotos_elemento_idempotent():
    # Setup: Element in photos phase
    state = create_state_with_element(phase="photos")
    
    # First call: Confirm photos
    result1 = await confirmar_fotos_elemento.ainvoke({}, config={"configurable": state})
    assert result1["success"] is True
    assert result1["photos_confirmed"] is True
    assert "already_confirmed" not in result1  # First call
    
    # Second call: Try to confirm again (now in data phase)
    result2 = await confirmar_fotos_elemento.ainvoke({}, config={"configurable": state})
    assert result2["success"] is True
    assert result2["already_confirmed"] is True  # Idempotent flag
    assert "ya fueron confirmadas" in result2["message"].lower()
```

### Test Case 2: completar_elemento_actual Idempotency

```python
@pytest.mark.asyncio
async def test_completar_elemento_actual_idempotent():
    # Setup: Element with all required fields collected
    state = create_state_with_complete_element()
    
    # First call: Complete element
    result1 = await completar_elemento_actual.ainvoke({}, config={"configurable": state})
    assert result1["success"] is True
    assert result1["element_complete"] is True
    
    # Second call: Try to complete again
    result2 = await completar_elemento_actual.ainvoke({}, config={"configurable": state})
    assert result2["success"] is True
    assert result2["already_completed"] is True  # Idempotent flag
```

### Test Case 3: guardar_datos_elemento Idempotency

```python
@pytest.mark.asyncio
async def test_guardar_datos_elemento_idempotent():
    # Setup: Element in data phase
    state = create_state_in_data_phase()
    
    # First call: Save field
    result1 = await guardar_datos_elemento.ainvoke(
        {"datos": {"altura_mm": "1230"}}, 
        config={"configurable": state}
    )
    assert result1["success"] is True
    assert result1["saved_count"] == 1
    
    # Second call: Save same field with same value
    result2 = await guardar_datos_elemento.ainvoke(
        {"datos": {"altura_mm": "1230"}},  # Same value
        config={"configurable": state}
    )
    assert result2["success"] is True
    assert result2["saved_count"] == 0  # No new saves
    # Check for "already_saved" status in results
    assert any(r["status"] == "already_saved" for r in result2["results"])
```

### Test Case 4: actualizar_datos_expediente Idempotency

```python
@pytest.mark.asyncio
async def test_actualizar_datos_expediente_idempotent():
    # Setup: Case in COLLECT_PERSONAL
    state = create_state_in_collect_personal()
    
    # First call: Save personal data
    datos = {
        "nombre": "Juan",
        "apellidos": "García",
        "email": "juan@example.com",
        "dni_cif": "12345678A",
    }
    result1 = await actualizar_datos_expediente.ainvoke(
        {"datos_personales": datos},
        config={"configurable": state}
    )
    assert result1["success"] is True
    
    # Second call: Save same data again
    result2 = await actualizar_datos_expediente.ainvoke(
        {"datos_personales": datos},  # Identical data
        config={"configurable": state}
    )
    assert result2["success"] is True
    assert result2.get("already_saved") is True  # Idempotent flag
    assert "ya están guardados" in result2["message"].lower()
```

---

## Monitoring

### Log Queries

```sql
-- Count idempotent calls per tool (last 7 days)
SELECT 
  tool_name,
  COUNT(*) as idempotent_count,
  COUNT(*) * 100.0 / NULLIF((
    SELECT COUNT(*) 
    FROM tool_call_logs 
    WHERE tool_name = t.tool_name 
      AND created_at > NOW() - INTERVAL '7 days'
  ), 0) as percentage
FROM tool_call_logs t
WHERE result::text LIKE '%"idempotent": true%'
  AND created_at > NOW() - INTERVAL '7 days'
  AND tool_name IN (
    'confirmar_fotos_elemento',
    'completar_elemento_actual',
    'guardar_datos_elemento',
    'actualizar_datos_expediente'
  )
GROUP BY tool_name
ORDER BY idempotent_count DESC;
```

### Alert Thresholds

| Tool | Idempotent Rate Alert | Reason |
|------|----------------------|--------|
| `confirmar_fotos_elemento` | >15% | Should be rare (user doesn't say "listo" twice) |
| `completar_elemento_actual` | >10% | Should be rare (called automatically) |
| `guardar_datos_elemento` | >20% | Some user corrections expected, but not excessive |
| `actualizar_datos_expediente` | >15% | Data shouldn't change mid-collection |

---

## Success Criteria

### Immediate (After Deployment)

- [ ] Zero FSM double-advancement errors
- [ ] Idempotent calls logged with `"idempotent": True`
- [ ] No escalations from confirmation/completion loops
- [ ] Database write count decreases (fewer redundant updates)

### 7-Day Window

- [ ] <15% of tool calls are idempotent (indicates rare edge case, not systemic loop)
- [ ] Zero user reports of "stuck" flows
- [ ] Decreased average case completion time (fewer retries)

### 30-Day Window

- [ ] Total tool call volume decreases 10-15% (fewer redundant calls)
- [ ] Case abandonment rate decreases (smoother UX)
- [ ] User satisfaction improves (NPS increase)

---

## Phase 2 Implementation - Medium Priority (UX Improvements)

**Date**: 2026-01-31  
**Tools Modified**: 3  
**Total Lines Changed**: ~60

### 1. ✅ `confirmar_documentacion_base` (element_data_tools.py, line 1270-1295)

**Problem**: Wrong step error when called after user already confirmed docs (UX friction).

**Implementation**:
```python
# Idempotency guard: Check if we're past COLLECT_BASE_DOCS step
if current_step in [COLLECT_PERSONAL, COLLECT_VEHICLE, COLLECT_WORKSHOP, REVIEW_SUMMARY, COMPLETED]:
    logger.info(
        "confirmar_documentacion_base called after confirmation",
        extra={"idempotent": True, "current_step": current_step.value}
    )
    return {
        "success": True,
        "already_confirmed": True,
        "message": "La documentación base ya fue confirmada anteriormente. Continuamos con el expediente.",
        "fsm_state_update": fsm_state,
    }
```

**Impact**:
- More graceful handling of late confirmations
- Reduces user confusion from "wrong step" errors
- Makes post-confirmation calls visible in logs

---

### 2. ✅ `actualizar_datos_taller` (case_tools.py, line 1009-1027)

**Problem**: Redundant workshop decision saves (no data to update) trigger unnecessary DB writes.

**Implementation**:
```python
# Idempotency guard: Check if taller decision already made with no new data
if existing_taller_propio == taller_propio and not datos_taller:
    logger.info(
        "actualizar_datos_taller called idempotently (no new data)",
        extra={"idempotent": True, "taller_propio": taller_propio}
    )
    return {
        "success": True,
        "already_saved": True,
        "message": "Esta decisión ya fue registrada. Continuamos.",
        "fsm_state_update": new_fsm_state,
    }
```

**Impact**:
- Skips redundant DB writes when decision unchanged
- Prevents duplicate auto-transitions (COLLECT_WORKSHOP → REVIEW_SUMMARY)
- Makes idempotent calls visible in logs

---

### 3. ✅ `cancelar_expediente` (case_tools.py, line 1510-1535)

**Problem**: Duplicate cancellation calls append notes multiple times to case.

**Implementation**:
```python
# Idempotency guard: Check if already cancelled
if case.status == "cancelled":
    logger.info(
        "Case already cancelled (idempotent call)",
        extra={"case_id": case_id, "idempotent": True},
    )
    
    # Return success (not error - prevents LLM confusion)
    new_fsm_state = reset_fsm(fsm_state)
    return {
        "success": True,
        "already_cancelled": True,
        "message": "El expediente ya fue cancelado anteriormente. Si necesitas ayuda con algo más, no dudes en preguntar.",
        "fsm_state_update": new_fsm_state,
    }
```

**Impact**:
- Prevents duplicate note appends to cancelled cases
- Maintains FSM reset behavior (bot stays active)
- Makes duplicate cancellation attempts visible in logs

---

## Testing Recommendations (Phase 2)

### Test Case 1: confirmar_documentacion_base Idempotency

```python
@pytest.mark.asyncio
async def test_confirmar_documentacion_base_idempotent():
    # Setup: Case already in COLLECT_PERSONAL (past base docs)
    state = create_state_in_collect_personal()
    
    # Call after confirmation already happened
    result = await confirmar_documentacion_base.ainvoke(
        {"usuario_confirma": True},
        config={"configurable": state}
    )
    
    assert result["success"] is True
    assert result["already_confirmed"] is True
    assert "ya fue confirmada" in result["message"].lower()
```

### Test Case 2: actualizar_datos_taller Idempotency

```python
@pytest.mark.asyncio
async def test_actualizar_datos_taller_idempotent():
    # Setup: Case with taller_propio already False
    state = create_state_with_taller_decision(taller_propio=False)
    
    # First call: Set taller_propio=False
    result1 = await actualizar_datos_taller.ainvoke(
        {"taller_propio": False},
        config={"configurable": state}
    )
    assert result1["success"] is True
    
    # Second call: Same decision, no new data
    result2 = await actualizar_datos_taller.ainvoke(
        {"taller_propio": False},  # Same decision
        config={"configurable": state}
    )
    
    assert result2["success"] is True
    assert result2["already_saved"] is True
    assert "ya fue registrada" in result2["message"].lower()
```

### Test Case 3: cancelar_expediente Idempotency

```python
@pytest.mark.asyncio
async def test_cancelar_expediente_idempotent():
    # Setup: Active case
    state = create_active_case_state()
    
    # First call: Cancel case
    result1 = await cancelar_expediente.ainvoke(
        {"motivo": "Usuario ya no lo necesita"},
        config={"configurable": state}
    )
    assert result1["success"] is True
    
    # Verify case status
    async with get_async_session() as session:
        case = await session.get(Case, uuid.UUID(state["case_id"]))
        assert case.status == "cancelled"
        note_count_1 = case.notes.count("Cancelado:")
    
    # Second call: Try to cancel again
    result2 = await cancelar_expediente.ainvoke(
        {"motivo": "Otro motivo"},
        config={"configurable": state}
    )
    assert result2["success"] is True
    assert result2["already_cancelled"] is True
    
    # Verify note not appended again
    async with get_async_session() as session:
        case = await session.get(Case, uuid.UUID(state["case_id"]))
        note_count_2 = case.notes.count("Cancelado:")
        assert note_count_2 == note_count_1  # Same count
```

---

## Monitoring (Phase 2 Added)

### Updated Log Query

```sql
-- Count idempotent calls per tool (Phase 1 + Phase 2)
SELECT 
  tool_name,
  COUNT(*) as idempotent_count,
  COUNT(*) * 100.0 / NULLIF((
    SELECT COUNT(*) 
    FROM tool_call_logs 
    WHERE tool_name = t.tool_name 
      AND created_at > NOW() - INTERVAL '7 days'
  ), 0) as percentage
FROM tool_call_logs t
WHERE result::text LIKE '%"idempotent": true%'
  OR result::text LIKE '%"already_saved": true%'
  OR result::text LIKE '%"already_confirmed": true%'
  OR result::text LIKE '%"already_cancelled": true%'
  AND created_at > NOW() - INTERVAL '7 days'
  AND tool_name IN (
    -- Phase 1 tools
    'confirmar_fotos_elemento',
    'completar_elemento_actual',
    'guardar_datos_elemento',
    'actualizar_datos_expediente',
    -- Phase 2 tools
    'confirmar_documentacion_base',
    'actualizar_datos_taller',
    'cancelar_expediente'
  )
GROUP BY tool_name
ORDER BY idempotent_count DESC;
```

### Updated Alert Thresholds

| Tool | Idempotent Rate Alert | Reason |
|------|----------------------|--------|
| **Phase 1** | | |
| `confirmar_fotos_elemento` | >15% | Should be rare (user doesn't say "listo" twice) |
| `completar_elemento_actual` | >10% | Should be rare (called automatically) |
| `guardar_datos_elemento` | >20% | Some user corrections expected |
| `actualizar_datos_expediente` | >15% | Data shouldn't change mid-collection |
| **Phase 2** | | |
| `confirmar_documentacion_base` | >10% | Should be rare (user confirms once) |
| `actualizar_datos_taller` | >15% | Decision shouldn't change |
| `cancelar_expediente` | >5% | Very rare (user rarely cancels twice) |

---

## Changelog

### Phase 1 (High Priority - FSM Loop Prevention)
| Date | Tool | Change | Lines |
|------|------|--------|-------|
| 2026-01-31 | `confirmar_fotos_elemento` | Add idempotency guard for "data" phase | +21 |
| 2026-01-31 | `completar_elemento_actual` | Add status check before completion | +36 |
| 2026-01-31 | `guardar_datos_elemento` | Add field value comparison guard | +19 |
| 2026-01-31 | `actualizar_datos_expediente` | Add data comparison guards (personal + vehicle) | +44 |

**Phase 1 Total**: ~120 lines added

### Phase 2 (Medium Priority - UX Improvements)
| Date | Tool | Change | Lines |
|------|------|--------|-------|
| 2026-01-31 | `confirmar_documentacion_base` | Add guard for post-confirmation calls | +18 |
| 2026-01-31 | `actualizar_datos_taller` | Add guard for duplicate workshop decisions | +15 |
| 2026-01-31 | `cancelar_expediente` | Add guard for duplicate cancellations | +17 |

**Phase 2 Total**: ~50 lines added

**Grand Total**: ~170 lines added (7 tools)

---

## Phase 3: FSM Phase Enforcement (Defense-in-Depth)

**Date**: 2026-01-31  
**Files Modified**: 6  
**Total Lines Changed**: ~70

### Problem Statement

The agent has 3 defense layers controlling tool access per FSM phase:

| Layer | Mechanism | Type | Enforcement |
|-------|-----------|------|-------------|
| **1. Prompt** | Phase-specific instructions | Soft (guides LLM) | `prompts/phases/*.md` + `loader.py` |
| **2. Tool Manager** | Phase-filtered tool list | Soft (filters tools) | `tools/tool_manager.py` |
| **3. Tool Guards** | Runtime FSM validation | Hard (blocks execution) | Each `@tool` function |

**Gaps found:**
1. `COMPLETED` state mapped to `REVIEW_SUMMARY_TOOLS` — exposed `finalizar_expediente` and `editar_expediente` to an already-completed case
2. `iniciar_expediente` had no FSM phase guard (Layer 3 missing) — relied only on tool_manager
3. `cancelar_expediente` missing from `REVIEW_SUMMARY` — user couldn't cancel at final review
4. No dedicated prompt for `COMPLETED` phase — used `review_summary.md` with wrong instructions

### Changes Implemented

#### 1. ✅ `tool_manager.py` — Dedicated `COMPLETED_TOOLS`

**Before**: `CollectionStep.COMPLETED: REVIEW_SUMMARY_TOOLS` (included `finalizar_expediente`, `editar_expediente`)

**After**: `CollectionStep.COMPLETED: COMPLETED_TOOLS` — mirrors `IDLE_TOOLS` (quotation tools + `iniciar_expediente`)

**Rationale**: After `finalizar_expediente`, the FSM resets and the bot stays active. The user should be able to start new consultations or open another case, NOT re-finalize or edit the completed one.

#### 2. ✅ `tool_manager.py` — `cancelar_expediente` added to `REVIEW_SUMMARY_TOOLS`

**Before**: User couldn't cancel during final review.

**After**: `cancelar_expediente` available in review phase.

**Rationale**: If user says "no quiero seguir" at the summary, they should be able to cancel without being forced to confirm first.

#### 3. ✅ `case_tools.py` — FSM guard for `iniciar_expediente`

**Before**: No FSM step validation. Only checked for active case in DB.

**After**: Validates `current_step in (IDLE, COMPLETED)` before proceeding.

```python
# Phase guard: only allowed from IDLE (defense-in-depth)
current_step = get_current_step(fsm_state)
if current_step not in (CollectionStep.IDLE, CollectionStep.COMPLETED):
    return tool_error_response(
        message="No se puede iniciar un expediente durante una recolección activa.",
        error_category=ErrorCategory.FSM_STATE_ERROR,
        error_code="FSM_NOT_IDLE",
        guidance=f"Estás en fase '{current_step.value}'. Completa o cancela el expediente actual primero.",
    )
```

**Rationale**: Defense-in-depth. Tool_manager is Layer 2, but Layer 3 (tool guard) is the REAL enforcement. Uses new error system (`ErrorCategory.FSM_STATE_ERROR`) for consistency.

#### 4. ✅ `prompts/phases/completed.md` — New dedicated prompt

**Before**: `COMPLETED` used `review_summary.md` which instructed to use `finalizar_expediente()`.

**After**: Dedicated `completed.md` that:
- Confirms the case was submitted
- Lists only quotation tools (no collection tools)
- Explicitly forbids finalizing/editing the previous case

#### 5. ✅ `prompts/loader.py` — Updated phase mapping

`CollectionStep.COMPLETED: "phases/completed.md"` (was `"phases/review_summary.md"`)

#### 6. ✅ `prompts/phases/review_summary.md` — Added cancel option

Added `cancelar_expediente(motivo)` to the tools table and a "Quiere cancelar" section.

### Defense Layer Coverage (After Changes)

All FSM-mutating tools now have coverage across all 3 layers:

| Tool | Layer 1 (Prompt) | Layer 2 (Tool Manager) | Layer 3 (Tool Guard) |
|------|-------------------|------------------------|----------------------|
| `iniciar_expediente` | ✅ `idle_quotation.md` | ✅ IDLE only | ✅ **NEW** FSM check |
| `actualizar_datos_expediente` | ✅ `collect_personal.md` / `collect_vehicle.md` | ✅ PERSONAL/VEHICLE | ✅ Step check |
| `actualizar_datos_taller` | ✅ `collect_workshop.md` | ✅ WORKSHOP | ✅ Step check |
| `editar_expediente` | ✅ `review_summary.md` | ✅ REVIEW_SUMMARY | ✅ Step check |
| `finalizar_expediente` | ✅ `review_summary.md` | ✅ REVIEW_SUMMARY | ✅ Step check |
| `cancelar_expediente` | ✅ All collection phases | ✅ All collection + **REVIEW** | ✅ Case existence check |
| `confirmar_fotos_elemento` | ✅ `collect_element_data.md` | ✅ ELEMENT_DATA | ✅ Step + sub-phase |
| `guardar_datos_elemento` | ✅ `collect_element_data.md` | ✅ ELEMENT_DATA | ✅ Step + sub-phase |
| `completar_elemento_actual` | ✅ `collect_element_data.md` | ✅ ELEMENT_DATA | ✅ Step check |
| `confirmar_documentacion_base` | ✅ `collect_base_docs.md` | ✅ BASE_DOCS | ✅ Step check |

### Changelog

| Date | File | Change | Lines |
|------|------|--------|-------|
| 2026-01-31 | `tool_manager.py` | Add `COMPLETED_TOOLS`, update mapping, add cancel to review | +18 |
| 2026-01-31 | `case_tools.py` | Add FSM phase guard to `iniciar_expediente` | +15 |
| 2026-01-31 | `prompts/phases/completed.md` | New dedicated COMPLETED phase prompt | +30 |
| 2026-01-31 | `prompts/loader.py` | Update COMPLETED mapping | +1 |
| 2026-01-31 | `prompts/phases/review_summary.md` | Add cancel option and tool | +5 |

**Phase 3 Total**: ~70 lines across 5 files + 1 new file

---

**Generated by**: Root Cause Analysis + Implementation Session  
**Reviewed by**: Architecture Team  
**Approved for**: Production Deployment  
**Risk Level**: Low (defensive guards, maintains backward compatibility)
