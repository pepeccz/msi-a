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
│   ├── __init__.py
│   ├── run_all_seeds.py         # Main orchestrator
│   ├── seed_utils.py            # Deterministic UUIDs for idempotency
│   ├── validate_elements_seed.py # Validation script
│   ├── verify_warning_sync.py   # Verify warning synchronization (inline + associations)
│   ├── create_admin_user.py     # Create admin user script
│   ├── WARNING_SYSTEM.md        # Documentation on dual warning system
│   │
│   ├── data/                    # Data definitions (constants only)
│   │   ├── __init__.py
│   │   ├── common.py            # Shared types (TypedDict) and constants
│   │   ├── motos_part.py        # Motos particular: CATEGORY, TIERS, ELEMENTS...
│   │   ├── aseicars_prof.py     # Autocaravanas profesional data
│   │   └── tier_mappings.py     # Tier-element mappings (single source of truth)
│   │
│   └── seeders/                 # Reusable seeding logic
│       ├── __init__.py
│       ├── base.py              # BaseSeeder with uniform logging, upsert
│       ├── category.py          # CategorySeeder (category, tiers, warnings, services)
│       ├── element.py           # ElementSeeder (elements, images, warnings dual system)
│       └── inclusion.py         # InclusionSeeder (tier-element relationships)
│
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
| `TierElementInclusion` | Tier-element relationships |
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

## Seeds Architecture

### Data Module Pattern

```python
# seeds/data/nueva_categoria.py
from decimal import Decimal
from database.seeds.data.common import CategoryData, TierData, ElementData

CATEGORY_SLUG = "nueva-cat"

CATEGORY: CategoryData = {
    "slug": CATEGORY_SLUG,
    "name": "Nueva Categoria",
    "client_type": "particular",
    ...
}

TIERS: list[TierData] = [...]
ELEMENTS: list[ElementData] = [...]
CATEGORY_WARNINGS: list[WarningData] = [...]
ADDITIONAL_SERVICES: list[AdditionalServiceData] = [...]
BASE_DOCUMENTATION: list[BaseDocumentationData] = [...]
PROMPT_SECTIONS: list[PromptSectionData] = [...]
```

### Adding a New Category

1. Create `data/nueva_categoria.py` with all required constants
2. Import in `run_all_seeds.py`:
   ```python
   from database.seeds.data import nueva_categoria
   # ...
   await seed_category(nueva_categoria)
   ```
3. Add tier mappings in `data/tier_mappings.py` if needed
4. No modifications needed to seeders (they are reusable)

## Element Warning System (Dual Architecture)

### Overview

Element warnings use a **dual system** for compatibility:

1. **Inline Warnings**: `warnings.element_id` (FK to elements) - Used by agent/tariff services
2. **Association Warnings**: `element_warning_associations` (many-to-many) - Used by admin panel

**Both representations are created automatically** by seeds to maintain synchronization.

### Why Two Systems?

- Agent services query warnings via `warnings.element_id` directly
- Admin panel queries via `element_warning_associations` for flexibility
- Seeds create both to avoid breaking changes and data inconsistencies

### Database Schema

```sql
-- System 1: Inline (agent uses this)
warnings (
    id,
    code,
    message,
    element_id FK → elements.id  -- Direct foreign key
)

-- System 2: Associations (admin uses this)
element_warning_associations (
    id,
    element_id FK → elements.id,
    warning_id FK → warnings.id,
    show_condition,          -- Extra flexibility
    threshold_quantity
)
```

### How Seeds Work

ElementSeeder automatically:
1. Creates warnings with `element_id` (inline)
2. Creates corresponding `ElementWarningAssociation` entries
3. Uses deterministic UUIDs for idempotency
4. Logs statistics: "X created, Y updated, Z associations created"

### Adding Warnings to Elements

Simply add warnings to your element data:

```python
# seeds/data/motos_part.py
ELEMENTS: list[ElementData] = [
    {
        "code": "MY_ELEMENT",
        "warnings": [  # ← Just add here
            {
                "code": "MY_WARNING",
                "message": "Warning message",
                "severity": "warning",
            }
        ]
    }
]
```

**No additional code needed** - both inline and associations are created automatically.

### Verification

After running seeds, verify synchronization:

```bash
# Run verification script
python -m database.seeds.verify_warning_sync

# Expected output:
# ✅ SUCCESS: Both systems have 39 warnings (SYNCED)
```

### Affected Code

**Consumers (Inline)**:
- `agent/services/tarifa_service.py` - `get_warnings_by_scope()`

**Consumers (Associations)**:
- `agent/services/element_service.py` - `get_element_warnings()`
- `api/routes/elements.py` - `GET /elements/{id}/warnings`

### Documentation

See `database/seeds/WARNING_SYSTEM.md` for complete documentation.

## Commands

```bash
# Create migration
alembic revision -m "description"

# Run migrations
alembic upgrade head

# Rollback one
alembic downgrade -1

# Run seeds
python -m database.seeds.run_all_seeds

# Validate seeds
python -m database.seeds.validate_elements_seed

# Verify warning synchronization
python -m database.seeds.verify_warning_sync
```

## Critical Rules

- ALWAYS use UUID as primary key
- ALWAYS include timestamps
- ALWAYS use `DateTime(timezone=True)`
- ALWAYS use `lazy="selectin"` for relationships
- NEVER use synchronous operations
- Seeds use deterministic UUIDs for idempotency

### Auto-invoke Skills

When performing these actions, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Creating/modifying database models | `msia-database` |
| Writing Alembic migrations | `sqlalchemy-async` |
