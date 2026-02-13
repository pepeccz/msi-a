# ADR-006: Fix FSM Compat State Propagation

## Status

**Accepted** — February 2026

## Context

The MSI-a agent was migrated from v1 (FSM-based) to v2 (Mode-based) architecture. The v1 tools were recycled with a compatibility layer (`fsm_compat.py`) that wraps state updates in `{"case_collection": {...}}`. However, a critical design flaw in this layer caused state updates to be silently lost in two ways:

### Bug 1 — Chained Calls Overwrite

`update_case_fsm_state()` ignored its `fsm_state` parameter and always created a new dict, meaning chained calls (e.g., `transition_to()` followed by `update_case_fsm_state()`) would lose the first call's data.

```python
# BUG: Always creates new dict, ignores existing fsm_state
def update_case_fsm_state(fsm_state: dict, key: str, value: Any) -> dict:
    return {"case_collection": {key: value}}  # Previous keys LOST
```

### Bug 2 — Double-Nesting Not Unwrapped

Tools return `{"fsm_state_update": {"case_collection": {...}}}`, but the mode extractor only searched for `case_collection` at the root level, never finding it inside `fsm_state_update`.

```python
# Tool returns:
{"fsm_state_update": {"case_collection": {"expediente_sub_mode": "collect_element_data"}}}

# Extractor looks for:
data.get("case_collection")  # None — it's nested one level deeper
```

### Bug 3 — Parameter Mismatch

The extractor looked for a `seccion` parameter on `actualizar_datos_expediente` that never existed in the tool's signature. Sub-mode transitions from this tool were silently ignored.

### Bug 4 — Missing Handler

`editar_expediente` had no handler in `_extract_context_from_tool()`. Any state updates from editing expediente data were discarded.

### Bug 5 — Model Field Mismatch

`validate_case_id()` in the constraint service referenced `Case.is_active` which doesn't exist on the model. The `Case` model uses a `status` field. This caused validation to always fail with an AttributeError, breaking all expediente operations that needed case validation.

### Impact

These bugs affected **100% of expediente conversations** with elements requiring technical data. The combination of silent state loss meant:

- Sub-mode transitions failed (stuck in wrong collection phase)
- Element technical data was collected but never persisted to mode_context
- Case validation always errored, preventing expediente creation
- 12 distinct failure modes identified across the 5 bugs

## Decision

Implement a 3-level fix targeting immediate resolution, defense in depth, and architectural stabilization.

### Level 1 — Immediate (resolves active bugs)

**Fix `update_case_fsm_state()` to MERGE** instead of overwriting:

```python
# FIXED: Merge with existing case_collection
def update_case_fsm_state(fsm_state: dict, key: str, value: Any) -> dict:
    existing = fsm_state.get("case_collection", {}) if fsm_state else {}
    existing[key] = value
    return {"case_collection": existing}
```

**Fix `_extract_context_from_tool()` to unwrap `fsm_state_update`**:

```python
# FIXED: Check both root-level and nested case_collection
case_collection = data.get("case_collection")
if not case_collection:
    fsm_update = data.get("fsm_state_update", {})
    if isinstance(fsm_update, dict):
        case_collection = fsm_update.get("case_collection")
```

**Fix `validate_case_id()` to use `Case.status`**:

```python
# FIXED: Use correct model field
case = await session.get(Case, case_id)
if not case or case.status == "cancelled":
    return {"valid": False, "error": "Expediente no encontrado o cancelado"}
```

### Level 2 — Defense in Depth (prevents recurrence)

- Fix `actualizar_datos_expediente` handler to detect transitions by `next_step` field instead of non-existent `seccion` parameter
- Add handler for `editar_expediente` tool
- Add redundant root-level fields to tool return values (belt + suspenders)
- Fix incorrect docstrings that documented non-existent parameters

### Level 3 — Architectural Stabilization (eliminates technical debt)

- Create `_context_updates` contract for new tools (`tool_context_contract.py`) — standardized way for tools to declare state changes
- Add state reconciliation with DB at the start of each expediente turn — safety net against future state loss
- Progressive migration of v1 tools to new contract (future work)

## Consequences

### Positive

- All 12 identified failure modes are resolved (8 from chaining, 3 from nesting, 1 from Case model)
- Expediente flow now correctly transitions between all 6 sub-modes
- State reconciliation provides a safety net against future state loss
- New tools have a clean, explicit contract for state updates
- `validate_case_id()` now works correctly with meaningful error messages
- Redundant root-level fields ensure state propagation even if one path fails

### Negative

- `fsm_compat.py` remains as a compatibility layer (not eliminated)
- Tools now have redundant state declarations (root-level + `fsm_state_update`) — trade-off for reliability
- State reconciliation adds one DB query per turn in expediente mode
- Increased complexity in `_extract_context_from_tool()` with two unwrapping paths

### Neutral

- 6 files modified in production code
- 1 new file created (`tool_context_contract.py`)
- No changes to tool signatures — backward compatible

## Alternatives Considered

### Alternative 1: Complete Elimination of fsm_compat.py

Rewrite all 26 tools to use mode_context directly, removing the compatibility layer entirely.

**Rejected** — Too high risk of regression with 26 tools affected across 6 tool files. The compatibility layer works correctly once the merge bug is fixed. Planned as incremental migration (Level 3, Task 3.3).

### Alternative 2: Only Fix the Extractor

Fix `_extract_context_from_tool()` to unwrap double-nesting, but leave `update_case_fsm_state()` as-is.

**Rejected** — Doesn't resolve the chaining bug, which affects 8 tools independently of the nesting issue. Both bugs must be fixed together for correct behavior.

### Alternative 3: Replace mode_context with Top-Level State Fields

Move all expediente state from `mode_context["case_collection"]` to top-level `ConversationState` fields.

**Rejected** — Breaks mode encapsulation (mode-specific data leaks to global state) and requires checkpointer migration. The nested structure is correct; only the propagation mechanism was broken.

## Files Changed

| File | Change |
|------|--------|
| `agent/utils/fsm_compat.py` | Merge semantics for `update_case_fsm_state()` |
| `agent/modes/expediente_mode.py` | Extractor fixes, new handlers, state reconciliation |
| `agent/services/constraint_service.py` | `Case.status` fix (was `Case.is_active`) |
| `agent/tools/element_data_tools.py` | Redundant root-level fields in returns |
| `agent/utils/tool_context_contract.py` | New file — standard contract for tool state updates |
| `api/utils/pagination.py` | Docstring fixes |

## Related ADRs

- **ADR-002**: Dynamic Prompts — Establishes mode-based prompt architecture
- **ADR-005**: Tool-Driven State Management — Establishes `_internal_flags` pattern for presupuesto; this ADR fixes the equivalent mechanism for expediente
- **ADR-007**: Overwrite-Based Mode Transitions — Related mode transition fixes

## References

- Compatibility layer: `agent/utils/fsm_compat.py`
- Mode extractor: `agent/modes/expediente_mode.py` (`_extract_context_from_tool`)
- Tool context contract: `agent/utils/tool_context_contract.py`
- Constraint service: `agent/services/constraint_service.py`

---

**Author**: Agent Dev  
**Date**: February 2026  
**Status**: Accepted & Implemented
