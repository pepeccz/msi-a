# Plan: Fix Foundation Architecture — Critical Bug Fixes

**Created**: 2026-02-12
**Updated**: 2026-02-12 (scoped to Phases 0-2 only; Phases 3-4 deferred to separate plan)
**Status**: APPROVED
**Estimated effort**: 2 days
**Risk level**: HIGH (production system, 3 critical bugs blocking sales funnel)
**Author**: architect agent

---

## Executive Summary

MSI-a's agent has **three critical bugs** that collectively break the entire sales funnel from quote acceptance to case collection. These bugs all share a root cause: **implicit type boundaries** — data crosses component boundaries via untyped dicts, unparsed strings, and implicit conventions instead of explicit contracts.

This plan addresses the **3 critical bugs** in 3 phases. Architectural cleanup (LLM loop extraction, ToolResult dataclass) has been deferred to a [separate future plan](./refactor-llm-loop-toolresult.md) pending a regression test suite.

| Phase | Description | Effort | Status |
|-------|-------------|--------|--------|
| **Phase 0** | HOTFIX — Auto-create Case on EXPEDIENTE entry | 30 min | ✅ IMPLEMENTED |
| **Phase 1** | Clean mode transitions (use `transition_mode()`) | 1 day | PENDING |
| **Phase 2** | Fix constraint false positive (skip logic) | 0.5 days | PENDING |

---

## Phase 0: HOTFIX — Unblock Production Funnel (30 min)

### Objective

Unblock the EXPEDIENTE_MODE by adding `iniciar_expediente` to the tool list and auto-creating the Case when entering the mode. This is the **minimum viable fix** to restore the sales funnel.

### Urgency: CRITICAL — blocking production NOW

### Status: ✅ IMPLEMENTED (pending deploy)

### Changes

#### Change 0.1: Add `iniciar_expediente` to `_get_element_data_tools()`

- **File**: `agent/modes/expediente_mode.py`
- **What**: Added `iniciar_expediente` to the imports and return list in `_get_element_data_tools()`
- **Why**: `iniciar_expediente()` is defined in `agent/tools/case_tools.py` but was NOT imported or listed in ANY sub-mode tool list. When EVALUACION_GATEWAY transitions to EXPEDIENTE_MODE, the LLM enters COLLECT_ELEMENT_DATA sub-mode but had no tool to create the Case.

#### Change 0.2: Auto-create Case in `_initialize_mode_context()` when no Case found

- **File**: `agent/modes/expediente_mode.py`
- **What**: When `_initialize_mode_context()` finds no active Case, calls new `_auto_create_case()` method instead of silently returning empty context
- **Why**: After the EVALUACION_GATEWAY → EXPEDIENTE_MODE transition, the mode_context contains `elementos_confirmados`, `element_codes`, `tarifa_calculada`, and `categoria_slug` (carried via spread in `_handle_yes()`). But there is no Case row in the database yet. The old code logged a warning and returned an empty context, leaving all tools broken.

**New method `_auto_create_case()`**:
- Validates `categoria_slug` and `element_codes` exist in context
- Checks for existing active case (prevents duplicates) via `_get_active_case_for_conversation()`
- Looks up `category_id` by slug via `_get_category_id_by_slug()`
- Extracts tariff data from context if available
- Creates Case in DB with status `"collecting"`
- Returns fully initialized mode_context with `case_id`, `element_data_status`, etc.

#### Change 0.3: Update expediente_documentacion_elementos.md prompt

- **File**: `agent/prompts/modes/expediente_documentacion_elementos.md`
- **What**: Added `iniciar_expediente` to the "Herramientas Disponibles" section as a belt-and-suspenders backup

### Verification

1. **Manual test**: PRESUPUESTO → accept quote → EVALUACION_GATEWAY → "sí" → verify agent starts asking for element photos
2. **DB check**: `SELECT * FROM cases WHERE conversation_id = '<test>' ORDER BY created_at DESC LIMIT 1;`
3. **Syntax check**: ✅ `ast.parse()` passes

### Rollback

- `git checkout -- agent/modes/expediente_mode.py agent/prompts/modes/expediente_documentacion_elementos.md`
- No database migrations involved
- Auto-created Cases are valid and don't need cleanup

---

## Phase 1: Clean Mode Transitions (1 day)

### Objective

Fix EVALUACION_GATEWAY's `_handle_yes()`, `_handle_no()`, and `_handle_ambiguous()` to use `transition_mode()`, gaining `previous_mode`, `mode_history`, `draft_contexts`, and `mode_message_count` reset.

### ⚠️ Investigation Findings — Critical Risks Discovered

Deep analysis by investigator-dev revealed important risks that require mitigations:

#### Risk 1 (HIGH): `merge_dicts` reducer doesn't replace, it merges

`transition_mode()` returns a new `mode_context`, but the LangGraph reducer `merge_dicts` does `{**checkpoint_old, **new}`. If the new context is `{}` or partial, **old keys persist** (gateway_confirmed, pending_variants, precio_comunicado, etc.).

**Mitigation**: Use `transition_mode()` with **explicit `new_context`** parameter instead of relying on `preserve_keys` or draft restoration. Build the new context manually with only the keys EXPEDIENTE needs.

#### Risk 2 (MEDIUM): Draft contexts can be stale on re-entry

If a user previously visited EXPEDIENTE_MODE (aborted), then does PRESUPUESTO → GATEWAY → EXPEDIENTE again, `transition_mode()` would restore the **old draft** with stale data. `preserve_keys` won't overwrite keys that already exist in the draft.

**Mitigation**: Always pass `new_context` explicitly in `_handle_yes()`. Never rely on draft restoration for EXPEDIENTE entry.

#### Risk 3 (LOW): `ai_response` not included by `transition_mode()`

`transition_mode()` does NOT return `ai_response`. Must be added manually to the returned dict.

**Mitigation**: Always set `updates["ai_response"] = "..."` after calling `transition_mode()`.

### Changes

#### Change 1.1: Rewrite `_handle_yes()` with explicit `new_context`

- **File**: `agent/modes/evaluacion_gateway.py`
- **Lines**: 182-205

```python
def _handle_yes(
    self,
    state: ConversationState,
    mode_context: dict[str, Any],
) -> dict[str, Any]:
    """User confirmed — transition to EXPEDIENTE_MODE."""
    self._logger.info("gateway_confirmed")

    # Build EXPLICIT new_context with only the keys EXPEDIENTE needs.
    # This avoids relying on preserve_keys (which won't overwrite stale drafts)
    # and avoids gateway keys (gateway_confirmed, etc.) leaking through.
    new_context = {
        "elementos_confirmados": mode_context.get("elementos_confirmados", []),
        "element_codes": mode_context.get("element_codes", []),
        "tarifa_calculada": mode_context.get("tarifa_calculada"),
        "categoria_slug": mode_context.get("categoria_slug"),
    }

    updates = transition_mode(
        state,
        "EXPEDIENTE_MODE",
        new_context=new_context,
    )

    updates["ai_response"] = (
        "¡Perfecto! Vamos a iniciar el expediente. "
        "Te voy a ir pidiendo la información paso a paso."
    )

    return updates
```

**Why explicit `new_context`**: The investigator found that `preserve_keys` only copies keys that DON'T exist in `target_context`. If there's a stale draft of EXPEDIENTE, the new presupuesto data would be silently dropped. Explicit `new_context` guarantees the correct data arrives.

#### Change 1.2: Rewrite `_handle_no()` with explicit `new_context`

- **File**: `agent/modes/evaluacion_gateway.py`
- **Lines**: 207-230

```python
def _handle_no(
    self,
    state: ConversationState,
    mode_context: dict[str, Any],
) -> dict[str, Any]:
    """User declined — return to PRESUPUESTO_MODE."""
    self._logger.info("gateway_declined")

    # Pass the full mode_context as new_context to preserve all presupuesto data.
    # Remove gateway-specific keys that shouldn't pollute PRESUPUESTO.
    presupuesto_context = {
        k: v for k, v in mode_context.items()
        if not k.startswith("gateway_")
    }

    updates = transition_mode(
        state,
        "PRESUPUESTO_MODE",
        new_context=presupuesto_context,
    )

    updates["ai_response"] = (
        "Sin problema. El presupuesto queda guardado "
        "por si lo quieres retomar más adelante. "
        "¿Hay algo más en lo que te pueda ayudar?"
    )

    return updates
```

**Why filter gateway keys**: The current code does `{**mode_context, ...}` which carries gateway_confirmed, gateway_attempts, etc. into PRESUPUESTO. Filtering `gateway_*` keys produces a cleaner context.

#### Change 1.3: Rewrite `_handle_ambiguous()` max-retries

- **File**: `agent/modes/evaluacion_gateway.py`
- **Lines**: 248-269 (the `if attempts >= MAX_GATEWAY_RETRIES:` block)

```python
if attempts >= MAX_GATEWAY_RETRIES:
    self._logger.warning(
        "gateway_max_retries",
        attempts=attempts,
    )

    # Same approach as _handle_no: clean context back to PRESUPUESTO
    presupuesto_context = {
        k: v for k, v in mode_context.items()
        if not k.startswith("gateway_")
    }

    updates = transition_mode(
        state,
        "PRESUPUESTO_MODE",
        new_context=presupuesto_context,
    )
    updates["ai_response"] = (
        "Entiendo que todavía no estás seguro. "
        "No hay problema, el presupuesto queda guardado. "
        "Cuando quieras iniciar el expediente, avísame."
    )
    return updates
```

**NOTE**: The reprompt path (when attempts < MAX_GATEWAY_RETRIES) does NOT transition modes — it stays in EVALUACION_GATEWAY with an updated attempt counter. This path should NOT use `transition_mode()`.

#### Change 1.4: Add imports at module level

- **File**: `agent/modes/evaluacion_gateway.py`
- **Lines**: 20-28

```python
from agent.state.conversation_state import ConversationState, transition_mode
```

### Verification

1. **Unit test**: `_handle_yes()` returns proper transition:
   - `result["current_mode"] == "EXPEDIENTE_MODE"`
   - `result["previous_mode"] == "EVALUACION_GATEWAY"`
   - `result["retry_state"]["retry_count"] == 0`
   - `result["mode_message_count"] == 0`
   - `"element_codes" in result["mode_context"]`
   - `"gateway_confirmed" not in result["mode_context"]`

2. **Unit test**: `_handle_no()` returns clean PRESUPUESTO context:
   - `result["current_mode"] == "PRESUPUESTO_MODE"`
   - `result["previous_mode"] == "EVALUACION_GATEWAY"`
   - `"gateway_confirmed" not in result["mode_context"]`
   - `"tarifa_calculada" in result["mode_context"]` (presupuesto data preserved)

3. **Manual test**: Full flow PRESUPUESTO → EVAL → "sí" → EXPEDIENTE
4. **Manual test**: Full flow PRESUPUESTO → EVAL → "no" → PRESUPUESTO (verify pricing data intact)

### Rollback

- `git checkout -- agent/modes/evaluacion_gateway.py`
- No database changes involved

---

## Phase 2: Fix Constraint System (0.5 days)

### Objective

Eliminate the false positive from `variant_requires_tool` constraint by adding conservative skip logic. Do NOT change the regex.

### ⚠️ Investigation Findings — Corrections to Original Plan

Deep analysis by investigator-dev revealed:

1. **`elementos_confirmados` is DEAD CODE** — never written anywhere in the codebase. The original plan's skip condition based on `elementos_confirmados` would **never activate**. Must use `tarifa_calculada` and `element_codes` instead.

2. **The proposed regex change is too restrictive** — the new regex `(?:qu[eé]\s+tipo|...)` would miss real violations like "¿Es estándar o full air?". Do NOT change the regex.

3. **`presupuesto_completado` in existing skip logic is also dead code** — never written, only read. The existing `price_requires_tool` skip works by other conditions.

### Changes

#### Change 2.1: Add conservative `variant_requires_tool` skip logic

- **File**: `agent/services/constraint_service.py`
- **Lines**: After existing skip logic (before final `return False`)

```python
    # Skip variant_requires_tool when variants are definitively resolved
    if constraint_type == "variant_requires_tool":
        # If tariff was already calculated, all variants are definitively resolved
        has_tarifa = fsm_state.get("tarifa_calculada") is not None
        if has_tarifa:
            logger.info(
                "skip_constraint_variant_tarifa_exists",
                constraint_type=constraint_type,
            )
            return True

        # If pending_variants is explicitly empty AND elements were identified
        pending = fsm_state.get("pending_variants")
        has_elements = bool(fsm_state.get("element_codes"))
        if isinstance(pending, list) and len(pending) == 0 and has_elements:
            logger.info(
                "skip_constraint_variant_no_pending",
                constraint_type=constraint_type,
                element_count=len(fsm_state.get("element_codes", [])),
            )
            return True

    return False
```

**Why this is conservative**:
- Only skips when `tarifa_calculada` exists (tariff calculated = variants definitively resolved), OR
- When `pending_variants` is explicitly `[]` AND `element_codes` exist (elements identified, no pending variants)
- Does NOT skip when `pending_variants` is `None` (never set = element identification not started)
- Does NOT skip when `pending_variants` has items (variant resolution in progress)

**Why NOT `elementos_confirmados`**: Investigation confirmed it's never written. Dead code.

#### Change 2.2: Upgrade skip logs to INFO level

- **File**: `agent/services/constraint_service.py`
- **What**: Change existing `logger.debug()` calls in `_should_skip_constraint()` to `logger.info()` for production observability

#### Change 2.3: Do NOT change the regex ❌

The original plan proposed tightening the regex. Investigation showed the proposed regex is **too restrictive** and would lose protection against real hallucinations. The current regex is kept as-is; the skip logic alone resolves the false positive issue.

### Verification

1. **Unit test**: Skip when tarifa exists
   ```python
   assert _should_skip_constraint(
       "variant_requires_tool",
       {"tarifa_calculada": {"datos": {"price": 410}}}
   ) == True
   ```

2. **Unit test**: Skip when no pending variants + elements exist
   ```python
   assert _should_skip_constraint(
       "variant_requires_tool",
       {"pending_variants": [], "element_codes": ["ESCAPE"]}
   ) == True
   ```

3. **Unit test**: Do NOT skip when variants are pending
   ```python
   assert _should_skip_constraint(
       "variant_requires_tool",
       {"pending_variants": [{"element": "SUSPENSION"}]}
   ) == False
   ```

4. **Unit test**: Do NOT skip when pending_variants is None (never set)
   ```python
   assert _should_skip_constraint(
       "variant_requires_tool",
       {"element_codes": ["ESCAPE"]}  # No pending_variants key
   ) == False
   ```

5. **Regression test**: Production false positive no longer triggers
   ```python
   is_valid, _ = validate_response(
       "¿Tienes el subchasis ya instalado en la moto?",
       {"calcular_tarifa_con_elementos"},
       constraints,
       fsm_state={"pending_variants": [], "tarifa_calculada": {...}},
   )
   assert is_valid  # No false positive
   ```

### Rollback

- `git checkout -- agent/services/constraint_service.py`
- No database changes (regex NOT modified)

---

## Dependencies Between Phases

```
Phase 0 (HOTFIX) ─── can deploy immediately ✅ IMPLEMENTED
    │
    ├── Phase 1 (Transitions) ─── depends on Phase 0
    │
    └── Phase 2 (Constraints) ─── independent, can run in PARALLEL with Phase 1
```

**Execution order**:
1. **Phase 0**: Deploy immediately (30 min) ✅
2. **Phase 1 + Phase 2**: In parallel (1 day + 0.5 day)

---

## Files Modified (Complete List)

| File | Phase | Type of Change |
|------|-------|----------------|
| `agent/modes/expediente_mode.py` | 0 | Add `iniciar_expediente` to tools, add `_auto_create_case()` |
| `agent/prompts/modes/expediente_documentacion_elementos.md` | 0 | Add `iniciar_expediente` to available tools list |
| `agent/modes/evaluacion_gateway.py` | 1 | Rewrite `_handle_yes()`, `_handle_no()`, `_handle_ambiguous()` to use `transition_mode()` with explicit `new_context` |
| `agent/services/constraint_service.py` | 2 | Add conservative `variant_requires_tool` skip logic |

**Files NOT modified** (confirmed working, don't touch):
- `agent/graph/conversation_graph.py` — graph topology is correct
- `agent/router/mode_transitions.py` — transition rules and CONTEXT_PRESERVE_RULES are correct
- `agent/state/conversation_state.py` — reducers and `transition_mode()` are correct
- `agent/tools/case_tools.py` — `iniciar_expediente()` implementation is correct
- `agent/fallback/fallback_handler.py` — retry policies are correct
- Database `response_constraints` table — regex NOT changed

---

## Risk Assessment

### High Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Phase 0 auto-create creates duplicate Cases | Medium: orphaned rows | `_auto_create_case()` checks for existing active case first |
| Phase 1 `merge_dicts` reducer merges instead of replacing mode_context | High: stale keys persist | Use explicit `new_context` instead of `preserve_keys` |
| Phase 1 stale draft restored on re-entry | High: wrong data in EXPEDIENTE | Explicit `new_context` overrides any draft |

### Medium Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Phase 1 `ai_response` forgotten | High: empty response to user | Always set `updates["ai_response"]` after `transition_mode()` |
| Phase 2 skip logic too permissive | Low: constraint disabled incorrectly | Conservative conditions (require tarifa OR empty pending + elements) |

### Low Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Phase 0 category not found | Low: falls back to empty context | Error logged, existing fallback behavior |
| Phase 1 reprompt path uses transition_mode | Medium: breaks gateway flow | Reprompt path explicitly excluded — only transition paths use it |

---

## Success Criteria

### Phase 0 (HOTFIX) ✅
- [ ] A user can say "sí" in EVALUACION_GATEWAY and enter EXPEDIENTE_MODE without getting stuck
- [ ] A Case row exists in the database after entering EXPEDIENTE_MODE
- [ ] Element data collection tools work (confirmar_fotos, guardar_datos, etc.)
- [ ] `iniciar_expediente` appears in `_get_element_data_tools()` output

### Phase 1 (Transitions)
- [ ] `_handle_yes()` result includes `previous_mode == "EVALUACION_GATEWAY"`
- [ ] `_handle_yes()` result has `retry_state.retry_count == 0`
- [ ] Gateway-specific keys NOT in EXPEDIENTE mode_context
- [ ] `_handle_no()` returns to PRESUPUESTO with pricing data intact, without gateway keys
- [ ] Reprompt path (ambiguous, not max retries) stays in gateway without using transition_mode
- [ ] Full flow test: PRESUPUESTO → EVAL → EXPEDIENTE with clean state at each step

### Phase 2 (Constraints)
- [ ] "¿Tienes el subchasis ya instalado en la moto?" does NOT trigger false positive when tarifa exists
- [ ] Actual variant invention with pending_variants DOES trigger
- [ ] Skip does NOT activate when pending_variants is None (never set)
- [ ] Constraint skip events logged at INFO level in production

### Overall
- [ ] Full sales funnel works: PRESUPUESTO → EVAL_GATEWAY → EXPEDIENTE → element collection starts
- [ ] No false positive constraint violations in production logs for 48 hours
- [ ] No regression in PRESUPUESTO flow (pricing, variant resolution, image sending)

---

## Deferred Work

Phases 3 (LLM Loop Extraction) and 4 (ToolResult dataclass) have been deferred to a separate plan: [`docs/plans/refactor-llm-loop-toolresult.md`](./refactor-llm-loop-toolresult.md)

**Reason**: Deep investigation revealed 3 HIGH-risk behavioral differences between the 3 mode LLM loops that require a regression test suite before safe refactoring. The architectural cleanup benefits (maintainability, ~400 fewer lines) don't justify the production risk without comprehensive tests.

**Prerequisites for Phases 3-4**:
1. Regression test suite covering all 3 modes' LLM loop behavior
2. Phases 0-2 deployed and verified stable for at least 1 week
3. Feature flag mechanism for gradual rollout
