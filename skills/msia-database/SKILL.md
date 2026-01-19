---
name: msia-database
description: >
  MSI-a database patterns using SQLAlchemy and Alembic.
  Trigger: When creating/modifying database models, writing migrations, or working with seeds.
metadata:
  author: msi-automotive
  version: "2.0"
  scope: [root, database]
  auto_invoke: "Creating/modifying database models"
---

## Database Structure

```
database/
├── models.py           # All SQLAlchemy models
├── connection.py       # Async engine and session
├── __init__.py
├── seeds/
│   ├── run_all_seeds.py         # Main orchestrator
│   ├── seed_utils.py            # Deterministic UUIDs
│   ├── validate_elements_seed.py
│   │
│   ├── data/                    # Data definitions (constants only)
│   │   ├── common.py            # Shared types and constants
│   │   ├── motos_part.py        # Motos particular data
│   │   ├── aseicars_prof.py     # Autocaravanas profesional data
│   │   └── tier_mappings.py     # Tier-element mappings
│   │
│   └── seeders/                 # Reusable seeding logic
│       ├── base.py              # BaseSeeder with uniform logging
│       ├── category.py          # CategorySeeder
│       ├── element.py           # ElementSeeder
│       └── inclusion.py         # InclusionSeeder
│
└── alembic/
    ├── env.py
    ├── script.py.mako
    └── versions/
```

## Key Models

| Model | Description |
|-------|-------------|
| `User` | WhatsApp users (phone, client_type) |
| `ConversationHistory` | Conversation metadata |
| `VehicleCategory` | Categories by client type |
| `TariffTier` | Pricing tiers (T1-T6) |
| `Element` | Homologable elements |
| `TierElementInclusion` | Tier - Element relationships |
| `Warning` | Contextual warnings |
| `AdminUser` | Admin panel users |
| `RegulatoryDocument` | RAG documents |
| `DocumentChunk` | RAG chunks |

## Model Pattern

```python
import uuid
from datetime import datetime, UTC
from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

class Element(Base):
    """Element model - Catalog of homologable elements per category."""
    __tablename__ = "elements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicle_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    category: Mapped["VehicleCategory"] = relationship(back_populates="elements")

    __table_args__ = (
        UniqueConstraint("category_id", "code", name="uq_category_element_code"),
    )
```

## Alembic Migration Pattern

```python
"""Add elements table

Revision ID: 012_element_system
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "012_element_system"
down_revision = "011_section_mappings"

def upgrade() -> None:
    op.create_table(
        "elements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("category_id", UUID(as_uuid=True), 
                  sa.ForeignKey("vehicle_categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("keywords", JSONB, nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_elements_category_id", "elements", ["category_id"])
    op.create_unique_constraint("uq_category_element_code", "elements", ["category_id", "code"])

def downgrade() -> None:
    op.drop_constraint("uq_category_element_code", "elements")
    op.drop_index("ix_elements_category_id")
    op.drop_table("elements")
```

## Seed Architecture

### Data Module Pattern

```python
# seeds/data/motos_part.py
from decimal import Decimal
from database.seeds.data.common import CategoryData, TierData, ElementData

CATEGORY_SLUG = "motos-part"

CATEGORY: CategoryData = {
    "slug": CATEGORY_SLUG,
    "name": "Motocicletas",
    "client_type": "particular",
    ...
}

TIERS: list[TierData] = [
    {"code": "T1", "name": "Proyecto Completo", "price": Decimal("410.00"), ...},
    ...
]

ELEMENTS: list[ElementData] = [
    {"code": "ESCAPE", "name": "Escape", "keywords": [...], "warnings": [...], ...},
    ...
]

CATEGORY_WARNINGS: list[WarningData] = [...]
ADDITIONAL_SERVICES: list[AdditionalServiceData] = [...]
BASE_DOCUMENTATION: list[BaseDocumentationData] = [...]
PROMPT_SECTIONS: list[PromptSectionData] = [...]
```

### Seeder Pattern

```python
# seeds/seeders/base.py
class BaseSeeder:
    def __init__(self, category_slug: str, session: AsyncSession):
        self.category_slug = category_slug
        self.session = session
        self.stats = {"created": 0, "updated": 0, "skipped": 0}

    def log_created(self, entity_type: str, code: str) -> None:
        self.stats["created"] += 1
        logger.info(f"  + {entity_type} {code}: Created")

    def log_updated(self, entity_type: str, code: str) -> None:
        self.stats["updated"] += 1
        logger.info(f"  ~ {entity_type} {code}: Updated")

    async def upsert(self, model_class, deterministic_id, data: dict) -> tuple[Any, str]:
        existing = await self.session.get(model_class, deterministic_id)
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            self.log_updated(...)
            return existing, "updated"
        instance = model_class(id=deterministic_id, **data)
        self.session.add(instance)
        self.log_created(...)
        return instance, "created"
```

### Adding a New Category

1. Create `seeds/data/nueva_categoria.py` with all constants
2. Import in `run_all_seeds.py` and add:
   ```python
   await seed_category(nueva_categoria)
   ```
3. Add tier mappings in `tier_mappings.py` if needed
4. No modifications to seeders required

## Connection Pattern

```python
# database/connection.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from shared.config import settings

DATABASE_URL = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(DATABASE_URL, echo=settings.debug, pool_size=5, max_overflow=10)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

## Common Queries

```python
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Get with relationships
result = await session.execute(
    select(VehicleCategory)
    .options(selectinload(VehicleCategory.elements))
    .where(VehicleCategory.slug == "motos-part")
)
category = result.scalar_one_or_none()

# Filter active
result = await session.execute(
    select(Element)
    .where(Element.category_id == category_id)
    .where(Element.is_active == True)
    .order_by(Element.sort_order)
)
elements = result.scalars().all()
```

## Critical Rules

- ALWAYS use UUID as primary key
- ALWAYS include `created_at` and `updated_at` timestamps
- ALWAYS use `DateTime(timezone=True)` for timestamps
- ALWAYS use `ondelete="CASCADE"` or `"SET NULL"` on ForeignKeys
- ALWAYS create indexes for frequently queried columns
- ALWAYS use `lazy="selectin"` for relationships (async-safe)
- NEVER use synchronous operations
- ALWAYS use `expire_on_commit=False` for async sessions
- Seeds use deterministic UUIDs for idempotency

## Commands

```bash
# Create migration
alembic revision -m "description"

# Run migrations
alembic upgrade head

# Rollback one
alembic downgrade -1

# Show current
alembic current

# Run seeds
python -m database.seeds.run_all_seeds

# Validate seeds
python -m database.seeds.validate_elements_seed
```

## Resources

- [sqlalchemy-async skill](../sqlalchemy-async/SKILL.md) - Generic patterns
