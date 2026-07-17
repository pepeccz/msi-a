# MSI-a: WhatsApp Customer Support & Automated Quoting Agent

Production WhatsApp customer-service system built for a vehicle-homologation company in Spain. The agent handles the full pre-sales conversation — discovering what the customer needs, identifying homologation elements, and generating a priced quote automatically — then walks confirmed customers through structured case-file data collection, escalating to a human only when needed.

Built with **LangGraph**, **FastAPI**, **Next.js 16** and **PostgreSQL**.

---

## Highlights

- **Automated quoting engine** — element identification (NLP + fuzzy matching + variant resolution) feeds a tariff system of categories, tiers and inclusions; the agent quotes in-conversation without human intervention
- **Hybrid local/cloud LLM routing** — classification and extraction run on local models (Ollama) at zero marginal cost; only complex reasoning goes to the cloud, with automatic fallback. Significant LLM cost reduction versus cloud-only
- **Mode-based conversation architecture** — no brittle FSM: intent routing, digression detection, and tool-driven state transitions (`_state_update` canonical channel, documented in ADRs)
- **Anti-hallucination constraint validation** — responses are checked against business constraints before sending (local-only, never cloud)
- **235 Python test files**, structured JSON logging with PII masking, CI-friendly Docker Compose stack

---

## Architecture

### Services (Docker Compose)

| Service | Port | Purpose |
|---------|------|---------|
| **postgres** | 5432 | PostgreSQL 15 |
| **redis** | 6379 | Redis Stack (Streams, cache, checkpoints) |
| **api** | 8000 | FastAPI backend |
| **agent** | — | LangGraph conversational agent |
| **admin-panel** | 8001 | Next.js 16 admin panel |
| **ollama** | 11434 | Local LLM server |

**External integration**: Chatwoot (WhatsApp messaging)

### Conversational Agent (Mode-Based)

```
WhatsApp → Chatwoot → API Webhook → Redis Streams → Agent
                                                       ↓
                                             Intent Router
                                   (Keyword + LLM classification)
                                                       ↓
                                ┌──────────────────────┴──────────────────────┐
                                ↓                                             ↓
                      PRE_EXPEDIENTE_MODE                          EXPEDIENTE_MODE (subgraph)
                      (~90% of traffic)                            (6 sub-modes:
                      3 dynamic phases:                             element data →
                       - DISCOVERY                                   base docs →
                       - PRICING                                     personal →
                       - POST_PRICE                                  vehicle →
                                                                     workshop →
                                                                     review)
                                ↓                                             ↓
                          quote confirmation ────────────────────────────────┘
                                                                              ↓
                                                                    Escalation → Human
```

- Mode-based architecture with a compiled subgraph for case-file collection
- Intent routing + digression detection (off-topic handling inside focused modes)
- LangGraph `StateGraph` + custom `tool_node` (deduplication, persistent logging, `_state_update` extraction)
- Tool-driven state management — tools declare state changes; the graph routes (ADR-005)
- Orphaned-case recovery (Redis checkpoint expiry → PostgreSQL fallback)

### Hybrid LLM System

| Tier | Model | Used for | Cost |
|------|-------|----------|------|
| **Tier 1 (Local)** | Ollama: `gemma4:e4b` | Classification, extraction, simple tasks | $0 |
| **Tier 2 (Cloud)** | OpenRouter: `deepseek/deepseek-chat` | Conversation, complex reasoning, tool calling | ~$0.14/1M input |

Routing by `TaskType` in `shared/llm_router.py`, with cloud→local fallback. Constraint validation is pinned to local models by design (customer data never leaves the box for that step).

---

## Project Structure

```
msi-a/
├── shared/              # Shared modules (config, Redis, Chatwoot, LLM router, image security)
├── database/            # SQLAlchemy models + Alembic migrations + seeds
├── api/                 # FastAPI backend (13 route modules)
│   ├── routes/          # API endpoints
│   ├── services/        # Billing, Stripe, PDF generation, image security
│   └── workers/         # Background workers
├── agent/               # LangGraph agent
│   ├── graph/           # StateGraph + expediente subgraph
│   ├── router/          # Intent router, digression detection, mode transitions
│   ├── modes/           # Mode nodes + custom tool-loop subgraph
│   ├── prompts/         # Dynamic prompt assembly (core + per-mode, XML-tagged)
│   ├── tools/           # LangChain tools with Pydantic args_schema
│   ├── services/        # Business logic (tariffs, elements, escalation, constraints)
│   └── state/           # Conversation state + Redis checkpointer
├── admin-panel/         # Next.js 16 + React 19 + Radix UI + Tailwind
├── tests/               # Test suite (235 Python test files)
├── docs/                # ADRs, coding standards, architecture docs
└── docker-compose.yml   # Service orchestration
```

---

## Quick Start

### Requirements

- Docker and Docker Compose
- A configured Chatwoot account
- An OpenRouter API key

### Setup

1. **Clone and configure**:

```bash
git clone <repo-url>
cd msi-a
cp .env.example .env
# Edit .env with your credentials (see .env.example for all variables)
```

2. **Critical variables in `.env`**:

```env
OPENROUTER_API_KEY=your_api_key
LLM_MODEL=deepseek/deepseek-chat
CHATWOOT_API_URL=https://app.chatwoot.com
CHATWOOT_API_TOKEN=your_token
CHATWOOT_ACCOUNT_ID=your_account_id
CHATWOOT_INBOX_ID=your_inbox_id
CHATWOOT_WEBHOOK_TOKEN=secret_token
ADMIN_JWT_SECRET=jwt_secret  # openssl rand -hex 32
```

3. **Start services**:

```bash
docker compose up -d
docker compose exec api alembic upgrade head  # Migrations
docker compose logs -f agent api              # Verify
```

---

## Testing

```bash
# Backend
pytest tests/ -v --cov --cov-report=html

# Single test module
pytest tests/test_element_service.py -v

# Frontend
cd admin-panel && npm test
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| `CLAUDE.md` | Guide for AI coding agents |
| `docs/coding-standards/` | Coding standards (9 files) |
| `docs/decisions/` | Architecture Decision Records (ADRs) |
| `skills/` | Contextual AI agent skills |

---

## Security

- JWT authentication (HttpOnly cookies) + RBAC
- SSRF prevention (URL validation before any download)
- Multi-layer image security (magic numbers, PIL verification, decompression-bomb detection)
- Path-traversal prevention
- Rate limiting (in-memory sliding window)
- Sanitized logging (phone numbers masked)

---

**Proprietary client project — all rights reserved. Published as a portfolio reference; not licensed for reuse.**
