# msia-database Critical Rules

**Quick refresh for long sessions (~50 tokens)**

## ALWAYS

- UUID as primary key
- `created_at` and `updated_at` timestamps
- `DateTime(timezone=True)` for all timestamps
- `ondelete="CASCADE"` or `"SET NULL"` on ForeignKeys
- Indexes on frequently queried columns
- `expire_on_commit=False` for async sessions
- Deterministic UUIDs in seeds for idempotency

## NEVER

- Synchronous operations (use async)
- `lazy="joined"` with async → use `selectinload()`
