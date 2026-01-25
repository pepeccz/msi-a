# Python Backend Quick Rules

## FastAPI

```python
# Route pattern
@router.post("/", response_model=Response, status_code=201)
async def create(data: Request, db: AsyncSession = Depends(get_db)):
    service = MyService(db)
    return await service.create(data)
```

## SQLAlchemy Async

```python
# Always use async
result = await db.execute(select(Model).where(Model.id == id))
item = result.scalar_one_or_none()

# Avoid N+1 with selectinload
.options(selectinload(Model.relation))
```

## Pydantic

```python
# Request model (no id, no timestamps)
class CreateRequest(BaseModel):
    name: str = Field(min_length=1)

# Response model (includes id, timestamps)
class Response(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)
```

## Error Messages

```python
# Spanish for HTTPException detail
raise HTTPException(404, detail="Recurso no encontrado")
```

## Don't

- Don't use `db.query()` (sync API)
- Don't forget `await` on async calls
- Don't return raw SQLAlchemy models
- Don't use `print()` for logging
