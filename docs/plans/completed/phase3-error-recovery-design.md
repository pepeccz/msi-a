# Phase 3: Error Recovery & Retry - Design Document

**Date**: February 8, 2026  
**Status**: DESIGN  
**Prerequisites**: Phase 1 (Syntax/State validation) + Phase 2 (Semantic validation)

---

## Objective

Integrate automatic retry logic for validation errors with progressive reprompting, building on the existing `FallbackHandler` infrastructure.

**Key principle**: When validation fails, give the LLM a chance to fix its parameters automatically before escalating to human.

---

## Current State Analysis

### What We Have (Phase 1 + 2)

✅ **3-layer validation system** in `agent/utils/tool_validation.py`:
- Layer 1: Syntax (required params, types)
- Layer 2: State (dependencies from state)
- Layer 3: Semantic (DB validation)

✅ **Validation returns structured errors**:
```python
is_valid, errors = await validator.validate(tool, params, state)
# errors = ["La categoría 'INVALID' no existe en el sistema"]
```

✅ **Existing FallbackHandler** in `agent/fallback/fallback_handler.py`:
- Per-mode retry policies
- Progressive reprompting
- Retry counting (retry_state in conversation state)
- Fallback actions (escalate, reset, etc.)

✅ **RetryErrorType enum** already includes:
```python
class RetryErrorType(str, Enum):
    INTENT_NOT_UNDERSTOOD = "intent_not_understood"
    TOOL_CALL_FAILED = "tool_call_failed"
    VALIDATION_ERROR = "validation_error"  # ← Already defined!
    LLM_PARSE_ERROR = "llm_parse_error"
    USER_CONFUSION = "user_confusion"
```

### What We Need (Phase 3)

❌ **Validation error detection** in BaseModeNode tool execution loop
❌ **Automatic retry** when validation fails
❌ **Progressive reprompting** with validation context
❌ **Validation-specific error messages** (not generic)
❌ **Integration tests** for retry scenarios

---

## Design Decisions

### 1. Where to Intercept Validation Errors

**Option A**: In `base_mode.py` after `_execute_and_log_tool()`  
**Option B**: Inside `_execute_and_log_tool()` itself  
**Option C**: In a new middleware layer  

**Decision**: **Option A** - In `base_mode.py` after tool execution

**Rationale**:
- Keeps validation logic separate from execution
- BaseModeNode already has the LLM loop and message context
- FallbackHandler integration is already in BaseModeNode
- Easier to test and maintain

### 2. Retry Strategy

**When to retry**:
- Syntax validation errors → Retry (LLM can fix param names/types)
- State validation errors → DON'T retry (state won't change mid-conversation)
- Semantic validation errors → Retry IF error suggests typo (e.g., "categoria_slug 'motos-parts' doesn't exist" → maybe meant "motos-part")

**How many retries**:
- Use existing retry_state in conversation state
- Use per-mode policies from FallbackHandler
- PRESUPUESTO_MODE: max_retries = 4
- CONSULTA_MODE: max_retries = 3
- EXPEDIENTE_MODE: max_retries = 3

**Progressive reprompting**:
```
Retry 1: "Los parámetros no son válidos. Por favor, verifica e intenta de nuevo."
Retry 2: "Falta el parámetro 'categoria_slug'. Debes incluirlo en la llamada a calcular_tarifa_con_elementos."
Retry 3+: "No pude procesar la solicitud después de varios intentos. Te conecto con un humano."
```

### 3. Error Message Format

**Current tool error response** (from validation):
```python
{
    "success": False,
    "error": "Invalid tool parameters",
    "error_type": "parameter_validation",
    "tool_name": "calcular_tarifa_con_elementos",
    "validation_errors": [
        "La categoría 'INVALID_CATEGORY' no existe en el sistema"
    ],
}
```

**What LLM needs for retry**:
- Clear error message
- Which parameter failed
- What the valid options are (if applicable)

**Enhanced error response** (Phase 3):
```python
{
    "success": False,
    "error": "Invalid tool parameters",
    "error_type": "parameter_validation",
    "validation_layer": "semantic",  # NEW
    "tool_name": "calcular_tarifa_con_elementos",
    "validation_errors": [
        "La categoría 'INVALID_CATEGORY' no existe en el sistema"
    ],
    "failed_params": ["categoria_slug"],  # NEW
    "can_retry": True,  # NEW
    "retry_suggestion": "Verifica que categoria_slug sea una de: motos-part, motos-prof, aseicars-part, ...",  # NEW
}
```

### 4. Integration with Existing Validation

**No changes to validation layers** - they already return what we need:
```python
# agent/utils/tool_validation.py
async def validate(self, tool, params, state) -> tuple[bool, list[str]]:
    # Returns (is_valid, errors)
    pass
```

**We ADD retry logic** in BaseModeNode:
1. Call validation (existing code)
2. If validation fails → Check if should retry
3. If should retry → Add reprompt message, continue LLM loop
4. If max retries → Escalate to human

---

## Implementation Plan

### Step 1: Extend RetryErrorType (ALREADY DONE)

`agent/fallback/fallback_handler.py` already has:
```python
class RetryErrorType(str, Enum):
    VALIDATION_ERROR = "validation_error"  # ✅ Already exists
```

**No changes needed.**

### Step 2: Add Validation Context to FallbackHandler

**File**: `agent/fallback/fallback_handler.py`

**Add method** to track validation failures:
```python
def record_validation_error(
    self,
    retry_state: RetryStateData,
    tool_name: str,
    validation_errors: list[str],
    validation_layer: str,  # "syntax", "state", "semantic"
) -> RetryStateData:
    """
    Record a validation error with context.
    
    This is a specialized version of record_error() that includes
    validation-specific metadata for better reprompting.
    """
    now = datetime.now(UTC).isoformat()
    
    error_message = f"Validation failed in {validation_layer} layer for {tool_name}: {'; '.join(validation_errors)}"
    
    return RetryStateData(
        retry_count=retry_state.get("retry_count", 0) + 1,
        consecutive_errors=retry_state.get("consecutive_errors", 0) + 1,
        last_error_type=RetryErrorType.VALIDATION_ERROR.value,
        last_error_message=error_message,
        first_error_at=retry_state.get("first_error_at") or now,
        last_retry_at=now,
        # Store validation context for reprompting
        last_validation_context={  # NEW field in RetryStateData
            "tool_name": tool_name,
            "errors": validation_errors,
            "layer": validation_layer,
        },
    )
```

**Add method** to generate validation-specific reprompts:
```python
def get_validation_reprompt(
    self,
    retry_state: RetryStateData,
    policy: RetryPolicy,
) -> str:
    """
    Generate reprompt message for validation errors.
    
    Uses validation context from last error to provide specific guidance.
    """
    count = retry_state.get("retry_count", 0)
    context = retry_state.get("last_validation_context", {})
    
    # First retry: generic
    if count == 1:
        return (
            "Los parámetros que enviaste no son válidos. "
            "Por favor, revisa e intenta de nuevo."
        )
    
    # Second retry: specific
    if count == 2 and context:
        tool = context.get("tool_name", "la herramienta")
        errors = context.get("errors", [])
        
        if errors:
            return (
                f"Hay un problema con los parámetros de {tool}:\n"
                + "\n".join(f"- {err}" for err in errors)
                + "\n\nPor favor, corrige estos errores."
            )
    
    # Third+ retry: escalate
    if count >= policy.max_retries:
        return (
            "No pude procesar la solicitud después de varios intentos. "
            "Te voy a conectar con un humano que te puede ayudar mejor."
        )
    
    # Fallback
    return "Por favor, intenta de nuevo con parámetros correctos."
```

### Step 3: Detect Which Validation Layer Failed

**Problem**: Currently, `validator.validate()` returns `(bool, list[str])` but doesn't say WHICH layer failed.

**Solution**: Modify `ToolValidationService.validate()` to return layer info.

**File**: `agent/utils/tool_validation.py`

**Change return type**:
```python
# BEFORE (Phase 2)
async def validate(
    self, tool, params, state
) -> tuple[bool, list[str]]:
    pass

# AFTER (Phase 3)
async def validate(
    self, tool, params, state
) -> tuple[bool, list[str], str]:  # Added layer name
    """
    Returns:
        (is_valid, errors, failed_layer)
        
        failed_layer: "syntax" | "state" | "semantic" | "none"
    """
    pass
```

**Implementation**:
```python
async def validate(
    self,
    tool: BaseTool,
    params: dict[str, Any],
    state: dict[str, Any],
) -> tuple[bool, list[str], str]:
    """Run all validation layers. Returns (is_valid, errors, failed_layer)."""
    all_errors = []
    
    # Layer 1: Syntax
    is_valid, errors = await self.syntax_validator.validate(tool, params, state)
    if not is_valid:
        all_errors.extend(errors)
        logger.warning("tool_validation_failed", tool_name=tool.name, layer="syntax", errors=all_errors)
        return (False, all_errors, "syntax")  # ← Return layer
    
    # Layer 2: State
    is_valid, errors = await self.state_validator.validate(tool, params, state)
    if not is_valid:
        all_errors.extend(errors)
        logger.warning("tool_validation_failed", tool_name=tool.name, layer="state", errors=all_errors)
        return (False, all_errors, "state")  # ← Return layer
    
    # Layer 3: Semantic
    is_valid, errors = await self.semantic_validator.validate(tool, params, state)
    if not is_valid:
        all_errors.extend(errors)
        logger.warning("tool_validation_failed", tool_name=tool.name, layer="semantic", errors=all_errors)
        return (False, all_errors, "semantic")  # ← Return layer
    
    # All passed
    logger.info("tool_validation_passed", tool_name=tool.name)
    return (True, [], "none")  # ← No layer failed
```

**Impact**: This is a **breaking change** to the validation API, but we only use it in one place (BaseModeNode), so easy to update.

### Step 4: Integrate Retry Logic in BaseModeNode

**File**: `agent/modes/base_mode.py`

**Current tool execution** (simplified):
```python
async def _process_message(self, message, state):
    # LLM loop
    for iteration in range(MAX_TOOL_ITERATIONS):
        response = await llm.ainvoke(messages)
        
        if not response.tool_calls:
            return {"ai_response": response.content}
        
        # Execute tools
        for tool_call in response.tool_calls:
            result = await self._execute_and_log_tool(
                tool_call["name"],
                tool_call["args"],
                state["conversation_id"],
            )
            
            # Append to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(result),
            })
    
    return {"ai_response": "..."}
```

**NEW tool execution** (with retry):
```python
async def _process_message(self, message, state):
    # Get retry state
    retry_state = state.get("retry_state", create_empty_retry_state())
    fallback_handler = FallbackHandler()
    policy = fallback_handler.get_policy(self.mode_name)
    
    # LLM loop
    for iteration in range(MAX_TOOL_ITERATIONS):
        response = await llm.ainvoke(messages)
        
        if not response.tool_calls:
            return {"ai_response": response.content}
        
        # Execute tools
        validation_error_occurred = False
        
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_kwargs = tool_call["args"]
            
            # Execute tool (includes validation)
            result = await self._execute_and_log_tool(
                tool_name,
                tool_kwargs,
                state["conversation_id"],
            )
            
            # ═══════════════════════════════════════════════════════════
            # NEW: Check for validation errors
            # ═══════════════════════════════════════════════════════════
            if not result.get("success") and result.get("error_type") == "parameter_validation":
                validation_layer = result.get("validation_layer", "unknown")
                validation_errors = result.get("validation_errors", [])
                
                # Should we retry?
                if not fallback_handler.should_fallback(retry_state, policy):
                    # Update retry state
                    retry_state = fallback_handler.record_validation_error(
                        retry_state,
                        tool_name,
                        validation_errors,
                        validation_layer,
                    )
                    
                    # Get reprompt message
                    reprompt = fallback_handler.get_validation_reprompt(
                        retry_state,
                        policy,
                    )
                    
                    logger.info(
                        "validation_error_retry",
                        tool=tool_name,
                        layer=validation_layer,
                        retry_count=retry_state["retry_count"],
                        reprompt_preview=reprompt[:50],
                    )
                    
                    # Add reprompt to messages (as assistant message)
                    messages.append({
                        "role": "assistant",
                        "content": reprompt,
                    })
                    
                    # Signal retry
                    validation_error_occurred = True
                    break  # Exit tool loop, retry LLM
                
                else:
                    # Max retries reached - escalate
                    logger.warning(
                        "validation_max_retries",
                        tool=tool_name,
                        retry_count=retry_state["retry_count"],
                        max=policy.max_retries,
                    )
                    
                    return {
                        "ai_response": fallback_handler.get_validation_reprompt(retry_state, policy),
                        "escalation_triggered": True,
                        "escalation_reason": "max_validation_retries",
                        "retry_state": retry_state,
                    }
            
            # ═══════════════════════════════════════════════════════════
            # END validation error handling
            # ═══════════════════════════════════════════════════════════
            
            # Append result to messages (normal flow)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(result),
            })
        
        # If validation error occurred, continue to next LLM iteration (retry)
        if validation_error_occurred:
            continue
        
        # Otherwise, check if we should end the loop
        # ... (existing logic)
    
    return {"ai_response": "..."}
```

### Step 5: Update RetryStateData Schema

**File**: `agent/state/conversation_state.py`

**Current schema**:
```python
class RetryStateData(TypedDict, total=False):
    retry_count: int
    consecutive_errors: int
    last_error_type: str | None
    last_error_message: str | None
    first_error_at: str | None
    last_retry_at: str | None
```

**NEW schema** (add validation context):
```python
class RetryStateData(TypedDict, total=False):
    retry_count: int
    consecutive_errors: int
    last_error_type: str | None
    last_error_message: str | None
    first_error_at: str | None
    last_retry_at: str | None
    last_validation_context: dict[str, Any] | None  # NEW
```

---

## Testing Strategy

### Unit Tests

**File**: `tests/agent/test_phase3_error_recovery.py`

```python
@pytest.mark.asyncio
async def test_validation_error_triggers_retry():
    """Validation error should trigger retry with reprompt."""
    # Setup
    # Mock LLM to return tool call with invalid params
    # Execute
    # Assert: retry_count incremented, reprompt added to messages

@pytest.mark.asyncio
async def test_max_retries_escalates():
    """Max validation retries should escalate to human."""
    # Setup: retry_state with retry_count = max_retries - 1
    # Execute: trigger one more validation error
    # Assert: escalation_triggered = True

@pytest.mark.asyncio
async def test_syntax_error_retries():
    """Syntax validation errors should retry."""
    # Test that syntax errors (missing param) trigger retry

@pytest.mark.asyncio
async def test_state_error_no_retry():
    """State validation errors should NOT retry (state won't change)."""
    # Test that state errors escalate immediately

@pytest.mark.asyncio
async def test_semantic_error_retries():
    """Semantic validation errors should retry."""
    # Test that DB validation errors (invalid category) trigger retry

@pytest.mark.asyncio
async def test_progressive_reprompting():
    """Reprompt messages should get more specific with each retry."""
    # Test retry 1, 2, 3+ messages are different and progressive
```

### Integration Tests

**File**: `tests/integration/test_validation_retry_flow.py`

```python
@pytest.mark.asyncio
async def test_full_validation_retry_flow():
    """End-to-end test of validation error → retry → success."""
    # Scenario:
    # 1. LLM calls tool with invalid categoria_slug
    # 2. Validation fails (semantic layer)
    # 3. Retry with reprompt
    # 4. LLM fixes param
    # 5. Validation passes
    # 6. Tool executes successfully
```

---

## Success Criteria

- [ ] Validation errors trigger automatic retry (not immediate escalation)
- [ ] Retry counter increments on each validation failure
- [ ] Reprompt messages are progressive (1st generic, 2nd specific, 3rd escalate)
- [ ] Max retries escalates to human
- [ ] Syntax/Semantic errors retry, State errors don't retry
- [ ] Validation layer is logged for monitoring
- [ ] Tests cover all retry scenarios
- [ ] Zero regression in existing functionality

---

## Rollback Plan

If Phase 3 causes issues:

```bash
# Rollback to Phase 2
git reset --hard 325b5da  # Last Phase 2 commit
docker-compose restart agent
```

**Data loss**: None (retry_state is ephemeral)  
**Rollback time**: <2 minutes

---

## Estimated Effort

| Task | Estimated Time |
|------|----------------|
| Design document (this) | 1h ✅ |
| Extend FallbackHandler | 1.5h |
| Modify validation API | 1h |
| Integrate in BaseModeNode | 2h |
| Update RetryStateData schema | 0.5h |
| Unit tests | 2h |
| Integration tests | 1.5h |
| Documentation | 0.5h |

**Total**: ~10 hours (slightly higher than plan estimate of 6-8h due to API changes)

---

## Next Steps

1. ✅ Review this design document
2. ⏳ Implement Step 2 (FallbackHandler extensions)
3. ⏳ Implement Step 3 (Validation API change)
4. ⏳ Implement Step 4 (BaseModeNode integration)
5. ⏳ Implement Step 5 (RetryStateData schema)
6. ⏳ Write tests
7. ⏳ Deploy and monitor

---

**Created**: February 8, 2026 02:10 UTC  
**Author**: Claude Sonnet 4.5  
**Status**: Ready for implementation
