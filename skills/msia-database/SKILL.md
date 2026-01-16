---
name: msia-database
description: >
  MSI-a database patterns using SQLAlchemy and Alembic.
  Trigger: When creating/modifying database models, writing migrations, or working with seeds.
metadata:
  author: msi-automotive
  version: "1.0"
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
| `User` | WhatsApp users (phone, client_type) |
| `ConversationHistory` | Conversation metadata |
| `VehicleCategory` | Categories by client type |
| `TariffTier` | Pricing tiers (T1-T6) |
| `Element` | Homologable elements |
| `TierElementInclusion` | Tier ↔ Element relationships |
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
    """
    Element model - Catalog of homologable elements per category.
    """
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
    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Unique element code (e.g., 'ESC_MEC')",
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    keywords: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Keywords for matching",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
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

    # Relationships
    category: Mapped["VehicleCategory"] = relationship(
        "VehicleCategory",
        back_populates="elements",
    )

    __table_args__ = (
        UniqueConstraint("category_id", "code", name="uq_category_element_code"),
    )

    def __repr__(self) -> str:
        return f"<Element(id={self.id}, code={self.code})>"
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
        sa.Column("category_id", UUID(as_uuid=True), sa.ForeignKey("vehicle_categories.id", ondelete="CASCADE"), nullable=False),
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

## Seed Pattern

```python
# seeds/motos_elements_seed.py
import asyncio
from sqlalchemy import select
from database.connection import async_session
from database.models import VehicleCategory, Element

ELEMENTS = [
    {
        "code": "ESCAPE",
        "name": "Escape/Silenciador",
        "keywords": ["escape", "silenciador", "tubo de escape", "exhaust"],
    },
    {
        "code": "MANILLAR",
        "name": "Manillar",
        "keywords": ["manillar", "handlebar", "puños"],
    },
    # ...
]

async def seed_motos_elements():
    async with async_session() as session:
        # Get category
        result = await session.execute(
            select(VehicleCategory).where(VehicleCategory.slug == "motos-part")
        )
        category = result.scalar_one_or_none()
        
        if not category:
            print("Category motos-part not found")
            return
        
        for elem_data in ELEMENTS:
            # Check if exists
            existing = await session.execute(
                select(Element).where(
                    Element.category_id == category.id,
                    Element.code == elem_data["code"]
                )
            )
            if existing.scalar_one_or_none():
                continue
            
            element = Element(
                category_id=category.id,
                **elem_data
            )
            session.add(element)
        
        await session.commit()
        print(f"Seeded {len(ELEMENTS)} elements for motos-part")

if __name__ == "__main__":
    asyncio.run(seed_motos_elements())
```

## Connection Pattern

```python
# database/connection.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from shared.config import settings

DATABASE_URL = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(
    DATABASE_URL,
    echo=settings.debug,
    pool_size=5,
    max_overflow=10,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

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
```

## Resources

- [sqlalchemy-async skill](../sqlalchemy-async/SKILL.md) - Generic patterns
