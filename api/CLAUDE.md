# API Component Guidelines

This directory contains the MSI-a FastAPI backend.

## Auto-invoke Skills

When working in this directory, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Creating/modifying routes | `msia-api` |
| Creating/modifying services | `msia-api` |
| Working with Pydantic models | `msia-api` |
| Working with Chatwoot webhooks | `msia-api` |
| Generic FastAPI patterns | `fastapi` |
| Writing tests | `msia-test` |
| Working with tariffs | `msia-tariffs` |

## Directory Structure

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
│   └── log_monitor.py      # Error monitoring
├── models/
│   ├── chatwoot_webhook.py # Webhook schemas
│   ├── tariff_schemas.py   # Tariff models
│   └── element.py          # Element schemas
├── middleware/
│   └── rate_limit.py       # Rate limiting
└── workers/
    └── document_processor_worker.py
```

## Key Patterns

### Route with Dependency Injection

```python
@router.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: str,
    session: AsyncSession = Depends(get_session),
):
    ...
```

### Pydantic Response Model

```python
class ItemResponse(BaseModel):
    id: UUID
    name: str
    model_config = {"from_attributes": True}
```

## Critical Rules

- ALWAYS use `async def` for route handlers
- ALWAYS use Pydantic for request/response
- ALWAYS use `Depends(get_session)` for database
- NEVER put business logic in routes (use services)
- ALWAYS return appropriate HTTP status codes
