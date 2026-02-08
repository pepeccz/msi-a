# Phase 3: Validation Retry - Usage Guide for Mode Developers

**Date**: February 8, 2026  
**Status**: IMPLEMENTATION GUIDE

---

## Overview

Phase 3 adds automatic retry logic for validation errors. When a tool call fails validation (syntax, state, or semantic layer), the system now:

1. **Detects the error** automatically
2. **Checks retry limit** based on mode policy
3. **Adds reprompt** with specific validation guidance
4. **Retries the LLM loop** - giving the LLM a chance to fix parameters
5. **Escalates** only after max retries

This is implemented via two helper methods in `BaseModeNode`:
- `_is_validation_error()` - Detects validation errors
- `_handle_validation_retry()` - Handles retry logic

---

## Quick Integration (5 Lines of Code)

To add validation retry to your mode, add these lines **after tool execution**:

```python
# In your _process_message() method, after calling _execute_and_log_tool()

for tool_call in tool_calls:
    tool_name = tool_call["name"]
    tool_args = tool_call["args"]
    tool_call_id = tool_call["id"]
    
    # Execute tool (with validation)
    result = await self._execute_and_log_tool(
        conversation_id=conversation_id,
        tool_name=tool_name,
        tool_args=tool_args,
        tools=tools,
        iteration=iteration + 1,
    )
    
    # ═══════════════════════════════════════════════════════════
    # NEW: Phase 3 validation retry logic
    # ═══════════════════════════════════════════════════════════
    is_val_error, error_dict = self._is_validation_error(result)
    
    if is_val_error:
        should_retry, retry_state = self._handle_validation_retry(
            tool_name=tool_name,
            error_dict=error_dict,
            retry_state=state.get("retry_state", create_empty_retry_state()),
            llm_messages=llm_messages,
        )
        
        if should_retry:
            # Reprompt added to llm_messages, continue LLM loop
            continue  # Go to next iteration
        else:
            # Max retries reached - escalate
            return {
                "ai_response": self._fallback.get_validation_reprompt(retry_state, self._policy),
                "escalation_triggered": True,
                "escalation_reason": "max_validation_retries",
                "retry_state": retry_state,
            }
    # ═══════════════════════════════════════════════════════════
    # End validation retry logic
    # ═══════════════════════════════════════════════════════════
    
    # Normal flow: append tool result to messages
    llm_messages.append({
        "role": "tool",
        "content": result,
        "tool_call_id": tool_call_id,
    })
```

**That's it!** Your mode now has automatic validation retry.

---

## Complete Example: consulta_mode.py

Here's a complete example showing how to integrate validation retry:

```python
async def _process_message(
    self,
    message: str,
    state: ConversationState,
) -> dict[str, Any]:
    """Process message in CONSULTA_MODE with validation retry."""
    conversation_id = state.get("conversation_id", "unknown")
    messages = state.get("messages", [])
    retry_state = state.get("retry_state", create_empty_retry_state())
    
    # Build system prompt
    system_prompt = assemble_system_prompt(mode="CONSULTA_MODE")
    
    # Build LLM messages
    llm_messages = [{"role": "system", "content": system_prompt}]
    llm_messages.extend(format_messages_for_llm(messages))
    llm_messages.append({"role": "user", "content": message})
    
    # Get LLM with tools
    tools = self.get_tools()
    llm = self._get_llm(tools)
    
    # Tool calling loop
    for iteration in range(MAX_TOOL_ITERATIONS):
        response = await llm.ainvoke(llm_messages)
        
        # No tool calls → return AI response
        if not response.tool_calls:
            return {"ai_response": response.content}
        
        # Execute tool calls
        llm_messages.append(self._ai_message_to_dict(response))
        
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call["id"]
            
            # Execute tool
            result = await self._execute_and_log_tool(
                conversation_id=conversation_id,
                tool_name=tool_name,
                tool_args=tool_args,
                tools=tools,
                iteration=iteration + 1,
            )
            
            # ═══════════════════════════════════════════════════════════
            # Phase 3: Validation retry
            # ═══════════════════════════════════════════════════════════
            is_val_error, error_dict = self._is_validation_error(result)
            
            if is_val_error:
                should_retry, retry_state = self._handle_validation_retry(
                    tool_name=tool_name,
                    error_dict=error_dict,
                    retry_state=retry_state,
                    llm_messages=llm_messages,
                )
                
                if should_retry:
                    # Retry with reprompt
                    break  # Exit tool loop, go to next LLM iteration
                else:
                    # Escalate
                    return {
                        "ai_response": self._fallback.get_validation_reprompt(retry_state, self._policy),
                        "escalation_triggered": True,
                        "escalation_reason": "max_validation_retries",
                        "retry_state": retry_state,
                    }
            # ═══════════════════════════════════════════════════════════
            
            # Append result to messages
            llm_messages.append({
                "role": "tool",
                "content": result,
                "tool_call_id": tool_call_id,
            })
    
    # Max iterations reached
    return {"ai_response": "Disculpa, intenta reformular tu pregunta."}
```

---

## What Happens Under the Hood

### 1. Tool Execution with Validation

When you call `_execute_and_log_tool()`, it:
1. Gets the tool instance
2. **Validates parameters** (syntax → state → semantic)
3. If validation fails:
   - Logs the error with layer info
   - Returns JSON error: `{"success": False, "error_type": "parameter_validation", ...}`
4. If validation passes:
   - Executes the tool
   - Returns tool result

### 2. Error Detection

`_is_validation_error(result)` parses the JSON result and checks:
- Is `success` False?
- Is `error_type` == "parameter_validation"?

If yes, returns `(True, error_dict)`.

### 3. Retry Logic

`_handle_validation_retry()` does:

```python
# 1. Record error in retry_state
updated_retry = self._fallback.record_validation_error(
    retry_state,
    tool_name,
    validation_errors,
    validation_layer,
)

# 2. Check retry limit
if retry_count >= max_retries:
    return (False, updated_retry)  # Escalate

# 3. Get reprompt
reprompt = self._fallback.get_validation_reprompt(updated_retry, self._policy)

# 4. Add to llm_messages
llm_messages.append({
    "role": "system",
    "content": f"[VALIDATION ERROR]: {reprompt}",
})

return (True, updated_retry)  # Retry
```

### 4. Progressive Reprompting

The reprompt messages get more specific with each retry:

**Retry 1** (generic):
```
Los parámetros que enviaste no son válidos.
Por favor, revisa e intenta de nuevo.
```

**Retry 2** (specific):
```
Hay un problema con los parámetros de calcular_tarifa_con_elementos:
- La categoría 'INVALID_CATEGORY' no existe en el sistema

Por favor, corrige estos errores.
```

**Retry 3+** (escalate):
```
No pude procesar la solicitud después de varios intentos.
Te voy a conectar con un humano que te puede ayudar mejor.
```

---

## Retry Policies by Mode

Retry limits are defined in `FallbackHandler`:

| Mode             | Max Retries | Action on Limit      |
| ---------------- | ----------- | -------------------- |
| CONSULTA_MODE    | 3           | Offer human help     |
| PRESUPUESTO_MODE | 4           | Escalate to human    |
| EXPEDIENTE_MODE  | 3           | Offer human help     |
| EVALUACION_GATEWAY | 2         | Reset to mode start  |

These are automatically applied when you use `_handle_validation_retry()`.

---

## Validation Layers and Retry Strategy

### Syntax Errors → ALWAYS RETRY

Example:
```
Missing required parameter: categoria_slug
```

**Strategy**: LLM can fix this by adding the missing parameter.

### State Errors → DON'T RETRY (Future Enhancement)

Example:
```
Required state missing: case_id
```

**Current**: Still retries (Phase 3 doesn't distinguish yet)  
**Future**: Could skip retry if state won't change mid-conversation

### Semantic Errors → ALWAYS RETRY

Example:
```
La categoría 'INVALID_CATEGORY' no existe en el sistema
```

**Strategy**: LLM might have made a typo, retry gives it a chance to correct.

---

## Migration Guide for Existing Modes

### Step 1: Add retry_state to method signature

```python
async def _process_message(self, message, state):
    # ADD THIS
    retry_state = state.get("retry_state", create_empty_retry_state())
```

### Step 2: Add validation retry in tool loop

After `result = await self._execute_and_log_tool(...)`, add:

```python
is_val_error, error_dict = self._is_validation_error(result)

if is_val_error:
    should_retry, retry_state = self._handle_validation_retry(
        tool_name, error_dict, retry_state, llm_messages
    )
    if should_retry:
        break  # or continue, depending on loop structure
    else:
        return {
            "ai_response": self._fallback.get_validation_reprompt(retry_state, self._policy),
            "escalation_triggered": True,
            "escalation_reason": "max_validation_retries",
            "retry_state": retry_state,
        }
```

### Step 3: Return retry_state in response

```python
return {
    "ai_response": ai_response,
    "mode_context": updated_context,
    "retry_state": retry_state,  # ADD THIS
}
```

**That's it!** Your mode now has validation retry.

---

## Testing Your Integration

### Manual Test

1. **Trigger a validation error** (call tool with invalid params)
2. **Check logs** for `validation_error_retry` event
3. **Verify reprompt** was added to messages
4. **Verify LLM retries** with corrected params
5. **Verify escalation** after max retries

### Example Test Scenario

```python
# Scenario: LLM calls calcular_tarifa with invalid category
# Expected flow:
# 1. Validation fails (semantic layer)
# 2. Retry 1: Generic reprompt
# 3. LLM tries again with corrected category
# 4. Validation passes
# 5. Tool executes successfully
```

---

## Monitoring

### Key Log Events

```bash
# Validation error detected
grep "validation_error_retry" logs/agent.log

# Max retries reached
grep "validation_max_retries_reached" logs/agent.log

# Which layer failed
grep "validation_layer" logs/agent.log | jq .validation_layer
```

### Metrics to Track

- **Validation retry rate**: % of tool calls that trigger retry
- **Retry success rate**: % of retries that succeed on 2nd attempt
- **Escalation rate**: % of validation errors that escalate

---

## FAQ

### Q: Do I need to modify my tools?

**A**: No! Tools don't change. The validation and retry logic is handled by `_execute_and_log_tool()` and the new helpers.

### Q: What if I don't want retry for a specific mode?

**A**: Just don't add the retry logic. The validation still happens (and errors are returned to the LLM), but without automatic retry.

### Q: Can I customize the reprompt messages?

**A**: Yes, modify the `get_validation_reprompt()` method in `FallbackHandler`, or override it in your mode.

### Q: Will this slow down tool execution?

**A**: No. Validation is already happening (Phase 2). This just adds retry logic when validation fails, which is better than immediate escalation.

### Q: What about nested tool calls?

**A**: Works the same. Each tool call is validated independently.

---

## Next Steps

1. ✅ Review this guide
2. ⏳ Update one mode as proof-of-concept (consulta_mode recommended)
3. ⏳ Test with real traffic
4. ⏳ Roll out to all modes if successful
5. ⏳ Add monitoring dashboard

---

**Created**: February 8, 2026  
**Author**: Claude Sonnet 4.5  
**Status**: Ready for implementation
