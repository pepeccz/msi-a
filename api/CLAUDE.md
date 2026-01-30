# API Component Guidelines

This directory contains the MSI-a FastAPI backend.

> For detailed patterns, invoke the skills: [msia-api](../skills/msia-api/SKILL.md), [msia-rag](../skills/msia-rag/SKILL.md)

## Directory Structure

```
api/
├── main.py                    # FastAPI app, router registration, startup/shutdown
├── routes/
│   ├── chatwoot.py            # Webhook endpoint (Redis Streams, idempotency)
│   ├── admin.py               # Admin panel API (JWT auth, RBAC, 26 endpoints)
│   ├── tariffs.py             # Tariff management (31 endpoints, audit log)
│   ├── elements.py            # Element CRUD (24 endpoints, hierarchy)
│   ├── images.py              # Image upload/serve (4 endpoints, rate limiting)
│   ├── cases.py               # Case management (12 endpoints, ZIP download)
│   ├── system.py              # System management (11 endpoints, Docker API, SSE logs)
│   ├── rag_query.py           # RAG queries (6 endpoints, full pipeline)
│   ├── regulatory_documents.py # Document upload/management (9 endpoints)
│   ├── public_tariffs.py      # Public tariff endpoints (6 endpoints, no auth)
│   ├── token_usage.py         # Token usage tracking (3 endpoints)
│   ├── conversation_messages.py # Conversation messages (2 endpoints)
│   ├── llm_metrics.py         # LLM metrics (4 endpoints, hybrid monitoring)
│   ├── tool_logs.py           # Tool call logs (4 endpoints, debugging)
│   └── constraints.py         # Response constraints (4 endpoints, anti-hallucination)
├── services/
│   ├── image_service.py       # Image processing (security validation)
│   ├── chatwoot_image_service.py # Chatwoot image handling (SSRF prevention)
│   ├── rag_service.py         # RAG orchestrator (hybrid LLM routing)
│   ├── embedding_service.py   # Ollama embeddings (Redis cache)
│   ├── qdrant_service.py      # Vector storage (retry logic)
│   ├── reranker_service.py    # BGE reranking (sentence_transformers)
│   ├── document_processor.py  # PDF extraction (Docling + PyMuPDF fallback)
│   ├── query_classifier.py    # Query complexity classification
│   ├── message_persistence_service.py # Message persistence (fire-and-forget)
│   └── log_monitor.py         # Error monitoring (Docker logs)
├── models/
│   ├── chatwoot_webhook.py    # Webhook schemas (E.164 phone validation)
│   ├── tariff_schemas.py      # Tariff models (51 Pydantic classes)
│   ├── element.py             # Element schemas (hierarchy, required fields)
│   ├── admin_user.py          # Admin user schemas (JWT, RBAC)
│   └── token_usage.py         # Token usage schemas (cost calculation)
├── middleware/
│   └── rate_limit.py          # In-memory rate limiting (sliding window)
├── workers/
│   └── document_processor_worker.py # Document processing (Redis Streams, crash recovery)
└── utils/
    └── (placeholder for shared utilities)
```

---

## Router Architecture

**Total**: 17 routers, ~147 endpoints

| Router                      | Prefix                             | Auth       | Endpoints | Purpose                                  |
| --------------------------- | ---------------------------------- | ---------- | --------- | ---------------------------------------- |
| `chatwoot.router`             | `/webhook`                           | Token (URL) | 1         | Chatwoot webhook processing              |
| `admin.router`                | `/api/admin`                         | JWT + RBAC  | 26        | Admin panel backend                      |
| `tariffs.router`              | `/api/admin`                         | JWT        | 31        | Tariff management (full CRUD)            |
| `public_tariffs.router`       | `/api/tariffs`                       | None       | 6         | Public tariff API for agent              |
| `system.router`               | `/api/admin/system`                  | JWT        | 11        | Docker service management, SSE logs      |
| `images.router`               | `/api/admin`                         | JWT        | 4         | Image upload/management (admin)          |
| `images.get_public_image_router()` | `/images`                            | None       | 1         | Public image serving                     |
| `images.get_case_images_router()`  | `/case-images`                       | None       | 1         | Case image serving                       |
| `regulatory_documents.router` | `/api/admin/regulatory-documents`    | JWT        | 9         | RAG document upload/management           |
| `rag_query.router`            | `/api/admin/rag`                     | JWT        | 6         | RAG queries, analytics, health           |
| `elements.router`             | `/api/admin`                         | JWT        | 24        | Element CRUD, images, warnings, fields   |
| `cases.router`                | `/api/admin/cases`                   | JWT        | 12        | Case management, image download/ZIP      |
| `token_usage.router`          | `/api/token-usage`                   | JWT (admin) | 3         | Token usage tracking                     |
| `conversation_messages.router`| `/api/admin/conversations`           | JWT        | 2         | Message-level conversation access        |
| `constraints.router`          | `/api/admin/response-constraints`    | JWT        | 4         | Anti-hallucination constraint management |
| `tool_logs.router`            | `/api/admin/tool-logs`               | JWT        | 4         | Agent tool call debugging logs           |
| `llm_metrics.router`          | `/llm-metrics`                       | None       | 4         | Hybrid LLM architecture monitoring       |

---

## Routes by Module (Summary)

### Key Modules

| Module | Endpoints | Key Features |
|--------|-----------|--------------|
| **chatwoot.py** | 1 | Token auth, Redis idempotency (SETNX 5min), auto-creates users, Chatwoot sync, panic button, attachments |
| **admin.py** | 26 | JWT auth (HttpOnly cookie + Bearer), RBAC (`require_role`), dashboard KPIs, user CRUD, conversation cascade delete (DB + Redis), settings, admin users, access logs, escalations + Chatwoot integration |
| **tariffs.py** | 31 | Categories, tiers, prompt sections (versioning), base docs, warnings, additional services, audit log, Redis cache invalidation |
| **elements.py** | 24 | Hierarchy (parent/children/variants), images, tier inclusions (XOR), warnings, required fields (conditional, circular ref prevention), soft delete |
| **images.py** | 4+2 | Upload with rate limiting (10/min), security validation (magic numbers + PIL), SSRF prevention, path traversal prevention, public routers |
| **cases.py** | 12 | Stats, CRUD, Chatwoot integration (disable/reactivate bot), image download/ZIP, image validation, element data tracking |
| **system.py** | 11 | Docker API (Unix socket/TCP), service status (8 containers), SSE log streaming (query param token), restart/stop (self-protection), cache clear, error logs + stats |
| **rag_query.py** | 6 | Full RAG pipeline, query caching (Redis), performance metrics, citation tracking, component health (Ollama, Qdrant, reranker) |
| **regulatory_documents.py** | 9 | PDF upload, SHA256 dedup, Redis Streams queue, Qdrant sync, 3-layer deletion (Qdrant→file→DB), reprocessing |
| **public_tariffs.py** | 6 | No auth, Redis cache (5min), classification rules matching, client type in slug, global + category services |
| **token_usage.py** | 3 | Last 12 months, current month EUR costs, pricing config (admin only) |
| **conversation_messages.py** ⭐ | 2 | Message history, stats (counts, timestamps), image tracking, Chatwoot ID cross-ref |
| **llm_metrics.py** ⭐ | 4 | Hybrid LLM monitoring (local vs cloud), cost savings, fallback tracking, hourly breakdown, health, config, **NO AUTH** |
| **tool_logs.py** ⭐ | 4 | Tool call logging (name, params, result type, execution time), per-tool stats, conversation history |
| **constraints.py** ⭐ | 4 | Anti-hallucination rules (regex + required tool + error injection), priority-based, category-scoped, agent cache invalidation |

---

## Services (Organized by Functionality)

### Image Services

| Service | Purpose | Key Features |
|---------|---------|--------------|
| `image_service.py` | Admin panel uploads | Magic numbers + PIL validation, save to disk + DB metadata, paginated listing |
| `chatwoot_image_service.py` | Chatwoot downloads | SSRF prevention (allowed domains), manual redirect following, 3 retry attempts (exponential backoff), concurrent batch download |

### RAG Services

| Service | Purpose | Key Features |
|---------|---------|--------------|
| `rag_service.py` | RAG orchestrator | **Full pipeline**: query expansion → hybrid search (vector + keyword) → RRF merge → keyword boosting → BGE rerank → **hybrid LLM routing** → citations → logging → caching. **Heavy Redis usage** (query cache). |
| `embedding_service.py` | Ollama embeddings | nomic-embed-text model, **Redis cache** (24h TTL, key: `emb:{sha256}`), batch parallel generation, 3 retry attempts |
| `qdrant_service.py` | Vector storage | Collection creation (5 retry attempts), batch upsert (100 chunks), vector search with active filter, delete by document, active status updates, health check |
| `reranker_service.py` | BGE reranking | **sentence_transformers CrossEncoder** (lazy-loaded, not Ollama), graceful fallback (returns original order), health check |
| `query_classifier.py` ⭐ | Query complexity | **SIMPLE vs COMPLEX** classification for hybrid LLM routing. Uses regex patterns, keywords, length heuristics, conjunctions. Returns enum + 0.0-1.0 score. |

### Processing Services

| Service | Purpose | Key Features |
|---------|---------|--------------|
| `document_processor.py` | PDF processing | **Docling** (primary, AI-powered, markdown) + **PyMuPDF** (fallback). Semantic chunking with RecursiveCharacterTextSplitter. Heading hierarchy extraction. **Section mapping extraction with LLM** (hybrid: Ollama primary + OpenRouter fallback). SHA256 hashing. |

### Persistence Services

| Service | Purpose | Key Features |
|---------|---------|--------------|
| `message_persistence_service.py` ⭐ | Message persistence | Fire-and-forget PostgreSQL persistence (`ConversationHistory` + `ConversationMessage`). Tracks images, Chatwoot message IDs. Errors logged but never propagated. |

### Monitoring Services

| Service | Purpose | Key Features |
|---------|---------|--------------|
| `log_monitor.py` | Container error logs | Real-time Docker log streaming (Unix socket), error/critical/fatal extraction (JSON + plain text), stack trace accumulation, PostgreSQL persistence (`ContainerErrorLog`), one task per container, exponential backoff |

---

## RAG Pipeline (Complete)

### Architecture Flow

```
User Query
    ↓
Query Expansion (add technical terms)
    ↓
Hybrid Search (parallel)
    ├─ Vector Search (Qdrant + Ollama embeddings)
    └─ Keyword Search (PostgreSQL ILIKE + hierarchy enrichment)
    ↓
Reciprocal Rank Fusion (RRF merge)
    ↓
Keyword Boosting (domain-specific terms: homologación, reglamento, etc.)
    ↓
BGE Reranking (sentence_transformers CrossEncoder)
    ↓
Context Building (top 5 chunks with section mappings)
    ↓
Query Complexity Classification (SIMPLE vs COMPLEX)
    ├─ SIMPLE → Ollama Local (Tier 2: primary)
    ├─ COMPLEX → OpenRouter Cloud (Tier 3)
    └─ FALLBACK → Ollama Local (Tier 1: fast model)
    ↓
LLM Answer Generation
    ↓
Citation Building (with similarity + rerank scores)
    ↓
Query Logging (PostgreSQL) + Caching (Redis)
    ↓
Response with Citations
```

### Query Complexity Classification

**Simple Queries** (Ollama local):
- Factual questions (¿Qué es...?, ¿Cuál es...?)
- Definition lookups
- Single-answer questions
- Short queries (< 50 chars)
- Low complexity keywords

**Complex Queries** (OpenRouter cloud):
- Multi-question queries
- Analytical questions (analiza, evalúa, explica)
- Comparisons (diferencia, compara, pros/contras)
- Procedural questions (cómo, paso a paso)
- Long context (> 8000 chars)
- High complexity keywords

### Hybrid LLM Routing

| Tier | Model | Purpose | Selection |
|------|-------|---------|-----------|
| **Tier 1** | Ollama (fast fallback) | Fallback for primary failures | Primary fails |
| **Tier 2** | Ollama (primary) | Simple factual queries | `QueryComplexity.SIMPLE` |
| **Tier 3** | OpenRouter (cloud) | Complex analytical queries | `QueryComplexity.COMPLEX` or `force_cloud=True` |

### Caching Strategy

- **Embeddings**: Redis (24h TTL), key: `emb:{sha256}`
- **Query results**: Redis (configurable TTL), key: `rag:query:{sha256}`
- **Cache hit tracking**: `RAGQuery.was_cache_hit`

### Performance Metrics

- `retrieval_ms` - Vector + keyword search
- `rerank_ms` - BGE reranking
- `llm_ms` - LLM generation
- `total_ms` - End-to-end
- `tokens_used` - Token count

---

## Security Architecture

### 1. JWT Authentication

- **Algorithm**: HS256, **Expiry**: 24h, **JTI**: Unique token ID
- **Storage**: HttpOnly cookie + Bearer token (dual auth)
- **Blacklist**: Redis (`jwt_blacklist:{jti}`, TTL: token expiry)

**Flow**:
```
Login → Verify bcrypt → Generate JWT + JTI → Set cookie + return Bearer → Log access
Request → Extract JWT → Check Redis blacklist → Validate → DB lookup → Check active → Attach user
Logout → Add JTI to Redis blacklist → Clear cookie
```

### 2. RBAC (Role-Based Access Control)

- **Roles**: `admin`, `user`
- **Dependency**: `require_role(*roles)`

```python
@router.get("/sensitive", dependencies=[Depends(require_role("admin"))])
async def sensitive_endpoint(): ...
```

### 3. SSRF Prevention

**Chatwoot image downloads**:
- Allowed domains whitelist
- URL validation before download
- Manual redirect following with validation

### 4. Image Security

**Two-layer validation**:
```python
validate_image_full(image_bytes)
# Layer 1: Magic number check (fast)
# Layer 2: PIL full parsing (thorough)
```

Validates magic numbers, no polyglot files, PIL parsing, extracts dimensions.

### 5. Rate Limiting

In-memory sliding window:
```python
limiter.check_rate_limit(key=f"upload:{username}", max_requests=10, window_seconds=60)
```

**Note**: Single-instance. Use Redis for multi-instance production.

### 6. Path Traversal Prevention

```python
safe_filename = os.path.basename(filename)
file_path = (base_dir / safe_filename).resolve()
if not file_path.is_relative_to(base_dir):
    raise ValueError("Path traversal detected")
```

### 7. SQL Injection Prevention

**SQLAlchemy ORM only** (no raw SQL):
```python
select(User).where(User.username == username)  # Safe
```

---

## Workers

### Document Processor Worker

**Purpose**: Async PDF processing via Redis Streams with crash recovery.

**Architecture**:
```
Producer (API) → Redis Stream → Consumer Group → Worker(s) → Qdrant + PostgreSQL
```

**Key Features**:
- Consumer group: `document_workers` (multi-instance support)
- Unique consumer name: `worker-<8-char-hex>`
- Crash recovery: Claims messages idle >30s from dead consumers
- Blocking read: 5s with `count=1`
- Always ACK (even on failure)
- Service wait: Redis + Qdrant (exponential backoff, 10 attempts)

**Processing Pipeline**:
1. PDF Extraction (0%→20%) - Docling primary, PyMuPDF fallback
2. Semantic Chunking (20%→40%) - RecursiveCharacterTextSplitter
3. Section Mapping (40%→50%) - LLM extraction (non-blocking)
4. Embedding Generation (50%→70%) - Batch embeddings
5. Qdrant Indexing (70%→90%) - Batch upsert (100 chunks)
6. DB Persistence (90%→100%) - Save DocumentChunk records

**Error Handling**: Sets status to `"failed"`, stores truncated error (max 1000 chars).

---

## Key Patterns

### Route with Auth

```python
from api.routes.admin import get_current_user, require_role

@router.get("/sensitive")
async def sensitive_endpoint(
    current_user: AdminUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Only authenticated users."""
    ...

@router.delete("/critical", dependencies=[Depends(require_role("admin"))])
async def critical_endpoint(current_user: AdminUser = Depends(get_current_user)):
    """Only admin role."""
    ...
```

### Pydantic with Validators

```python
from pydantic import BaseModel, Field, validator

class TierCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    price: Decimal = Field(..., ge=0)
    
    @validator('code')
    def validate_code_uppercase(cls, v):
        return v.upper()
```

### Image Upload with Security

```python
from shared.image_security import validate_image_full, ImageSecurityError

content = await file.read()
if len(content) > MAX_SIZE:
    raise HTTPException(400, "File too large")

try:
    mime_type, width, height = validate_image_full(content)
except ImageSecurityError as e:
    raise HTTPException(400, f"Invalid image: {e}")
```

### Error Handling

```python
# Not found
raise HTTPException(404, f"Document {doc_id} not found")

# Validation
raise HTTPException(400, "Invalid category slug format")

# Conflict
raise HTTPException(409, "Element code already exists")

# Unauthorized
raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Bearer"})

# Forbidden
raise HTTPException(403, "Admin role required")
```

---

## Critical Rules

- ALWAYS use `async def` for route handlers
- ALWAYS use Pydantic models for request/response validation
- ALWAYS use `Depends(get_session)` for database access
- ALWAYS use `Depends(get_current_user)` for authenticated endpoints
- ALWAYS validate file types and sizes before processing
- ALWAYS use full security validation for image uploads
- ALWAYS log sensitive operations (audit trail)
- ALWAYS return appropriate HTTP status codes
- ALWAYS invalidate caches after mutations
- NEVER put business logic in routes (use services)
- NEVER trust user input (validate everything)
- NEVER use raw SQL (use SQLAlchemy ORM)
- NEVER expose internal error details to users
- NEVER store passwords in plain text (use bcrypt)
- NEVER auto-follow redirects for external URLs (SSRF prevention)

---

## Auto-invoke Skills

When performing these actions, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Creating/modifying API routes | `msia-api` |
| Creating/modifying FastAPI services | `fastapi` |
| Working with Pydantic models | `msia-api` |
| Working with Chatwoot webhooks | `msia-api` |
| Working with RAG system or documents | `msia-rag` |
| Working with tariffs or elements | `msia-tariffs` |
| Writing Alembic migrations | `sqlalchemy-async` |
| Writing Python tests | `pytest-async` |
| Writing tests for MSI-a | `msia-test` |
