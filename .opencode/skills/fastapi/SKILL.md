---
name: fastapi
description: >
  FastAPI patterns for building APIs.
  Trigger: When creating/modifying API routes, Pydantic models, middleware, or dependency injection.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root, api]
  auto_invoke: "Creating/modifying FastAPI services"
---

## Router Pattern

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_session

router = APIRouter(prefix="/items", tags=["items"])

@router.get("/", response_model=list[ItemResponse])
async def list_items(
    session: AsyncSession = Depends(get_session),
    skip: int = 0,
    limit: int = 100,
):
    """List all items with pagination."""
    items = await ItemService.get_all(session, skip=skip, limit=limit)
    return items

@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get a single item by ID."""
    item = await ItemService.get_by_id(session, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} not found"
        )
    return item

@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    data: ItemCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new item."""
    return await ItemService.create(session, data)

@router.put("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    data: ItemUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update an existing item."""
    item = await ItemService.update(session, item_id, data)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} not found"
        )
    return item

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete an item."""
    deleted = await ItemService.delete(session, item_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} not found"
        )
```

## Pydantic Models

```python
from pydantic import BaseModel, Field
from datetime import datetime

# Base model with shared fields
class ItemBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    price: float = Field(..., gt=0)

# Create model (input)
class ItemCreate(ItemBase):
    pass

# Update model (partial updates)
class ItemUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    price: float | None = Field(None, gt=0)

# Response model (output)
class ItemResponse(ItemBase):
    id: int
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}
```

## Dependency Injection

```python
from fastapi import Depends, Header, HTTPException, status
from typing import Annotated

# Simple dependency
async def get_current_user(
    authorization: Annotated[str | None, Header()] = None
) -> User:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required"
        )
    # Validate token and return user
    return await validate_token(authorization)

# Dependency with parameters
def get_pagination(
    skip: int = 0,
    limit: int = 100,
) -> dict:
    return {"skip": max(0, skip), "limit": min(100, limit)}

# Usage
@router.get("/")
async def list_items(
    user: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[dict, Depends(get_pagination)],
):
    ...
```

## Exception Handling

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

class AppException(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message}
    )
```

## Middleware

```python
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
import time

class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        response.headers["X-Process-Time"] = f"{duration:.4f}"
        return response

app = FastAPI()
app.add_middleware(TimingMiddleware)
```

## Background Tasks

```python
from fastapi import BackgroundTasks

async def send_notification(email: str, message: str):
    # Long-running task
    ...

@router.post("/notify")
async def notify_user(
    email: str,
    message: str,
    background_tasks: BackgroundTasks,
):
    background_tasks.add_task(send_notification, email, message)
    return {"status": "Notification queued"}
```

## Critical Rules

- ALWAYS use `async def` for route handlers
- ALWAYS use Pydantic models for request/response
- ALWAYS use dependency injection for database sessions
- NEVER put business logic in routes (use services)
- ALWAYS return appropriate HTTP status codes
- ALWAYS use `response_model` for type safety
