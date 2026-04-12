# ADR-012: 4-Tier Error Handling Strategy

## Status

Accepted

## Context

The agent had custom retry logic in `agent/fallback/fallback_handler.py` using a class named `RetryPolicy`. This name collides directly with LangGraph's own `RetryPolicy` from `langgraph.types`, which is the native mechanism for retrying transient infrastructure errors (network, LLM API timeouts) at the graph node level.

The collision meant:

1. Any import of both LangGraph's `RetryPolicy` and the internal one in the same module required aliasing, which was error-prone.
2. LangGraph's `RetryPolicy` was not being used — transient network errors would propagate to the agent's `FallbackHandler`, which is designed for *business* errors (user confusion, intent failures). This caused spurious escalations and incorrect retry counts when the real problem was a network blip.
3. `BaseModeNode.process()` caught all exceptions indiscriminately and routed them through `FallbackHandler`, meaning a transient `httpx.TimeoutException` looked the same as a `USER_CONFUSION` error.

## Decision

Implement a 4-tier error handling strategy with clear separation of concerns:

### Tier 1 — LangGraph RetryPolicy (graph node level)

Apply `langgraph.types.RetryPolicy` on `add_node()` for LLM-calling nodes (`consulta_mode`, `presupuesto_mode`, `expediente_mode`). Configuration:

- `max_attempts=3`
- `initial_interval=1.0`
- `backoff_factor=2.0`
- `retry_on=_is_transient_error` (custom predicate)

Transient errors detected by `_is_transient_error`:
- `httpx.TimeoutException`, `httpx.ConnectError`, `httpx.RemoteProtocolError`
- `ConnectionError`, `TimeoutError`
- `openai.APIConnectionError`, `openai.APITimeoutError`, `openai.InternalServerError` (optional import)

Nodes NOT receiving RetryPolicy: `preprocess`, `router`, `maybe_summarize` (these do no LLM calls and should fail fast).

### Tier 2 — ConversationalRetryPolicy + FallbackHandler (mode level)

The internal `RetryPolicy` dataclass is renamed to `ConversationalRetryPolicy` to eliminate the name collision and clarify its purpose: it governs *conversational* retry behavior (how many times to re-prompt a confused user before escalating).

`FallbackHandler` handles: `INTENT_NOT_UNDERSTOOD`, `TOOL_CALL_FAILED`, `VALIDATION_ERROR`, `LLM_PARSE_ERROR`, `USER_CONFUSION`.

### Tier 3 — handle_tool_errors decorator (tool level)

The `handle_tool_errors` decorator in tool definitions catches tool-level errors and returns structured error dicts rather than raising. Already updated in WS2 to use `ensure_config()`.

### Tier 4 — constraint_service (response validation)

Database-driven post-hoc validation of LLM responses to prevent hallucinated prices and tool bypasses.

### Separation contract

`BaseModeNode.process()` checks whether an exception is transient before routing it to `FallbackHandler`. If the exception IS transient, it re-raises immediately so LangGraph's Tier 1 RetryPolicy can handle it. Only non-transient (business) exceptions go to `FallbackHandler`.

This prevents double-retry: LangGraph retries the node 3 times for transient errors; `FallbackHandler` counts retries for business errors. They never interfere.

## Consequences

- Transient infrastructure errors (network, API timeouts) are retried automatically by LangGraph up to 3 times with exponential backoff before failing hard.
- Business errors (user confusion, bad tool calls) are handled by `FallbackHandler` with per-mode escalation thresholds.
- The name collision between `RetryPolicy` (internal) and `RetryPolicy` (LangGraph) is permanently resolved.
- Importing `langgraph.types.RetryPolicy` in `conversation_graph.py` is unambiguous.
- `ConversationalRetryPolicy` is more self-documenting than `RetryPolicy`.

## Files Affected

- `agent/fallback/fallback_handler.py` — rename `RetryPolicy` → `ConversationalRetryPolicy`
- `agent/modes/base_mode.py` — update import + transient error propagation logic
- `agent/graph/conversation_graph.py` — add `_is_transient_error`, `_LLM_RETRY`, apply on LLM nodes
