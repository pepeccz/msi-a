# Estándares Database (PostgreSQL + SQLAlchemy + Alembic)

Patrones para modelos, migraciones y seeds de MSI-a.

---

## 1. Model Definition Pattern

```python
from sqlalchemy import String, DateTime, Boolean, JSONB, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from database.connection import Base
from datetime import datetime, UTC
import uuid

class MyModel(Base):
    __tablename__ = "my_models"
    
    # ✅ UUID primary key (OBLIGATORIO)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # ✅ Timezone-aware timestamps (OBLIGATORIO)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(UTC),
        nullable=True,
    )
    
    # Strings con constraints
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,  # Si se busca frecuentemente
    )
    
    # JSONB para datos flexibles (✅ NOT TEXT)
    metadata_: Mapped[dict] = mapped_column(
        "metadata",  # Nombre en DB
        JSONB,
        nullable=False,
        default=dict,  # ✅ Siempre default
    )
    
    # Soft delete
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Foreign key con ondelete (✅ OBLIGATORIO especificar)
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # ✅ Relationship con lazy="selectin" (async-safe)
    category: Mapped["Category"] = relationship(
        "Category",
        back_populates="items",
        lazy="selectin",  # ✅ NUNCA "joined" en async
    )
```

---

## 2. Migration Pattern

```python
"""add my_models table

Revision ID: 035_add_my_models
Revises: 034_previous_migration
Create Date: 2026-02-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '035_add_my_models'
down_revision = '034_previous_migration'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Create table
    op.create_table(
        'my_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('metadata', postgresql.JSONB(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['category_id'],
            ['categories.id'],
            name=op.f('fk_my_models_category_id_categories'),
            ondelete='CASCADE'  # ✅ OBLIGATORIO
        ),
    )
    
    # 2. Create indexes DESPUÉS de create table
    op.create_index(op.f('ix_my_models_name'), 'my_models', ['name'])
    op.create_index(op.f('ix_my_models_category_id'), 'my_models', ['category_id'])

def downgrade() -> None:
    # ✅ OBLIGATORIO implementar (nunca pass)
    # 1. Drop indexes ANTES de drop table
    op.drop_index(op.f('ix_my_models_category_id'), table_name='my_models')
    op.drop_index(op.f('ix_my_models_name'), table_name='my_models')
    
    # 2. Drop table
    op.drop_table('my_models')
```

---

## 3. Seed Pattern (Deterministic UUIDs)

```python
# database/seeds/seeders/my_seeder.py
from database.seeds.seed_utils import SEED_NAMESPACE
import uuid

def my_model_uuid(category_slug: str, code: str) -> uuid.UUID:
    """Generate deterministic UUID for MyModel."""
    return uuid.uuid5(SEED_NAMESPACE, f"mymodel:{category_slug}:{code}")

class MyModelSeeder(BaseSeeder):
    async def seed(self, category_slug: str, data: list[dict]):
        for item in data:
            item_id = my_model_uuid(category_slug, item["code"])
            
            await self.upsert(
                MyModel,
                deterministic_id=item_id,
                data={
                    "name": item["name"],
                    "metadata": item.get("metadata", {}),
                    "category_id": category_id,
                },
                entity_type="my_model",
                code=item["code"],
            )
```

---

## 4. Dual Warning System (CRÍTICO para elements)

```python
# Sistema 1: Inline (agent usa esto)
warning = Warning(
    id=warning_uuid(category_slug, warning_data["code"]),
    code=warning_data["code"],
    message=warning_data["message"],
    severity=warning_data["severity"],
    element_id=element_id,  # ← FK directo
)

# Sistema 2: Association (admin usa esto)
association = ElementWarningAssociation(
    id=assoc_uuid(element_id, warning_id),
    element_id=element_id,
    warning_id=warning_id,
    show_condition="always",
)

# ✅ AMBOS deben existir SIEMPRE
```

---

## 5. Self-Referential Hierarchy

```python
class Element(Base):
    __tablename__ = "elements"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    
    # Self-reference
    parent_element_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("elements.id", ondelete="CASCADE"),
        nullable=True,
    )
    
    # Variant system
    variant_type: Mapped[str | None] = mapped_column(String(50))  # "color", "size"
    variant_code: Mapped[str | None] = mapped_column(String(50))  # "red", "large"
    
    # Relationships
    parent: Mapped["Element | None"] = relationship(
        "Element",
        remote_side=[id],
        back_populates="children",
        lazy="selectin",
    )
    children: Mapped[list["Element"]] = relationship(
        back_populates="parent",
        lazy="selectin",
    )

# Seeding requiere dos pasadas
# Pass 1: Crear todos los elements sin parent
# Pass 2: Resolver parent_element_id
```

---

## 6. Conditional Fields

```python
class ElementRequiredField(Base):
    __tablename__ = "element_required_fields"
    
    field_name: Mapped[str]
    field_type: Mapped[str]  # "text", "number", "boolean", "select"
    is_required: Mapped[bool]
    
    # Conditional display
    condition_field_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("element_required_fields.id"),  # Self-reference
        nullable=True,
    )
    condition_operator: Mapped[str | None]  # "equals", "not_equals"
    condition_value: Mapped[str | None]
    
    # ✅ Validar circular references en application code
```

---

## 7. Tier Inheritance

```python
class TierElementInclusion(Base):
    __tablename__ = "tier_element_inclusions"
    
    tier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tariff_tiers.id"))
    
    # XOR: Either element OR tier
    element_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("elements.id", ondelete="CASCADE")
    )
    included_tier_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tariff_tiers.id", ondelete="CASCADE")
    )
    
    # Check constraint in migration:
    # CHECK ((element_id IS NOT NULL AND included_tier_id IS NULL) OR
    #        (element_id IS NULL AND included_tier_id IS NOT NULL))
```

---

## 8. Reglas Críticas

1. ✅ **SIEMPRE** UUID primary key (nunca auto-increment)
2. ✅ **SIEMPRE** DateTime(timezone=True)
3. ✅ **SIEMPRE** lazy="selectin" para relaciones
4. ✅ **SIEMPRE** ondelete="CASCADE" o "SET NULL"
5. ✅ **SIEMPRE** implementar downgrade()
6. ✅ **SIEMPRE** JSONB con default=dict o default=list
7. ✅ **SIEMPRE** UUIDs determinísticos en seeds (UUID v5)
8. ✅ **SIEMPRE** dual warning system para elements
9. ✅ **SIEMPRE** indexes DESPUÉS de create table en upgrade
10. ✅ **SIEMPRE** drop indexes ANTES de drop table en downgrade
11. ❌ **NUNCA** lazy="joined" en async
12. ❌ **NUNCA** TEXT con JSON → usar JSONB
13. ❌ **NUNCA** hard-delete seed data → usar is_active=False
14. ❌ **NUNCA** modificar migraciones existentes → crear nueva

---

**Referencias:**
- `database/AGENTS.md` - Inventario completo de modelos
- `database/seeds/WARNING_SYSTEM.md` - Dual warning system
- `skills/sqlalchemy-async/SKILL.md`

**Última actualización:** Febrero 2026
