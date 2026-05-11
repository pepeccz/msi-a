# 013: Unified inbox state snapshot for human pause/resume

**Date**: 2026-05-11
**Status**: Accepted

## Context

The unified inbox lets agents pause the bot per-conversation and respond
manually. The LangGraph checkpointer in Redis has TTLs that don't survive
long human pauses (PRE_EXPEDIENTE 4h, ESCALATION 2h). If a pause lasts
longer than the TTL, the agent loses its full conversation state on resume.

Three options were considered:

1. **Accept cold-start**: shortest path, worst UX — the bot resumes with
   empty context and asks the user to repeat everything.
2. **Increase Redis TTL globally to 7d**: simple config change, but Redis
   RAM pressure scales linearly with all active conversations, and the
   longer TTL benefits only the subset that are currently paused.
3. **Snapshot state to Postgres on pause, restore on resume**: targeted
   persistence — only paused conversations incur the storage cost, and
   the JSONB field is cleared on resume.

We chose option 3.

## Decision

When `ConversationActionService.pause_bot` runs:

1. Serialize the LangGraph thread state into a JSON-safe dict, filtering
   transient fields (`user_message`, `ai_response`, callbacks) and adding
   an explicit `version=1` discriminator.
2. Persist the snapshot to `ConversationHistory.state_snapshot` (JSONB)
   along with `state_snapshot_version=1`.
3. Set `bot_paused_at = NOW()` and `bot_paused_by_user_id = <agent id>`.

When `resume_bot` runs:

1. Validate `state_snapshot_version == 1` (raise
   `UnsupportedSnapshotVersionError` otherwise, preventing corrupt replay).
2. Replay the snapshot via `graph.aupdate_state(config, snapshot.state)`.
3. Query `ConversationMessage` rows created during the paused interval,
   scoped by `conversation_history_id`, and inject them as `HumanMessage`
   with `additional_kwargs={author_type, author_user_id, chatwoot_message_id}`.
4. Clear `state_snapshot`, `bot_paused_at`, `bot_paused_by_user_id`,
   `bot_pause_reason`. Set `bot_resumed_at = NOW()`.

The compiled LangGraph graph is loaded into the API process at startup
(`app.state.compiled_graph`) via `create_compiled_graph(checkpointer)`.
If graph initialisation fails, `/pause` and `/resume` return 503 —
the rest of the inbox (list, thread, mark-read, templates) keeps working.

## Consequences

**Positive**:

- Human pauses of arbitrary duration survive Redis TTL expiry.
- Resume preserves both the bot's prior context and what the human agent
  did in between (human messages are injected into the LangGraph history).
- The snapshot carries a `version` discriminator, so future schema changes
  can be migrated without breaking existing paused conversations.
- Storage is bounded: `state_snapshot` (JSONB, ~tens of KB) is cleared on
  resume, so accumulation requires many concurrently-paused conversations.

**Negative**:

- The compiled graph is loaded in both the `agent` process and the `api`
  process, so the API process pays the cold-start cost on every restart.
- Resume injection adds messages to the LangGraph history, increasing
  token cost on the next agent turn proportional to pause length. This
  is acceptable because human-managed pauses are expected to be short.
- The `state_snapshot` JSONB field can be large if the conversation had
  many prior turns. A future optimisation could store a diff rather than
  the full state.
