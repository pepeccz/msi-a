---
name: msia-api
description: >
  MSI-a FastAPI backend patterns.
  Trigger: When creating/modifying API routes, services, webhooks, or Pydantic models.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root, api]
  auto_invoke: "Creating/modifying API routes"
---

## API Structure

```
api/
├── main.py                 # FastAPI app, router registration
├── routes/
│   ├── chatwoot.py         # Webhook endpoint
│   ├── admin.py            # Admin panel API
│   ├── tariffs.py          # Tariff management
│   ├── elements.py         # Element CRUD
│   ├── images.py           # Image upload/serve
│   ├── cases.py            # Case management
│   ├── system.py           # System settings
│   └── rag_query.py        # RAG queries
├── services/
│   ├── image_service.py    # Image processing
│   ├── rag_service.py      # RAG retrieval
│   ├── reranker_service.py # Result reranking
│   └── log_monitor.py      # Error log monitoring
├── models/
│   ├── chatwoot_webhook.py # Webhook schemas
│   ├── tariff_schemas.py   # Tariff Pydantic models
│   └── element.py          # Element schemas
├── middleware/
│   └── rate_limit.py       # Rate limiting
└── workers/
    └── document_processor_worker.py  # Background processing
```

## Route Pattern

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_session
from api.models.tariff_schemas import TierResponse, TierCreate

router = APIRouter(prefix="/api/tariffs", tags=["tariffs"])

@router.get("/categories/{category_id}/tiers", response_model=list[TierResponse])
async def list_tiers(
    category_id: str,
    session: AsyncSession = Depends(get_session),
):
    """List all tiers for a category."""
    from database.models import TariffTier
    from sqlalchemy import select
    
    result = await session.execute(
        select(TariffTier)
        .where(TariffTier.category_id == category_id)
        .order_by(TariffTier.sort_order)
    )
    return result.scalars().all()

@router.post("/tiers", response_model=TierResponse, status_code=status.HTTP_201_CREATED)
async def create_tier(
    data: TierCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new tariff tier."""
    tier = TariffTier(**data.model_dump())
    session.add(tier)
    await session.flush()
    return tier
```

## Chatwoot Webhook Pattern

```python
from fastapi import APIRouter, Request, BackgroundTasks
from api.models.chatwoot_webhook import ChatwootWebhook

router = APIRouter(prefix="/api/chatwoot", tags=["chatwoot"])

@router.post("/webhook")
async def chatwoot_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Handle incoming Chatwoot webhooks."""
    payload = await request.json()
    webhook = ChatwootWebhook.model_validate(payload)
    
    # Only process incoming messages
    if webhook.event != "message_created":
        return {"status": "ignored"}
    
    if webhook.message_type != "incoming":
        return {"status": "ignored"}
    
    # Queue for async processing
    background_tasks.add_task(
        process_message,
        conversation_id=webhook.conversation.id,
        message=webhook.content,
    )
    
    return {"status": "queued"}
```

## Pydantic Schema Pattern

```python
from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import datetime
from uuid import UUID

# Response model (from database)
class TierResponse(BaseModel):
    id: UUID
    category_id: UUID
    code: str
    name: str
    price: Decimal
    conditions: str | None
    sort_order: int
    is_active: bool
    created_at: datetime
    
    model_config = {"from_attributes": True}

# Create model (input)
class TierCreate(BaseModel):
    category_id: UUID
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=100)
    price: Decimal = Field(..., ge=0)
    conditions: str | None = None
    sort_order: int = 0

# Update model (partial)
class TierUpdate(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=20)
    name: str | None = Field(None, min_length=1, max_length=100)
    price: Decimal | None = Field(None, ge=0)
    conditions: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None
```

## Image Upload Pattern

```python
from fastapi import APIRouter, UploadFile, File, HTTPException
from api.services.image_service import ImageService

router = APIRouter(prefix="/api/images", tags=["images"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_SIZE = 10 * 1024 * 1024  # 10MB

@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    category: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Upload an image."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "Invalid file type")
    
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(400, "File too large")
    
    result = await ImageService.save(
        session,
        content=content,
        filename=file.filename,
        content_type=file.content_type,
        category=category,
    )
    
    return {"id": result.id, "url": f"/api/images/{result.stored_filename}"}
```

## Error Handling

```python
from fastapi import HTTPException, status

# Not found
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail=f"Tier {tier_id} not found"
)

# Validation error
raise HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="Invalid category slug"
)

# Conflict
raise HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="Element code already exists"
)
```

## Critical Rules

- ALWAYS use `async def` for route handlers
- ALWAYS use Pydantic models for request/response
- ALWAYS use `Depends(get_session)` for database
- NEVER put business logic in routes (use services)
- ALWAYS return appropriate HTTP status codes
- ALWAYS use `response_model` for type safety
- ALWAYS validate file types and sizes for uploads

## Resources

- [fastapi skill](../fastapi/SKILL.md) - Generic FastAPI patterns
- [Chatwoot docs](https://www.chatwoot.com/docs/product/channels/api/receive-messages)
