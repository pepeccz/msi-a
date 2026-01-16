# Database Component Guidelines

This directory contains SQLAlchemy models, Alembic migrations, and data seeds.

## Auto-invoke Skills

When working in this directory, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Creating/modifying models | `msia-database` |
| Writing migrations | `msia-database` |
| Working with seeds | `msia-database` |
| Generic SQLAlchemy patterns | `sqlalchemy-async` |
| Working with tariff models | `msia-tariffs` |

## Directory Structure

```
database/
├── models.py           # All SQLAlchemy models
├── connection.py       # Async engine and session
├── __init__.py
├── seeds/
│   ├── run_all_seeds.py
│   ├── seed_utils.py
│   ├── motos_elements_seed.py
│   ├── motos_particular_seed.py
│   └── aseicars_professional_seed.py
└── alembic/
    ├── env.py
    ├── script.py.mako
    └── versions/
        ├── 001_initial_schema.py
        ├── 002_tariff_system.py
        └── ...
```

## Key Models

| Model | Description |
|-------|-------------|
| `User` | WhatsApp users |
| `VehicleCategory` | Categories by client type |
| `TariffTier` | Pricing tiers (T1-T6) |
| `Element` | Homologable elements |
| `Warning` | Contextual warnings |
| `AdminUser` | Admin panel users |
| `RegulatoryDocument` | RAG documents |

## Key Patterns

### Model with UUID and Timestamps

```python
class MyModel(Base):
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=lambda: datetime.now(UTC))
```

### Migration

```python
def upgrade() -> None:
    op.create_table(...)
    op.create_index(...)

def downgrade() -> None:
    op.drop_table(...)
```

## Commands

```bash
alembic revision -m "description"
alembic upgrade head
alembic downgrade -1
python -m database.seeds.run_all_seeds
```

## Critical Rules

- ALWAYS use UUID as primary key
- ALWAYS include timestamps
- ALWAYS use `DateTime(timezone=True)`
- ALWAYS use `lazy="selectin"` for relationships
- NEVER use synchronous operations
