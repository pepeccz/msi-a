# Plan: Fix Option B — Skip EVALUACION_GATEWAY for Explicit Expediente Confirmation

**Created**: 2026-02-13
**Status**: DRAFT — Pending approval
**Priority**: HIGH (UX bug in production)
**Estimated effort**: ~20 lines changed across 3 files + 1 prompt update
**Risk**: LOW (surgical changes, gateway preserved for Option A flow)

---

## 1. Problem Statement

### The Bug (Observed in Production — Pepe's Conversation, 2026-02-13 16:32-16:37 Spain)

When a user explicitly chooses **Option B** ("abrir expediente directamente") after receiving a price quote, the agent sends a hardcoded internal tool message instead of a proper contextual response:

```
User: "Holaaa quiero homologar el subchasis de mi moto"
Bot:  "El presupuesto es de 410 EUR +IVA [...] A) Ver fotos B) Abrir expediente"
User: "B"
Bot:  "Perfecto, vamos a confirmar los detalles antes de abrir el expediente."  ← BUG
```

The message "Perfecto, vamos a confirmar los detalles..." is the `message` field from the `confirmar_presupuesto()` tool return (line 103, `transition_tools.py`), NOT an LLM-generated response. It reaches the user because of the **fast-path pattern** in `presupuesto_mode.py` (lines 420-437) which breaks the LLM loop immediately when a tool sets `_transition_to`, using the tool's internal `message` as `ai_response`.

### The UX Problem

After this turn, the state transitions to `EVALUACION_GATEWAY`, which will ask the user **again**: "¿Quieres iniciar el expediente?" — a redundant double-confirmation. The user already said "B" (= "abrir expediente directamente"). Asking again is friction with no value.

### Root Cause Chain

1. `confirmar_presupuesto()` tool returns `_transition_to: "EVALUACION_GATEWAY"` + hardcoded `message`
2. Fast-path in `presupuesto_mode.py:420-437` grabs the tool's `message` as `ai_response` and breaks the LLM loop
3. The LLM never gets a chance to generate a proper contextual response
4. State transitions to `EVALUACION_GATEWAY` which asks for yes/no confirmation
5. User must confirm **again** something they already confirmed

---

## 2. Approved Solution: Option C — Direct Transition to EXPEDIENTE_MODE

When the user explicitly confirms via Option B (which triggers `confirmar_presupuesto()`), skip `EVALUACION_GATEWAY` and transition directly to `EXPEDIENTE_MODE`.

### Why This Works

- The gateway's purpose is to confirm **implicit** intent (e.g., after viewing photos, the agent asks "want to open expediente?" — the user's intent was ambiguous, so confirmation makes sense)
- When the user **explicitly** says "B" / "abre el expediente" / "vamos con el trámite", intent is already confirmed — the gateway adds no value
- The gateway remains intact for the Option A flow (photos → "want to open expediente?" → gateway needed)
- The gateway also remains intact for the `intent_router` flows (`INICIAR_EXPEDIENTE`, `ABRIR_EXPEDIENTE` intents from START mode)

### What Changes

| Aspect | Before | After |
|--------|--------|-------|
| `confirmar_presupuesto()` target | `EVALUACION_GATEWAY` | `EXPEDIENTE_MODE` |
| Fast-path message | Hardcoded tool `message` | Proper welcome message for expediente entry |
| `ALLOWED_TRANSITIONS` | PRESUPUESTO→GATEWAY only | PRESUPUESTO→GATEWAY OR PRESUPUESTO→EXPEDIENTE |
| `CONTEXT_PRESERVE_RULES` | Only PRESUPUESTO→GATEWAY | Also PRESUPUESTO→EXPEDIENTE |
| Gateway | Used for all flows | Only for Option A / implicit intent flows |
| Prompt (presupuesto_mode.md) | "transiciona a EVALUACION_GATEWAY" | "transiciona a EXPEDIENTE_MODE directamente" |

---

## 3. Implementation Plan (File-by-File)

### 3.1. `agent/tools/transition_tools.py` — Change transition target + message

**Current** (lines 100-114):
```python
return {
    "success": True,
    "message": (
        "Perfecto, vamos a confirmar los detalles antes de abrir el expediente."
    ),
    "resumen": {
        "precio": precio,
        "elementos": element_codes,
        "categoria": categoria,
    },
    "_internal_flags": {
        "_transition_to": "EVALUACION_GATEWAY",
        "gateway_question_asked": True,
    },
}
```

**New**:
```python
return {
    "success": True,
    "message": (
        "¡Perfecto! Vamos a iniciar el expediente. "
        "Te iré pidiendo la información paso a paso."
    ),
    "resumen": {
        "precio": precio,
        "elementos": element_codes,
        "categoria": categoria,
    },
    "_internal_flags": {
        "_transition_to": "EXPEDIENTE_MODE",
    },
}
```

**Changes**:
1. `_transition_to`: `"EVALUACION_GATEWAY"` → `"EXPEDIENTE_MODE"`
2. Remove `gateway_question_asked` flag (no longer relevant — we're not going to gateway)
3. Update `message` to a proper expediente welcome message (this is what the fast-path will send to the user)

**Why the message matters**: The fast-path pattern (presupuesto_mode.py:420-437) uses the tool's `message` field as `ai_response`. Until we refactor the fast-path (separate effort), we need this message to be user-appropriate. The new message matches what the gateway's `_handle_yes()` sends (evaluacion_gateway.py:192-195).

**Also update docstring** (lines 23-40): Change "señal de transicion a EVALUACION_GATEWAY" → "señal de transicion a EXPEDIENTE_MODE"

---

### 3.2. `agent/router/mode_transitions.py` — Allow direct transition + preserve rules

#### 3.2.1. Add EXPEDIENTE_MODE to ALLOWED_TRANSITIONS (line 37-41)

**Current**:
```python
"PRESUPUESTO_MODE": [
    "EVALUACION_GATEWAY",
    "ESCALATION",
    # NO backwards to CONSULTA (funnel enforcement)
],
```

**New**:
```python
"PRESUPUESTO_MODE": [
    "EVALUACION_GATEWAY",
    "EXPEDIENTE_MODE",     # Direct transition when user explicitly confirms (Option B)
    "ESCALATION",
    # NO backwards to CONSULTA (funnel enforcement)
],
```

#### 3.2.2. Add CONTEXT_PRESERVE_RULES for PRESUPUESTO→EXPEDIENTE (after line 71)

**Current** (lines 63-71):
```python
"PRESUPUESTO_MODE": {
    "EVALUACION_GATEWAY": [
        "element_codes",
        "tarifa_calculada",
        "categoria_slug",
        "precio_comunicado",
    ],
},
```

**New**:
```python
"PRESUPUESTO_MODE": {
    "EVALUACION_GATEWAY": [
        "element_codes",
        "tarifa_calculada",
        "categoria_slug",
        "precio_comunicado",
    ],
    "EXPEDIENTE_MODE": [           # Direct from Option B (skip gateway)
        "element_codes",
        "tarifa_calculada",
        "categoria_slug",
    ],
},
```

**Why these keys**: Same keys as `EVALUACION_GATEWAY → EXPEDIENTE_MODE` (line 74-78). The `_auto_create_case()` in `expediente_mode.py:248-412` needs `categoria_slug`, `element_codes`, and optionally `tarifa_calculada` to auto-create the Case record.

**Note**: We do NOT carry `precio_comunicado` to EXPEDIENTE_MODE — it's a PRESUPUESTO_MODE flag that has no meaning in the expediente context.

#### 3.2.3. Remove/update reason_map entry (line 227)

**Current**:
```python
("PRESUPUESTO_MODE", "EXPEDIENTE_MODE"): "Debe pasar por EVALUACION_GATEWAY",
```

**New**: Remove this line entirely. The transition is now allowed.

---

### 3.3. `agent/prompts/modes/presupuesto_mode.md` — Update prompt references

Multiple lines reference "transiciona a EVALUACION_GATEWAY" for the Option B flow. Update to reflect the new behavior.

**Changes** (content updates, not exhaustive — all instances):

| Line | Current | New |
|------|---------|-----|
| 16 | "Transicionar a EVALUACION_GATEWAY cuando el usuario confirme" | "Transicionar a EXPEDIENTE_MODE cuando el usuario confirme Opción B" |
| 176 | "Confirmar presupuesto y transicionar a EVALUACION_GATEWAY" | "Confirmar presupuesto e iniciar expediente directamente" |
| 242 | "El sistema transicionará automáticamente a EVALUACION_GATEWAY" | "El sistema transicionará automáticamente a EXPEDIENTE_MODE" |
| 245 | "señalar la transición" | "señalar la transición directa a EXPEDIENTE_MODE" |
| 255 | "NO iniciar expediente directamente — usar confirmar_presupuesto() que transiciona a EVALUACION_GATEWAY" | "Usar confirmar_presupuesto() que transiciona directamente a EXPEDIENTE_MODE" |
| 291 | "→ EVALUACION_GATEWAY" | "→ EXPEDIENTE_MODE (directo)" |
| 338-339 | "→ Sistema transiciona automáticamente a EVALUACION_GATEWAY" | "→ Sistema transiciona directamente a EXPEDIENTE_MODE" |
| 389 | "transiciona automáticamente a EVALUACION_GATEWAY" | "transiciona directamente a EXPEDIENTE_MODE" |
| 453 | "→ confirmar_presupuesto() → transiciona a EVALUACION_GATEWAY" | "→ confirmar_presupuesto() → transiciona a EXPEDIENTE_MODE" |
| 505 | "B → confirmar_presupuesto() → transiciona a EVALUACION_GATEWAY" | "B → confirmar_presupuesto() → transiciona a EXPEDIENTE_MODE" |
| 597 | "NO inicies expediente directamente — usa confirmar_presupuesto() que transiciona por EVALUACION_GATEWAY" | "Usa confirmar_presupuesto() para transicionar directamente a EXPEDIENTE_MODE" |

**Key insight**: The prompt currently tells the LLM "NO inicies expediente directamente" (rule 7, line 255, and rule on line 597). This rule was designed to prevent the LLM from trying to modify `current_mode` directly. The rule still applies — the LLM must use the tool, not try to transition manually. But the destination changes from gateway to expediente.

---

### 3.4. NO Changes Required (Verified)

| Component | Why No Change Needed |
|-----------|---------------------|
| `presupuesto_mode.py` (fast-path L420-437) | Works as-is. It reads `_transition_to` from mode_context and breaks. The transition target is just a string — changing it in the tool is sufficient. |
| `presupuesto_mode.py` (transition handling L470-489) | Calls `validate_transition()` and `get_preserve_keys()`. Both will return correct values after mode_transitions.py changes. |
| `evaluacion_gateway.py` | No changes. Gateway still works for Option A flow and intent_router flows. |
| `expediente_mode.py` | No changes. `_initialize_mode_context` (L154) and `_auto_create_case` (L248) already handle first entry with preserved context. They check for `categoria_slug` + `element_codes` — both carried by new preserve rules. |
| `conversation_graph.py` | No changes. `route_to_mode()` maps modes to nodes generically. EXPEDIENTE_MODE is already mapped. |
| `conversation_state.py` | No changes. `transition_mode()` is mode-agnostic. |
| `intent_router.py` | No changes. `INICIAR_EXPEDIENTE` and `ABRIR_EXPEDIENTE` still route to EVALUACION_GATEWAY (from START mode). Different flow. |

---

## 4. Data Flow Verification

### Before (Current):
```
PRESUPUESTO_MODE                EVALUACION_GATEWAY              EXPEDIENTE_MODE
─────────────────               ──────────────────              ───────────────
User: "B"                       
  ↓                             
confirmar_presupuesto()         
  → _transition_to: GATEWAY     
  → message: "Perfecto..."     
  ↓                             
fast-path → ai_response =       
  "Perfecto, vamos a confirmar" ← USER SEES THIS (bad)
  ↓                             
transition_mode() →              
  mode_context = Overwrite({    
    element_codes, tarifa_calc,  
    categoria_slug, precio_com   
  })                             
═══════ END OF TURN 1 ═══════   

                                 Turn 2: User says anything
                                 gateway: "¿Quieres iniciar?" ← REDUNDANT
                                   ↓
                                 Turn 3: User: "sí"
                                 _handle_yes() →
                                   transition_mode(EXPEDIENTE)   → Turn 4: EXPEDIENTE starts
```

### After (Proposed):
```
PRESUPUESTO_MODE                                                EXPEDIENTE_MODE
─────────────────                                               ───────────────
User: "B"
  ↓
confirmar_presupuesto()
  → _transition_to: EXPEDIENTE
  → message: "¡Perfecto! Vamos a
    iniciar el expediente..."
  ↓
fast-path → ai_response =
  "¡Perfecto! Vamos a iniciar..." ← USER SEES THIS (good)
  ↓
transition_mode() →
  mode_context = Overwrite({
    element_codes, tarifa_calc,
    categoria_slug
  })
═══════ END OF TURN 1 ═══════

                                                                 Turn 2: User says anything
                                                                 _process_message →
                                                                   _initialize_mode_context →
                                                                     _auto_create_case() ← Creates Case from preserved data
                                                                   _handle_element_data() ← First sub-mode starts
```

**Turns saved**: 2 (gateway presentation + gateway confirmation)
**Data preserved**: `element_codes`, `tarifa_calculada`, `categoria_slug` — exactly what `_auto_create_case()` needs.

---

## 5. Edge Cases & Risk Analysis

### 5.1. What if `precio_comunicado` is False when confirmar_presupuesto runs?

**No change**. The tool already has a precondition check (lines 51-63) that rejects if price wasn't communicated. This guard stays intact.

### 5.2. What if the user reaches EVALUACION_GATEWAY from a different path?

**No impact**. The gateway is still in the graph and still handles:
- Option A flow: Photos sent → follow_up asks "¿quieres abrir expediente?" → user says "sí" → next turn: intent_router classifies as CONFIRMACION → `_resolve_target_mode()` checks `previous_mode == "PRESUPUESTO_MODE"` → routes to `EVALUACION_GATEWAY` (conversation_graph.py:274)
- Intent router from START: User says "quiero abrir expediente" → `INICIAR_EXPEDIENTE` intent → maps to `EVALUACION_GATEWAY` (intent_router.py:54)

### 5.3. What about the `gateway_question_asked` flag?

**Removed from confirmar_presupuesto**. Since we're not going to the gateway, this flag is irrelevant. The gateway's own `_present_confirmation()` sets it independently (evaluacion_gateway.py:166) when it needs it.

### 5.4. What if transition_mode() loses context?

**Verified safe**. `transition_mode()` uses `Overwrite()` for mode_context (conversation_state.py:453), which starts clean. The `preserve_keys` mechanism copies specified keys from the old context into the new one (lines 439-442). Our new preserve rules carry exactly what `_auto_create_case()` needs.

### 5.5. What about the intent_router `CONFIRMACION` resolution?

**Edge case to monitor**. In `conversation_graph.py:269-274`, if the intent is CONFIRMACION and `previous_mode == "PRESUPUESTO_MODE"`, it routes to EVALUACION_GATEWAY. This is the Option A post-photos flow. This still works correctly because:
- Option B: Tool-driven transition (confirmar_presupuesto → EXPEDIENTE_MODE directly, within PRESUPUESTO_MODE turn — never hits the router)
- Option A: Router-driven transition (next turn after photos, intent_router classifies → gateway)

### 5.6. What about the fast-path anti-pattern?

**Known tech debt, separate effort**. The fast-path pattern (presupuesto_mode.py:420-437, expediente_mode.py:800-822) remains. The message in `confirmar_presupuesto` is now user-appropriate, which mitigates the immediate UX bug. A broader refactor of the fast-path pattern is recommended but out of scope for this fix.

---

## 6. Testing Plan

### 6.1. Manual Testing (Production Conversation)

| Test Case | Steps | Expected Result |
|-----------|-------|-----------------|
| **Option B direct** | 1. User asks to homologate element 2. Agent gives price + A/B 3. User says "B" | Agent responds with expediente welcome, transitions to EXPEDIENTE_MODE. Next turn starts element data collection. |
| **Option A → post-photos confirm** | 1. User says "A" 2. Photos sent 3. Follow-up: "¿abrir expediente?" 4. User says "sí" | Gateway presents confirmation. User confirms → EXPEDIENTE_MODE. |
| **Option B variants** | User says "B", "b", "Opción B", "la B", "abre el expediente", "empezamos" | All trigger confirmar_presupuesto → EXPEDIENTE_MODE |
| **precio not communicated** | Somehow confirmar_presupuesto called without price | Tool rejects: "No puedo iniciar el expediente todavía..." |
| **EXPEDIENTE context** | After Option B transition, check mode_context | Must contain: element_codes, tarifa_calculada, categoria_slug |
| **Case auto-creation** | After transition, EXPEDIENTE_MODE enters first sub-mode | Case created in DB with correct category, elements, tariff amount |

### 6.2. Unit Tests (if applicable)

```python
# test_transition_tools.py
async def test_confirmar_presupuesto_transitions_to_expediente():
    """confirmar_presupuesto should transition to EXPEDIENTE_MODE, not EVALUACION_GATEWAY."""
    # Setup state with precio_comunicado=True and tarifa_calculada
    result = await confirmar_presupuesto.ainvoke({})
    assert result["_internal_flags"]["_transition_to"] == "EXPEDIENTE_MODE"
    assert "gateway_question_asked" not in result["_internal_flags"]

# test_mode_transitions.py
def test_presupuesto_to_expediente_allowed():
    """PRESUPUESTO_MODE → EXPEDIENTE_MODE should be an allowed transition."""
    allowed, reason = validate_transition("PRESUPUESTO_MODE", "EXPEDIENTE_MODE")
    assert allowed is True
    assert reason == ""

def test_presupuesto_to_expediente_preserves_keys():
    """Context preserve rules should carry element data to EXPEDIENTE_MODE."""
    keys = get_preserve_keys("PRESUPUESTO_MODE", "EXPEDIENTE_MODE")
    assert "element_codes" in keys
    assert "tarifa_calculada" in keys
    assert "categoria_slug" in keys
```

---

## 7. Rollback Plan

If the change causes unexpected issues:

1. Revert `_transition_to` in `transition_tools.py` back to `"EVALUACION_GATEWAY"`
2. Revert `ALLOWED_TRANSITIONS` and `CONTEXT_PRESERVE_RULES`
3. Restore `reason_map` entry
4. Revert prompt changes

All changes are isolated and reversible. The gateway is never removed — only bypassed for the Option B flow.

---

## 8. Future Improvements (Out of Scope)

These are related issues discovered during investigation that should be addressed separately:

| Issue | Severity | Description | Effort |
|-------|----------|-------------|--------|
| **Fast-path anti-pattern** | CRITICAL | Tool `message` fields reach users as `ai_response` in both presupuesto_mode.py:420 and expediente_mode.py:800. Should either remove fast-path (let LLM generate response) or require tools to provide explicit user-facing messages. | MEDIUM |
| **`waiting_for_image_choice` never set** | MEDIUM | REFACTOR-001 removed pattern matching that set this flag. Regex block in presupuesto_mode.py:172-194 is dead code. Need a tool flag or remove the detection logic. | LOW |
| **`gateway_question_asked` flag loss** | LOW | Flag set by confirmar_presupuesto's `_internal_flags` but lost during transition_mode's `Overwrite()`. Currently masked because gateway classifies yes/no first. With this fix, this is no longer relevant for Option B but still affects Option A flow if it ever uses this flag. | LOW |
| **Hardcoded messages in case_tools.py** | HIGH | `cancelar_expediente` (L1683, 1707) and `finalizar_expediente` return hardcoded user-facing messages via the same fast-path pattern. | MEDIUM |

---

## 9. Implementation Order

1. **`agent/router/mode_transitions.py`** — Add transition + preserve rules (must be first — validation runs before transition)
2. **`agent/tools/transition_tools.py`** — Change transition target + message
3. **`agent/prompts/modes/presupuesto_mode.md`** — Update prompt references
4. **Test manually** — Send a test message through the system
5. **Restart agent service** — `docker-compose restart agent`

---

## 10. Approval Checklist

- [ ] Plan reviewed by developer
- [ ] No conflicts with active plans (verified: no overlap with `fix-foundation-architecture.md` or `transition-hardening.md`)
- [ ] ADR needed? **NO** — This is a bug fix, not an architecture change. The gateway concept remains intact.
- [ ] Impact on other services? **NO** — Changes are agent-internal only. API, admin panel, database unaffected.
- [ ] Documentation update needed? **YES** — prompt file (included in plan)
