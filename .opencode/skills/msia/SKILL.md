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
| Agent | Python 3.11+, LangGraph, Ollama (hybrid LLM), OpenRouter | `agent/` |
| API | FastAPI, Pydantic, SQLAlchemy | `api/` |
| Admin Panel | Next.js 16, React 19, Radix UI, Tailwind | `admin-panel/` |
| Database | PostgreSQL, SQLAlchemy, Alembic | `database/` |
| Shared | LLM router, Redis, Chatwoot client, image security, settings cache | `shared/` |

## Architecture Flow

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

## Key Data Flow

1. **Message Reception**: Chatwoot webhook → `api/routes/chatwoot.py`
2. **Queue**: Redis Streams for reliable async processing
3. **Processing**: Agent reads from stream, processes with LangGraph
4. **Response**: Agent sends via Chatwoot API → WhatsApp

## Hybrid LLM Architecture

**3-tier system** for cost optimization:

| Tier | Model | Purpose | Cost |
|------|-------|---------|------|
| Tier 1 (Fast) | Ollama: `qwen2.5:3b` | Classification, extraction, fallback | $0 |
| Tier 2 (Capable) | Ollama: `llama3:8b` | Simple RAG, vehicle classification | $0 |
| Tier 3 (Cloud) | OpenRouter: `deepseek/deepseek-chat` | Conversation, complex RAG | ~$0.27/1M tokens |

**Routing**: TaskType → Tier with automatic fallback chain

**Implementation**: `shared/llm_router.py`

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

# Check Ollama models
docker-compose exec ollama ollama list

# Run seeds
docker-compose exec api python -m database.seeds.run_all_seeds

# Run tests
docker-compose exec api pytest tests/
```

## Environment Variables

### Core Configuration

| Category | Key Variables |
|----------|---------------|
| **Database** | `DATABASE_URL`, `POSTGRES_*` |
| **Redis** | `REDIS_URL`, `USE_REDIS_STREAMS` |
| **Chatwoot** | `CHATWOOT_API_URL/TOKEN/ACCOUNT_ID/INBOX_ID` |
| **LLM (Cloud)** | `OPENROUTER_API_KEY`, `LLM_MODEL` (default: `deepseek/deepseek-chat`) |
| **Hybrid LLM** | `USE_HYBRID_LLM`, `LOCAL_FAST_MODEL`, `LOCAL_CAPABLE_MODEL`, `USE_LOCAL_FOR_SIMPLE_RAG` |
| **RAG System** | `QDRANT_URL`, `OLLAMA_BASE_URL`, `EMBEDDING_MODEL`, `BGE_RERANKER_MODEL` |
| **Admin Auth** | `ADMIN_JWT_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH` |

See `.env.example` for complete list (~46 variables).

## Related Skills

| Skill | When to Use |
|-------|-------------|
| `msia-agent` | Working on conversation flow, nodes, tools |
| `msia-api` | Creating routes, services, webhooks |
| `msia-admin` | Working on admin panel UI |
| `msia-database` | Database models, migrations |
| `msia-tariffs` | Tariff system, elements, tiers |
| `msia-rag` | RAG pipeline, embeddings, document processing |
| `msia-test` | Writing tests |

## Critical Rules

- ALWAYS maintain consistency between backend and frontend
- ALWAYS use Spanish for user-facing content, English for code/docs
- NEVER start services (docker, npm, etc.) unless explicitly requested
- Development happens locally, execution on separate machine
- **Security**: Multi-layer protection (JWT + RBAC, SSRF prevention, image validation, prompt injection defense, rate limiting)
- **Database**: Dual warning system (inline + association), UUID primary keys, deterministic seeds
- **Frontend**: Client Components predominant (25/28 pages), NO Server Actions (use API client)
- **Async**: All I/O operations use async/await
- **Hybrid LLM**: Use `LLMRouter` from `shared/llm_router.py` with appropriate `TaskType`

## Resources

- [AGENTS.md](../../AGENTS.md) - Main repository guidelines
- Component AGENTS.md: [agent/](../../agent/AGENTS.md), [api/](../../api/AGENTS.md), [database/](../../database/AGENTS.md), [admin-panel/](../../admin-panel/AGENTS.md)
