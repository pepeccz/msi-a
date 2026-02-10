# Semantic Validation - Quick Reference Card

**Phase 2 Implementation** | **Date**: Feb 8, 2026

---

## What is Semantic Validation?

**Layer 3** of the defensive validation system that checks parameter **values** against the database before tool execution.

```
Syntax ✓ → State ✓ → Semantic ✓ → Execute
```

---

## Quick Usage

### For Tool Developers

**No changes needed!** Semantic validation is automatic for configured tools.

```python
# Just define your tool normally
@tool
async def my_tool(categoria_slug: str, case_id: str):
    """My tool."""
    # If parameters are invalid, validation stops execution before this runs
    return "ok"
```

### For Mode Developers

**No changes needed!** BaseModeNode already integrates validation.

```python
# Existing code in base_mode.py handles everything
is_valid, errors = await validator.validate(tool, tool_input, state)
if not is_valid:
    # LLM receives errors and fixes parameters
    pass
```

---

## Supported Validators

| Parameter | Checks | Example Error |
|-----------|--------|---------------|
| `categoria_slug` | Exists in DB | "La categoría 'invalid-slug' no existe" |
| `element_code` | Exists for category | "El elemento 'INVALID' no existe en 'motos-part'" |
| `case_id` | Exists, active, valid UUID | "El expediente está inactivo" |
| `user_id` | Exists, valid UUID | "El usuario no existe" |
| `tier_id` | Exists for category | "La tarifa no existe en 'motos-part'" |

---

## Adding New Tool Coverage

Edit `agent/utils/tool_validation.py`:

```python
class SemanticValidator:
    TOOL_VALIDATIONS = {
        "my_new_tool": ["categoria_slug", "case_id"],  # Add this line
        # ... existing tools
    }
```

**That's it!** Validation is automatic.

---

## Adding New Validator

1. **Add validator function** in `agent/services/constraint_service.py`:

```python
async def validate_my_param(value: str) -> tuple[bool, str | None]:
    """Validate my_param exists in DB."""
    cache_key = f"semantic_validation:my_param:{value}"
    
    async def query():
        async with get_async_session() as session:
            result = await session.execute(
                select(MyModel.id).where(MyModel.code == value)
            )
            exists = result.scalar_one_or_none() is not None
            return {"exists": exists}
    
    result = await cached_db_lookup(cache_key, query, ttl=300)
    
    if result["exists"]:
        return (True, None)
    else:
        return (False, f"Mi parámetro '{value}' no existe")
```

2. **Add to SemanticValidator** in `agent/utils/tool_validation.py`:

```python
# In SemanticValidator.validate()
elif param_name == "my_param":
    is_valid, error = await validate_my_param(param_value)
    if not is_valid:
        errors.append(error)
```

3. **Add tests** in `tests/agent/utils/test_semantic_validation.py`.

---

## Performance Tips

### Cache TTL Selection

- **Static data** (categories, elements, tiers): 5 minutes
- **Dynamic data** (cases, active states): 1 minute
- **User data** (users, contacts): 5 minutes

### Cache Key Format

```python
f"semantic_validation:{entity}:{value}"
f"semantic_validation:{entity}:{context}:{value}"  # For relationships
```

**Examples**:
- `semantic_validation:categoria:motos-part`
- `semantic_validation:element:motos-part:ESCAPE`
- `semantic_validation:case:550e8400-e29b-41d4-a716-446655440000`

---

## Debugging

### Check Validation Logs

```bash
docker-compose logs agent | grep semantic_validation
```

**Events**:
- `semantic_validation_failed` - Validation rejected parameters
- `element_code_validation_skipped_no_category` - Missing context
- `cache_hit` / `cache_miss` - Redis cache performance

### Manual Testing

```python
# In Python console
from agent.services.constraint_service import validate_categoria_slug

# Test validator
is_valid, error = await validate_categoria_slug("motos-part")
print(f"Valid: {is_valid}, Error: {error}")

# Expected: Valid: True, Error: None
```

### Check Cache

```bash
# In Redis CLI
redis-cli
> KEYS semantic_validation:*
> GET semantic_validation:categoria:motos-part
> TTL semantic_validation:categoria:motos-part
```

---

## Common Issues

### Issue: Validator Skipped for Tool

**Symptom**: Tool executes with invalid parameters.

**Fix**: Add tool to `TOOL_VALIDATIONS` mapping:
```python
TOOL_VALIDATIONS = {
    "my_tool": ["param_to_validate"],
}
```

### Issue: Cache Never Hits

**Symptom**: Every validation queries DB.

**Fix**: Check Redis connection:
```bash
docker-compose logs redis
# Ensure Redis is running and accessible
```

### Issue: Validation Rejects Valid Parameter

**Symptom**: Valid parameter marked as invalid.

**Possible causes**:
1. Cache is stale (wait for TTL expiry)
2. Record is `is_active=False` (check DB)
3. Wrong cache key format (check logs)

**Debug**:
```python
# Query DB directly
async with get_async_session() as session:
    result = await session.execute(
        select(Model).where(Model.field == value)
    )
    print(result.scalar_one_or_none())
```

---

## Error Message Guidelines

**Format**: Spanish, user-friendly, specific

✅ **Good**:
```
"La categoría 'invalid-slug' no existe en el sistema"
"El expediente '550e8400-...' está inactivo"
```

❌ **Bad**:
```
"Invalid categoria_slug"
"Case not found"
```

**Pattern**:
```python
return (False, f"El {entity} '{value}' no existe en {context}")
```

---

## Performance Benchmarks

| Operation | Cached | Uncached |
|-----------|--------|----------|
| `validate_categoria_slug` | <5ms | ~40ms |
| `validate_element_code` | <5ms | ~50ms |
| `validate_case_id` | <5ms | ~30ms |
| `validate_tier_id` | <5ms | ~50ms |

**Target**: >99% cache hit rate in production.

---

## Testing

### Run Unit Tests

```bash
docker-compose run --rm agent pytest \
  tests/agent/utils/test_semantic_validation.py -v
```

### Run Integration Test

```bash
python3 scripts/test_semantic_validation_integration.py
```

### Test New Validator

```python
@pytest.mark.asyncio
async def test_validate_my_param_valid():
    """Test valid my_param."""
    with patch("constraint_service.cached_db_lookup", return_value={"exists": True}):
        is_valid, error = await validate_my_param("valid-value")
    
    assert is_valid is True
    assert error is None
```

---

## Monitoring Metrics

### Key Metrics

1. **Validation Failure Rate**
   - By layer (syntax/state/semantic)
   - By tool name
   - By parameter type

2. **Cache Performance**
   - Hit rate (target: >99%)
   - Latency p50/p95/p99
   - Miss rate by entity type

3. **Database Load**
   - Validation queries per minute
   - Query latency distribution

4. **Error Distribution**
   - Most common invalid parameters
   - Error message frequency

### Alerts

- Cache hit rate <95% for 5 minutes
- Semantic validation failure rate >5%
- Database query latency p95 >100ms

---

## FAQ

**Q: Does semantic validation slow down the agent?**  
A: No. With 99%+ cache hit rate, validation adds <5ms per tool call.

**Q: What happens if Redis is down?**  
A: Validation continues using direct DB queries. Performance degrades but functionality remains.

**Q: Can I disable semantic validation for a tool?**  
A: Yes, remove it from `TOOL_VALIDATIONS` mapping.

**Q: How do I invalidate cache after DB changes?**  
A: Cache auto-expires after TTL. For immediate invalidation, delete Redis key:
```bash
redis-cli DEL semantic_validation:categoria:motos-part
```

**Q: Why are error messages in Spanish?**  
A: LLM consumes these errors and responds to users in Spanish. Spanish errors reduce translation overhead.

---

## Related Documentation

- **Implementation Details**: `docs/phase2-semantic-validation-implementation.md`
- **Full Plan**: `docs/plans/defensive-parameter-validation-system.md`
- **Phase 1 (Syntax/State)**: `tests/agent/utils/test_tool_validation.py`
- **Phase 3 (Error Recovery)**: Coming soon

---

**Last Updated**: February 8, 2026  
**Version**: Phase 2 Complete  
**Status**: ✅ Production Ready
