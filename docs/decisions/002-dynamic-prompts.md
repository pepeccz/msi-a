# ADR-002: Dynamic Prompt System

## Status

Accepted

## Date

2026-01-22

## Context

The MSI-a agent uses a system prompt to guide LLM behavior. The original implementation used a single static prompt (`prompts/system.md`) with ~7,000 tokens that was sent with every LLM call.

**Problems identified:**
1. **Token waste**: 7,000 tokens per call regardless of context
2. **Irrelevant content**: Quotation instructions sent during data collection phases
3. **Hard to maintain**: Single 500+ line file
4. **No context awareness**: Same prompt for all FSM phases

With DeepSeek as the LLM, token costs are lower but still significant at scale.

## Decision

Implement a modular, phase-aware prompt system:

```
prompts/
├── loader.py              # Assembles prompts dynamically
├── state_summary.py       # Generates real-time context
├── core/                  # ~2,200 tokens - ALWAYS included
│   ├── 01_security.md     # Security rules
│   ├── 02_identity.md     # MSI-a identity
│   └── ...                # 8 modules total
└── phases/                # One included per call
    ├── idle_quotation.md  # ~1,000 tokens
    ├── collect_images.md  # ~500 tokens
    └── ...                # 6 phases total
```

### Assembly Flow

```python
prompt = assemble_system_prompt(
    fsm_state=fsm_state,           # Determines which phase
    state_summary=state_summary,    # Dynamic context
    client_context=client_context,  # Client type, categories
)
# Result: CORE + PHASE + SUMMARY + CLIENT_CONTEXT + SECURITY_REMINDER
```

### Token Comparison

| Configuration | Tokens | vs Legacy |
|--------------|--------|-----------|
| Legacy (static) | ~5,400 | baseline |
| IDLE phase | ~3,200 | -40% |
| COLLECT_IMAGES | ~2,700 | -50% |
| COLLECT_PERSONAL | ~2,700 | -50% |
| COLLECT_VEHICLE | ~2,500 | -54% |

## Consequences

### Positive

- **40-60% token savings** per LLM call
- **Phase-focused content**: Only relevant instructions included
- **Easier maintenance**: Small, focused files
- **Dynamic context**: State summary provides real-time info
- **Cached loading**: Modules cached in memory after first load

### Negative

- **More complexity**: Multiple files instead of one
- **Potential inconsistency**: Rules might conflict between modules
- **Testing overhead**: Need to test different phase combinations
- **Cache invalidation**: Must call `clear_cache()` after editing (dev only)

### Neutral

- Legacy `system.md` kept as backup
- Security delimiters maintained from original system

## Alternatives Considered

### Alternative A: Prompt Compression

Use LLM-based prompt compression to reduce tokens.

**Rejected because:**
- Adds latency (compression call)
- Unpredictable results
- May lose important nuances

### Alternative B: Few-shot Examples Only

Remove detailed instructions, rely on examples.

**Rejected because:**
- Less predictable behavior
- Harder to enforce specific rules
- Security instructions still needed

### Alternative C: Fine-tuned Model

Fine-tune a model with MSI-a behavior.

**Rejected because:**
- High cost and maintenance
- Less flexibility to change behavior
- OpenRouter/DeepSeek doesn't support custom fine-tuning easily

## Implementation Details

### Core Modules (Always Loaded)

| Module | Tokens | Purpose |
|--------|--------|---------|
| 01_security.md | ~280 | Anti-jailbreak, attack detection |
| 02_identity.md | ~160 | MSI-a persona |
| 03_format_style.md | ~180 | Tone, format rules |
| 04_anti_patterns.md | ~430 | Loop prevention, variant rules |
| 05_tools_efficiency.md | ~280 | Tool usage rules |
| 06_escalation.md | ~80 | When to escalate |
| 07_pricing_rules.md | ~440 | Price communication |
| 08_documentation.md | ~315 | Doc rules |

### Phase Modules (One per Call)

| Phase | Tokens | FSM States |
|-------|--------|------------|
| idle_quotation.md | ~1,030 | IDLE, CONFIRM_START |
| collect_images.md | ~490 | COLLECT_IMAGES |
| collect_personal.md | ~540 | COLLECT_PERSONAL |
| collect_vehicle.md | ~450 | COLLECT_VEHICLE |
| collect_workshop.md | ~550 | COLLECT_WORKSHOP |
| review_summary.md | ~615 | REVIEW_SUMMARY, COMPLETED |

## References

- Implementation: `agent/prompts/loader.py`, `agent/prompts/state_summary.py`
- Integration: `agent/nodes/conversational_agent.py`
- Core modules: `agent/prompts/core/*.md`
- Phase modules: `agent/prompts/phases/*.md`
