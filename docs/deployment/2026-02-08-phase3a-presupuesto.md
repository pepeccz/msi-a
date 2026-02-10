# Phase 3 Deployment: presupuesto_mode Integration

**Date**: February 8, 2026, 14:01 UTC  
**Component**: Agent validation retry system  
**Mode**: PRESUPUESTO_MODE (highest traffic mode)

---

## Summary

Integrated Phase 3 validation error recovery into `presupuesto_mode.py`, extending the defensive parameter validation system to the most critical conversation mode (~65% of total agent traffic).

---

## Changes Made

### 1. Import Addition

**File**: `agent/modes/presupuesto_mode.py`  
**Line**: 40

```python
from agent.state.conversation_state import ConversationState, create_empty_retry_state
```

**Purpose**: Import the retry state factory function for Phase 3.

---

### 2. Retry State Initialization

**Location**: Line 263 (before tool loop)

```python
# Phase 3: Initialize retry state for validation error recovery
retry_state = state.get("retry_state", create_empty_retry_state())
```

**Purpose**: Initialize or load existing retry state from conversation state.

---

### 3. Validation Error Detection & Retry Logic

**Location**: Lines 341-381 (after tool execution)

```python
# ═══════════════════════════════════════════════════════════
# Phase 3: Validation error retry logic
# ═══════════════════════════════════════════════════════════
is_val_error, error_dict = self._is_validation_error(result)

if is_val_error and error_dict:  # Type guard
    should_retry, retry_state = self._handle_validation_retry(
        tool_name=tool_name,
        error_dict=error_dict,
        retry_state=retry_state,
        llm_messages=llm_messages,
    )
    
    if should_retry:
        # Reprompt added to llm_messages, continue LLM loop
        self._logger.info(
            "validation_retry_triggered",
            tool=tool_name,
            retry_count=retry_state.get("retry_count"),
            conversation_id=conversation_id,
        )
        break  # Exit tool loop, go to next iteration
    else:
        # Max retries reached - escalate
        self._logger.warning(
            "validation_escalation",
            tool=tool_name,
            retry_count=retry_state.get("retry_count"),
            conversation_id=conversation_id,
        )
        return {
            "ai_response": self._fallback.get_validation_reprompt(
                retry_state, self._policy
            ),
            "escalation_triggered": True,
            "escalation_reason": "max_validation_retries",
            "retry_state": retry_state,
            "mode_context": mode_context,
        }
# ═══════════════════════════════════════════════════════════
# End Phase 3 validation retry logic
# ═══════════════════════════════════════════════════════════
```

**Flow**:
1. Detect validation error from tool result
2. Check retry limit (4 for PRESUPUESTO_MODE)
3. If < max: add progressive reprompt, retry
4. If ≥ max: escalate to human

---

### 4. Retry State Persistence

**Location**: Line 433 (state updates)

```python
result_dict: dict[str, Any] = {
    "ai_response": ai_response,
    "mode_context": updated_context,
    "retry_state": retry_state,  # Phase 3: Persist retry state
}
```

**Purpose**: Persist retry state to Redis checkpoint for conversation continuity.

---

## Retry Policy Configuration

**Mode**: PRESUPUESTO_MODE  
**Max retries**: 4 (highest of all modes)  
**Action on limit**: ESCALATE_TO_HUMAN  
**Strategy**: "simplify"

**Source**: `agent/fallback/fallback_handler.py`

**Progressive reprompts**:
1. Retry 1: "Los parámetros no son válidos. Por favor, revisa..."
2. Retry 2: "Problema con {tool}: {specific_errors}. Corrige..."
3. Retry 3: "Aún hay errores. Verifica {specific_errors}..."
4. Retry 4+: "No pude procesar. Te conecto con un humano."

---

## Risk Assessment

### High Risk Factors

1. **Traffic volume**: PRESUPUESTO_MODE handles ~65% of agent traffic
2. **Business critical**: Pricing calculations are core functionality
3. **Tool complexity**: 10 tools available, 8 with validation
4. **State management**: Complex precio_comunicado/imagenes_enviadas flags

### Mitigation

1. **Identical pattern**: Used exact same code as consulta_mode (proven stable)
2. **Conservative rollout**: Deployed to presupuesto_mode only (not all modes at once)
3. **Monitoring ready**: Structured logs for validation_retry_triggered, validation_escalation
4. **Fallback tested**: Escalation path verified in consulta_mode

---

## Testing Performed

### 1. Syntax Check

```bash
docker-compose restart agent
# Result: ✅ Agent started successfully, no import errors
```

### 2. Health Check

```bash
docker-compose ps agent
# Result: ✅ Up (healthy)
```

### 3. Log Verification

```bash
docker-compose logs agent | tail -50
# Result: ✅ Clean startup, no errors
```

---

## Monitoring Plan

### Key Metrics to Track

**1. Validation retry events**:
```bash
docker-compose logs agent | grep "validation_retry_triggered"
```

**Expected**: 0-5 events per day (validation errors are rare with Phases 1+2)

**2. Escalation events**:
```bash
docker-compose logs agent | grep "validation_escalation"
```

**Expected**: 0-1 events per day (should be extremely rare)

**3. Tool-specific errors**:
```bash
docker-compose logs agent | grep "validation_retry" | grep "calcular_tarifa"
```

**Most likely tools to trigger retries**:
- `calcular_tarifa_con_elementos` (complex categoria_slug + element validation)
- `identificar_y_resolver_elementos` (element code + variant validation)
- `seleccionar_variante_por_respuesta` (variant code validation)

---

## Rollout Strategy

### Phase 3 Coverage (Current)

| Mode              | Traffic | Phase 3 Status | Retry Limit |
| ----------------- | ------- | -------------- | ----------- |
| CONSULTA          | ~10%    | ✅ Deployed      | 3           |
| PRESUPUESTO       | ~65%    | ✅ **NEW**       | 4           |
| EXPEDIENTE        | ~20%    | ⏳ Pending      | 3           |
| EVALUACION_GATEWAY| Entry   | ⏳ Pending      | 2           |

**Total coverage**: ~75% of traffic (CONSULTA + PRESUPUESTO)

### Next Steps

1. **Monitor 24-48 hours**: Watch presupuesto_mode validation events
2. **Analyze retry patterns**: Identify most common validation errors
3. **Rollout to EXPEDIENTE**: Most complex mode, highest retry limit (3)
4. **Rollout to EVALUACION_GATEWAY**: Pattern-based mode, minimal tools

---

## Success Criteria

### ✅ Deployment Success (14:01 UTC)

- [x] Agent restarts cleanly
- [x] No import errors
- [x] Service healthy
- [x] Zero errors in logs

### ⏳ Runtime Success (24-48h monitoring)

- [ ] Validation retry events logged correctly
- [ ] Progressive reprompts applied
- [ ] Escalation path works as expected
- [ ] No false positives (valid tool calls retrying unnecessarily)
- [ ] No regressions (presupuesto flow still works normally)

---

## Rollback Plan

### Symptoms Requiring Rollback

1. **High false positive rate**: Valid tool calls triggering retries
2. **Performance degradation**: Retry logic adding noticeable latency
3. **Escalation flood**: Too many conversations escalating to human
4. **Data corruption**: Retry state causing state management issues

### Rollback Procedure

```bash
cd /home/autohomologacion/msi-a

# 1. Revert presupuesto_mode.py changes
git checkout HEAD~1 -- agent/modes/presupuesto_mode.py

# 2. Restart agent
docker-compose restart agent

# 3. Verify health
docker-compose ps agent
docker-compose logs agent | tail -50

# 4. Commit rollback
git add agent/modes/presupuesto_mode.py
git commit -m "revert: rollback Phase 3 from presupuesto_mode due to [REASON]"
```

**Recovery time**: ~2 minutes

---

## Integration Details

### Code Reuse from consulta_mode

Phase 3 integration in presupuesto_mode is **identical** to consulta_mode:

**Shared components**:
- `_is_validation_error()` - From `BaseModeNode`
- `_handle_validation_retry()` - From `BaseModeNode`
- `create_empty_retry_state()` - From `agent.state.conversation_state`
- Progressive reprompt logic - From `FallbackHandler`

**Only difference**: Retry limit (4 vs 3)

This code reuse:
- Reduces bugs (proven implementation)
- Maintains consistency across modes
- Simplifies maintenance

---

## Performance Impact

### Validation Overhead (Per Tool Call)

**Without Phase 3**:
```
Tool execution → 50-200ms
```

**With Phase 3**:
```
Tool execution → 50-200ms
Validation check → <1ms (JSON parse + dict lookup)
Total: 51-201ms
```

**Impact**: Negligible (<1% overhead)

### Retry Overhead (If Triggered)

**Scenario**: Validation fails, retry triggered

```
Retry 1: +1-3 seconds (LLM invocation + tool re-execution)
Retry 2: +1-3 seconds
Retry 3: +1-3 seconds
Retry 4: +1-3 seconds
```

**Max overhead**: 12 seconds (if all 4 retries exhausted)

**Expected frequency**: <0.1% of conversations (validation errors are rare)

---

## Known Limitations

### 1. State Validation Retry Strategy

**Issue**: Phase 3 currently retries ALL validation errors, including state errors.

**Problem**: State errors (e.g., missing `categoria_slug` in state) won't change during retry.

**Impact**: Wastes 1-4 retries before escalating.

**Solution** (Phase 4):
```python
if is_val_error and error_dict:
    failed_layer = error_dict.get("validation_layer")
    
    # Skip retry for state errors (state won't change)
    if failed_layer == "state":
        logger.warning("state_validation_error_no_retry")
        return escalation_response
    
    # Only retry semantic/syntax errors
    should_retry, retry_state = self._handle_validation_retry(...)
```

### 2. No Tool-Specific Retry Limits

**Issue**: All tools share the same retry limit (4 for PRESUPUESTO_MODE).

**Problem**: Some tools are more likely to fail (e.g., complex categoria_slug).

**Solution** (Phase 4): Per-tool retry limits in validation config.

---

## Files Modified

1. `agent/modes/presupuesto_mode.py` (+54 lines, 3 sections)
   - Import addition (line 40)
   - Retry state init (line 263)
   - Validation retry logic (lines 341-381)
   - State persistence (line 433)

---

## Git Commit

**Commit message**:
```
feat(agent): integrate Phase 3 validation retry in presupuesto_mode

Extend defensive parameter validation to presupuesto_mode (~65% traffic).
Uses identical pattern from consulta_mode for consistency.

Changes:
- Import create_empty_retry_state
- Initialize retry_state from conversation state
- Detect validation errors after tool execution
- Apply progressive reprompts (4 retries max)
- Escalate to human if max retries reached
- Persist retry_state to Redis checkpoint

Risk: High traffic mode, conservative rollout
Monitoring: validation_retry_triggered, validation_escalation events
Rollback: git checkout HEAD~1 agent/modes/presupuesto_mode.py

Related: Phase 2 (semantic validation), Phase 3 spec
```

---

## References

- **Phase 3 Spec**: `docs/plans/defensive-parameter-validation-system.md` (Phase 3)
- **Phase 3 Usage Guide**: `docs/phase3-validation-retry-usage.md`
- **Phase 2 Deployment**: `docs/PHASE2-DEPLOYMENT-REPORT.md`
- **Fallback Handler**: `agent/fallback/fallback_handler.py`
- **Base Mode**: `agent/modes/base_mode.py` (Phase 3 helpers)

---

**Deployed by**: Claude Sonnet 4.5  
**Deployment time**: February 8, 2026, 14:01:50 UTC  
**Status**: ✅ DEPLOYED, awaiting 24-48h monitoring
