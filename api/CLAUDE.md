# API Component Guidelines

This directory contains the MSI-a FastAPI backend.

> For detailed patterns, invoke the skills: [msia-api](../skills/msia-api/SKILL.md)

## Directory Structure

```
api/
├── main.py                         # FastAPI app, router registration, startup/shutdown
├── routes/
│   ├── chatwoot.py                 # Webhook endpoint (Redis Streams, idempotency)
│   ├── admin.py                    # Admin panel API (JWT auth, RBAC, 26 endpoints)
│   ├── tariffs.py                  # Tariff management (31 endpoints, audit log)
│   ├── elements.py                 # Element CRUD (24 endpoints, hierarchy)
│   ├── images.py                   # Image upload/serve (4 endpoints, rate limiting)
│   ├── cases.py                    # Case management (12 endpoints, ZIP download)
│   ├── system.py                   # System management (11 endpoints, Docker API, SSE logs)
│   ├── public_tariffs.py           # Public tariff endpoints (6 endpoints, no auth)
│   ├── token_usage.py              # Token usage tracking (3 endpoints)
│   ├── conversation_messages.py    # Conversation messages (2 endpoints)
│   ├── validation_metrics.py       # Validation metrics (agent output quality)
│   └── billing.py                  # Billing management (invoices, Stripe)
├── services/
│   ├── image_service.py            # Image processing (security validation)
│   ├── chatwoot_image_service.py   # Chatwoot image handling (SSRF prevention)
│   ├── message_persistence_service.py  # Message persistence (fire-and-forget)
│   ├── cache_service.py            # Redis cache helpers
│   ├── conversation_reset_coordinator.py   # Conversation reset orchestration
│   ├── conversation_reset_chatwoot_executor.py
│   ├── conversation_reset_db_executor.py
│   ├── conversation_reset_files_executor.py
│   ├── conversation_reset_redis_executor.py
│   ├── garbage_collection_service.py   # GC for stale data
│   ├── pdf_service.py              # PDF generation (invoices)
│   ├── stripe_service.py           # Stripe payment integration
│   └── billing_service.py          # Billing business logic
├── models/
│   ├── chatwoot_webhook.py         # Webhook schemas (E.164 phone validation)
│   ├── tariff_schemas.py           # Tariff models (51 Pydantic classes)
│   ├── element.py                  # Element schemas (hierarchy, required fields)
│   ├── admin_user.py               # Admin user schemas (JWT, RBAC)
│   ├── token_usage.py              # Token usage schemas (cost calculation)
│   ├── billing.py                  # Billing/invoice schemas
│   └── conversation_reset.py       # Conversation reset schemas
├── middleware/
│   └── rate_limit.py               # In-memory rate limiting (sliding window)
├── workers/
│   └── billing_worker.py           # Monthly invoice + overdue check (asyncio tasks)
└── utils/
    └── pagination.py               # Pagination helpers
```

---

## Router Architecture

**Total**: 12 routers registered in `main.py`

| Router                           | Prefix                        | Auth        | Endpoints | Purpose                                 |
| -------------------------------- | ----------------------------- | ----------- | --------- | --------------------------------------- |
| `chatwoot.router`                | `/webhook`                    | Token (URL) | 1         | Chatwoot webhook processing             |
| `admin.router`                   | `/api/admin`                  | JWT + RBAC  | 26        | Admin panel backend                     |
| `tariffs.router`                 | `/api/admin`                  | JWT         | 31        | Tariff management (full CRUD)           |
| `public_tariffs.router`          | `/api/tariffs`                | None        | 6         | Public tariff API for agent             |
| `system.router`                  | `/api/admin/system`           | JWT         | 11        | Docker service management, SSE logs     |
| `images.router`                  | `/api/admin`                  | JWT         | 4         | Image upload/management (admin)         |
| `images.get_public_image_router()` | `/images`                   | None        | 1         | Public image serving                    |
| `images.get_case_images_router()` | `/case-images`               | None        | 1         | Case image serving                      |
| `elements.router`                | `/api/admin`                  | JWT         | 24        | Element CRUD, images, warnings, fields  |
| `cases.router`                   | `/api/admin/cases`            | JWT         | 12        | Case management, image download/ZIP     |
| `token_usage.router`             | `/api/token-usage`            | JWT (admin) | 3         | Token usage tracking                    |
| `billing.router`                 | `/api/admin/billing`          | JWT         | —         | Invoice management, Stripe              |
| `conversation_messages.router`   | `/api/admin/conversations`    | JWT         | 2         | Message-level conversation access       |
| `validation_metrics.router`      | `/api/admin/validation`       | JWT         | —         | Agent output quality metrics            |

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
| **system.py** | 11 | Docker API (Unix socket/TCP), service status (6 containers), SSE log streaming (query param token), restart/stop (self-protection), cache clear, error logs + stats |
| **public_tariffs.py** | 6 | No auth, Redis cache (5min), classification rules matching, client type in slug, global + category services |
| **token_usage.py** | 3 | Last 12 months, current month EUR costs, pricing config (admin only) |
| **conversation_messages.py** | 2 | Message history, stats (counts, timestamps), image tracking, Chatwoot ID cross-ref |
| **billing.py** | — | Invoice listing, Stripe payment links, invoice status |
| **validation_metrics.py** | — | Agent output quality tracking, per-tool metrics |

---

## Services (Organized by Functionality)

### Image Services

| Service | Purpose | Key Features |
|---------|---------|--------------|
| `image_service.py` | Admin panel uploads | Magic numbers + PIL validation, save to disk + DB metadata, paginated listing |
| `chatwoot_image_service.py` | Chatwoot downloads | SSRF prevention (allowed domains), manual redirect following, 3 retry attempts (exponential backoff), concurrent batch download |

### Persistence Services

| Service | Purpose | Key Features |
|---------|---------|--------------|
| `message_persistence_service.py` | Message persistence | Fire-and-forget PostgreSQL persistence (`ConversationHistory` + `ConversationMessage`). Tracks images, Chatwoot message IDs. Errors logged but never propagated. |
| `cache_service.py` | Redis cache helpers | Centralized cache key management, TTL defaults |

### Conversation Reset Services

| Service | Purpose |
|---------|---------|
| `conversation_reset_coordinator.py` | Orchestrates full reset: delegates to DB, Redis, Chatwoot, and file executors |
| `conversation_reset_db_executor.py` | Deletes DB conversation records |
| `conversation_reset_redis_executor.py` | Clears Redis state for conversation |
| `conversation_reset_chatwoot_executor.py` | Syncs reset with Chatwoot |
| `conversation_reset_files_executor.py` | Removes conversation image files |

### Billing Services

| Service | Purpose | Key Features |
|---------|---------|--------------|
| `billing_service.py` | Billing business logic | Invoice generation, overdue detection, Stripe sync |
| `stripe_service.py` | Stripe integration | Payment intent creation, webhook handling |
| `pdf_service.py` | PDF generation | Invoice PDF rendering |

### Maintenance Services

| Service | Purpose | Key Features |
|---------|---------|--------------|
| `garbage_collection_service.py` | GC for stale data | Removes orphaned files, expired records |

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

### `billing_worker`

**Purpose**: Monthly invoice generation and overdue detection via asyncio background tasks.

**Architecture**: Two loops running in parallel inside the `api` process:
1. **`_monthly_invoice_loop`**: Fires on the 1st of each month at 02:00 UTC. Calls `BillingService.generate_invoice()`. Idempotent (HTTP 409 is logged as INFO, not ERROR).
2. **`_overdue_check_loop`**: Fires daily at 03:00 UTC. Calls `BillingService.check_overdue()`.

**Key Features**:
- Uses `_seconds_until(target_hour, target_minute, target_day)` — calculates exact seconds to next firing without polling.
- Sleeps via `asyncio.wait_for(shutdown_event.wait(), timeout=seconds)` for clean SIGTERM handling.
- Started in `api/main.py` startup event; stopped via `_shutdown_event`.

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
| Working with tariffs or elements | `msia-tariffs` |
| Writing Alembic migrations | `sqlalchemy-async` |
| Writing Python tests | `pytest-async` |
| Writing tests for MSI-a | `msia-test` |
