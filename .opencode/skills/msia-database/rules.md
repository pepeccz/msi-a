# msia-database Critical Rules

**Quick refresh for long sessions (~150 tokens)**

## ALWAYS

### Models
- UUID as primary key (`UUID(as_uuid=True)`)
- `created_at` and `updated_at` timestamps
- `DateTime(timezone=True)` for all timestamps
- `ondelete="CASCADE"` or `"SET NULL"` on ForeignKeys
- Indexes on frequently queried columns (`index=True`)
- `lazy="selectin"` for ALL relationships (async-safe)

### Migrations
- Include `downgrade()` in every migration (never `pass`)
- Use `op.f()` for constraint naming (Alembic auto-naming)
- Create indexes AFTER creating tables
- Drop constraints/indexes BEFORE dropping tables in downgrade()

### Seeds
- Deterministic UUIDs (UUID v5) for idempotency
- Use dual warning system (inline + association) for element warnings
- Use `upsert_with_uuid_fn()` for upsert logic
- Soft delete via `is_active=False` (never hard delete)

### Async Patterns
- `expire_on_commit=False` for async sessions
- `selectinload()` for eager loading relationships
- `get_async_session()` context manager for all DB operations

### JSONB
- Use JSONB for flexible/dynamic data (not TEXT with JSON strings)
- Always provide default values (`default=dict` or `default=list`)
- Validate JSONB structure in application code (Pydantic)

## NEVER

### Models
- Synchronous operations (use async/await)
- `lazy="joined"` with async → use `lazy="selectin"` instead
- Models without `id`, `created_at`, `updated_at`
- Hard-delete seed data → use `is_active=False`

### Migrations
- Modify existing migrations → create new ones
- Leave `downgrade()` as `pass` → always implement rollback
- Create indexes before tables → always AFTER

### Seeds
- Random UUIDs in seeds → use UUID v5 with fixed namespace
- Reference element warnings only via inline OR only via association → use BOTH

### Logging
- `print()` statements → use structured logging

## Dual Warning System (Critical)

**Element warnings MUST exist in BOTH systems**:
1. Inline: `warnings.element_id` (agent uses)
2. Association: `element_warning_associations` (admin uses)

`ElementSeeder` creates both automatically — never create only one.

## Common Anti-Patterns

❌ **Don't**:
```python
# Random UUIDs in seeds (non-idempotent)
element = Element(id=uuid.uuid4(), code="ESCAPE")

# Lazy joined with async
category: Mapped["VehicleCategory"] = relationship(lazy="joined")

# No downgrade
def downgrade() -> None:
    pass
```

✅ **Do**:
```python
# Deterministic UUIDs
element_id = element_uuid(category_slug, "ESCAPE")
element = Element(id=element_id, code="ESCAPE")

# Selectin for async
category: Mapped["VehicleCategory"] = relationship(lazy="selectin")

# Always implement downgrade
def downgrade() -> None:
    op.drop_table("my_table")
```
