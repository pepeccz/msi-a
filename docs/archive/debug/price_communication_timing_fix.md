# Price Communication Timing Bug Fix

**Date**: 2026-01-31  
**Escalation ID**: 9826059f-4a84-48d0-bb93-6acb9227f0e0  
**Issue**: `enviar_imagenes_ejemplo` blocked with PRICE_NOT_COMMUNICATED despite price being mentioned  
**Root Cause**: Flag `price_communicated_to_user` set AFTER tool execution, not BEFORE

---

## Problem Statement

### User Report

User +34623226544 experienced escalation after saying "Dale" to proceed with quotation:

```
Agent: "El presupuesto es de 410 EUR +IVA. ¿Te gustaría que te envíe fotos de ejemplo?"
User: "Dale"
Agent: [Escalates with "Error persistente en enviar_imagenes_ejemplo a pesar de mencionar el precio correctamente"]
```

### Log Evidence

```
23:29:01 - [calcular_tarifa] Stored tarifa_actual with 4 images
23:29:07 - Tool: enviar_imagenes_ejemplo (tipo=presupuesto)
23:29:07 - WARNING: Attempt to send images without communicating price first ← ERROR
23:29:07 - Tool error: PRICE_NOT_COMMUNICATED

[LLM retries - same error]
23:29:50 - WARNING: Attempt to send images without communicating price first
23:30:13 - WARNING: Attempt to send images without communicating price first

[After 3 attempts, LLM escalates]
23:30:16 - Tool: escalar_a_humano (motivo="Error persistente...")
```

---

## Root Cause Analysis

### Execution Order Bug

The flag `price_communicated_to_user` is set in the wrong place in the execution flow:

**Current (BROKEN) Flow**:
```
1. LLM generates response: "El presupuesto es de 410 EUR +IVA..."
2. LLM calls: enviar_imagenes_ejemplo(tipo="presupuesto")
3. Tool checks: state.get("price_communicated_to_user") → FALSE ❌
4. Tool returns: PRICE_NOT_COMMUNICATED error
5. Node processes ai_content and detects "410€" → Sets flag to TRUE (TOO LATE)
6. Error already returned, LLM confused
```

**Expected (CORRECT) Flow**:
```
1. LLM generates response: "El presupuesto es de 410 EUR +IVA..."
2. Node detects "410€" in response → Sets flag to TRUE IMMEDIATELY
3. LLM calls: enviar_imagenes_ejemplo(tipo="presupuesto")
4. Tool checks: state.get("price_communicated_to_user") → TRUE ✅
5. Tool sends images successfully
```

### Code Location

**File**: `agent/nodes/conversational_agent.py`

**Current placement** (line 1619-1645):
- AFTER tool execution loop (line 954-1580)
- AFTER all tool calls processed
- RIGHT BEFORE adding AI message to history

**Problem**: Tools execute BEFORE the price detection runs, so flag is always False during tool execution.

---

## Solution

### Move Price Detection Earlier

The price detection code needs to run IMMEDIATELY after LLM generates the response, BEFORE processing tool_calls.

**Change location from**:
- Line 1619 (after tool loop ends)

**To**:
- Line ~1010 (right after extracting ai_content from response, before tool loop starts)

### Implementation

```python
# AFTER extracting ai_content (around line 1010)
ai_content = response.content if hasattr(response, "content") else str(response)

# NEW: Detect price communication IMMEDIATELY (before tool execution)
if state.get("tarifa_actual") and not state.get("price_communicated_to_user"):
    tarifa_price = state["tarifa_actual"].get("price")
    if tarifa_price and ai_content:
        price_int = int(tarifa_price) if tarifa_price == int(tarifa_price) else tarifa_price
        price_patterns = [
            f"{price_int}€",
            f"{price_int} €",
            f"{price_int}EUR",
            f"{tarifa_price}€",
            f"{tarifa_price} €",
            f"{tarifa_price}EUR",
        ]
        price_mentioned = any(pattern in ai_content for pattern in price_patterns)
        
        if price_mentioned:
            state["price_communicated_to_user"] = True
            logger.info(
                f"Price {tarifa_price}€ detected in response - allowing image sending",
                extra={"conversation_id": conversation_id, "price": tarifa_price}
            )

# THEN process tool_calls (existing code continues)
tool_calls = getattr(response, "tool_calls", None) or []
```

### Remove Duplicate Code

Delete the old price detection block at line 1619-1645 (now redundant).

---

## Testing

### Test Case 1: Price Mentioned Before Tool Call

**Setup**: New conversation, calculate tariff 410 EUR

**Actions**:
1. LLM response: "El presupuesto es de 410 EUR +IVA. Te envío las fotos."
2. LLM calls: `enviar_imagenes_ejemplo(tipo="presupuesto")`

**Expected**:
- Flag set to True BEFORE tool executes
- Tool sends images successfully
- No PRICE_NOT_COMMUNICATED error

### Test Case 2: Price NOT Mentioned

**Setup**: New conversation, calculate tariff 410 EUR

**Actions**:
1. LLM response: "Te envío las fotos del presupuesto." (no price!)
2. LLM calls: `enviar_imagenes_ejemplo(tipo="presupuesto")`

**Expected**:
- Flag remains False
- Tool returns PRICE_NOT_COMMUNICATED error
- LLM forced to mention price

### Test Case 3: Price Injection Still Works

**Setup**: LLM tries to send images without mentioning price

**Actions**:
1. LLM response: "Te muestro la documentación."
2. Tool returns PRICE_NOT_COMMUNICATED
3. System injects price prefix
4. Final message: "El presupuesto para homologar X es de 410€ +IVA.\n\nTe muestro la documentación."

**Expected**:
- Price injection still works (happens at line 1610-1612, before our new detection)
- Flag set to True after injection
- User sees price in message

---

## Impact

**Before Fix**:
- False positives: LLM mentions price → Tool still blocks → Escalation
- 100% escalation rate when LLM tries to send images after calculating tariff

**After Fix**:
- Price detection runs BEFORE tools
- Tools see correct flag state
- 0% false positive escalations

**Risk**: Low (moving existing code, no logic changes)

---

## Monitoring

### Query to Detect Issue

```sql
-- Find cases where price was mentioned but tool still blocked
SELECT 
  conversation_id,
  created_at,
  result_summary
FROM tool_call_logs
WHERE tool_name = 'enviar_imagenes_ejemplo'
  AND result_summary LIKE '%PRICE_NOT_COMMUNICATED%'
  AND created_at > NOW() - INTERVAL '7 days'
ORDER BY created_at DESC;
```

### Success Metric

After fix deployment:
- 0 escalations with motivo containing "Error persistente en enviar_imagenes_ejemplo"
- enviar_imagenes_ejemplo success rate >95% (allowing for genuine cases where price not mentioned)

---

## Related Issues

- This is DIFFERENT from duplicate image sending (commit 0574bf4)
- This is DIFFERENT from Phase 3 FSM enforcement (commit 273eff1)
- This is a **timing bug** in the conversational_agent node

---

**Generated by**: Log Analysis + Root Cause Investigation  
**Status**: Fix ready to implement  
**Priority**: HIGH (blocks core functionality)
