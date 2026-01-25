# Repository Guidelines

## How to Use This Guide

- Start here for project-wide norms and navigation
- Each component has its own `AGENTS.md` with specific guidelines (e.g., `agent/AGENTS.md`, `api/AGENTS.md`)
- Component docs override this file when guidance conflicts
- Use skills for detailed patterns on-demand

## Development Environment

> **IMPORTANT**: Do NOT start services or execute commands (docker, npm, python, etc.) unless explicitly requested. Development happens locally, but services run on a separate machine with the necessary power for testing and execution. Limit yourself to editing code, analyzing, and answering questions unless instructed otherwise.

- Always maintain consistency between backend and frontend
- Use Spanish for user-facing content, English for code and documentation

---

## Available Skills

Use these skills for detailed patterns on-demand:

### Generic Skills (Reusable)

| Skill | Description | URL |
|-------|-------------|-----|
| `fastapi` | Routers, Pydantic, dependency injection, middleware | [SKILL.md](skills/fastapi/SKILL.md) |
| `langgraph` | StateGraph, nodes, edges, checkpointers, tools | [SKILL.md](skills/langgraph/SKILL.md) |
| `sqlalchemy-async` | Async models, relationships, queries | [SKILL.md](skills/sqlalchemy-async/SKILL.md) |
| `nextjs-16` | App Router, Server Components, Server Actions | [SKILL.md](skills/nextjs-16/SKILL.md) |
| `radix-tailwind` | Radix UI + Tailwind patterns, cn() utility | [SKILL.md](skills/radix-tailwind/SKILL.md) |
| `pytest-async` | Async fixtures, mocking, parametrize | [SKILL.md](skills/pytest-async/SKILL.md) |
| `skill-creator` | Create new AI agent skills | [SKILL.md](skills/skill-creator/SKILL.md) |
| `git-commits` | Clean commits without AI markers, Conventional Commits | [SKILL.md](skills/git-commits/SKILL.md) |

### MSI-a Specific Skills

| Skill | Description | URL |
|-------|-------------|-----|
| `msia` | Project overview, architecture, component navigation | [SKILL.md](skills/msia/SKILL.md) |
| `msia-agent` | LangGraph flow, nodes, state, tools, prompts | [SKILL.md](skills/msia-agent/SKILL.md) |
| `msia-api` | FastAPI routes, services, Chatwoot webhooks | [SKILL.md](skills/msia-api/SKILL.md) |
| `msia-admin` | Next.js panel, React components, contexts, hooks | [SKILL.md](skills/msia-admin/SKILL.md) |
| `msia-database` | SQLAlchemy models, Alembic migrations, seeds | [SKILL.md](skills/msia-database/SKILL.md) |
| `msia-tariffs` | Tariff system, elements, tiers, inclusions | [SKILL.md](skills/msia-tariffs/SKILL.md) |
| `msia-rag` | RAG pipeline, embeddings, Qdrant, document processing | [SKILL.md](skills/msia-rag/SKILL.md) |
| `msia-test` | Testing conventions for API and agent | [SKILL.md](skills/msia-test/SKILL.md) |

---

## Project Overview

**MSI-a** is a WhatsApp customer service system for MSI Automotive, a vehicle homologation company in Spain.

| Component | Location | Tech Stack |
|-----------|----------|------------|
| Agent | `agent/` | Python 3.11+, LangGraph, OpenRouter |
| API | `api/` | FastAPI, Pydantic, SQLAlchemy |
| Admin Panel | `admin-panel/` | Next.js 16, React 19, Radix UI, Tailwind |
| Database | `database/` | PostgreSQL, SQLAlchemy, Alembic |
| Shared | `shared/` | Common utilities, Redis client, Chatwoot client |

### Architecture Flow

```
WhatsApp → Chatwoot → Webhook (API) → Redis Streams → Agent → LLM → Response
                                                        ↓
                                                   PostgreSQL
                                                        ↓
Admin Panel → API → Document Upload → Redis Stream → Document Processor
                                                           ↓
                                              Ollama (embeddings) → Qdrant
```

---

## Directory Structure

```
msi-a/
├── docker-compose.yml      # Service orchestration (9 services)
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variables template
├── uploads/                # Uploaded documents (PDFs, images)
│
├── shared/
│   ├── config.py           # Centralized config (Pydantic Settings)
│   ├── redis_client.py     # Redis client with Streams
│   ├── chatwoot_client.py  # Chatwoot API client
│   └── logging_config.py   # JSON structured logging
│
├── database/
│   ├── models.py           # SQLAlchemy models (22 models)
│   ├── connection.py       # Async PostgreSQL connection
│   ├── seeds/              # Data seeds
│   └── alembic/            # Database migrations
│
├── api/
│   ├── main.py             # FastAPI entry point
│   ├── routes/             # API endpoints (10 modules)
│   ├── services/           # Business logic (RAG, embeddings, etc.)
│   ├── models/             # Pydantic schemas
│   └── workers/            # Background workers (document processor)
│
├── agent/
│   ├── main.py             # Agent entry point
│   ├── graphs/             # LangGraph StateGraph definitions
│   ├── nodes/              # Graph nodes (process_message, conversational_agent)
│   ├── tools/              # LangGraph tools (20 tools)
│   ├── services/           # Agent services (tariffs, elements)
│   ├── fsm/                # Finite state machines (case collection)
│   ├── state/              # State schemas and checkpointer
│   └── prompts/            # System prompts
│
└── admin-panel/
    ├── src/
    │   ├── app/            # Next.js App Router
    │   ├── components/     # React components
    │   ├── contexts/       # React contexts
    │   ├── hooks/          # Custom hooks
    │   └── lib/            # Utilities
    └── package.json
```

---

## Code Conventions

### Python

- Strict type hints everywhere
- Async/await for I/O operations
- JSON structured logging
- Pydantic for data validation

### TypeScript/React

- Next.js App Router
- Server Components by default
- Radix UI for components
- Tailwind CSS for styles

---

## Useful Commands

```bash
# Start services
docker-compose up -d

# View agent logs
docker-compose logs -f agent

# Run migrations
docker-compose exec api alembic upgrade head

# Access PostgreSQL
docker-compose exec postgres psql -U msia msia_db

# Access Redis CLI
docker-compose exec redis redis-cli
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | API key for LLM |
| `LLM_MODEL` | Model to use (default: openai/gpt-4o-mini) |
| `CHATWOOT_*` | Chatwoot configuration |
| `USE_REDIS_STREAMS` | true to use Streams (recommended) |
| `MESSAGE_BATCH_WINDOW_SECONDS` | Batching window (0 = disabled) |

---

## Session Context (Long Sessions)

For coding sessions longer than 1 hour, use `.session-context.md` to track:

- **Active Skills** - Skills loaded (rules to remember)
- **Critical Rules** - Most relevant rules for current task
- **Recent Changes** - Files modified this session
- **Decisions Made** - Architecture choices taken

### Commands

| Command | Action | Tokens |
|---------|--------|--------|
| `"read session context"` | Re-read `.session-context.md` | ~200 |
| `"refresh rules for [skill]"` | Read `skills/[skill]/rules.md` | ~50 |
| `"update session context"` | Add recent work to context | ~50 |
| `"check context"` | Verify AI remembers rules | ~100 |

### Rule Snippets

Quick-refresh files for when AI "forgets" rules:

| Skill | File | Purpose |
|-------|------|---------|
| `msia-agent` | `skills/msia-agent/rules.md` | Agent anti-patterns, FSM rules |
| `msia-api` | `skills/msia-api/rules.md` | Route patterns, Pydantic |
| `msia-database` | `skills/msia-database/rules.md` | Models, migrations |
| `msia-tariffs` | `skills/msia-tariffs/rules.md` | Pricing, elements |

---

## Development Notes

- MSI-a agent answers queries about vehicle homologations
- Specific data collection flows will be added later
- Prices are fixed by homologation type (no assignable resources)
- Escalate to human when case is complex or customer requests it

### Auto-invoke Skills

When performing these actions, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| After creating/modifying a skill | `skill-sync` |
| Creating git commits | `git-commits` |
| Creating new skills | `skill-creator` |
| Creating/modifying API routes | `msia-api` |
| Creating/modifying FastAPI services | `fastapi` |
| Creating/modifying agent tools | `msia-agent` |
| Creating/modifying database models | `msia-database` |
| Creating/modifying graph nodes | `msia-agent` |
| General MSI-a development questions | `msia` |
| Regenerate AGENTS.md Auto-invoke tables | `skill-sync` |
| Troubleshoot missing skill in auto-invoke | `skill-sync` |
| Working on FSM case collection | `msia-agent` |
| Working on LangGraph graphs/nodes | `langgraph` |
| Working on admin panel components | `msia-admin` |
| Working on agent conversation flow | `msia-agent` |
| Working on system prompts | `msia-agent` |
| Working with ConversationState | `msia-agent` |
| Working with Next.js App Router | `nextjs-16` |
| Working with RAG system or documents | `msia-rag` |
| Working with Radix UI + Tailwind | `radix-tailwind` |
| Working with tariffs or elements | `msia-tariffs` |
| Writing Alembic migrations | `sqlalchemy-async` |
| Writing Python tests | `pytest-async` |
| Writing tests for MSI-a | `msia-test` |

---

## AI Development Workflow

Enhanced AI-assisted development using specialized agents and commands.

### Available Commands

| Command | Description | Agent |
|---------|-------------|-------|
| `/plan` | Create implementation plan before coding | planner |
| `/tdd` | Guide TDD implementation cycle | tdd-guide |
| `/code-review` | Review code for quality and security | code-reviewer |
| `/security-review` | Security audit (OWASP + LLM) | security-reviewer |
| `/architecture` | Architectural guidance and ADRs | architect |
| `/build-fix` | Diagnose and fix build/type errors | build-error-resolver |
| `/doc-update` | Sync documentation with code changes | doc-updater |
| `/refactor-clean` | Find and remove dead code | refactor-cleaner |

### OpenCode Skills (.opencode/skills/)

| Skill | Description |
|-------|-------------|
| `coding-standards` | Python and TypeScript coding rules |
| `python-backend-patterns` | FastAPI, SQLAlchemy async patterns |
| `typescript-frontend-patterns` | Next.js 16, Radix UI, Tailwind |
| `tdd-workflow` | Red-Green-Refactor methodology |
| `security-review` | OWASP Top 10 + LLM security |
| `context-optimization` | Reduce token usage, longer sessions |

### Recommended Workflow

1. **Plan First**: Use `/plan` for non-trivial features
2. **TDD When Possible**: Use `/tdd` for new implementations
3. **Review Before Commit**: Use `/code-review` and `/security-review`
4. **Fix Errors Fast**: Use `/build-fix` when builds fail
5. **Keep Docs Updated**: Use `/doc-update` after API changes

### Context Optimization

For long sessions:
- Delegate to specialized agents (reduces main context)
- Compact frequently after completing tasks
- Use `.session-context.md` to track state
- Load skills on-demand, not all at once

See `.opencode/skills/context-optimization/SKILL.md` for detailed strategies.

---

## Critical Rules (Always Remember)

These rules apply across ALL components. **Re-read this section when uncertain.**

### General

1. **Spanish for users, English for code** - All user-facing text in Spanish, code/docs in English
2. **Don't execute services** - Dev happens locally, services run on remote machine. Don't run docker/npm/python unless asked
3. **Auto-invoke skills** - Load the relevant skill BEFORE starting work on any component
4. **Check ADRs first** - Read `docs/decisions/` before proposing architecture changes

### Python (Agent/API)

5. **Async everywhere** - Use `async def` for all I/O operations (DB, Redis, HTTP)
6. **Type hints required** - All functions must have complete type annotations
7. **Pydantic for validation** - Never use raw dicts for API input/output schemas
8. **JSON structured logging** - Use `structlog` with JSON format, never print()

### Agent-Specific

9. **Price before images** - NEVER send example images without stating the price first
10. **Never re-identify** - Use `seleccionar_variante_por_respuesta()` for variant answers, not `identificar_y_resolver_elementos()`
11. **Skip validation after ID** - Always use `skip_validation=True` in `calcular_tarifa_con_elementos()` after identification
12. **FSM tools only** - Use case_tools for FSM transitions, never modify fsm_state directly

### Frontend (Admin Panel)

13. **Server Components default** - Only add `'use client'` when you need hooks/interactivity
14. **Radix + Tailwind patterns** - Use existing components from `components/ui/`, don't reinvent
15. **Server Actions for mutations** - Prefer Server Actions over API routes for form submissions
