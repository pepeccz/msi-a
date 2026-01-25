# Coding Standards Quick Rules

## Must Do

1. **Type hints on all functions** - No exceptions
2. **Async for all I/O** - Database, HTTP, file operations
3. **Pydantic for validation** - Never raw dicts for API schemas
4. **Spanish for users** - User-facing text in Spanish
5. **English for code** - Variables, functions, comments

## File Limits

- **500 lines** max per file
- **50 lines** max per function
- **5 parameters** max per function

## Python

```python
# Required pattern
async def get_item(item_id: int) -> Item | None:
    """English docstring."""
    pass
```

## TypeScript

```typescript
// Server Component by default
// 'use client' only when hooks/interactivity needed
```

## Logging

```python
# GOOD
logger.info("event_name", key=value)

# BAD
logger.info(f"Something happened: {value}")
print("Debug")
```
