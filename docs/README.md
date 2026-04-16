# MSI-a Documentation

Technical documentation for MSI-a organized by purpose.

---

## Structure

| Directory | Purpose |
|-----------|---------|
| [decisions/](decisions/) | Architecture Decision Records (ADRs) — source of truth for design decisions |
| [coding-standards/](coding-standards/) | Conventions for Python, TypeScript, DB, security, testing |
| [plans/](plans/) | Implementation plans — `active/` (in progress) + `completed/` (archive) |
| [deployment/](deployment/) | Deployment history, rollouts, phase reports |
| [bugs/](bugs/) | Bug fix reports with root cause analysis |
| [testing/](testing/) | Testing documentation, validation results |
| [sessions/](sessions/) | Development session notes |
| [research/](research/) | Technical spikes, investigations |
| [legal/](../legal/) | Legal/compliance artifacts (AEPD, UE AI Act) |

**Live architecture docs**: `CLAUDE.md` (root), `agent/AGENTS.md`, `agent/CLAUDE.md`. Component-level READMEs (`api/`, `admin-panel/`, `database/`, `shared/`) have specific guidelines.

---

## Quick Start

### For new developers

1. Read `README.md` + `CLAUDE.md` at the repo root
2. Read `agent/AGENTS.md` for the agent architecture (modes, tool loop, transitions)
3. Browse [decisions/](decisions/) for context on key architectural choices
4. Check [plans/active/](plans/active/) for ongoing work

### For AI agents

1. Before making changes: check [decisions/](decisions/) for relevant ADRs
2. For coding patterns: [coding-standards/](coding-standards/)
3. For the agent's critical rules: `agent/CLAUDE.md`

---

## Key Documents

### Standards

- [General](coding-standards/00-general.md) — fundamental rules for all components
- [Python Backend](coding-standards/01-python-backend.md) — FastAPI + SQLAlchemy patterns
- [Database](coding-standards/02-database.md) — SQLAlchemy models, Alembic migrations
- [Agent Architecture](coding-standards/03-agent-architecture.md) — LangGraph + mode patterns
- [Frontend React](coding-standards/04-frontend-react.md) — Next.js 16 + Radix UI
- [Security](coding-standards/05-security.md) — JWT, RBAC, SSRF prevention, image validation
- [Testing](coding-standards/07-testing.md) — pytest patterns

### Decisions

- [ADR Index](decisions/README.md) — all ADRs
- [ADR Template](decisions/template.md)

### Plans

- [Active](plans/active/) — in progress
- [Completed](plans/completed/) — historical reference

---

## Finding Information

| Topic | Location |
|-------|----------|
| Agent conversation flow | `agent/AGENTS.md`, `agent/CLAUDE.md` |
| Writing API routes | [coding-standards/01-python-backend.md](coding-standards/01-python-backend.md) |
| Writing DB models | [coding-standards/02-database.md](coding-standards/02-database.md) |
| Writing agent tools | [coding-standards/03-agent-architecture.md](coding-standards/03-agent-architecture.md), `agent/AGENTS.md` |
| Writing React components | [coding-standards/04-frontend-react.md](coding-standards/04-frontend-react.md) |
| Security best practices | [coding-standards/05-security.md](coding-standards/05-security.md) |
| Why Redis Streams | [decisions/001-redis-streams.md](decisions/001-redis-streams.md) |
| Why dynamic prompts | [decisions/002-dynamic-prompts.md](decisions/002-dynamic-prompts.md) |
| Tool-driven state | [decisions/005-tool-driven-state-management.md](decisions/005-tool-driven-state-management.md) |
| Expediente state integrity | [decisions/010-expediente-state-integrity.md](decisions/010-expediente-state-integrity.md) |
| Error handling strategy | [decisions/ADR-012-error-handling-strategy.md](decisions/ADR-012-error-handling-strategy.md) |

---

## Maintenance

### Adding new documentation

1. **Architecture change** → create an ADR in [decisions/](decisions/)
2. **New feature** → create a plan in [plans/active/](plans/active/)
3. **Bug fix** → document in [bugs/](bugs/) after resolution
4. **Deployment** → add summary to [deployment/](deployment/)

### Updating existing documentation

1. Check if an ADR needs updating when decisions change
2. Update coding standards if patterns change
3. Update `agent/AGENTS.md` + `agent/CLAUDE.md` when agent structure changes
4. Update this README if the directory structure changes
