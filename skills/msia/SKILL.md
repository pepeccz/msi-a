---
name: msia
description: >
  Main entry point for MSI-a development - quick reference for all components.
  Trigger: General MSI-a development questions, project overview, component navigation.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root]
  auto_invoke: "General MSI-a development questions"
---

## Project Overview

**MSI-a** is a WhatsApp customer service system for MSI Automotive, a vehicle homologation company in Spain.

## Components

| Component | Stack | Location |
|-----------|-------|----------|
| Agent | Python 3.11+, LangGraph, OpenRouter | `agent/` |
| API | FastAPI, Pydantic, SQLAlchemy | `api/` |
| Admin Panel | Next.js 16, React 19, Radix UI, Tailwind | `admin-panel/` |
| Database | PostgreSQL, SQLAlchemy, Alembic | `database/` |
| Shared | Redis, Chatwoot client, config | `shared/` |

## Architecture Flow

```
WhatsApp → Chatwoot → Webhook (API) → Redis Streams → Agent → LLM → Response
                                                        ↓
                                                   PostgreSQL
```

## Key Data Flow

1. **Message Reception**: Chatwoot webhook → `api/routes/chatwoot.py`
2. **Queue**: Redis Streams for reliable async processing
3. **Processing**: Agent reads from stream, processes with LangGraph
4. **Response**: Agent sends via Chatwoot API → WhatsApp

## Quick Commands

```bash
# Start all services
docker-compose up -d

# View specific service logs
docker-compose logs -f agent
docker-compose logs -f api

# Run migrations
docker-compose exec api alembic upgrade head

# Access PostgreSQL
docker-compose exec postgres psql -U msia msia_db

# Access Redis CLI
docker-compose exec redis redis-cli
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | LLM API key |
| `LLM_MODEL` | Model (default: openai/gpt-4o-mini) |
| `CHATWOOT_*` | Chatwoot configuration |
| `USE_REDIS_STREAMS` | true for Streams (recommended) |
| `MESSAGE_BATCH_WINDOW_SECONDS` | Batching window |

## Related Skills

| Skill | When to Use |
|-------|-------------|
| `msia-agent` | Working on conversation flow, nodes, tools |
| `msia-api` | Creating routes, services, webhooks |
| `msia-admin` | Working on admin panel UI |
| `msia-database` | Database models, migrations |
| `msia-tariffs` | Tariff system, elements, tiers |
| `msia-test` | Writing tests |

## Critical Rules

- ALWAYS maintain consistency between backend and frontend
- ALWAYS use Spanish for user-facing content, English for code/docs
- NEVER start services (docker, npm, etc.) unless explicitly requested
- Development happens locally, execution on separate machine
- **Security**: Agent uses multi-layer prompt injection defense (see `msia-agent` skill)

## Resources

- [AGENTS.md](../../AGENTS.md) - Main repository guidelines
