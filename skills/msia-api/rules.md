# msia-api Critical Rules

**Quick refresh for long sessions (~40 tokens)**

## ALWAYS

- `async def` for route handlers
- Pydantic models for request/response
- `Depends(get_session)` for database access
- `response_model` in decorators for type safety
- Appropriate HTTP status codes (201, 400, 404, 409)

## NEVER

- Business logic in routes → use services
- Return raw dicts → use Pydantic schemas
- Forget file type/size validation for uploads
