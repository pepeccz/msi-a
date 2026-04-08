# MSI-a — Repository Guidelines

## Project Overview

**MSI-a** is a WhatsApp customer service system for MSI Automotive (vehicle homologation company, Spain).

| Component | Location | Stack |
|-----------|----------|-------|
| Agent | `agent/` | Python 3.11+, LangGraph, Ollama + OpenRouter |
| API | `api/` | FastAPI, Pydantic, SQLAlchemy async |
| Admin Panel | `admin-panel/` | Next.js 16, React 19, Radix UI, Tailwind |
| Database | `database/` | PostgreSQL, SQLAlchemy, Alembic |
| Shared | `shared/` | LLM router, Redis, Chatwoot client, image security |

### Agent Modes (current)

3 active modes + escalation:
- **CONSULTA_MODE** — Educational/informational queries
- **PRESUPUESTO_MODE** (~90% traffic) — Pricing + example images
- **EXPEDIENTE_MODE** — Formal case data collection (6 sub-modes)
- **ESCALATION** — Hand off to human agent

### Hybrid LLM (2-tier)

| Tier | Model | Purpose |
|------|-------|---------|
| Tier 1 (Local) | Ollama: `gemma4:e4b` | Classification, extraction, simple tasks |
| Tier 2 (Cloud) | OpenRouter: `deepseek/deepseek-chat` | Conversation, complex reasoning |

Routing via `shared/llm_router.py` with `TaskType` enum. Fallback: Cloud → Local.

---

## Development Environment

> **Do NOT start services locally.** Code editing and analysis only — services run on a remote server (see Deployment).

- Spanish for user-facing content, English for code and documentation
- Each component has its own `AGENTS.md` with specific guidelines
- Coding standards in `docs/coding-standards/` (9 files)
- Architecture decisions in `docs/decisions/` (ADRs) — read before proposing changes

---

## Deployment

Services run on a remote server via SSH:

```bash
# Connect
ssh autohomologacion@autohomologacion-server
cd msi-a

# Service management
docker compose up -d              # Start all
docker compose down               # Stop all
docker compose restart <service>  # Restart one
docker compose ps                 # Status
docker compose logs -f <service>  # Follow logs

# Common operations
docker compose exec api alembic upgrade head    # Run migrations
docker compose exec postgres psql -U msia msia_db  # DB shell
docker compose exec redis redis-cli             # Redis CLI
docker compose exec ollama ollama list          # Check models
```

### Docker Services (6)

| Service | Port | Purpose |
|---------|------|---------|
| `postgres` | 5432 | PostgreSQL 15 |
| `redis` | 6379 | Redis Stack (Streams, cache) |
| `api` | 8000 | FastAPI backend |
| `agent` | — | LangGraph agent (Streams consumer) |
| `admin-panel` | 8001 | Next.js admin UI |
| `ollama` | 11434 | Local LLM server |

---

## Critical Rules

### General

1. **Spanish for users, English for code** — All user-facing text in Spanish
2. **Don't execute services locally** — SSH to server for docker operations
3. **Use Pydantic Settings** — `get_settings()` from `shared/config.py`, NEVER `os.getenv()`
4. **Check ADRs first** — Read `docs/decisions/` before proposing architecture changes
5. **Auto-invoke skills** — Load the relevant skill BEFORE starting work (see table below)

### Python (Agent + API)

6. **Async everywhere** — `async def` for all I/O (DB, Redis, HTTP, files)
7. **Type hints required** — Complete annotations on all functions
8. **Pydantic for validation** — Never raw dicts for API schemas
9. **JSON structured logging** — `structlog` with JSON format, never `print()`

### Agent-Specific (BUSINESS CRITICAL)

10. **Price before images** — NEVER send example images without stating the price first
11. **Never re-identify** — Use `seleccionar_variante_por_respuesta()` for variant answers, NOT `identificar_y_resolver_elementos()`
12. **Skip validation after ID** — Always `skip_validation=True` in `calcular_tarifa_con_elementos()` after identification
13. **Mode transitions via state** — Return `{"current_mode": "NEW_MODE"}`, don't modify state directly
14. **Tool-driven state** — Tools declare state changes via `_internal_flags`, NOT pattern matching (ADR-005)

### Database

15. **UUID primary keys** — All models use UUID, never auto-increment
16. **Dual warning system** — Element warnings MUST exist in BOTH `warnings.element_id` AND `element_warning_associations`
17. **Deterministic UUIDs in seeds** — UUID v5 with fixed namespace from `seed_utils.py`
18. **Soft delete** — `is_active=False`, never hard delete seed data
19. **Always implement downgrade** — Migration `downgrade()` must never be `pass`
20. **selectinload for async** — Always `lazy="selectin"` for relationships

### Frontend (Admin Panel)

21. **Client Components predominant** — Most pages are Client Components
22. **API client for mutations** — Singleton client, NO Server Actions for mutations
23. **Radix + Tailwind** — Use existing `components/ui/`, don't reinvent
24. **Dialog-based CRUD** — `<Dialog>` for create/edit, `<AlertDialog>` for destructive actions

### Security

25. **JWT + RBAC** — `require_role` dependency for protected endpoints
26. **SSRF prevention** — Validate URLs with `image_security.validate_url()`
27. **Image security** — Multi-layer validation with `validate_image_full()`

---

## Skills

Load the relevant skill BEFORE starting work on any component.

### Auto-invoke Table

| Action | Skill |
|--------|-------|
| Agent tools, modes, graph nodes, prompts, ConversationState | `msia-agent` |
| API routes, FastAPI services | `msia-api`, `fastapi` |
| Database models, Alembic migrations | `msia-database`, `sqlalchemy-async` |
| Admin panel components | `msia-admin`, `nextjs-16`, `radix-tailwind` |
| Tariffs or elements | `msia-tariffs` |
| RAG system or documents | `msia-rag` |
| Python tests | `msia-test`, `pytest-async` |
| Git commits | `git-commits` |
| Creating new skills | `skill-creator` |
| LangGraph graphs/nodes | `langgraph` |

### Available Skills

| Skill | Description |
|-------|-------------|
| `msia` | Project overview, architecture, component navigation |
| `msia-agent` | LangGraph flow, nodes, state, tools, prompts |
| `msia-api` | FastAPI routes, services, Chatwoot webhooks |
| `msia-admin` | Next.js panel, components, contexts, hooks |
| `msia-database` | SQLAlchemy models, Alembic migrations, seeds |
| `msia-tariffs` | Tariff system, elements, tiers, inclusions |
| `msia-rag` | RAG pipeline, embeddings, Qdrant |
| `msia-test` | Testing conventions for API and agent |
| `fastapi` | Routers, Pydantic, dependency injection |
| `langgraph` | StateGraph, nodes, edges, checkpointers |
| `sqlalchemy-async` | Async models, relationships, queries |
| `nextjs-16` | App Router, Server Components |
| `radix-tailwind` | Radix UI + Tailwind patterns |
| `pytest-async` | Async fixtures, mocking, parametrize |
| `git-commits` | Conventional Commits, clean history |
| `skill-creator` | Create new AI agent skills |

---

**Last updated**: April 2026
