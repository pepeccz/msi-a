# Skill Registry — msi-a

Generated: 2026-03-31
Persistence: engram

## Project-Level Skills (`skills/`)

| Name | Path | Trigger |
|------|------|---------|
| `fastapi` | `skills/fastapi/SKILL.md` | Creating/modifying API routes, Pydantic models, middleware, or dependency injection |
| `git-commits` | `skills/git-commits/SKILL.md` | When committing changes, after completing tasks, or user asks to commit |
| `langgraph` | `skills/langgraph/SKILL.md` | Working on StateGraph, nodes, edges, checkpointers, or tool calling |
| `msia` | `skills/msia/SKILL.md` | General MSI-a development questions, project overview, component navigation |
| `msia-admin` | `skills/msia-admin/SKILL.md` | Working on admin panel components, pages, contexts, or hooks |
| `msia-agent` | `skills/msia-agent/SKILL.md` | Working on agent conversation flow, nodes, state, tools, prompts, or mode-based architecture |
| `msia-api` | `skills/msia-api/SKILL.md` | Creating/modifying API routes, services, webhooks, or Pydantic models |
| `msia-database` | `skills/msia-database/SKILL.md` | Creating/modifying database models, writing migrations, or working with seeds |
| `msia-prompts` | `skills/msia-prompts/SKILL.md` | Editing, reviewing, or creating any file under agent/prompts/**/*.md |
| `msia-rag` | `skills/msia-rag/SKILL.md` | Working with document processing, embeddings, vector search, or RAG queries |
| `msia-tariffs` | `skills/msia-tariffs/SKILL.md` | Working with tariffs, elements, tiers, categories, or pricing logic |
| `msia-test` | `skills/msia-test/SKILL.md` | Writing tests for MSI-a components |
| `nextjs-16` | `skills/nextjs-16/SKILL.md` | Working with App Router, Server Components, Server Actions, or route handlers |
| `pytest-async` | `skills/pytest-async/SKILL.md` | Writing tests with pytest, especially async tests, fixtures, mocking, or parametrize |
| `radix-tailwind` | `skills/radix-tailwind/SKILL.md` | Working with UI components, Radix primitives, or Tailwind styling |
| `skill-creator` | `skills/skill-creator/SKILL.md` | When user asks to create a new skill, add agent instructions, or document patterns for AI |
| `skill-sync` | `skills/skill-sync/SKILL.md` | When updating skill metadata, regenerating Auto-invoke tables, or after creating/modifying skills |
| `sqlalchemy-async` | `skills/sqlalchemy-async/SKILL.md` | When working with database models, async queries, relationships, or migrations |
| `typescript-frontend-patterns` | `skills/typescript-frontend-patterns/SKILL.md` | When working on React components, TypeScript types, API clients, or custom hooks |

## User-Level Skills (`~/.claude/skills/`)

> Note: `~/.config/Claude/skills/` does not exist — only `~/.claude/skills/` found.

| Name | Path | Trigger |
|------|------|---------|
| `branch-pr` | `~/.claude/skills/branch-pr/SKILL.md` | When creating a pull request, opening a PR, or preparing changes for review |
| `go-testing` | `~/.claude/skills/go-testing/SKILL.md` | When writing Go tests, using teatest, or adding test coverage |
| `issue-creation` | `~/.claude/skills/issue-creation/SKILL.md` | When creating a GitHub issue, reporting a bug, or requesting a feature |
| `judgment-day` | `~/.claude/skills/judgment-day/SKILL.md` | When user says "judgment day", adversarial dual review |
| `sdd-apply` | `~/.claude/skills/sdd-apply/SKILL.md` | When the orchestrator launches you to implement one or more tasks from a change |
| `sdd-archive` | `~/.claude/skills/sdd-archive/SKILL.md` | When the orchestrator launches you to archive a change after implementation and verification |
| `sdd-design` | `~/.claude/skills/sdd-design/SKILL.md` | When the orchestrator launches you to write or update the technical design for a change |
| `sdd-explore` | `~/.claude/skills/sdd-explore/SKILL.md` | When the orchestrator launches you to think through a feature, investigate the codebase |
| `sdd-init` | `~/.claude/skills/sdd-init/SKILL.md` | Initialize Spec-Driven Development context in any project |
| `sdd-propose` | `~/.claude/skills/sdd-propose/SKILL.md` | When the orchestrator launches you to create or update a proposal for a change |
| `sdd-spec` | `~/.claude/skills/sdd-spec/SKILL.md` | When the orchestrator launches you to write or update specs for a change |
| `sdd-tasks` | `~/.claude/skills/sdd-tasks/SKILL.md` | When the orchestrator launches you to create or update the task breakdown for a change |
| `sdd-verify` | `~/.claude/skills/sdd-verify/SKILL.md` | When the orchestrator launches you to verify a completed (or partially completed) change |
| `skill-creator` | `~/.claude/skills/skill-creator/SKILL.md` | (same as project-level — project-level wins) |

## Project Convention Files

| File | Path |
|------|------|
| AGENTS.md (root) | `AGENTS.md` |
| AGENTS.md (agent) | `agent/AGENTS.md` |
| AGENTS.md (api) | `api/AGENTS.md` (referenced) |
| AGENTS.md (database) | `database/AGENTS.md` (referenced) |
| AGENTS.md (admin-panel) | `admin-panel/AGENTS.md` |
| Coding Standards | `docs/coding-standards/*.md` |

## Resolution Notes

- Deduplication rule applied: project-level `skill-creator` wins over user-level.
- SDD-specific skills (`sdd-*`) from user-level — not duplicated at project level.
- `~/.config/Claude/skills/` does NOT exist (checked); `~/.claude/skills/` is the active user-level dir.
