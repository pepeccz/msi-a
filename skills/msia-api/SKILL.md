---
name: msia-api
description: >
  MSI-a FastAPI backend patterns.
  Trigger: When creating/modifying API routes, services, webhooks, or Pydantic models.
metadata:
  author: msi-automotive
  version: "2.0"
  scope: [root, api]
  auto_invoke:
    - "Creating/modifying API routes"
    - "Working with Pydantic models"
    - "Working with Chatwoot webhooks"
---

## API Overview

**Scale**: 17 routers, ~147 endpoints, 11 services, 51 Pydantic models

See [api/AGENTS.md](../../api/AGENTS.md) for complete architecture and router details.

---

## JWT Authentication

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from jose import jwt

security = HTTPBearer()

async def get_current_user(
    token: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> AdminUser:
    # Decode JWT
    payload = jwt.decode(token.credentials, SECRET_KEY, algorithms=["HS256"])
    jti = payload.get("jti")
    
    # Check Redis blacklist
    if await redis.get(f"jwt_blacklist:{jti}"):
        raise HTTPException(401, "Token revoked")
    
    # Lookup user
    user = await session.get(AdminUser, payload.get("user_id"))
    if not user or not user.is_active:
        raise HTTPException(401, "Invalid user")
    
    return user

def require_role(*roles: str):
    """RBAC dependency factory."""
    def checker(user: AdminUser = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(403, "Insufficient permissions")
        return user
    return Depends(checker)
```

**Usage**:
```python
@router.get("/data")
async def get_data(user: AdminUser = Depends(get_current_user)):
    # Any authenticated user
    ...

@router.delete("/critical", dependencies=[Depends(require_role("admin"))])
async def critical_op(user: AdminUser = Depends(get_current_user)):
    # Only admin role
    ...
```

---

## Chatwoot Webhook

```python
@router.post("/chatwoot/{token}")
async def webhook(token: str, request: Request, session: AsyncSession = Depends(get_session)):
    # 1. Timing-safe token check
    if not hmac.compare_digest(token, settings.CHATWOOT_WEBHOOK_TOKEN):
        raise HTTPException(403, "Invalid token")
    
    # 2. Parse payload
    payload = await request.json()
    webhook = ChatwootWebhook.model_validate(payload)
    
    # 3. Filter events
    if webhook.event != "message_created" or webhook.message_type != "incoming":
        return {"status": "ignored"}
    
    # 4. Redis idempotency (SETNX 5min)
    key = f"webhook:{webhook.conversation_id}:{webhook.message_id}"
    if not await redis.setnx(key, "1"):
        return {"status": "duplicate"}
    await redis.expire(key, 300)
    
    # 5. Auto-create user (E.164 validated phone)
    user = await get_or_create_user(webhook.sender_phone, session)
    
    # 6. Bidirectional Chatwoot sync
    await sync_to_chatwoot(webhook.conversation_id, user)
    
    # 7. Queue to Redis Streams
    await redis.xadd(settings.AGENT_STREAM, {
        "conversation_id": webhook.conversation_id,
        "customer_phone": user.phone,
        "message_text": webhook.content or "",
        "user_id": str(user.id),
        "attachments": json.dumps([{"id": a.id, "file_type": a.file_type, "data_url": a.data_url} for a in webhook.attachments]),
    })
    
    return {"status": "queued"}
```

---

## Pydantic Models

### With Validators

```python
from pydantic import BaseModel, Field, validator

class TierCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=20, pattern=r'^[A-Z0-9_-]+$')
    price: Decimal = Field(..., ge=0)
    min_elements: int | None = Field(None, ge=0)
    max_elements: int | None = Field(None, ge=0)
    
    @validator('code')
    def uppercase_code(cls, v):
        return v.upper()
    
    @validator('max_elements')
    def validate_max_ge_min(cls, v, values):
        min_el = values.get('min_elements')
        if v is not None and min_el is not None and v < min_el:
            raise ValueError('max must be >= min')
        return v
```

### E.164 Phone

```python
import phonenumbers

class ChatwootEvent(BaseModel):
    customer_phone: str
    
    @validator('customer_phone')
    def validate_phone_e164(cls, v):
        parsed = phonenumbers.parse(v, "ES")
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError(f'Invalid phone: {v}')
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
```

---

## Image Upload (Secure)

```python
from shared.image_security import validate_image_full, ImageSecurityError

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_SIZE = 10 * 1024 * 1024

@router.post("/upload")
async def upload(file: UploadFile = File(...), user: AdminUser = Depends(get_current_user)):
    # 1. Check declared type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "Invalid type")
    
    # 2. Read & check size
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(400, "File too large")
    
    # 3. Full security validation (magic numbers + PIL)
    try:
        mime_type, width, height = validate_image_full(content)
    except ImageSecurityError as e:
        raise HTTPException(400, f"Invalid image: {e}")
    
    # 4. Save
    stored_filename = f"{uuid4()}-{sanitize_filename(file.filename)}"
    async with aiofiles.open(UPLOAD_DIR / stored_filename, "wb") as f:
        await f.write(content)
    
    # 5. DB metadata
    image = UploadedImage(stored_filename=stored_filename, mime_type=mime_type, ...)
    session.add(image)
    await session.commit()
    
    return {"id": str(image.id), "url": f"/images/{stored_filename}"}
```

---

## RAG Query

```python
from api.services.rag_service import get_rag_service

@router.post("/rag/query")
async def rag_query(data: QueryRequest, user: AdminUser = Depends(get_current_user)):
    service = get_rag_service()
    
    # Full pipeline: expand → hybrid search → RRF → boost → rerank → LLM (hybrid routing) → citations
    result = await service.query(
        query_text=data.query,
        user_id=str(user.id),
        conversation_id=data.conversation_id,
    )
    
    return QueryResponse(
        answer=result["answer"],
        citations=result["citations"],
        query_id=result["query_id"],
        was_cache_hit=result["was_cache_hit"],
        performance_metrics=result.get("metrics"),
    )
```

---

## Worker (Redis Streams)

```python
from shared.redis_client import create_consumer_group, read_from_stream, acknowledge_message

STREAM = "document_processing_stream"
GROUP = "document_workers"

async def main():
    redis = get_redis_client()
    await create_consumer_group(redis, STREAM, GROUP)
    consumer = f"worker-{os.urandom(4).hex()}"
    
    # Crash recovery: claim pending messages
    await process_pending(redis, consumer)
    
    # Main loop
    while True:
        messages = await read_from_stream(redis, STREAM, GROUP, consumer, count=1, block_ms=5000)
        if not messages:
            continue
        
        for message_id, data in messages[0][1]:
            doc_id = data[b"document_id"].decode()
            try:
                await process_document(doc_id)
            finally:
                await acknowledge_message(redis, STREAM, GROUP, message_id)

async def process_pending(redis, consumer):
    """Claim messages idle >30s from dead consumers."""
    pending = await redis.xpending_range(STREAM, GROUP, "-", "+", 100)
    ids = [p["message_id"] for p in pending if p["time_since_delivered"] > 30000]
    if ids:
        claimed = await redis.xclaim(STREAM, GROUP, consumer, 30000, ids)
        for msg_id, data in claimed:
            await process_document(data[b"document_id"].decode())
            await acknowledge_message(redis, STREAM, GROUP, msg_id)
```

---

## Anti-Patterns

❌ **Business logic in routes**
```python
# BAD
@router.post("/users")
async def create_user(data: UserCreate):
    if "@" not in data.email:  # Validation in route
        raise HTTPException(400, "Invalid email")
    user = User(email=data.email)  # Logic in route
    ...
```

✅ **Use services**
```python
# GOOD
@router.post("/users")
async def create_user(data: UserCreate, session: AsyncSession = Depends(get_session)):
    service = UserService(session)
    return await service.create_user(data)
```

❌ **Raw SQL**
```python
# BAD
query = f"SELECT * FROM users WHERE email = '{email}'"
```

✅ **SQLAlchemy ORM**
```python
# GOOD
result = await session.execute(select(User).where(User.email == email))
```

❌ **Missing error context**
```python
# BAD
raise HTTPException(404)
```

✅ **Descriptive errors**
```python
# GOOD
raise HTTPException(404, f"Document {doc_id} not found")
```

---

## Critical Rules

- ALWAYS use `async def` for routes
- ALWAYS use Pydantic for request/response
- ALWAYS use `Depends(get_session)` for DB
- ALWAYS use `Depends(get_current_user)` for auth
- ALWAYS validate files (type, size, magic numbers)
- ALWAYS use `response_model` for type safety
- ALWAYS return specific HTTP codes (404, 409, 403, etc.)
- ALWAYS invalidate caches after mutations
- NEVER put logic in routes (use services)
- NEVER trust user input (validate)
- NEVER use raw SQL
- NEVER expose internal errors
- NEVER store passwords plaintext (bcrypt)
- NEVER auto-follow external redirects (SSRF)

---

## Security Checklist

✅ JWT + blacklist (Redis)  
✅ RBAC (`require_role`)  
✅ Input validation (Pydantic)  
✅ Image security (magic numbers + PIL)  
✅ SSRF prevention (allowed domains)  
✅ Rate limiting (sliding window)  
✅ SQL injection prevention (ORM)  
✅ Audit logging (CUD operations)  
✅ Path traversal prevention  

---

## Resources

- [api/AGENTS.md](../../api/AGENTS.md) - Complete API architecture
- [msia-rag skill](../msia-rag/SKILL.md) - RAG patterns
- [fastapi skill](../fastapi/SKILL.md) - Generic FastAPI patterns
- [FastAPI docs](https://fastapi.tiangolo.com/)
- [Pydantic V2](https://docs.pydantic.dev/latest/)
