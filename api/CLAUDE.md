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
| Working with RAG/documents | `msia-rag` |
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
│   ├── rag_query.py        # RAG queries
│   ├── regulatory_documents.py # Document upload/management
│   ├── public_tariffs.py   # Public tariff endpoints
│   └── token_usage.py      # Token usage tracking
├── services/
│   ├── image_service.py    # Image processing
│   ├── chatwoot_image_service.py # Chatwoot image handling
│   ├── rag_service.py      # RAG orchestrator
│   ├── embedding_service.py # Ollama embeddings
│   ├── qdrant_service.py   # Vector storage
│   ├── reranker_service.py # BGE reranking
│   ├── document_processor.py # PDF extraction
│   └── log_monitor.py      # Error monitoring
├── models/
│   ├── chatwoot_webhook.py # Webhook schemas
│   ├── tariff_schemas.py   # Tariff models
│   ├── element.py          # Element schemas
│   ├── admin_user.py       # Admin user schemas
│   └── token_usage.py      # Token usage schemas
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

### Auto-invoke Skills

When performing these actions, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Creating/modifying API routes | `msia-api` |
| Creating/modifying FastAPI services | `fastapi` |
| Working with RAG system or documents | `msia-rag` |
| Working with tariffs or elements | `msia-tariffs` |
| Writing Alembic migrations | `sqlalchemy-async` |
| Writing Python tests | `pytest-async` |
| Writing tests for MSI-a | `msia-test` |
