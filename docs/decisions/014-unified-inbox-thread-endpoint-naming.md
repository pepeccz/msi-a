# 014: Unified inbox thread endpoint naming and legacy route deprecation

**Date**: 2026-05-11
**Status**: Accepted

## Context

The legacy `conversation_messages.py` router exposes:

```
GET  /api/admin/conversations/{id}/messages
GET  /api/admin/conversations/{id}/messages/stats
```

These endpoints were designed before the unified inbox and return a flat
message list without cursor pagination, `author_type` attribution, or
read-tracking — all required by the inbox thread view.

When the inbox thread endpoint was added in PR4 (`conversations_admin.py`),
two naming options were considered:

1. **Reuse `/messages`**: rename or replace the legacy endpoint in-place.
   Risk: breaks the existing conversation detail page (`/conversations/[id]`)
   which still calls the legacy endpoint during the post-MVP transition period.

2. **New path `/thread`**: introduce a distinct endpoint that can coexist
   with the legacy route without a coordinated migration.

We chose option 2.

## Decision

The new unified inbox thread endpoint is registered at:

```
GET /api/admin/conversations/{id}/thread
```

It returns cursor-paginated `ConversationMessage` rows with full attribution
(`author_type`, `author_user_id`), `read_at` timestamps, and a `has_more`
flag. It is the canonical source for the inbox thread view.

The legacy `/messages` and `/messages/stats` endpoints remain active but
are considered **deprecated**. They will be removed in a future cleanup PR
once the legacy conversation detail page (`/conversations/[id]`) is migrated
to use `/thread` or superseded by the unified inbox.

## Consequences

**Positive**:

- No breaking change during the parallel operation period — both old and
  new pages continue to work without a coordinated deploy.
- The `/thread` name is semantically clearer for a paginated, real-time
  thread view than `/messages`.

**Negative**:

- Two overlapping endpoints serve related data with different shapes.
  Developers must know which to use. This is documented in the route
  module docstrings and this ADR.
- The legacy routes will accumulate drift (missing new fields) over time
  until they are removed. A follow-up task should be created to migrate
  `/conversations/[id]` and then delete `conversation_messages.py`.
