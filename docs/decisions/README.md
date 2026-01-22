# Architecture Decision Records (ADR)

This directory contains Architecture Decision Records for MSI-a. ADRs document significant architectural decisions, their context, and consequences.

## Index

| ID | Title | Status | Date |
|----|-------|--------|------|
| [ADR-001](001-redis-streams.md) | Redis Streams for Message Queue | Accepted | 2024-12 |
| [ADR-002](002-dynamic-prompts.md) | Dynamic Prompt System | Accepted | 2026-01 |

## Why ADRs?

ADRs help AI assistants and developers understand:
- **Why** decisions were made (not just what)
- **What alternatives** were considered and rejected
- **What trade-offs** exist
- **What constraints** led to the decision

This prevents re-visiting decided issues and helps maintain architectural consistency.

## When to Create an ADR

Create an ADR when:
- Choosing between multiple viable approaches
- Making a decision that affects multiple components
- Introducing a new pattern or technology
- Changing an existing architectural pattern
- A decision might be questioned later

## ADR Lifecycle

```
Proposed → Accepted → [Superseded by ADR-XXX]
                    → [Deprecated]
```

## Template

Use [template.md](template.md) to create new ADRs.

## For AI Assistants

When working on MSI-a, **read relevant ADRs** before:
- Suggesting architectural changes
- Implementing new patterns
- Questioning existing approaches

If you think an ADR should be updated or superseded, discuss with the user first.
