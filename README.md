# MSI-a: Sistema de Atención al Cliente WhatsApp

Sistema de atención al cliente vía WhatsApp para **MSI Automotive**, empresa especializada en homologaciones de vehículos en España.

Construido con **LangGraph**, **FastAPI**, **Next.js 16** y **PostgreSQL**.

---

## Arquitectura

### Servicios Docker (6 servicios)

| Servicio | Puerto | Propósito |
|----------|--------|-----------|
| **postgres** | 5432 | PostgreSQL 15 |
| **redis** | 6379 | Redis Stack (Streams, cache, checkpoints) |
| **api** | 8000 | Backend FastAPI |
| **agent** | — | Agente conversacional LangGraph |
| **admin-panel** | 8001 | Panel de administración Next.js 16 |
| **ollama** | 11434 | Servidor LLM local (gemma4:e4b) |

**Integración externa**: Chatwoot (WhatsApp messaging)

---

### Agente Conversacional (Mode-Based)

```
WhatsApp → Chatwoot → API Webhook → Redis Streams → Agent
                                                       ↓
                                             Intent Router
                                   (Keyword + LLM classification)
                                                       ↓
                           ┌───────────────────────────┼────────────────────┐
                           ↓                           ↓                    ↓
                   CONSULTA_MODE              PRESUPUESTO_MODE      EXPEDIENTE_MODE
                (Educational ~10%)         (Pricing + Images ~90%)  (Case collection)
                                                                           ↓
                                                                  Escalation → Human
```

- Mode-based architecture (no FSM)
- Intent routing + digression detection
- Fallback & retry patterns
- Tool-driven state management (ADR-005)
- Orphaned case recovery (Redis checkpoint expiry → PostgreSQL fallback)

---

### Sistema LLM Híbrido (2-Tier)

| Tier | Modelo | Uso | Costo |
|------|--------|-----|-------|
| **Tier 1 (Local)** | Ollama: `gemma4:e4b` | Clasificación, extracción, tareas simples | $0 |
| **Tier 2 (Cloud)** | OpenRouter: `deepseek/deepseek-chat` | Conversación, razonamiento complejo | ~$0.14/1M input |

Routing por `TaskType` en `shared/llm_router.py`. Fallback: Cloud → Local.

---

## Estructura del Proyecto

```
msi-a/
├── shared/              # Módulos compartidos (config, Redis, Chatwoot, LLM router)
├── database/            # SQLAlchemy models + Alembic migrations
├── api/                 # FastAPI backend (13 route modules)
│   ├── routes/          # API endpoints
│   ├── services/        # RAG, embeddings, document processor
│   └── workers/         # Background workers
├── agent/               # Agente LangGraph
│   ├── graph/           # StateGraph definition
│   ├── router/          # Intent router, digression, transitions
│   ├── modes/           # CONSULTA, PRESUPUESTO, EXPEDIENTE + sub-modes
│   ├── prompts/         # Dynamic prompts (core + mode-specific)
│   ├── tools/           # LangChain tools
│   ├── services/        # Business logic (tarifas, elementos)
│   └── state/           # Conversation state + checkpointer
├── admin-panel/         # Next.js 16 + React 19 + Radix UI + Tailwind
├── tests/               # Test suite (101 test files)
├── docs/                # Documentación, ADRs, coding standards
├── skills/              # AI agent skills (17 skills)
└── docker-compose.yml   # Orquestación de servicios
```

---

## Inicio Rápido

### Requisitos

- Docker y Docker Compose
- Cuenta de Chatwoot configurada
- API Key de OpenRouter

### Configuración

1. **Clonar y configurar**:

```bash
git clone <repo-url>
cd msi-a
cp .env.example .env
# Editar .env con credenciales (ver .env.example para todas las variables)
```

2. **Variables críticas en `.env`**:

```env
OPENROUTER_API_KEY=tu_api_key
LLM_MODEL=deepseek/deepseek-chat
CHATWOOT_API_URL=https://app.chatwoot.com
CHATWOOT_API_TOKEN=tu_token
CHATWOOT_ACCOUNT_ID=tu_account_id
CHATWOOT_INBOX_ID=tu_inbox_id
CHATWOOT_WEBHOOK_TOKEN=token_secreto
ADMIN_JWT_SECRET=secreto_jwt  # openssl rand -hex 32
```

3. **Iniciar servicios**:

```bash
docker compose up -d
docker compose exec api alembic upgrade head  # Migraciones
docker compose logs -f agent api              # Verificar
```

---

## Deployment (Producción)

```bash
# Conectar al servidor
ssh autohomologacion@autohomologacion-server
cd msi-a

# Gestión de servicios
docker compose up -d
docker compose down
docker compose restart <servicio>
docker compose ps
docker compose logs -f <servicio>

# Operaciones comunes
docker compose exec api alembic upgrade head
docker compose exec postgres psql -U msia msia_db
docker compose exec redis redis-cli
docker compose exec ollama ollama list
```

---

## URLs de Acceso

| Servicio | URL |
|----------|-----|
| API REST (docs) | http://localhost:8000/docs |
| Admin Panel | http://localhost:8001 |
| Ollama API | http://localhost:11434 |

---

## Testing

```bash
# Backend
pytest tests/ -v --cov --cov-report=html

# Test específico
pytest tests/test_element_service.py -v

# Frontend
cd admin-panel && npm test
```

---

## Documentación

| Documento | Propósito |
|-----------|-----------|
| `CLAUDE.md` | Guía para AI agents (Claude Code) |
| `docs/coding-standards/` | Estándares de código (9 archivos) |
| `docs/decisions/` | Architecture Decision Records (ADRs) |
| `skills/` | AI agent skills (17 skills contextuales) |

---

## Seguridad

- JWT authentication (HttpOnly cookies) + RBAC
- SSRF prevention (URL validation)
- Image security (multi-layer: magic numbers, PIL, decompression bombs)
- Path traversal prevention
- Rate limiting (in-memory sliding window)
- Sanitized logging (phone numbers masked)

---

**Proyecto propietario de MSI Automotive. Todos los derechos reservados.**

**Última actualización**: Abril 2026
