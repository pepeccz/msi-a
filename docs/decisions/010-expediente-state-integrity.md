# ADR-010: Expediente State Integrity Fixes

## Status
**Accepted** — 2026-03-29

Implemented in `fix-expediente-state-integrity` (SDD change).

## Context

A production regression in EXPEDIENTE_MODE produced three distinct failure symptoms:

1. **Hallucinated phase progression** — Agent replied with "Paso 5/6 - Taller" content while in `collect_personal`. No tool was called to advance the phase.
2. **Stale state reads** — `actualizar_datos_expediente()` and `actualizar_datos_taller()` re-read `_get_mode_context()` AFTER a DB write. The ContextVar snapshot is captured BEFORE the tool runs, so the re-read returns stale data — missing the fields just saved. This caused `missing_fields` to be non-empty even when all data was present, blocking the sub-mode transition.
3. **Marker resurrection** — `expediente_transition_marker` (and other context keys) were cleared with `dict.pop()` only. `merge_dicts()` does `{**current, **update}`: a key absent from `update` survives from the Redis checkpoint. The marker would re-appear on turn N+2 and trigger duplicate or wrong transitions.

The three failures compose into a chain: F2 (resurrection) triggers a wrong-mode kickoff → F3 (hallucinated phase) fires → F1 (stale read) blocks the corrective transition.

## Decision

Three surgical, independently-revertible fixes:

### Fix A — Tool-Local Validation (F1)

Tools that write to DB then validate completeness **MUST derive their validation dict from `updates_for_fsm`** (the dict they just built), not from a second `_get_mode_context()` call.

**Affected files**: `agent/tools/case_tools.py`
- `actualizar_datos_expediente()` — removed stale reread at line 1448; validation now uses `updates_for_fsm.get("personal_data", case_fsm_state.get("personal_data", {}))`
- `actualizar_datos_taller()` — removed stale reread at line 1738; validation now uses `updates_for_fsm.get("taller_propio")` / `updates_for_fsm.get("taller_data")`
- `obtener_estado_expediente()` — now queries DB with `selectinload(Case.images, Case.element_data, Case.user)`; derives `current_step` from DB truth; `mode_context` is fallback-only.

**Invariant**: After `await _update_fsm_state(...)`, never call `_get_mode_context()` again in the same tool invocation.

### Fix B — Tombstone Protocol (F2)

Any mode or tool clearing a `mode_context` key **MUST assign `None`** to that key in the emitted update dict after `pop()`. This ensures `merge_dicts()` overwrites the checkpoint value instead of leaving it to survive.

**Affected files**:
- `agent/modes/expediente_mode.py` — 7 cleanup sites now use `pop()` + `= None` tombstone:
  - `expediente_transition_marker`
  - `just_transitioned_from`
  - `_transition_to`
  - `expediente_intro_message`
  - `case_instructions`
  - `_fsm_state_init`
  - `_guard_photo_fired_this_turn` (uses `= False`)
- `agent/modes/presupuesto_mode.py` — `_tarifa_actual` cleanup site now tombstoned.

Each site is annotated with `# TOMBSTONE: assign None/False after pop so merge_dicts overwrites checkpoint; never use pop() alone`.

**Why `None` is safe**: All callers use `.get(key)` or `.get(key, default)`, which treat `None` identically to absent. No code does `if key in mode_context` without also checking truthiness.

**Note**: `merge_dicts()` in `conversation_state.py` did NOT need to be changed — `{**current, **{"key": None}}` yields `{"key": None}`, which is functionally equivalent to absent for all callers.

### Fix C — Kickoff Phase Truthfulness Guard (F3)

On no-tool kickoff turns, the LLM can hallucinate content from a different phase. The guard detects two violation types and strips the offending content:

**Type 1 — Step-number mismatch**: Response contains `Paso X/6` where `X ≠ _SUBMODE_STEP_MAP[sub_mode]`.

**Type 2 — Advancement without tools**: Response contains advancement language (`siguiente paso`, `pasemos a`, `hemos completado`, etc.) without any tool having been called.

```python
_SUBMODE_STEP_MAP = {
    "collect_element_data": 1,
    "collect_base_docs": 2,
    "collect_personal": 3,
    "collect_vehicle": 4,
    "collect_workshop": 5,
    "review_summary": 6,
}
```

**On violation**: Strip the matched content, log `kickoff_phase_mismatch_detected` or `kickoff_advancement_without_tools` with structured fields. Pass the cleaned response through (forgiving, not full-reject).

**Scope**: Only fires for `_is_kickoff_no_tool_turn = True`. Normal turns with tools use the standard constraint validation path.

**Affected file**: `agent/modes/expediente_mode.py` — guard implemented at lines 3361-3401.

## Consequences

**Positive**:
- Eliminates the F2→F3→F1 failure chain that produced incoherent escalations and phantom `Paso X/6` decoration.
- Fix A is zero-latency (no extra I/O — local dict lookup replaces a redundant ContextVar read).
- Fix B is zero-overhead (one dict assignment per cleanup site).
- Fix C is cheap (two compiled regex checks on kickoff-only no-tool turns).
- All three fixes are independently revertible.

**Negative / Trade-offs**:
- Fix C regex patterns must be maintained if new advancement phrases are added to prompts.
- `None` tombstones are "invisible" in mode_context dicts — callers must not assume absent = never-set (use explicit `is None` checks when distinguishing "not yet set" from "cleared").

## Alternatives Considered

| Alternative | Rejected Because |
|-------------|-----------------|
| Re-read DB after every DB write (Fix A) | Extra I/O per tool invocation; local dict is already the truth |
| Change `merge_dicts()` to strip `None` values globally (Fix B) | Would break callers that legitimately set a key to `None` as a valid value |
| Keyword blocklist per sub-mode (Fix C) | Brittle — LLM phrasing varies; too many false positives |
| Require a tool call on all kickoff turns (Fix C) | Too strict — valid kickoff responses don't need tool calls |

## Tests Added

| File | Coverage |
|------|----------|
| `tests/agent/tools/test_stale_reread_fix.py` | Fix A: stale-context personal/vehicle/workshop scenarios |
| `tests/unit/test_tombstone_merge_semantics.py` | Fix B: two-turn merge cycle, no resurrection on turn N+2 |
| `tests/unit/test_expediente_kickoff_phase_guard.py` | Fix C: step-number mismatch + advancement language stripping |
| `tests/unit/test_expediente_state_integrity_regression.py` | F2→F3→F1 incident chain non-recurrence (pure logic, no Docker) |
| `tests/integration/test_expediente_state_integrity.py` | Full flow, DB-sourced state, production incident chain (Docker) |

**Coverage**: 114 tests passed (0 failed) in verification run.

## Follow-up Fixes (p0-state-integrity-fixes, 2026-03-29)

Four additional surgical fixes applied as a follow-on change to `fix-expediente-state-integrity`. These are not new architectural decisions — they are targeted corrections of four related defects discovered after the original ADR was implemented.

### Fix 1 — Tombstone `_transition_to` in `presupuesto_mode.py`

`_transition_to` was popped but not tombstoned in `presupuesto_mode.py` (line ~1065). The same tombstone protocol documented in Fix B above now applies here. Without the tombstone, the key could resurrect from the Redis checkpoint on the next turn, causing phantom mode transitions in the presupuesto flow.

**File**: `agent/modes/presupuesto_mode.py` — added `updated_context["_transition_to"] = None  # TOMBSTONE` after pop.

### Fix 2 — `finalizar_expediente()` reads from DB, not stale `case_fsm_state`

`finalizar_expediente()` in `agent/tools/case_tools.py` was reading `element_codes`, `categoria_slug`, `taller_propio`, and `tariff_amount` from `case_fsm_state` (stale ContextVar snapshot). These fields are authoritative columns on the `Case` row. Fixed to use `selectinload(Case.category)` + read from the ORM object.

**File**: `agent/tools/case_tools.py` — `finalizar_expediente()` rewritten to eager-load case with category and read fields from DB.

### Fix 3 — `tool_validation.py` fail-closed on missing `categoria_slug`

`SemanticValidator.validate()` was using `continue` when `categoria_slug` was absent during `element_code`/`tier_id` validation — silently passing invalid tool calls. Fixed to append an error to the `errors` list before `continue`, making validation fail-closed.

**File**: `agent/utils/tool_validation.py` — both `element_code` and `tier_id` branches now append error before `continue`.

### Fix 4 — Canonical sub-mode names in `expediente_transition_adapter.py`

`CANONICAL_SUB_MODES` and `SUB_MODE_ALIAS_MAP` used `collect_taller` and `review` as canonical names, but the rest of the codebase (`expediente_mode.py`, `guardrails.py`, constants, loader) uses `collect_workshop` and `review_summary`. Fixed 9 string constants to match canonical names. `ENABLE_CANONICAL_TRANSITION_ADAPTER` is now safe to enable.

**File**: `agent/utils/expediente_transition_adapter.py` — 9 string replacements (lines 43–76).

### Tests Added (p0-state-integrity-fixes)

| File | Coverage |
|------|----------|
| `tests/unit/test_p0_tombstone_presupuesto.py` | Fix 1: tombstone prevents `_transition_to` resurrection across turns |
| `tests/agent/tools/test_p0_finalizar_expediente_db.py` | Fix 2: DB-sourced fields in Chatwoot note vs. stale fsm_state |
| `tests/unit/test_p0_validation_fail_closed.py` | Fix 3: missing `categoria_slug` returns `(False, [error])` |
| `tests/unit/test_p0_adapter_submode_names.py` | Fix 4: canonical sub-mode names match codebase constants |

**Coverage**: 30 new tests passed (0 failed) in verification run.

**Change artifacts**: Engram observations #1863 (proposal), #1864 (spec), #1865 (design), #1866 (tasks), #1874 (verify-report), archive-report.

## References

- Change artifacts: Engram observations #1821 (proposal), #1822 (spec), #1823 (design), #1824 (tasks), #1828 (verify-report), archive-report
- Related: `docs/decisions/005-tool-driven-state-management.md` — original tool-driven state pattern
- Related: `docs/decisions/007-overwrite-transitions.md` — overwrite transition semantics
