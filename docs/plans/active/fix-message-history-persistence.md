# Plan: Fix Message History Persistence (Bug A)

**Status**: PROPOSED  
**Created**: 2026-02-10  
**Priority**: CRITICAL  
**Estimated effort**: ~2-3 hours implementation + testing  
**Services affected**: Agent only (no API/DB/Admin changes)

---

## Problem Statement

The LLM in ALL mode nodes operates **without conversation history**. Each turn, it only sees:
1. System prompt (~9,000-12,000 tokens)
2. Current user message
3. mode_context flags (boolean surrogates: `precio_comunicado`, `imagenes_enviadas`, etc.)

### Root Cause

The `messages` field in `ConversationState` uses an `Annotated[list, add]` reducer (append-only), but **no node ever returns `messages` in its result dict**. The list remains permanently empty.

```
state_input = { messages: [] }
  → add(checkpoint_messages=[], new=[]) = []  ← always empty
  → mode_node reads messages → []
  → mode_node returns { ai_response, mode_context }  ← no "messages" key
  → add([], nothing) = []  ← still empty
```

### User Impact

- Ambiguous confirmations ("Dale", "Sí", "Ok") fail because the LLM doesn't know what was asked
- The follow_up_message asking "¿Te gustaría que abramos el expediente?" is never in LLM context
- Users get stuck in loops when the LLM can't interpret short responses
- ~90% of conversations eventually hit this problem

### What Already Works

1. `format_messages_for_llm()` in `helpers.py` — formats messages for LLM (security tags, tool compression)
2. `add_message()` in `helpers.py` — creates message dicts with FIFO windowing (max 20) — **EXISTS BUT NEVER CALLED**
3. All mode nodes already read `state.get("messages", [])` and pass to `format_messages_for_llm()`
4. Token budget: ~49,000 tokens available after system prompt (DeepSeek 64K context)

---

## Solution Architecture

### Approach: Centralized message persistence in `base_mode.process()`

**Why `base_mode.process()` and not each mode individually?**
- ALL modes go through `process()` (wrapper around `_process_message()`)
- Single point of change, zero risk of inconsistency
- Error paths also go through `process()` via `_handle_error()`

### Change #1: `base_mode.py` — Append messages to state

In `process()`, after `_process_message()` returns, add user + assistant messages:

```python
async def process(self, state: ConversationState) -> dict[str, Any]:
    message = cast(str, state.get("user_message", ""))
    now = datetime.now(UTC).isoformat()
    
    try:
        result = await self._process_message(message, state)
        # ... existing retry/timestamp logic ...
        
        # NEW: Persist conversation history
        ai_response = result.get("ai_response", "")
        new_messages = []
        if message:
            new_messages.append({
                "role": "user",
                "content": message,
                "timestamp": now,
            })
        if ai_response:
            new_messages.append({
                "role": "assistant",
                "content": ai_response,
                "timestamp": now,
            })
        result["messages"] = new_messages
        
        return result
        
    except Exception as exc:
        error_result = self._handle_error(exc, retry_state, state)
        # Also persist messages on error path
        ai_response = error_result.get("ai_response", "")
        new_messages = []
        if message:
            new_messages.append({
                "role": "user",
                "content": message,
                "timestamp": now,
            })
        if ai_response:
            new_messages.append({
                "role": "assistant",
                "content": ai_response,
                "timestamp": now,
            })
        error_result["messages"] = new_messages
        return error_result
```

The `add` reducer on `messages` will append these to the existing list in the checkpoint.

### Change #2: `main.py` — Persist follow_up_message to state

After sending `follow_up_message` from `pending_images`, we need to inject it into the checkpoint. Two options:

**Option A (Simple — Recommended)**: Include the follow_up in the mode node's return

Instead of main.py sending the follow_up separately, have presupuesto_mode include it as part of `ai_response` (concatenated). The mode already knows the follow_up from `pending_images`.

**Rejected**: This changes the UX — the follow_up is sent AFTER a 5-second delay post-images. Concatenating would send it immediately.

**Option B (Direct checkpoint update)**: After sending the follow_up, update the checkpoint with a follow_up message entry.

```python
# In main.py, after sending follow_up
if follow_up:
    # ... send to chatwoot ...
    # ... persist to DB ...
    
    # NEW: Update checkpoint with follow_up message
    follow_up_msg = {
        "role": "assistant",
        "content": follow_up_clean,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    # Use graph.aupdate_state() to inject into checkpoint
    await graph.aupdate_state(
        config={"configurable": {"thread_id": conversation_id}},
        values={"messages": [follow_up_msg]},
    )
```

**Concern with Option B**: `graph.aupdate_state()` may trigger reducers and have side effects. Needs testing.

**Option C (Pragmatic — Recommended)**: Inject follow_up text into mode_context

Store the follow_up text in `mode_context["last_follow_up"]` from the mode node. The system prompt already includes mode_context. The LLM will see "last follow-up sent: ¿Te gustaría...?" on the next turn.

```python
# In presupuesto_mode, when setting up pending_images:
if follow_up_message:
    updated_context["last_follow_up_sent"] = follow_up_message
```

This is simpler, requires no graph API calls, and the information is visible to the LLM via the mode_context section of the system prompt.

**RECOMMENDED**: Combine Change #1 (message history in base_mode) + Option C (follow_up in mode_context).

### Change #3: Message windowing

The `add` reducer appends indefinitely. We need windowing to prevent unbounded growth.

**Strategy**: Apply windowing at READ TIME, not write time. Keep the full history in the checkpoint, but limit what we send to the LLM.

Already built into `format_messages_for_llm()`:
- `recent_threshold=6` — compresses tool results older than 6 messages
- But no hard limit on total messages

**Add windowing in mode nodes** (where messages are read):

```python
# In each mode's _process_message():
messages = state.get("messages", [])
# Only use last N messages for LLM context
MAX_HISTORY_MESSAGES = 20
recent_messages = messages[-MAX_HISTORY_MESSAGES:] if len(messages) > MAX_HISTORY_MESSAGES else messages
llm_messages.extend(format_messages_for_llm(recent_messages))
```

**Alternative**: Modify `format_messages_for_llm()` to accept a `max_messages` parameter:

```python
def format_messages_for_llm(messages, max_messages=20, compress_old_tools=True, recent_threshold=6):
    messages = messages[-max_messages:] if len(messages) > max_messages else messages
    # ... rest unchanged
```

**RECOMMENDED**: Modify `format_messages_for_llm()` — single point of change, all modes benefit.

### Change #4: evaluacion_gateway.py — No change needed

This mode uses pattern matching (regex), not LLM. It does NOT read `messages` from state. No change needed. `base_mode.process()` will still persist the user/assistant messages (it wraps all modes including this one).

---

## Implementation Plan

### Phase 1: Core message persistence (30 min)

| # | File | Change | Risk |
|---|------|--------|------|
| 1 | `agent/modes/base_mode.py` | Add message persistence in `process()` | LOW — additive only |
| 2 | `agent/state/helpers.py` | Add `max_messages` param to `format_messages_for_llm()` | LOW — backward compatible |

### Phase 2: Follow-up message persistence (15 min)

| # | File | Change | Risk |
|---|------|--------|------|
| 3 | `agent/modes/presupuesto_mode.py` | Store follow_up text in `mode_context["last_follow_up_sent"]` | LOW |
| 4 | `agent/modes/expediente_mode.py` | Same if applicable | LOW |

### Phase 3: Verification (30 min)

| # | Action |
|---|--------|
| 5 | Write unit tests for message persistence in `test_mode_transitions.py` |
| 6 | Write test for `format_messages_for_llm()` with windowing |
| 7 | Manual test with real WhatsApp conversation |

### Phase 4: Deploy (10 min)

```bash
docker compose build agent && docker compose up -d agent
```

---

## Token Impact Analysis

| Scenario | System Prompt | Message History | Total Input | % of 64K |
|----------|--------------|----------------|-------------|----------|
| Current (no history) | ~12,000 | 0 | ~12,000 | 19% |
| 5 turns (10 messages) | ~12,000 | ~2,000 | ~14,000 | 22% |
| 10 turns (20 messages) | ~12,000 | ~5,000 | ~17,000 | 27% |
| 20 turns (40 messages) | ~12,000 | ~10,000 | ~22,000 | 34% |

**Max window of 20 messages**: ~34% of context used. **Plenty of headroom.**

**Cost impact**: ~15-40% more tokens per turn (input tokens). At DeepSeek rates ($0.27/1M input), this is negligible — roughly $0.003-0.005 per conversation.

---

## Migration Strategy

### Existing conversations

Conversations already in progress will have `messages: []` in their checkpoints. After deployment:
- The LLM will start seeing history from the NEXT turn onwards
- Previous turns are lost (acceptable — they were already lost)
- No migration needed — the `add` reducer handles empty lists gracefully

### No database changes

This fix is entirely in the agent Python code. No DB migrations, no API changes, no admin panel changes.

---

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Checkpoint size grows unbounded | LOW | Messages accumulate in Redis | Window at read time (20 messages). Long conversations rarely exceed 30 turns. |
| LLM behaves differently with history | MEDIUM | Different response patterns | Test with real conversations before full deploy |
| Follow-up message not in history | LOW | "Dale" still fails if follow_up not visible | Option C stores in mode_context, visible in system prompt |
| Token cost increase | LOW | Negligible at DeepSeek rates | Monitor via token_tracking.py |

---

## Success Criteria

1. ✅ LLM sees previous user messages and assistant responses
2. ✅ "Dale" after "¿Te gustaría que abramos el expediente?" correctly triggers `confirmar_presupuesto()`
3. ✅ Message history persists across turns via Redis checkpoint
4. ✅ Windowing prevents unbounded growth (max 20 messages to LLM)
5. ✅ No regression in existing mode behavior
6. ✅ Token cost increase < 50% per turn

---

## Files to Modify

| File | Lines Changed | Type |
|------|--------------|------|
| `agent/modes/base_mode.py` | ~20 lines | MODIFY |
| `agent/state/helpers.py` | ~5 lines | MODIFY |
| `agent/modes/presupuesto_mode.py` | ~5 lines | MODIFY |
| `agent/modes/expediente_mode.py` | ~5 lines (if applicable) | MODIFY |
| `tests/unit/test_mode_transitions.py` | ~30 lines | ADD TESTS |

**Total: ~65 lines changed, 0 new files, 0 DB changes**

---

## Decision Log

- **Rejected**: Pattern-matching hotfix for "Dale" — fragile, false positives, doesn't fix root cause
- **Rejected**: Storing tool call history — too many tokens, structured data better in mode_context
- **Rejected**: `graph.aupdate_state()` for follow_up — complex, side effects unknown
- **Chosen**: Centralized message persistence in `base_mode.process()` — minimal changes, maximum impact
- **Chosen**: Window at read time (not write) — preserves full history for debugging
- **Chosen**: Follow-up in mode_context — simple, reliable, no graph API complexity
