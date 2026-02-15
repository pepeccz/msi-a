# ADR-008: Restore Escalation & Expediente Integration

## Status

**Accepted** — February 2026

## Context

During the v1→v2 migration, several critical integrations were replaced with stubs:

1. **`escalar_a_humano` tool** — 100-line stub that returned a farewell string but performed NO actual escalation (no Chatwoot notification, no DB record, no team assignment).
2. **`escalation_node` in conversation graph** — stub that returned a farewell message to the user but did nothing in Chatwoot.
3. **`FallbackAction.ESCALATE_TO_HUMAN`** — set `current_mode: "ESCALATION"` but the escalation node only fired on the NEXT user message (which may never come after a farewell).
4. **`_auto_create_case` in expediente_mode** — missing `CaseElementData` rows, `base_doc_descriptions`, `fsm_state` initialization, and LLM instructions. Tools failed with "case_collection not found" on the first turn.

**Discovery trigger**: A real customer conversation on 2026-02-14 was escalated but nobody on the MSI team was notified because all escalation paths were non-functional stubs.

## Decision

### 1. Centralized Escalation Service

Create `agent/services/escalation_service.py` as the **single source of truth** for escalation logic. Both the `escalar_a_humano` tool and the `escalation_node` call this service. This eliminates duplication and ensures consistency.

**6-step escalation process:**
1. Duplicate check (prevent double-escalation within 5 minutes)
2. Disable bot on conversation (set `agent_bot_id: null` in Chatwoot)
3. Add escalation labels in Chatwoot (`escalado`, `requiere-atencion`)
4. Post private note with reason and context for human agents
5. Assign to team (if `CHATWOOT_TEAM_GROUP_ID` is configured)
6. Create `Escalation` record in PostgreSQL

### 2. Immediate Escalation on Fallback

When `FallbackHandler` returns `ESCALATE_TO_HUMAN`, `base_mode.py` now calls `_perform_immediate_escalation()` which executes the escalation service inline — no dependency on the user sending another message.

### 3. Complete Case Initialization in Expediente

`_auto_create_case` now produces the same initialization as `iniciar_expediente`:
- Creates `CaseElementData` rows per element
- Retrieves `base_doc_descriptions` from tarifa_service
- Builds `initial_fsm_state` via `update_case_fsm_state()` and propagates it to the ContextVar before tools execute
- Injects `case_instructions` into the system prompt telling the LLM the case is already created

### 4. Bug Fix: `case.category_slug`

The `Case` model has no `category_slug` column — only `category_id` with a relationship to `VehicleCategory`. Fixed to use `case.category.slug`.

## Consequences

**Positive:**
- Escalations now actually reach human agents via Chatwoot
- Database records provide audit trail for all escalations
- Duplicate escalation prevention (5-minute window)
- EXPEDIENTE_MODE tools work immediately after auto-case-creation
- Graceful degradation: if Chatwoot calls fail, DB record still created

**Negative:**
- Additional Chatwoot API calls during escalation (4 calls: update attributes, add labels, private note, team assignment)
- `_fsm_state_init` pattern adds a transient key to `mode_context` that gets popped in `_run_llm_loop`

## Alternatives Considered

1. **Separate escalation logic per call site** — Rejected: leads to drift between tool and node implementations
2. **Fire-and-forget escalation via Redis Stream** — Rejected: escalation must be synchronous to guarantee the user sees confirmation only after Chatwoot is updated
3. **Add `iniciar_expediente` to EXPEDIENTE_MODE toolset** — Rejected: would allow duplicate case creation since `_auto_create_case` already runs

## Files Changed

### Created
- `agent/services/escalation_service.py` — centralized escalation (~230 lines)

### Modified
- `agent/tools/shared_tools.py` — `escalar_a_humano` rewritten
- `agent/graph/conversation_graph.py` — `escalation_node` rewritten
- `agent/modes/base_mode.py` — added `_perform_immediate_escalation`
- `agent/modes/expediente_mode.py` — enhanced `_auto_create_case` + FSM state propagation + `case.category_slug` bug fix
