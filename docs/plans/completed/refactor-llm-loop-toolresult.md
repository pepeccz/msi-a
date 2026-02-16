# Plan: Refactor LLM Loop + ToolResult Dataclass (Deferred)

**Created**: 2026-02-12
**Status**: DEFERRED — Pending regression test suite
**Estimated effort**: 2-3 days
**Risk level**: HIGH (3 behavioral differences between modes, 90% traffic through PRESUPUESTO)
**Depends on**: `fix-foundation-architecture.md` Phases 0-2 deployed and stable
**Author**: architect agent

---

## Why Deferred

Deep investigation (4 parallel investigator-dev agents) discovered that the 3 mode LLM loops have **22 documented differences**, of which **3 are HIGH-risk behavioral** differences that could cause regressions in production:

1. **Constraint injection role**: PRESUPUESTO uses `"system"` role with extra instruction text; CONSULTA and EXPEDIENTE use `"user"` role. Changing this for PRESUPUESTO could cause the LLM to ignore price corrections → hallucinated prices (90% of traffic).

2. **ContextVar re-injection**: Only EXPEDIENTE re-injects ContextVars after each tool call. Removing this causes tools to read stale state → silent data corruption in case collection.

3. **`_extract_context_from_tool()` signature**: EXPEDIENTE uses 4 parameters (includes `current_context`); PRESUPUESTO uses 3. Cannot safely unify without choosing the wider signature.

**Decision**: These risks are not justified without a regression test suite that can verify behavioral equivalence before and after refactoring.

---

## Prerequisites Before Starting

- [ ] Phases 0-2 from `fix-foundation-architecture.md` deployed and stable for ≥1 week
- [ ] Regression test suite created for all 3 modes covering:
  - PRESUPUESTO: pricing flow, variant resolution, image sending, constraint validation
  - EXPEDIENTE: sub-mode transitions, ContextVar state consistency, tool chaining
  - CONSULTA: RAG queries, first interaction greeting, entity extraction
- [ ] Feature flag mechanism for gradual rollout (run old and new loops in shadow mode)

---

## Phase 3: Extract LLM Loop to BaseModeNode (1-2 days)

### Objective

Extract the ~300-line duplicated LLM tool-calling loop from `presupuesto_mode.py`, `expediente_mode.py`, and `consulta_mode.py` into a template method in `base_mode.py`.

### Complete Difference Inventory (22 differences)

#### HIGH-RISK Behavioral Differences (MUST preserve per-mode)

| # | Aspect | PRESUPUESTO | EXPEDIENTE | CONSULTA |
|---|--------|-------------|------------|----------|
| 1 | Constraint injection role | `"system"` + tool instruction suffix | `"user"` | `"user"` |
| 2 | ContextVar re-injection mid-loop | ❌ NO | ✅ YES (after every tool) | ❌ NO |
| 3 | `_extract_context_from_tool` signature | 3 args | **4 args** (+ current_context) | Not called |

#### MEDIUM-RISK Behavioral Differences

| # | Aspect | PRESUPUESTO | EXPEDIENTE | CONSULTA |
|---|--------|-------------|------------|----------|
| 4 | Constraint injection text format | Extra suffix: "You MUST call tools..." | Only error_injection | Only error_injection |
| 5 | Token tracking placement | Inside loop (every iteration) | Inside loop | **Outside loop** (last response only) |
| 6 | `all_applied_flags` tracking | ✅ YES | ✅ YES | ❌ NO |
| 7 | Flag authority merge (FINAL AUTHORITY) | ✅ YES | ✅ YES | ❌ NO |
| 8 | Mode transition propagation (`_transition_to`) | ✅ YES | ✅ YES | ❌ NO |
| 9 | First interaction greeting injection | ❌ NO | ❌ NO | ✅ YES |
| 10 | Pre-loop A/B option detection | ✅ YES | ❌ NO | ❌ NO |
| 11 | ContextVar state construction | `dict(state)` + override | `dict(state)` + override | `state` directly (no copy) |

#### CONFIGURATION Differences (safe to parameterize)

| # | Aspect | PRESUPUESTO | EXPEDIENTE | CONSULTA |
|---|--------|-------------|------------|----------|
| 12 | MAX_TOOL_ITERATIONS | 10 | 10 | 8 |
| 13 | max_tokens LLM | 3000 | 1500 | 1500 |
| 14 | Fallback timeout text | Different per mode | Different | Different |

#### LOW-RISK / STRUCTURAL (safe to unify)

| # | Aspect | Notes |
|---|--------|-------|
| 15 | `_apply_tool_flags()` usage | PRES+EXP: yes, CONS: no |
| 16 | Pending images extraction | PRES+EXP: yes, CONS: no |
| 17 | `_tarifa_actual` cleanup | PRES only |
| 18 | Pending images follow-up persistence | PRES+EXP: yes, CONS: no |
| 19 | `consulta_history` tracking | CONS only |
| 20 | Entity extraction (pre-loop) | CONS only |
| 21 | Context memory injection (pre-loop) | CONS only |
| 22 | Identical helper methods (`_get_llm`, `_invoke_with_fallback`, `_ai_message_to_dict`, `_build_client_context`) | Safe to consolidate |

### Recommended Hook Methods (9 consolidated)

| Hook | Purpose | Override by | Default |
|------|---------|-------------|---------|
| `_get_loop_config()` | Returns `LoopConfig(max_iterations, max_tokens, fallback_text, track_tokens_per_iteration)` | All 3 | `LoopConfig(10, 1500, generic_text, True)` |
| `_pre_loop_setup(message, state, mode_context)` | Pre-loop mode-specific logic | PRES (A/B detection), CONS (entity extraction) | No-op |
| `_build_system_prompt(mode_context, state)` | Assembly + modifications | All 3 (different mode names + CONS adds context memory) | Abstract |
| `_build_initial_messages(system_prompt, messages, state)` | LLM message list construction | CONS (greeting injection) | Standard list |
| `_get_constraint_config()` | Returns `ConstraintConfig(role, text_format)` | PRES (`"system"` + suffix) | `ConstraintConfig("user", standard)` |
| `_should_apply_tool_flags()` | Whether to apply `_internal_flags` | CONS (False) | True |
| `_should_reinject_contextvar()` | Mid-loop ContextVar re-injection | EXP (True) | False |
| `_extract_context_from_tool(name, args, result, mode_context)` | Per-tool context extraction | PRES, EXP (different logic) | Empty dict |
| `_post_tool_hook(tool_name, result, mode_context, context_updates)` | Post-tool processing | CONS (consulta_history), PRES+EXP (pending images) | No-op |

### Changes Summary

1. **Move `_apply_tool_flags()` to `base_mode.py`** — Currently in presupuesto_mode.py, imported by expediente_mode.py. No circular import risk (confirmed by investigator).
2. **Add `_run_llm_loop()` template method to `BaseModeNode`** — ~200 lines consolidating the shared pattern.
3. **Refactor `PresupuestoModeNode._process_message()`** — From ~250 lines to ~30 lines + hook overrides.
4. **Refactor `ExpedienteModeNode._run_llm_loop()`** — Replace with base version + hooks.
5. **Refactor `ConsultaModeNode._process_message()`** — From ~150 lines to ~20 lines + hooks.
6. **Consolidate shared helpers** — `_get_llm()`, `_invoke_with_fallback()`, `_build_client_context()`, `_ai_message_to_dict()` into BaseModeNode.

### Critical Implementation Rules

1. **NEVER change constraint injection role per mode** — PRESUPUESTO MUST keep `"system"` with instruction suffix
2. **NEVER remove ContextVar re-injection from EXPEDIENTE** — Tools will read stale state
3. **Use 4-arg signature for `_extract_context_from_tool()`** — PRESUPUESTO ignores 4th param
4. **Token tracking hook** — CONSULTA tracks only final response; others track per-iteration
5. **ContextVar construction** — Always make a copy (safe pattern from PRES/EXP)

### Expected Results

- ~400 lines removed across 3 mode files
- Zero behavioral regressions (verified by regression tests)
- All mode-specific behavior captured in hooks
- `_apply_tool_flags()` in base_mode.py (proper home)

---

## Phase 4: Clean Tool→State Communication (0.5 days)

### Objective

Create a `ToolResult` dataclass wrapper around `_execute_and_log_tool()` to eliminate defensive JSON parsing at every call site.

### Investigation Findings

1. **`_execute_and_log_tool()` ALWAYS returns `str`** — JSON-dumps dicts, passes through pre-serialized strings, plaintext for exceptions.
2. **4 tools return pre-serialized `str`** (not dict): `calcular_tarifa_con_elementos`, `identificar_y_resolver_elementos`, `seleccionar_variante_por_respuesta`, `listar_elementos` — with indent=2 formatting.
3. **7 consumer patterns** all do `json.loads(result) if isinstance(result, str) else result` defensively.
4. **Critical risk**: If `ToolResult` object (not `.raw`) is passed as LLM message content, it BREAKS the conversation completely.

### Design

```python
@dataclass
class ToolResult:
    raw: str                      # Byte-for-byte identical to current string
    parsed: dict | None           # Pre-parsed, or None if not JSON
    success: bool                 # Inferred from parsed
    flags: dict                   # _internal_flags extracted
    tool_name: str                # For debugging

    def __str__(self) -> str:
        return self.raw  # Safety: if accidentally used as str
```

### Implementation Strategy: Gradual Wrapper (NOT big-bang)

1. **Create `ToolResult` and `_execute_tool_structured()`** — wrapper around existing `_execute_and_log_tool()`, which stays unchanged.
2. **Migrate `_run_llm_loop()`** (Phase 3) to use `ToolResult` internally, always using `.raw` for LLM messages.
3. **Keep `_execute_and_log_tool()` for backwards compatibility** — both methods coexist.
4. **Gradually migrate `_extract_context_from_tool`** and `_extract_pending_images` to accept `ToolResult` (optional, only if clarity improves).

### Critical Rules

- `ToolResult.raw` MUST be the exact output of `_execute_and_log_tool()` — NEVER re-serialize
- LLM messages MUST use `tool_result.raw`, NEVER the ToolResult object
- `_apply_tool_flags()` receives `tool_result.parsed or {}`, never the ToolResult object
- Must handle 4 raw formats: JSON dict, JSON with indent, plaintext error, "None" string

---

## Files Modified (Both Phases)

| File | Phase | Type of Change |
|------|-------|----------------|
| `agent/modes/base_mode.py` | 3, 4 | Add `_run_llm_loop()` template, `_apply_tool_flags()`, `ToolResult`, shared helpers, 9 hook methods |
| `agent/modes/presupuesto_mode.py` | 3 | Remove `_apply_tool_flags()`, replace `_process_message()` with hooks |
| `agent/modes/expediente_mode.py` | 3 | Replace `_run_llm_loop()` with base version + hooks |
| `agent/modes/consulta_mode.py` | 3 | Replace `_process_message()` with hooks |

---

## Risk Summary

| Risk | Severity | Mitigation |
|------|----------|------------|
| Constraint role change in PRESUPUESTO | 🔴 HIGH | Per-mode hook, never unify |
| ContextVar re-injection lost in EXPEDIENTE | 🔴 HIGH | `_should_reinject_contextvar()` hook, default False |
| `_extract_context_from_tool` signature mismatch | 🔴 HIGH | Use 4-arg signature, PRES ignores 4th |
| Token tracking inconsistency | 🟡 MEDIUM | `track_tokens_per_iteration` in LoopConfig |
| ToolResult object passed to LLM message | 🔴 HIGH | `__str__()` returns `.raw`, code review |
| Re-serialization alters format | 🟡 MEDIUM | Never re-serialize, `.raw` is exact passthrough |

---

## Success Criteria

### Phase 3
- [ ] Regression test suite passes with zero failures
- [ ] Total line count reduced by ~400
- [ ] All 3 modes use `_run_llm_loop()` from BaseModeNode
- [ ] `_apply_tool_flags()` in base_mode.py
- [ ] Behavioral equivalence verified for all 22 documented differences
- [ ] Production monitoring shows no change in constraint trigger rates, token usage patterns, or error rates for 48 hours

### Phase 4
- [ ] `ToolResult.raw` is byte-for-byte identical to current `_execute_and_log_tool()` output
- [ ] No more `json.loads(result) if isinstance(result, str) else result` in mode code
- [ ] All 18 existing tests still pass
- [ ] mypy clean on modified files
