# Rollback Playbook — Agent Harmony Hardening

Quick-reference for disabling hardening features if issues arise in production.

---

## Feature Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `ENABLE_STATE_CONTRACT_ENFORCEMENT` | `false` | Validate + strip unknown keys in mode_context and state updates |
| `ENABLE_PROMPT_BUDGET_GUARDRAIL` | `false` | Enforce prompt token/char limits; truncate oversized context |
| `ENABLE_LATENCY_GATING` | `false` | Skip optional expensive checks (LLM constraint validation) when confidence is high; enforce per-mode iteration caps |
| `ENABLE_TURN_TELEMETRY` | `false` | Emit structured per-turn telemetry JSON logs |
| `ENABLE_SAME_TURN_TRANSITION_CLOSURE` | `false` | Deterministic same-turn closure for ALL four expediente handoffs (change: fix-expediente-transicion) |

## Rollback Procedure

### 1. Set Flags to False

Edit `.env` on the production server:

```bash
ENABLE_STATE_CONTRACT_ENFORCEMENT=false
ENABLE_PROMPT_BUDGET_GUARDRAIL=false
ENABLE_LATENCY_GATING=false
ENABLE_TURN_TELEMETRY=false
ENABLE_SAME_TURN_TRANSITION_CLOSURE=false
```

### 2. Restart Agent Service

```bash
docker-compose restart agent
```

Settings are loaded once at startup via `get_settings()` with `lru_cache`, so a restart is required.

### 3. Verify Rollback

```bash
docker-compose logs -f agent --tail=50
```

Confirm no `turn_telemetry`, `non_canonical_*_keys_stripped`, or `prompt_budget_*` log events appear.

---

## Expected Behavior per Flag (OFF)

| Flag OFF | Behavior |
|----------|----------|
| `STATE_CONTRACT_ENFORCEMENT` | Unknown keys pass through unmodified; DEBUG-level log only (no data stripped) |
| `PROMPT_BUDGET_GUARDRAIL` | Prompts assembled without truncation; no budget checks |
| `LATENCY_GATING` | All constraint validations run; original `MAX_TOOL_ITERATIONS` constants used |
| `TURN_TELEMETRY` | `emit_turn_telemetry()` returns immediately (zero overhead) |
| `SAME_TURN_TRANSITION_CLOSURE` | Only element→base_docs closure is emitted (legacy path); other transitions fall back to tool message or LLM-generated text |

---

## Monitoring Checklist Post-Rollback

1. **Latency** — Watch P95 turn latency; may increase without gating (expected)
2. **Error rate** — Should remain unchanged or decrease
3. **Agent responses** — Verify no empty responses or missing escalations
4. **Tool calls** — Confirm tools execute normally (check `tool_call` log events)
5. **Chatwoot delivery** — Send a test WhatsApp message end-to-end

---

## Related Configuration (Thresholds)

These are informational thresholds, not enforcement gates. Safe to leave at defaults:

| Setting | Default | Purpose |
|---------|---------|---------|
| `PROMPT_MAX_TOKENS_ESTIMATE` | `4000` | Prompt budget ceiling (only active if guardrail ON) |
| `PROMPT_CONTEXT_MAX_CHARS` | `8000` | Max chars for dynamic context injection |
| `TURN_LATENCY_P95_THRESHOLD_MS` | `3000` | Latency alert threshold (telemetry only) |
| `MAX_TOOL_ITERATIONS_CONSULTA` | `3` | Consulta tool loop cap (only active if gating ON) |
| `MAX_TOOL_ITERATIONS_PRESUPUESTO` | `4` | Presupuesto tool loop cap (only active if gating ON) |
| `MAX_TOOL_ITERATIONS_EXPEDIENTE` | `5` | Expediente tool loop cap (only active if gating ON) |

---

## Incremental Re-enable

After resolving the issue, re-enable flags **one at a time**:

1. `ENABLE_TURN_TELEMETRY=true` → restart → monitor 30 min
2. `ENABLE_STATE_CONTRACT_ENFORCEMENT=true` → restart → monitor 30 min
3. `ENABLE_PROMPT_BUDGET_GUARDRAIL=true` → restart → monitor 30 min
4. `ENABLE_LATENCY_GATING=true` → restart → monitor 30 min
5. `ENABLE_SAME_TURN_TRANSITION_CLOSURE=true` → restart → monitor 30 min

Order matters: telemetry first (observe-only), then enforcement (data-modifying).

### fix-expediente-transicion Specific Rollback

If `ENABLE_SAME_TURN_TRANSITION_CLOSURE=true` causes unexpected behaviour on
non-element handoffs (base_docs→personal, personal→vehicle, vehicle→workshop,
workshop→review), set it back to `false` and restart:

```bash
ENABLE_SAME_TURN_TRANSITION_CLOSURE=false
docker-compose restart agent
```

The element→base_docs deterministic closure remains active regardless of this
flag (it was present before this change and is covered by existing regression
tests in `tests/unit/test_expediente_bugfixes.py`).
