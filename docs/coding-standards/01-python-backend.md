# Estándares Python Backend (FastAPI + SQLAlchemy)

Patrones y convenciones para el desarrollo de la API backend de MSI-a.

---

## 1. Estructura de Archivos

```
api/
├── main.py                      # FastAPI app, CORS, routers
├── routes/                      # Endpoints HTTP (15 módulos)
│   ├── admin.py                 # 26 endpoints - Dashboard, users, auth
│   ├── tariffs.py               # 31 endpoints - Tariff management
│   ├── elements.py              # 24 endpoints - Element CRUD
│   └── ...
├── services/                    # Lógica de negocio
│   ├── rag_service.py           # RAG orchestrator
│   ├── embedding_service.py     # Ollama embeddings
│   └── ...
├── models/                      # Pydantic schemas (51 clases)
│   ├── chatwoot_webhook.py
│   ├── tariff_schemas.py
│   └── ...
└── workers/                     # Background workers
    └── document_processor_worker.py
```

---

## 2. Route Pattern (OBLIGATORIO)

### Estructura Básica

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from database.connection import get_async_session
from api.models.schemas import ItemCreate, ItemUpdate, ItemResponse
from api.routes.admin import get_current_user
from database.models import Item, AdminUser

router = APIRouter(prefix="/api/items", tags=["items"])

@router.get("", response_model=dict)
async def list_items(
    current_user: AdminUser = Depends(get_current_user),
    search: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """
    List items with pagination and search.
    
    Returns:
        - items: List of items
        - total: Total count
        - has_more: Whether there are more items
    """
    async with get_async_session() as session:
        # Count total
        count_query = select(func.count(Item.id))
        if search:
            count_query = count_query.where(Item.name.ilike(f"%{search}%"))
        total = (await session.execute(count_query)).scalar() or 0
        
        # Fetch items
        query = select(Item).options(selectinload(Item.category))
        if search:
            query = query.where(Item.name.ilike(f"%{search}%"))
        query = query.order_by(Item.created_at.desc()).offset(offset).limit(limit)
        
        result = await session.execute(query)
        items = result.scalars().all()
        
        return {
            "items": [ItemResponse.model_validate(item) for item in items],
            "total": total,
            "has_more": offset + len(items) < total,
        }

@router.post("", response_model=ItemResponse, status_code=201)
async def create_item(
    data: ItemCreate,
    current_user: AdminUser = Depends(get_current_user),
) -> Item:
    """Create a new item."""
    async with get_async_session() as session:
        # Check for duplicates
        existing = await session.execute(
            select(Item).where(Item.name == data.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(409, "Item with this name already exists")
        
        # Create
        item = Item(**data.model_dump())
        session.add(item)
        await session.commit()
        await session.refresh(item)
        
        return item

@router.put("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: UUID,
    data: ItemUpdate,
    current_user: AdminUser = Depends(get_current_user),
) -> Item:
    """Update an existing item."""
    async with get_async_session() as session:
        item = await session.get(Item, item_id)
        if not item:
            raise HTTPException(404, "Item not found")
        
        # Update only provided fields
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        
        await session.commit()
        await session.refresh(item)
        
        return item

@router.delete("/{item_id}", status_code=204)
async def delete_item(
    item_id: UUID,
    current_user: AdminUser = Depends(get_current_user),
):
    """Delete an item (soft delete)."""
    async with get_async_session() as session:
        item = await session.get(Item, item_id)
        if not item:
            raise HTTPException(404, "Item not found")
        
        # Soft delete
        item.is_active = False
        await session.commit()
```

---

## 3. Pydantic Schemas (OBLIGATORIO)

### Patrón Base/Create/Update/Response

```python
from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import datetime
from uuid import UUID
from decimal import Decimal

class ItemBase(BaseModel):
    """Shared properties."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    price: Decimal = Field(..., ge=0, decimal_places=2)
    is_active: bool = Field(True)

class ItemCreate(ItemBase):
    """Properties to receive on creation."""
    category_id: UUID
    
    @field_validator('name')
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Name cannot be empty')
        return v.strip()

class ItemUpdate(BaseModel):
    """Properties to receive on update (all optional)."""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    price: Decimal | None = Field(None, ge=0, decimal_places=2)
    is_active: bool | None = None

class ItemResponse(ItemBase):
    """Properties to return to client."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    category_id: UUID
    created_at: datetime
    updated_at: datetime | None = None
```

---

## 4. Service Layer Pattern

**NUNCA pongas lógica de negocio en routes** → usar services/

```python
# api/services/item_service.py
from functools import lru_cache
import structlog

logger = structlog.get_logger(__name__)

class ItemService:
    """Business logic for items."""
    
    async def calculate_discounted_price(
        self,
        item_id: UUID,
        discount_percentage: Decimal,
    ) -> Decimal:
        """Calculate item price with discount."""
        async with get_async_session() as session:
            item = await session.get(Item, item_id)
            if not item:
                raise ValueError(f"Item {item_id} not found")
            
            discount = item.price * (discount_percentage / 100)
            final_price = item.price - discount
            
            logger.info(
                "discount_calculated",
                item_id=str(item_id),
                original_price=float(item.price),
                discount=float(discount),
                final_price=float(final_price),
            )
            
            return final_price

@lru_cache
def get_item_service() -> ItemService:
    """Get singleton ItemService instance."""
    return ItemService()

# En route:
from api.services.item_service import get_item_service

@router.post("/{item_id}/discount")
async def apply_discount(
    item_id: UUID,
    discount: Decimal = Query(..., ge=0, le=100),
    service: ItemService = Depends(get_item_service),
):
    final_price = await service.calculate_discounted_price(item_id, discount)
    return {"final_price": final_price}
```

---

## 5. Error Handling

### HTTP Status Codes

| Code | Uso | Ejemplo |
|------|-----|---------|
| 200 | Success (GET, PUT) | Item retrieved/updated |
| 201 | Created (POST) | Item created |
| 204 | No Content (DELETE) | Item deleted |
| 400 | Bad Request | Invalid input data |
| 401 | Unauthorized | Missing/invalid token |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Item doesn't exist |
| 409 | Conflict | Duplicate unique field |
| 422 | Unprocessable Entity | Pydantic validation failed |
| 500 | Internal Server Error | Unexpected error |
| 503 | Service Unavailable | External service down |

### Patrón de Error Handling

```python
from fastapi import HTTPException
import structlog
import traceback

logger = structlog.get_logger(__name__)

@router.post("/items")
async def create_item(data: ItemCreate):
    try:
        # Business logic
        async with get_async_session() as session:
            item = Item(**data.model_dump())
            session.add(item)
            await session.commit()
            return item
    
    except IntegrityError as e:
        # Log internal details
        logger.error(
            "database_integrity_error",
            error=str(e),
            data=data.model_dump(),
        )
        # Return generic error to user
        raise HTTPException(409, "Item with this name already exists")
    
    except ValueError as e:
        # Known validation error
        raise HTTPException(400, str(e))
    
    except Exception as e:
        # Unexpected error
        logger.error(
            "unexpected_error",
            error=str(e),
            stack_trace=traceback.format_exc(),
        )
        # Never expose internal details
        raise HTTPException(500, "Internal server error")
```

---

## 6. Dependency Injection

### Authentication

```python
from fastapi import Depends, HTTPException, Header
from api.routes.admin import get_current_user, require_role

# Require authentication
@router.get("/protected")
async def protected_endpoint(
    current_user: AdminUser = Depends(get_current_user),
):
    return {"message": f"Hello {current_user.username}"}

# Require specific role
@router.delete("/critical", dependencies=[Depends(require_role("admin"))])
async def critical_endpoint(
    current_user: AdminUser = Depends(get_current_user),
):
    return {"message": "Admin only"}
```

### Database Session

```python
# ✅ CORRECTO
@router.get("/items")
async def list_items():
    async with get_async_session() as session:
        result = await session.execute(select(Item))
        return result.scalars().all()

# ❌ INCORRECTO - No usar Depends para session
@router.get("/items")
async def list_items(session: AsyncSession = Depends(get_async_session)):
    # Don't do this!
    pass
```

---

## 7. Pagination (OBLIGATORIO)

**TODOS los endpoints de lista DEBEN tener paginación.**

```python
@router.get("/items")
async def list_items(
    limit: int = Query(50, ge=1, le=100, description="Max items per page"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
) -> dict:
    async with get_async_session() as session:
        # Count total
        total = (await session.execute(select(func.count(Item.id)))).scalar() or 0
        
        # Fetch page
        query = select(Item).offset(offset).limit(limit)
        items = (await session.execute(query)).scalars().all()
        
        return {
            "items": [ItemResponse.model_validate(i) for i in items],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < total,
        }
```

---

## 8. Relationships (Eager Loading)

```python
# ❌ INCORRECTO - N+1 query problem
@router.get("/items")
async def list_items():
    async with get_async_session() as session:
        items = (await session.execute(select(Item))).scalars().all()
        return [
            {
                "id": item.id,
                "category": item.category.name  # Lazy load = 1 query per item!
            }
            for item in items
        ]

# ✅ CORRECTO - Eager loading
from sqlalchemy.orm import selectinload

@router.get("/items")
async def list_items():
    async with get_async_session() as session:
        query = select(Item).options(selectinload(Item.category))
        items = (await session.execute(query)).scalars().all()
        return [
            {
                "id": item.id,
                "category": item.category.name  # Already loaded!
            }
            for item in items
        ]
```

---

## 9. Logging Estructurado

```python
import structlog

logger = structlog.get_logger(__name__)

@router.post("/items")
async def create_item(data: ItemCreate, current_user: AdminUser = Depends(get_current_user)):
    # ✅ CORRECTO - Structured logging
    logger.info(
        "item_create_attempt",
        user_id=str(current_user.id),
        item_name=data.name,
        category_id=str(data.category_id),
    )
    
    # Business logic...
    
    logger.info(
        "item_created",
        item_id=str(item.id),
        user_id=str(current_user.id),
    )
    
    # ❌ INCORRECTO
    print(f"Item created: {item.id}")  # NEVER!
    logging.info("Item created")        # No structured!
```

---

## 10. Cache Invalidation

```python
from shared.redis_client import get_redis_client

@router.put("/items/{item_id}")
async def update_item(item_id: UUID, data: ItemUpdate):
    async with get_async_session() as session:
        item = await session.get(Item, item_id)
        # Update...
        await session.commit()
        
        # Invalidate cache
        redis = get_redis_client()
        cache_key = f"item:{item_id}"
        await redis.delete(cache_key)
        
        # Invalidate list cache if needed
        await redis.delete("items:list:*")
        
        return item
```

---

## 11. Background Workers (Redis Streams)

```python
# api/workers/document_processor_worker.py
from shared.redis_client import get_redis_client, DOCUMENT_STREAM
import asyncio

async def process_documents():
    """Worker that processes documents from Redis Stream."""
    redis = get_redis_client()
    consumer_name = f"worker-{os.getpid()}"
    
    # Create consumer group
    try:
        await redis.xgroup_create(DOCUMENT_STREAM, "document_workers", id="0", mkstream=True)
    except Exception:
        pass  # Group already exists
    
    while True:
        # Read from stream
        messages = await redis.xreadgroup(
            "document_workers",
            consumer_name,
            {DOCUMENT_STREAM: ">"},
            count=1,
            block=5000,  # 5s timeout
        )
        
        for stream, msg_list in messages:
            for msg_id, data in msg_list:
                try:
                    # Process document
                    await process_single_document(data)
                    
                    # Acknowledge
                    await redis.xack(DOCUMENT_STREAM, "document_workers", msg_id)
                    
                except Exception as e:
                    logger.error("document_processing_failed", msg_id=msg_id, error=str(e))
                    # DLQ handling...

if __name__ == "__main__":
    asyncio.run(process_documents())
```

---

## 12. Type Hints (OBLIGATORIO)

```python
# ✅ CORRECTO - Complete type hints
from typing import Any
from uuid import UUID
from decimal import Decimal

async def calculate_total(
    items: list[UUID],
    discount: Decimal | None = None,
) -> dict[str, Any]:
    """Calculate total with optional discount."""
    total = Decimal("0.00")
    # Logic...
    return {
        "total": total,
        "items_count": len(items),
    }

# ❌ INCORRECTO - No type hints
async def calculate_total(items, discount=None):
    # Bad!
    pass
```

---

## 13. Reglas Críticas (Resumen)

1. ✅ **SIEMPRE** `async def` para route handlers
2. ✅ **SIEMPRE** Pydantic models para request/response
3. ✅ **SIEMPRE** `async with get_async_session()` para DB
4. ✅ **SIEMPRE** paginación en endpoints de lista
5. ✅ **SIEMPRE** `selectinload()` para relaciones
6. ✅ **SIEMPRE** logging estructurado con structlog
7. ✅ **SIEMPRE** complete type hints
8. ❌ **NUNCA** lógica de negocio en routes → usar services/
9. ❌ **NUNCA** raw SQL → usar SQLAlchemy ORM
10. ❌ **NUNCA** exponer errores internos → HTTPException genérico
11. ❌ **NUNCA** `print()` → usar structlog
12. ❌ **NUNCA** `os.getenv()` → usar `get_settings()`

---

**Referencias:**
- `api/AGENTS.md` - Inventario completo de routes y services
- `skills/fastapi/SKILL.md` - Patrones FastAPI genéricos
- `skills/msia-api/SKILL.md` - Patrones MSI-a específicos

**Última actualización:** Febrero 2026
