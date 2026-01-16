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

## Auto-invoke Skills

When performing these actions, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| General MSI-a development questions | `msia` |
| Working on agent conversation flow | `msia-agent` |
| Working on LangGraph graphs/nodes | `langgraph` |
| Creating/modifying API routes | `msia-api` |
| Creating/modifying FastAPI services | `fastapi` |
| Working on admin panel components | `msia-admin` |
| Working with Next.js App Router | `nextjs-16` |
| Working with Radix UI + Tailwind | `radix-tailwind` |
| Creating/modifying database models | `msia-database` |
| Writing Alembic migrations | `sqlalchemy-async` |
| Working with tariffs or elements | `msia-tariffs` |
| Working with RAG system or documents | `msia-rag` |
| Writing Python tests | `pytest-async` |
| Writing tests for MSI-a | `msia-test` |
| Creating new skills | `skill-creator` |

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

## Development Notes

- MSI-a agent answers queries about vehicle homologations
- Specific data collection flows will be added later
- Prices are fixed by homologation type (no assignable resources)
- Escalate to human when case is complex or customer requests it
