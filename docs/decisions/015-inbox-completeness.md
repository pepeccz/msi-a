# ADR-015: Inbox Completeness & Legacy Deprecation

**Date**: 2026-05-11  
**Status**: Accepted  
**Deciders**: Engineering team  
**Related**: ADR-013 (Unified Inbox), ADR-014 (Thread Endpoint Naming)

---

## Context

After merging the unified inbox (ADR-013, ADR-014), an audit of the `/inbox` page against
production usage revealed three blockers and three nice-to-have gaps:

**Blockers**
1. `resolve_escalation` in the backend still sent a `REACTIVATE_BOT` signal to the agent after
   resolving — creating a race condition where the bot re-engaged a conversation already handed
   to a human agent.
2. `/inbox` had no stats summary (pending / in-progress / resolved today / total today), forcing
   operators to scroll the full list to assess workload.
3. The DELETE endpoint for conversations had no RBAC guard — any authenticated user could delete.

**Nice-to-have gaps**
4. No escalation source badge (whatsapp / chatwoot_web / api_direct) on escalation cards.
5. No sort dropdown (last activity, oldest first, most messages, unread).
6. Message `image_count` was always 0; the thread showed `[imagen]` instead of a count.

**Deprecation gap**  
The legacy pages `/conversations`, `/conversations/:id`, and `/escalations` remained live after
unified inbox landed. Their sidebar entry ("Conversaciones") was still visible, causing confusion
about which page to use.

All six gaps plus deprecation were addressed across four stacked PRs (PR1–PR4).

---

## Decisions

### Decision 1: `resolve_escalation` must NOT reactivate the bot

**Option A** (chosen): Remove the `REACTIVATE_BOT` signal entirely from `resolve_escalation`.  
**Option B**: Keep the signal but add a flag to suppress it per call-site.

**Rationale**: When a human agent resolves an escalation, the customer interaction is considered
closed at the human level. Reactivating the bot immediately after creates a confusing experience
(bot messages after a human said goodbye). The signal was originally added for a different flow
(operator passes conversation back to bot intentionally) — that flow now uses a separate endpoint.
Removing the signal is the safest default; if bot reactivation is ever needed after resolve, it
should be an explicit opt-in action, not implicit.

**Semantic change**: This is a **breaking change in behavior** for any operator workflow that
relied on the implicit bot reactivation after resolve. Operators must now use the explicit
"resume bot" action if they want the bot to re-engage.

### Decision 2: Stats integrated into `GET /api/admin/inbox` (not a separate endpoint)

**Option A** (chosen): Add `stats: InboxStatsResponse` to the existing `InboxListResponse`.  
**Option B**: Create a new `GET /api/admin/inbox/stats` endpoint.

**Rationale**: Stats are always consumed alongside the list. A separate endpoint would require a
second fetch on every page load and complicate cache invalidation. Bundling stats into the list
response adds ~50 bytes per call and eliminates round-trips. The query uses a single `COUNT +
GROUP BY` subquery computed from the same filtered dataset as the list.

### Decision 3: Sort implemented in backend with EXISTS subquery

**Option A** (chosen): Backend sort via `_apply_sort()` using `EXISTS` subquery for
`unread_count` ordering, `ORDER BY` for other fields.  
**Option B**: Client-side sort in the frontend after fetching all records.

**Rationale**: Client-side sort breaks with pagination. Backend sort is the correct place for
ordered queries. The `unread_count` case uses an `EXISTS` subquery (not a join) to avoid
multiplying rows.

### Decision 4: RBAC hardening — DELETE is admin-only (frontend + backend)

`DELETE /api/admin/conversations/{id}` now requires `require_role("admin")` on the backend.
The frontend trash button is conditionally rendered only when `useAuth().isAdmin === true`.

Dual enforcement: UI hides the control for non-admins; backend rejects the request regardless.
This is the defensive pattern used across the codebase for destructive operations.

### Decision 5: Deprecation via 308 redirects + file deletion at end of rollout

**Sequence**: Legacy pages kept alive during PR1–PR3 rollout (rollback safety window). After
PR3 stabilized in production, PR4 adds 308 permanent redirects in `next.config.ts` and deletes
the source files.

Routes deprecated:
- `/conversations` → `/inbox` (308)
- `/conversations/:id` → `/inbox?conv=:id` (308)
- `/escalations` → `/inbox?tab=escaladas` (308, was already added in ADR-013 PR6)

Backend endpoints (`GET /api/admin/conversations`, `GET /api/admin/escalations`, etc.) are NOT
touched — they remain alive for external clients or integrations that may consume them directly.

**E2E tests**: Skipped. The 44 unit/integration tests across PR1–PR3 cover each capability
individually. An additional E2E would duplicate coverage without adding signal for a feature
of this scope.

---

## Consequences

### Positive

- **Single entrypoint**: `/inbox` is now the canonical page for all conversation and escalation
  management. Navigation is unambiguous.
- **Native supervision**: Stats, sort, source badge, and image count give operators immediate
  situational awareness without leaving the inbox.
- **Explicit RBAC**: Destructive operations require admin role at both layers — no accidental
  deletes by non-admin agents.
- **Clean codebase**: Three legacy page files and one unused dialog component deleted. Sidebar
  reflects the actual navigation structure.

### Negative / Risks

- **Resolve-no-resume semantic change**: Operators or automation scripts that assumed `resolve`
  would also restart the bot now need to trigger bot resume explicitly. This must be communicated
  in the operator onboarding docs.
- **308 is permanent**: Browsers cache 308 redirects aggressively. If `/inbox` is ever removed
  or renamed, users with cached redirects will land on a broken URL until cache expires or they
  clear browser data.
- **Backend endpoints still live**: The legacy `/api/admin/conversations` and
  `/api/admin/escalations` endpoints are not versioned or deprecated in the API. If they diverge
  from the inbox data model in the future, there is no automated warning.

---

## References

- PR1: backend blockers (T01–T06)
- PR2: frontend blockers (T07–T13)
- PR3: frontend nice-to-have (T14–T16)
- PR4: deprecation + ADR (T17–T22)
- `api/routes/admin.py` — resolve_escalation (Decision 1)
- `api/routes/conversations_admin.py` — stats + sort (Decisions 2, 3)
- `api/models/conversation_inbox.py` — schema extensions
- `admin-panel/next.config.ts` — redirects (Decision 5)
- `admin-panel/src/components/layout/sidebar.tsx` — Conversaciones item removed
