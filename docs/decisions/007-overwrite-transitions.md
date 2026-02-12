# ADR-007: Overwrite-Based Mode Transitions

## Status

**Accepted** — February 2026

## Context

Deep audit of MSI-a agent revealed **systemic issues** with mode transitions:

- Only **2 of 19** transition points (17%) used `transition_mode()`
- `merge_dicts` reducer is **append-only** — `mode_context` keys can never be deleted
- Fallback `RESET_TO_MODE_START` was a **no-op** (`{} + merge = no effect`)
- `draft_contexts.pop()` was **ineffective** (reducer re-merges from checkpoint)
- Gateway transitions leaked presupuesto keys into expediente context
- Escalation set `escalation_triggered=True` without `current_mode="ESCALATION"`
- EXPEDIENTE sub-modes received no prompt context (wrong mode name match)
- `expediente_completed`/`cancelled` flags set but no transition triggered

### Root Cause

LangGraph's `merge_dicts` reducer does `{**current, **update}` — keys can only be added or overwritten, never removed. This means `mode_context` grew indefinitely as conversations progressed through modes, accumulating stale keys from every previous mode.

### Solution Available

LangGraph 1.0.8 provides `Overwrite(value)` which **bypasses the reducer entirely**, replacing the state field with exactly the provided value.

## Decision

1. **`transition_mode()` is the ONLY way to change modes** — all 19 transition points now use it
2. **`Overwrite()` for clean context** — `mode_context` and `draft_contexts` wrapped in `Overwrite()` during transitions
3. **Explicit key contracts** — `CONTEXT_PRESERVE_RULES` defines exactly which keys survive each transition
4. **`draft_contexts` functional** — save before transition, restore on return (pop actually works now)

## Implementation (8 Phases)

| Phase | What | Bugs Fixed |
|-------|------|------------|
| 0 | Regression tests (52 total) | — |
| 1 | `Overwrite` in `transition_mode()` + key contracts | C1, H4 |
| 2 | Migrate Gateway to `transition_mode()` | C3 |
| 3 | Migrate tool-signaled transitions | — |
| 4 | Fallback resets + escalation | C2, H1 |
| 5 | Completion/cancellation + prompt context | H3, M4 |
| 6 | Cleanup ghost keys | M4 |
| 7 | ADR + documentation | — |

## Consequences

### Positive

- **Clean context per mode** — Each mode starts with ONLY the keys it needs
- **No key leaks** — Gateway/presupuesto keys don't pollute expediente
- **Working drafts** — Can save and restore context when switching modes
- **Working resets** — Fallback `RESET_TO_MODE_START` actually clears context
- **Complete escalation** — Always sets `current_mode="ESCALATION"`
- **Testable** — 52 unit tests validate all transition behavior
- **Smaller Redis checkpoints** — Less stale data in serialized state

### Negative

- **`Overwrite` dependency** — Tied to LangGraph's `Overwrite` feature (available since 1.0.x)
- **All transitions must use `transition_mode()`** — Adding a new mode requires updating `CONTEXT_PRESERVE_RULES` and `ALLOWED_TRANSITIONS`
- **Intra-mode updates still use `merge_dicts`** — Only TRANSITIONS use `Overwrite`; normal mode_context updates within a mode still merge

### Risks Mitigated

- `Overwrite` is a stable LangGraph feature (not experimental)
- 52 regression tests catch any breakage
- Each phase was independently deployable

## Alternatives Considered

1. **Replace `merge_dicts` reducer with a custom one that supports deletion markers** — Too risky, affects ALL mode_context updates not just transitions
2. **Use a separate `transition_context` field** — Adds complexity, still needs cleanup logic
3. **Manual key filtering after merge** — Fragile, easy to miss new keys

## Files Modified

- `agent/state/conversation_state.py` — `Overwrite` import, `transition_mode()` updated
- `agent/router/mode_transitions.py` — Expanded `CONTEXT_PRESERVE_RULES`, added `COMPLETED` transition
- `agent/modes/evaluacion_gateway.py` — All handlers use `transition_mode()`
- `agent/modes/presupuesto_mode.py` — Tool-signaled transitions use `transition_mode()`
- `agent/modes/expediente_mode.py` — Same + completion/cancellation transitions
- `agent/fallback/fallback_handler.py` — Resets use `Overwrite`, transitions use `transition_mode()`
- `agent/modes/consulta_mode.py` — Escalation sets `current_mode`
- `agent/prompts/loader.py` — Sub-mode context + key name fix
- `agent/router/digression_manager.py` — Key name fixes
