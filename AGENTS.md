# Repository Guidelines

## Agent Architecture (OpenCode v2.0)

MSI-a uses a **multi-agent architecture** that separates planning from execution for safer development in production.

### Available Agents

| Agent | Type | Purpose | When to Use |
|-------|------|---------|-------------|
| **zanovix** | PRIMARY | General mentor (default) | Simple tasks, questions, guidance |
| **architect** | PRIMARY | System planner (read-only) | Complex features, multi-service changes |
| **backend-dev** | SUBAGENT | FastAPI + SQLAlchemy | API routes, services, Pydantic schemas |
| **agent-dev** | SUBAGENT | LangGraph + Modes | Tools, modes, prompts, intent routing |
| **frontend-dev** | SUBAGENT | Next.js + Radix UI | Admin panel pages, components |
| **database-dev** | SUBAGENT | PostgreSQL + Alembic | Models, migrations, seeds |
| **qa-dev** | SUBAGENT | Testing | pytest, Jest, coverage verification |
| **deploy-dev** | PRIMARY | DevOps (controlled) | Docker operations, system status |
| **investigator-dev** | SUBAGENT | Diagnostics (read-only) | Problem investigation, root cause analysis |
| **general-helper** | PRIMARY | Simple tasks | Quick lookups, basic operations |

### Predefined Commands

| Command | Description |
|---------|-------------|
| `/plan [descripción]` | Flujo completo: investigator → architect → esperar aprobación → ejecutar |
| `/investigate [área]` | Diagnóstico técnico profundo (solo análisis, read-only) |
| `/test [scope]` | Ejecutar tests con **qa-dev** y verificar criterios de aceptación |
| `/sync-docs [contexto]` | Sincronizar skills y docs con cambios recientes (auto después de implementaciones) |
| `/commit [contexto]` | Proponer commit con Conventional Commits + pedir confirmación explícita |
| `/status` | Verificar estado de servicios Docker con **deploy-dev** |
| `/logs [service]` | Ver logs de servicios Docker con **deploy-dev** |

### Development Workflow

**Simple task** (pregunta, búsqueda, fix menor):
```
→ zanovix responde directamente
```
**Ejemplos**: "¿Cómo funciona el dual warning system?", "Muestra el modelo Element", "Fixea este typo"

**Moderate task** (cambio en un solo servicio, bug claro):
```
zanovix → subagente especializado → verificar si requiere sync-docs
```
**Ejemplos**: "Agregá validación de email en usuarios", "El webhook de Chatwoot no procesa imágenes"

**Complex task** (nueva feature, cambio multi-servicio, refactor):
```
1. investigator  → analiza área afectada, reporta hallazgos técnicos
2. zanovix       → presenta opciones al usuario, hace preguntas de afinación
3. architect     → crea plan detallado en docs/plans/active/[nombre].md
4. usuario       → APRUEBA el plan (sin esto NO se ejecuta nada)
5. subagentes    → ejecutan según dependencias del plan:
                    - database-dev (migrations primero si aplica)
                    - backend-dev (rutas y servicios API)
                    - agent-dev (tools, modes, prompts)
                    - frontend-dev (UI y componentes)
6. qa-dev        → verifica tests y criterios de aceptación del plan (>90% coverage)
7. sync-docs     → actualiza skills/docs si hay cambios arquitectónicos
8. zanovix       → propone commit con Conventional Commits y pide confirmación
```
**Ejemplos**: "Implementá sistema de notificaciones push", "Agregá roles personalizados", "Refactorizá sistema de tarifas"

### Coding Standards

All agents reference:
- **AGENTS.md** files (this file + component-specific)
- **docs/coding-standards/** (9 files with consolidated patterns)

See `docs/coding-standards/README.md` for complete guide.

---

## How to Use This Guide

- Start here for project-wide norms and navigation
- Each component has its own `AGENTS.md` with specific guidelines (e.g., `agent/AGENTS.md`, `api/AGENTS.md`)
- Component docs override this file when guidance conflicts
- Use skills for detailed patterns on-demand
- **NEW**: Coding standards in `docs/coding-standards/` provide consolidated rules

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
| `msia-prompts` | Prompt editing standards for agent/prompts/ files. Auto-invoked on any prompt file edit. | [SKILL.md](skills/msia-prompts/SKILL.md) |

---

## Project Overview

**MSI-a** is a WhatsApp customer service system for MSI Automotive, a vehicle homologation company in Spain.

| Component | Location | Tech Stack |
|-----------|----------|------------|
| Agent | `agent/` | Python 3.11+, LangGraph, Ollama (hybrid LLM), OpenRouter |
| API | `api/` | FastAPI, Pydantic, SQLAlchemy |
| Admin Panel | `admin-panel/` | Next.js 16, React 19, Radix UI, Tailwind |
| Database | `database/` | PostgreSQL, SQLAlchemy, Alembic |
| Shared | `shared/` | LLM router, Redis, Chatwoot client, image security, settings cache |

### Architecture Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         MESSAGE PROCESSING                              │
└─────────────────────────────────────────────────────────────────────────┘

WhatsApp → Chatwoot → Webhook (API) → Redis Streams → Agent
                                            ↓
                                    Message Batching
                                            ↓
                         ┌──────────────────────────────────┐
                         │     Hybrid LLM Router            │
                         │                                  │
                         │  Tier 1 (Fast): qwen2.5:3b      │
                         │  Tier 2 (Capable): llama3:8b    │
                         │  Tier 3 (Cloud): deepseek-chat  │
                         │                                  │
                         │  Fallback: Tier 3 → Tier 2 → 1  │
                         └──────────────────────────────────┘
                                            ↓
                              Conversation Graph (LangGraph)
                                            ↓
                                    PostgreSQL (State)
                                            ↓
                              Response → Chatwoot → WhatsApp


┌─────────────────────────────────────────────────────────────────────────┐
│                       RAG DOCUMENT PROCESSING                           │
└─────────────────────────────────────────────────────────────────────────┘

Admin Panel → API → Upload → Redis Stream → Document Processor Worker
                                                      ↓
                                    PDF Extraction (Docling/PyMuPDF)
                                                      ↓
                                          Semantic Chunking
                                                      ↓
                              Section Mapping (Hybrid LLM: Ollama + OpenRouter)
                                                      ↓
                                  Ollama Embeddings (nomic-embed-text)
                                                      ↓
                                  Qdrant (vectors) + PostgreSQL (metadata)


┌─────────────────────────────────────────────────────────────────────────┐
│                            RAG QUERY PIPELINE                           │
└─────────────────────────────────────────────────────────────────────────┘

Query → Expansion → Hybrid Search (Vector + Keyword) → RRF Merge
                                                           ↓
                                            Keyword Boosting (domain terms)
                                                           ↓
                                              BGE Reranking (top 5)
                                                           ↓
                                    Query Complexity Classification
                                                           ↓
                         ┌──────────────────────────────────────────┐
                         │  SIMPLE → Ollama Tier 2 (llama3:8b)     │
                         │  COMPLEX → OpenRouter Tier 3 (deepseek) │
                         └──────────────────────────────────────────┘
                                                           ↓
                                        LLM Answer + Citations
                                                           ↓
                                    Redis Cache (24h embeddings, 1h queries)
```

---

## Directory Structure

```
msi-a/
├── docker-compose.yml      # Service orchestration (9 services)
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variables template (46+ vars)
├── alembic.ini             # Alembic migration config
│
├── uploads/                # Uploaded documents (PDFs, images)
├── datos/                  # Data files (image mappings)
├── scripts/                # Utility scripts (SQL, Python, deploy)
├── tests/                  # Test suite (conftest + 9 test files)
│
├── docs/
│   ├── decisions/          # ADRs (Architecture Decision Records)
│   │   ├── 001-redis-streams.md
│   │   ├── 002-dynamic-prompts.md
│   │   ├── 003-remove-chatwoot-atencion-check.md
│   │   ├── 004-fix-presupuesto-corrupted-text.md
│   │   └── 005-tool-driven-state-management.md
│   └── arquitectura-agente/  # Agent architecture diagrams
│
├── shared/                 # Shared utilities (11 files, 3,402 lines)
│   ├── config.py           # Centralized config (Pydantic Settings, 46+ env vars)
│   ├── redis_client.py     # Redis client with Streams, consumer groups, DLQ
│   ├── chatwoot_client.py  # Chatwoot API client with retry logic
│   ├── chatwoot_sync.py    # User-to-Chatwoot contact sync
│   ├── logging_config.py   # JSON structured logging
│   ├── llm_router.py       # Hybrid LLM router (3-tier: fast/capable/cloud)
│   ├── ollama_client.py    # Ollama availability checks
│   ├── image_security.py   # Multi-layer image validation (SSRF, magic numbers, PIL)
│   ├── text_utils.py       # WhatsApp text formatting (markdown stripping)
│   ├── settings_cache.py   # Redis-cached system settings (5s TTL)
│   └── __init__.py
│
├── database/               # Database layer (32 models, 34 migrations)
│   ├── models.py           # SQLAlchemy models (32 models, 3,224 lines)
│   ├── connection.py       # Async PostgreSQL connection, pooling
│   ├── migrations/         # Manual SQL fixes
│   ├── seeds/              # Data seeds (4,887 lines)
│   │   ├── run_all_seeds.py         # Main orchestrator
│   │   ├── seed_utils.py            # Deterministic UUIDs (UUID v5)
│   │   ├── validate_elements_seed.py
│   │   ├── verify_warning_sync.py   # Dual warning verification
│   │   ├── create_admin_user.py
│   │   ├── WARNING_SYSTEM.md
│   │   ├── data/                    # Data modules (motos_part, aseicars_prof)
│   │   └── seeders/                 # Seeder classes (Base, Category, Element, Inclusion)
│   └── alembic/            # Database migrations (34 migrations, 4,490 lines)
│
├── api/                    # FastAPI backend (12 route modules)
│   ├── main.py             # FastAPI entry point
│   ├── routes/             # API endpoints (12 modules)
│   │   ├── chatwoot.py, admin.py, tariffs.py, elements.py
│   │   ├── images.py, cases.py, token_usage.py, system.py
│   │   ├── conversation_messages.py, public_tariffs.py
│   │   ├── validation_metrics.py, billing.py
│   │   └── __init__.py
│   ├── services/           # Business logic
│   │   ├── image_service.py                    # Image processing (security validation)
│   │   ├── chatwoot_image_service.py           # Chatwoot image handling (SSRF prevention)
│   │   ├── message_persistence_service.py      # Fire-and-forget message logging
│   │   ├── cache_service.py                    # Redis cache helpers
│   │   ├── conversation_reset_coordinator.py   # Conversation reset orchestration
│   │   ├── billing_service.py                  # Billing business logic
│   │   ├── stripe_service.py                   # Stripe payment integration
│   │   ├── pdf_service.py                      # PDF generation (invoices)
│   │   └── garbage_collection_service.py       # GC for stale data
│   ├── models/             # Pydantic schemas
│   └── workers/            # Background workers
│       └── billing_worker.py  # Monthly invoice + overdue check (asyncio tasks)
│
├── agent/                  # LangGraph agent (Mode-based architecture, NO FSM)
│   ├── main.py             # Agent entry point (Redis Streams consumer)
│   ├── graph/              # LangGraph StateGraph definition
│   │   └── conversation_graph.py    # Main graph (preprocess → router → modes → END)
│   ├── router/             # Intent routing and digression detection
│   │   ├── intent_router.py         # Intent classification (9 intents, keyword + LLM)
│   │   ├── digression_manager.py    # Off-topic detection in focused modes
│   │   └── mode_transitions.py      # Mode transition rules + context preservation
│   ├── fallback/           # Per-mode retry policies
│   │   └── fallback_handler.py      # Retry limits, progressive reprompts, escalation
│   ├── modes/              # Mode nodes + tool-loop subgraph
│   │   ├── base_mode.py             # BaseModeNode (fallback, retry state, telemetry, timeout)
│   │   ├── pre_expediente_mode.py   # PRE_EXPEDIENTE_MODE (~90% traffic) — 3 phases via state
│   │   ├── presupuesto_mode.py      # Backward-compat alias → pre_expediente_mode
│   │   ├── expediente_mode.py       # EXPEDIENTE_MODE — subgraph dispatch
│   │   ├── expediente_nodes.py      # Factory for 6 sub-mode nodes
│   │   ├── expediente_state.py      # Sub-mode state schema
│   │   ├── tool_loop.py             # build_mode_tool_loop() — custom tool_node subgraph
│   │   ├── tool_loop_state.py       # Loop state schema
│   │   ├── tool_executor.py         # execute_and_log_tool — dedup, logging
│   │   ├── post_tool_hooks.py       # post_tool_node hooks (_state_update merge)
│   │   └── submodos/                # 6 sub-mode handlers
│   ├── prompts/            # Dynamic prompt assembly (core + mode + context)
│   │   ├── loader.py                # Prompt assembly (core.md + mode file + mode_context)
│   │   ├── core.md                  # Single core with XML tags (identity, execution_model, security, principles, voice, format, pricing, photos_model, escalation)
│   │   ├── modes/                   # 10 mode/sub-mode prompts
│   │   │   ├── pre_expediente_discovery.md, pre_expediente_pricing.md, pre_expediente_post_price.md
│   │   │   ├── expediente_elements.md, expediente_base_docs.md
│   │   │   ├── expediente_personal.md, expediente_vehicle.md
│   │   │   ├── expediente_workshop.md, expediente_review.md
│   │   │   └── session_recovery.md
│   │   └── calculator_base.py       # Admin-only preview (used by api/routes/tariffs.py)
│   ├── tools/              # 29 LangChain tools with Pydantic args_schema
│   │   ├── element_tools.py         # 5 tools (identification, variants, tariff)
│   │   ├── tarifa_tools.py          # 3 tools (categories, tarifas, services)
│   │   ├── case_tools.py            # 10 tools (case lifecycle, data collection)
│   │   ├── element_data_tools.py    # 7 tools (photos + per-element data)
│   │   ├── image_tools.py           # 1 tool (example images)
│   │   ├── vehicle_tools.py         # 1 tool (vehicle classification)
│   │   ├── transition_tools.py      # 1 tool (confirmar_presupuesto — signals _transition_to)
│   │   ├── shared_tools.py          # 1 tool (escalar_a_humano)
│   │   ├── schemas.py               # Pydantic args schemas
│   │   └── types.py                 # ToolResult types, _state_update contract
│   ├── services/           # Business logic
│   │   ├── tarifa_service.py        # Tariff calculation with Redis caching
│   │   ├── element_service.py       # Element matching (NLP + fuzzy + variants)
│   │   ├── element_state_service.py # v2 COLLECTION_CONTEXT
│   │   ├── element_data_service.py  # Element data persistence
│   │   ├── element_required_fields_service.py  # Conditional fields
│   │   ├── variant_interpretation_service.py   # Multi-unit variant LLM interpreter
│   │   ├── collection_mode.py       # Sequential/Batch/Hybrid strategy
│   │   ├── constraint_service.py    # Response validation (anti-hallucination)
│   │   ├── tool_logging_service.py  # Persistent tool call logging
│   │   ├── escalation_service.py    # 6-step escalation flow
│   │   ├── expediente_guards.py     # Kickoff / phase guards
│   │   ├── token_tracking.py        # Token usage tracking
│   │   ├── image_service.py         # Image dispatch
│   │   └── prompt_service.py        # Admin-only preview (used by api/routes/tariffs.py)
│   ├── state/              # State schemas and checkpointer
│   │   ├── conversation_state.py    # ConversationState (Mode-based, NOT FSM)
│   │   ├── checkpointer.py          # Redis checkpointer (LangGraph persistence)
│   │   └── helpers.py               # State utilities (format_messages, etc.)
│   └── utils/              # Shared utilities
│       ├── validation.py            # Input validation (whitelist-based)
│       ├── errors.py                # Custom exceptions
│       ├── tool_helpers.py          # Tool execution helpers
│       └── text_utils.py            # Text processing
│
└── admin-panel/            # Next.js 16 admin panel (28 routes, 46 components, 91 files)
    ├── src/
    │   ├── app/            # Next.js App Router (28 routes)
    │   │   ├── (dashboard)/         # Dashboard routes (25 Client Components)
    │   │   │   ├── tariffs/         # Tariff CRUD (8 components + test)
    │   │   │   ├── elements/        # Element CRUD (4 components)
    │   │   │   ├── categories/      # Category management
    │   │   │   ├── documents/       # RAG document management
    │   │   │   ├── logs/            # System monitoring
    │   │   │   └── ...
    │   │   ├── api/                 # API routes (SSE proxy for Docker logs)
    │   │   └── login/               # Auth page
    │   ├── components/     # React components (46 total)
    │   │   ├── ui/                  # Radix UI components (21 components)
    │   │   └── [feature]/           # Feature components (25 components)
    │   ├── contexts/       # React contexts (3 contexts)
    │   │   ├── auth-context.tsx
    │   │   ├── sidebar-context.tsx
    │   │   └── global-search-context.tsx
    │   ├── hooks/          # Custom hooks (4 hooks)
    │   │   ├── use-category-data.ts
    │   │   ├── use-tier-elements.ts
    │   │   ├── use-category-elements.ts
    │   │   └── use-global-search.ts
    │   └── lib/            # Utilities
    │       ├── api.ts               # API client singleton (1,357 lines)
    │       ├── types.ts             # TypeScript types (1,397 lines)
    │       ├── auth.ts, constants.ts, utils.ts, validators.ts
    │       └── ...
    ├── package.json
    ├── next.config.mjs
    ├── tailwind.config.ts
    └── tsconfig.json
```

---

## Shared Component

The `shared/` directory contains **11 Python modules** (3,402 lines) with utilities shared across agent, API, and workers.

### File Inventory

| File | Lines | Purpose | Key Exports |
|------|-------|---------|-------------|
| `config.py` | 375 | **Centralized configuration** via Pydantic Settings. All env vars defined here. | `Settings` class (46+ fields), `get_settings()` singleton, `QUANTITY_PATTERNS`, `NEGATION_PATTERNS` |
| `redis_client.py` | 478 | **Redis client singleton** with Streams support, consumer groups, DLQ | `get_redis_client()`, `add_to_stream()`, `read_from_stream()`, `acknowledge_message()`, `move_to_dead_letter()` |
| `chatwoot_client.py` | 1141 | **Chatwoot API client** (httpx async) with retry logic (tenacity) | `ChatwootClient`: `send_message()`, `send_images()`, `update_contact()`, `add_labels()`, `get_conversation_messages()` |
| `chatwoot_sync.py` | 126 | **User-to-Chatwoot contact sync**. Bidirectional sync of name, email, client_type | `sync_user_to_chatwoot(user, save_contact_id)` |
| `logging_config.py` | 129 | **JSON structured logging** with phone sanitization, message truncation | `configure_logging()`, `sanitize_phone()`, `truncate_message()`, `JSONFormatter` |
| `llm_router.py` | 405 | **Hybrid LLM router**. Routes to Ollama (local) or OpenRouter (cloud) with fallback | `LLMRouter`: `invoke()`, `health_check()`. Enums: `TaskType`, `ModelTier`, `Provider`. `get_llm_router()` singleton |
| `ollama_client.py` | 63 | **Ollama availability checks** | `is_ollama_available()`, `check_ollama_model(model_name)` |
| `image_security.py` | 450 | **Multi-layer image security**. SSRF prevention, magic number validation, decompression bomb detection | `validate_filename()`, `validate_url()`, `validate_magic_number()`, `validate_image_content()`, `validate_image_full()`, `sanitize_filename()` |
| `text_utils.py` | 53 | **WhatsApp text formatting**. Strips markdown for WhatsApp compatibility | `strip_markdown_for_whatsapp(text)` |
| `settings_cache.py` | 164 | **Redis-cached system settings** with 5s TTL, manual invalidation | `get_cached_setting(key)`, `invalidate_setting_cache(key)`, `invalidate_all_settings()` |

### Key Patterns

**Pydantic Settings Singleton**:
```python
from shared.config import get_settings

settings = get_settings()  # Cached with lru_cache
database_url = settings.DATABASE_URL
```

**Redis Streams**:
```python
from shared.redis_client import get_redis_client, add_to_stream, INCOMING_STREAM

redis = get_redis_client()
await add_to_stream(redis, INCOMING_STREAM, {"message": "..."})
```

**Hybrid LLM Routing**:
```python
from shared.llm_router import get_llm_router, TaskType

router = get_llm_router()
response = await router.invoke(
    task_type=TaskType.CONVERSATION,
    messages=[...],
    force_cloud=False  # Auto-routes based on task
)
```

**Image Security Validation**:
```python
from shared.image_security import validate_image_full

await validate_image_full(
    file_path=path,
    url=url,  # Checks SSRF
    max_size_mb=10
)
```

---

## Hybrid LLM Architecture

MSI-a uses a **3-tier hybrid LLM system** to optimize costs and latency:

| Tier | Model | Purpose | Cost | Latency |
|------|-------|---------|------|---------|
| **Tier 1 (Fast)** | Ollama: `qwen2.5:3b` | Fallback, classification, extraction | $0 | ~200ms |
| **Tier 2 (Capable)** | Ollama: `llama3:8b` | Simple RAG queries, vehicle classification | $0 | ~1s |
| **Tier 3 (Cloud)** | OpenRouter: `deepseek/deepseek-chat` | Conversation, complex RAG, reasoning | ~$0.27/1M tokens | ~2s |

### Routing Logic

**By TaskType** (defined in `shared/llm_router.py`):
- `CONVERSATION` → Tier 3 (cloud) — Requires nuanced understanding
- `SIMPLE_RAG` → Tier 2 (capable) — Factual queries from documents
- `COMPLEX_RAG` → Tier 3 (cloud) — Multi-step reasoning
- `CLASSIFICATION` → Tier 1 (fast) — Simple categorization
- `EXTRACTION` → Tier 1 (fast) — Data extraction from text
- `SECTION_MAPPING` → Tier 1 (fast) + Tier 3 (fallback)

**Fallback Chain**: Tier 3 → Tier 2 → Tier 1 (if cloud fails, try capable; if capable fails, try fast)

### Configuration

```env
# Hybrid LLM
USE_HYBRID_LLM=true
LOCAL_FAST_MODEL=qwen2.5:3b         # Tier 1
LOCAL_CAPABLE_MODEL=llama3:8b        # Tier 2
LLM_MODEL=deepseek/deepseek-chat     # Tier 3 (cloud)

# Task-specific routing
USE_LOCAL_VEHICLE_CLASSIFICATION=true
USE_LOCAL_SECTION_MAPPING=true
USE_LOCAL_FOR_SIMPLE_RAG=true
```

**Cost Savings**: ~97% reduction for simple RAG queries, ~70% overall (assuming 70% simple queries).

---

## Docker Services

**6 services** orchestrated by `docker-compose.yml`:

| Service | Port | Purpose |
|---------|------|---------|
| `postgres` | 5432 | PostgreSQL database |
| `redis` | 6379 | Redis (Streams, cache, Pub/Sub) |
| `api` | 8000 | FastAPI backend |
| `agent` | — | LangGraph agent (Streams consumer) |
| `admin-panel` | 3000 | Next.js admin UI |
| `ollama` | 11434 | Ollama LLM server (local models) |

### Useful Commands

```bash
# Start all services
docker-compose up -d

# View logs (specific service)
docker-compose logs -f agent
docker-compose logs -f api

# Restart service
docker-compose restart agent

# Run migrations
docker-compose exec api alembic upgrade head

# Access PostgreSQL
docker-compose exec postgres psql -U msia msia_db

# Access Redis CLI
docker-compose exec redis redis-cli

# Check Ollama models
docker-compose exec ollama ollama list

# View all service status
docker-compose ps
```

---

## Code Conventions

### Python (Agent/API/Workers)

- **Strict type hints** — All functions must have complete type annotations
- **Async/await for I/O** — Database, Redis, HTTP, file operations
- **JSON structured logging** — Use `structlog` with JSON format (never `print()`)
- **Pydantic for validation** — Never use raw dicts for API input/output schemas
- **UUID primary keys** — All models use UUID (not auto-increment integers)
- **Timezone-aware timestamps** — `DateTime(timezone=True)`, use `datetime.now(UTC)`
- **SQLAlchemy async only** — `selectinload()` for relationships (never `lazy="joined"`)
- **Deterministic UUIDs in seeds** — UUID v5 with fixed namespace for idempotency

### TypeScript/React (Admin Panel)

- **Next.js App Router** — File-based routing in `app/`
- **Client Components predominant** — 25/28 pages are Client Components (not Server Components)
- **Client-side data fetching** — `useEffect` + API client singleton (NO Server Actions for mutations)
- **Radix UI + Tailwind** — Use existing components from `components/ui/`
- **Dialog-based CRUD** — `<Dialog>` for create/edit forms (not full-page forms)
- **AlertDialog for destructive actions** — Delete confirmations
- **Sonner toast for feedback** — Success/error notifications
- **useCallback wrapping** — Event handlers to prevent re-renders
- **Debounced search** — 300ms debounce for search inputs
- **API client pattern** — Singleton with JWT auth, error handling, type-safe endpoints

### Database

- **Dual warning system** — Element warnings exist in BOTH inline (`warnings.element_id`) AND association (`element_warning_associations`)
- **JSONB for flexible data** — Use JSONB (not TEXT with JSON strings) with default values
- **Soft delete** — `is_active=False` (never hard delete seed data)
- **Migration rollback** — ALWAYS implement `downgrade()` (never leave as `pass`)
- **Foreign key policies** — ALWAYS specify `ondelete="CASCADE"` or `"SET NULL"`

### Security

- **JWT authentication** — HttpOnly cookie + Bearer token dual auth
- **RBAC** — Role-based access control with `require_role` dependency
- **SSRF prevention** — Validate Chatwoot image URLs before download
- **Image security** — Multi-layer validation (magic numbers, PIL, decompression bombs)
- **Path traversal prevention** — Sanitize filenames, validate paths
- **Rate limiting** — In-memory sliding window rate limiter
- **Redis JWT blacklist** — Track invalidated tokens

---

## Environment Variables

**46+ variables** organized by category. See `.env.example` for complete template.

### Project

| Variable | Default | Description |
|----------|---------|-------------|
| `PROJECT_NAME` | `MSI-a` | Project name for logging |
| `AGENT_NAME` | `MSI Agent` | Agent display name |
| `ENVIRONMENT` | `development` | Environment (development/production) |
| `TIMEZONE` | `Europe/Madrid` | Timezone for timestamps |
| `LOG_LEVEL` | `INFO` | Logging level |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async PostgreSQL connection string |
| `POSTGRES_USER` | `msia` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `msia_password` | PostgreSQL password |
| `POSTGRES_DB` | `msia_db` | PostgreSQL database name |

### Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string |
| `REDIS_PASSWORD` | — | Redis password (optional) |
| `USE_REDIS_STREAMS` | `true` | Enable Redis Streams (recommended) |

### Chatwoot

| Variable | Default | Description |
|----------|---------|-------------|
| `CHATWOOT_API_URL` | — | Chatwoot API base URL |
| `CHATWOOT_API_TOKEN` | — | Chatwoot API token (Platform app) |
| `CHATWOOT_ACCOUNT_ID` | — | Chatwoot account ID |
| `CHATWOOT_INBOX_ID` | — | WhatsApp inbox ID |
| `CHATWOOT_TEAM_GROUP_ID` | — | Team/group ID for assignment |
| `CHATWOOT_WEBHOOK_TOKEN` | — | Webhook verification token |
| `CHATWOOT_STORAGE_DOMAIN` | — | Chatwoot storage domain for images |

### LLM (Cloud)

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | — | OpenRouter API key |
| `LLM_MODEL` | `deepseek/deepseek-chat` | Cloud model (Tier 3) |
| `SITE_URL` | — | Site URL for OpenRouter analytics |
| `SITE_NAME` | `MSI-a` | Site name for OpenRouter analytics |

### Hybrid LLM (Local)

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_HYBRID_LLM` | `true` | Enable hybrid LLM routing |
| `LOCAL_FAST_MODEL` | `qwen2.5:3b` | Tier 1: Fast model (Ollama) |
| `LOCAL_CAPABLE_MODEL` | `llama3:8b` | Tier 2: Capable model (Ollama) |
| `USE_LOCAL_VEHICLE_CLASSIFICATION` | `true` | Use local for vehicle classification |
| `VEHICLE_CLASSIFICATION_MODEL` | `qwen2.5:3b` | Model for vehicle classification |
| `USE_LOCAL_SECTION_MAPPING` | `true` | Use local for section mapping extraction |
| `SECTION_MAPPING_MODEL` | `qwen2.5:3b` | Model for section mapping |

### Admin Auth

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_USERNAME` | `admin` | Default admin username |
| `ADMIN_PASSWORD_HASH` | — | Bcrypt password hash |
| `ADMIN_JWT_SECRET` | — | JWT signing secret (generate with `openssl rand -hex 32`) |

### Monitoring

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_LLM_METRICS` | `true` | Track LLM usage metrics |
| `LLM_METRICS_RETENTION_DAYS` | `90` | LLM metrics retention (days) |
| `TOKEN_PRICE_INPUT` | `0.00027` | Input token price (USD per 1M tokens) |
| `TOKEN_PRICE_OUTPUT` | `0.00109` | Output token price (USD per 1M tokens) |

### Other

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | `http://localhost:3000` | CORS allowed origins (comma-separated) |
| `DOCKER_HOST` | `unix:///var/run/docker.sock` | Docker host for admin panel |
| `MESSAGE_BATCH_WINDOW_SECONDS` | `0` | Message batching window (0 = disabled) |

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

## Critical Rules (Always Remember)

These rules apply across ALL components. **Re-read this section when uncertain.**

### General

1. **Spanish for users, English for code** — All user-facing text in Spanish, code/docs in English
2. **Don't execute services** — Dev happens locally, services run on remote machine. Don't run docker/npm/python unless asked
3. **Auto-invoke skills** — Load the relevant skill BEFORE starting work on any component (see Auto-invoke table below)
4. **Check ADRs first** — Read `docs/decisions/` before proposing architecture changes
5. **Use Pydantic Settings** — NEVER use `os.getenv()` directly. Always use `get_settings()` from `shared/config.py`
6. **Coding standards** — Reference `docs/coding-standards/` for consolidated patterns (9 files)

### Python (Agent/API/Workers)

7. **Async everywhere** — Use `async def` for all I/O operations (DB, Redis, HTTP, file operations)
8. **Type hints required** — All functions must have complete type annotations
9. **Pydantic for validation** — Never use raw dicts for API input/output schemas
10. **JSON structured logging** — Use `structlog` with JSON format, never `print()`
11. **Redis Streams** — Use `get_redis_client()` and helper functions from `shared/redis_client.py`

### Agent-Specific (CRITICAL)

12. **Price before images** — NEVER send example images without stating the price first (business rule)
13. **Never re-identify** — Use `seleccionar_variante_por_respuesta()` for variant answers, not `identificar_y_resolver_elementos()`
14. **Skip validation after ID** — Always use `skip_validation=True` in `calcular_tarifa_con_elementos()` after identification
15. **Mode transitions via tool `_state_update`** — Tools return `{"_state_update": {"_transition_to": "NEW_MODE"}}`. The conditional edge in `conversation_graph.py` routes. No direct state mutation.
16. **Hybrid LLM routing** — Use `LLMRouter` from `shared/llm_router.py`, specify `TaskType` appropriately
17. **Tool-driven state** — Tools declare state changes via `_state_update` (canonical, ADR-005), merged by `post_tool_node`. NOT via pattern matching or direct state mutation.

### Database

18. **UUID primary keys** — All models use UUID (not auto-increment integers)
19. **Dual warning system** — Element warnings MUST exist in BOTH inline (`warnings.element_id`) AND association (`element_warning_associations`)
20. **Deterministic UUIDs in seeds** — Use UUID v5 with fixed namespace from `seed_utils.py`
21. **Soft delete** — Use `is_active=False`, never hard delete seed data
22. **Always implement downgrade** — Migration `downgrade()` must never be `pass`
23. **selectinload for async** — ALWAYS use `lazy="selectin"` for relationships (never `lazy="joined"`)

### Frontend (Admin Panel)

24. **Client Components predominant** — 25/28 pages are Client Components (NOT Server Components by default)
25. **API client for mutations** — Use API client singleton, NO Server Actions for mutations
26. **Radix + Tailwind patterns** — Use existing components from `components/ui/`, don't reinvent
27. **Dialog-based CRUD** — Use `<Dialog>` for create/edit forms (not full-page forms)
28. **AlertDialog for destructive** — Use `<AlertDialog>` for delete confirmations
29. **Sonner toast for feedback** — Use Sonner for success/error notifications

### Security

30. **JWT + RBAC** — Use `require_role` dependency for protected endpoints
31. **SSRF prevention** — Validate URLs before download (use `image_security.validate_url()`)
32. **Image security** — Multi-layer validation with `validate_image_full()`
33. **Path traversal prevention** — Sanitize filenames with `sanitize_filename()`
34. **Rate limiting** — Apply rate limiter to public endpoints (in-memory sliding window)

---

## Development Notes

- MSI-a agent answers queries about vehicle homologations using a **mode-based conversation architecture**
- Agent uses **intent routing** and **digression detection** to route between modes
- **Modes**: `PRE_EXPEDIENTE_MODE` (~90%, with 3 internal phases: DISCOVERY / PRICING / POST_PRICE), `EXPEDIENTE_MODE` (compiled subgraph with 6 sub-modes), and `ESCALATION` (terminal)
- Prices are fixed by homologation type (no assignable resources)
- Escalate to human when case is complex or customer requests it
- Check `docs/decisions/` for Architecture Decision Records (ADRs) before proposing changes

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
| Creating/modifying mode nodes | `msia-agent` |
| General MSI-a development questions | `msia` |
| Regenerate AGENTS.md Auto-invoke tables | `skill-sync` |
| Troubleshoot missing skill in auto-invoke | `skill-sync` |
| TypeScript/React patterns | `typescript-frontend-patterns` |
| Working on LangGraph graphs/nodes | `langgraph` |
| Working on admin panel components | `msia-admin` |
| Working on agent conversation flow | `msia-agent` |
| Working on mode-based architecture | `msia-agent` |
| Working on system prompts | `msia-agent` |
| Editing agent system prompts | `msia-prompts` |
| Modifying files in agent/prompts/ | `msia-prompts` |
| Adding rules to prompt modules | `msia-prompts` |
| Working with Chatwoot webhooks | `msia-api` |
| Working with ConversationState | `msia-agent` |
| Working with Next.js App Router | `nextjs-16` |
| Working with Pydantic models | `msia-api` |
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
| `/test` | Run tests (backend/frontend, auto-detect) | test-runner |
| `/code-review` | Review code for quality and security | code-reviewer |
| `/security-review` | Security audit (OWASP + LLM) | security-reviewer |
| `/architecture` | Architectural guidance and ADRs | architect |
| `/build-fix` | Diagnose and fix build/type errors | build-error-resolver |
| `/doc-update` | Sync documentation with code changes | doc-updater |
| `/refactor-clean` | Find and remove dead code | refactor-cleaner |

### Claude Code Skills (.claude/skills/)

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
3. **Test Continuously**: Use `/test` after implementing features
4. **Review Before Commit**: Use `/code-review` and `/security-review`
5. **Fix Errors Fast**: Use `/build-fix` when builds fail
6. **Keep Docs Updated**: Use `/doc-update` after API changes

### Context Optimization

For long sessions:
- Delegate to specialized agents (reduces main context)
- Compact frequently after completing tasks
- Use `.session-context.md` to track state
- Load skills on-demand, not all at once

See `.opencode/skills/context-optimization/SKILL.md` for detailed strategies.

---

**Última actualización**: Febrero 2026  
**Versión**: 2.0 (Mode-based architecture + OpenCode multi-agent)
