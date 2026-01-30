---
name: msia-database
description: >
  MSI-a database patterns using SQLAlchemy and Alembic.
  Trigger: When creating/modifying database models, writing migrations, or working with seeds.
metadata:
  author: msi-automotive
  version: "3.0"
  scope: [root, database]
  auto_invoke: "Creating/modifying database models"
---

## Overview

The MSI-a database component provides a complete PostgreSQL schema with 32 models, Alembic migrations, and a sophisticated seed system for tariff/element data.

### Key Features

- **32 SQLAlchemy Models**: Complete schema for users, tariffs, RAG, cases, admin, monitoring
- **Fully Async**: AsyncPG engine with connection pooling
- **Dual Warning System**: Element warnings stored inline + associations for compatibility
- **Deterministic UUID Seeding**: UUID v5 for idempotent re-runnable seeds
- **Tier Inheritance**: Tier-to-tier relationships via `TierElementInclusion`
- **Self-Referential Hierarchy**: Element parent-child with variants
- **Conditional Fields**: `ElementRequiredField` with condition_field_id logic
- **34 Alembic Migrations**: Complete migration history with rollback support

---

## Database Structure

```
database/
├── models.py                    # All 32 SQLAlchemy models (3,224 lines)
├── connection.py                # Async engine, session factory (88 lines)
├── __init__.py                  # Package exports
│
├── migrations/
│   └── apply_element_fixes.sql  # Manual SQL fixes (273 lines)
│
├── seeds/
│   ├── __init__.py
│   ├── run_all_seeds.py         # Main orchestrator (123 lines)
│   ├── seed_utils.py            # UUID v5 generation (132 lines)
│   ├── validate_elements_seed.py # Validation (176 lines)
│   ├── verify_warning_sync.py   # Dual warning verification (152 lines)
│   ├── create_admin_user.py     # Admin user creation (74 lines)
│   ├── WARNING_SYSTEM.md        # Dual warning docs (248 lines)
│   │
│   ├── data/                    # Data definitions
│   │   ├── __init__.py
│   │   ├── common.py            # TypedDict + constants (140 lines)
│   │   ├── motos_part.py        # Motos particular (2,222 lines)
│   │   ├── aseicars_prof.py     # Autocaravanas (817 lines)
│   │   └── tier_mappings.py     # Element-tier relationships (273 lines)
│   │
│   └── seeders/                 # Seeder classes
│       ├── __init__.py
│       ├── base.py              # BaseSeeder (133 lines)
│       ├── category.py          # CategorySeeder (267 lines)
│       ├── element.py           # ElementSeeder (304 lines)
│       └── inclusion.py         # InclusionSeeder (328 lines)
│
└── alembic/
    ├── env.py                   # Environment config (97 lines)
    ├── script.py.mako           # Migration template (26 lines)
    └── versions/                # 34 migrations (4,490 total lines)
```

---

## Complete Model Inventory (32 Models)

### Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CORE MODELS                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  User ──┬─→ ConversationHistory ──→ ConversationMessage                 │
│         │                                                                │
│         └─→ Case ──┬─→ CaseImage                                        │
│                    └─→ CaseElementData                                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         TARIFF SYSTEM                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  VehicleCategory ──┬─→ TariffTier ──┬─→ TierElementInclusion ──┐       │
│                    │                 │                           ↓       │
│                    ├─→ BaseDocumentation                     Element    │
│                    │                                            ↑ │      │
│                    ├─→ Warning (category)                      │ │      │
│                    │                                            │ │      │
│                    ├─→ AdditionalService                        │ │      │
│                    │                                            │ │      │
│                    └─→ TariffPromptSection                      │ │      │
│                                                                  │ │      │
│  Element ──┬─→ ElementImage                                    │ │      │
│            │                                                    │ │      │
│            ├─→ ElementRequiredField ─┐ (self-referential)      │ │      │
│            │                          │                         │ │      │
│            ├─→ parent_element_id ─────┘                        │ │      │
│            │                                                    │ │      │
│            └─→ ElementWarningAssociation ──→ Warning (element) ─┘ │      │
│                                                                    │      │
│  TierElementInclusion ──→ included_tier_id (tier inheritance) ────┘      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                           RAG SYSTEM                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  RegulatoryDocument ──→ DocumentChunk                                   │
│                                                                          │
│  RAGQuery ──→ QueryCitation ──→ DocumentChunk                           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                      ADMIN & MONITORING                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  AdminUser ──→ AdminAccessLog                                           │
│                                                                          │
│  UploadedImage, ContainerErrorLog, TokenUsage, LLMUsageMetric,          │
│  ToolCallLog, ResponseConstraint, Escalation, AuditLog                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Core Models (5)

| Model | Table | Key Relationships | Purpose |
|-------|-------|-------------------|---------|
| `User` | `users` | → ConversationHistory, Case | WhatsApp users; E.164 phone, client_type, chatwoot_contact_id |
| `ConversationHistory` | `conversation_history` | → ConversationMessage | Conversation metadata; chatwoot_conversation_id (unique), message_count |
| `ConversationMessage` | `conversation_messages` | ← ConversationHistory | Individual messages; role (user/assistant), has_images flag |
| `Policy` | `policies` | None | Business policies/FAQ; key-value with category |
| `SystemSetting` | `system_settings` | None | App configuration; value_type (string/integer/boolean/json) |

### Tariff System Models (11)

| Model | Table | Key Relationships | Purpose |
|-------|-------|-------------------|---------|
| `VehicleCategory` | `vehicle_categories` | → TariffTier, Element, Warning | Categories by client_type; slug, icon, sort_order |
| `TariffTier` | `tariff_tiers` | ← VehicleCategory, → TierElementInclusion | Pricing tiers (T1-T6); JSONB classification_rules |
| `BaseDocumentation` | `base_documentation` | ← VehicleCategory | Base required docs per category |
| `Element` | `elements` | ← VehicleCategory, → ElementImage, ElementRequiredField, parent (self) | Homologable elements; JSONB keywords/aliases, variant system |
| `ElementImage` | `element_images` | ← Element | Element images; image_type, status (active/placeholder) |
| `ElementRequiredField` | `element_required_fields` | ← Element, → condition_field (self) | Required fields; conditional display logic |
| `TierElementInclusion` | `tier_element_inclusions` | ← TariffTier, → Element OR TariffTier | Tier-element relationships; supports tier inheritance |
| `ElementWarningAssociation` | `element_warning_associations` | → Element, Warning | Many-to-many element-warning (admin panel) |
| `Warning` | `warnings` | → VehicleCategory OR TariffTier OR Element | Scoped warnings; XOR scoping, JSONB trigger_conditions |
| `AdditionalService` | `additional_services` | → VehicleCategory (optional) | Extra services; code, price, category_id |
| `TariffPromptSection` | `tariff_prompt_sections` | ← VehicleCategory | Editable AI prompts; section_type, version |

### RAG System Models (4)

| Model | Table | Key Relationships | Purpose |
|-------|-------|-------------------|---------|
| `RegulatoryDocument` | `regulatory_documents` | → DocumentChunk | RAG docs; file_hash (SHA256), JSONB section_mappings |
| `DocumentChunk` | `document_chunks` | ← RegulatoryDocument, → QueryCitation | Semantic chunks; qdrant_point_id, JSONB heading_hierarchy |
| `RAGQuery` | `rag_queries` | → QueryCitation, → User (optional) | Query analytics; performance metrics, was_cache_hit |
| `QueryCitation` | `query_citations` | ← RAGQuery, → DocumentChunk | Query-chunk links; rank, similarity/rerank scores |

### Case Management Models (4)

| Model | Table | Key Relationships | Purpose |
|-------|-------|-------------------|---------|
| `Case` | `cases` | ← User, → VehicleCategory, Escalation, CaseImage, CaseElementData | Expedientes; vehicle data, tariff, ITV, workshop, dimensions |
| `CaseImage` | `case_images` | ← Case | User-uploaded images; element_code, is_valid (tri-state) |
| `CaseElementData` | `case_element_data` | ← Case | Per-element data; JSONB field_values, status (pending/completed) |
| `Escalation` | `escalations` | → ConversationHistory | Escalations; reason, source (tool_call/auto/error) |

### Admin & Auth Models (3)

| Model | Table | Key Relationships | Purpose |
|-------|-------|-------------------|---------|
| `AdminUser` | `admin_users` | → AdminAccessLog, created_by (self) | Admin users; bcrypt password_hash, role (admin/user) |
| `AdminAccessLog` | `admin_access_log` | ← AdminUser | Login/logout logs; action, ip_address, user_agent |
| `UploadedImage` | `uploaded_images` | None | Image metadata; mime_type, dimensions, category |

### Monitoring & Audit Models (5)

| Model | Table | Key Relationships | Purpose |
|-------|-------|-------------------|---------|
| `ContainerErrorLog` | `container_error_logs` | → AdminUser (resolver) | Docker errors; service_name, stack_trace, resolution status |
| `TokenUsage` | `token_usage` | None | Monthly LLM tokens; BigInteger input/output_tokens |
| `LLMUsageMetric` | `llm_usage_metrics` | → ConversationHistory (optional) | Hybrid LLM metrics; tier (local/cloud), fallback tracking |
| `ToolCallLog` | `tool_call_logs` | → ConversationHistory | Agent tool calls; JSONB parameters, execution_time_ms |
| `ResponseConstraint` | `response_constraints` | → VehicleCategory (optional) | Anti-hallucination rules; detection_pattern (regex) |
| `AuditLog` | `audit_log` | → AdminUser | Change audit; entity_type, JSONB changes |

---

## Model Patterns

### Complete Model Example

```python
import uuid
from datetime import datetime, UTC
from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, Text, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase

class Base(DeclarativeBase):
    pass

class Element(Base):
    """
    Element model - Catalog of homologable elements per category.
    
    Supports:
    - JSONB keywords/aliases for flexible search
    - Self-referential parent-child hierarchy
    - Variant system (variant_type, variant_code)
    - Soft delete via is_active
    """
    __tablename__ = "elements"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Foreign keys
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicle_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_element_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("elements.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    # Basic fields
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    
    # JSONB fields
    keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    multi_select_keywords: Mapped[list[str]] = mapped_column(JSONB, default=list)
    
    # Variant system
    variant_type: Mapped[str | None] = mapped_column(String(50))
    variant_code: Mapped[str | None] = mapped_column(String(50))
    
    # Flags
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    inherit_parent_data: Mapped[bool] = mapped_column(Boolean, default=False)
    question_hint: Mapped[str | None] = mapped_column(Text)
    
    # Timestamps
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

    # Relationships (always use lazy="selectin" for async)
    category: Mapped["VehicleCategory"] = relationship(
        back_populates="elements",
        lazy="selectin",
    )
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
    images: Mapped[list["ElementImage"]] = relationship(
        back_populates="element",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    required_fields: Mapped[list["ElementRequiredField"]] = relationship(
        back_populates="element",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint("category_id", "code", name="uq_category_element_code"),
        Index("ix_elements_active", "is_active"),
    )
```

### Key Model Features

**UUID Primary Keys**:
```python
id: Mapped[uuid.UUID] = mapped_column(
    UUID(as_uuid=True),
    primary_key=True,
    default=uuid.uuid4,  # Auto-generate for new records
)
```

**Timezone-aware Timestamps**:
```python
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=lambda: datetime.now(UTC),
)
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    onupdate=lambda: datetime.now(UTC),
)
```

**Foreign Keys with Delete Policies**:
```python
category_id: Mapped[uuid.UUID] = mapped_column(
    ForeignKey("vehicle_categories.id", ondelete="CASCADE"),  # Delete elements when category deleted
    index=True,  # Always index FKs
)
parent_element_id: Mapped[uuid.UUID | None] = mapped_column(
    ForeignKey("elements.id", ondelete="SET NULL"),  # Preserve children if parent deleted
)
```

**JSONB for Flexible Data**:
```python
keywords: Mapped[list[str]] = mapped_column(JSONB, default=list)
metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
```

**Async-safe Relationships**:
```python
category: Mapped["VehicleCategory"] = relationship(
    back_populates="elements",
    lazy="selectin",  # ALWAYS use selectin for async
)
```

---

## Alembic Migration Patterns

### Complete Migration Example

```python
"""Add element required fields table

Revision ID: 030_element_required_fields
Revises: 029_tool_call_logs
Create Date: 2024-01-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# Revision identifiers
revision = "030_element_required_fields"
down_revision = "029_tool_call_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add element required fields table."""
    # Create table
    op.create_table(
        "element_required_fields",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("element_id", UUID(as_uuid=True), 
                  sa.ForeignKey("elements.id", ondelete="CASCADE"), 
                  nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("field_type", sa.String(50), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("placeholder", sa.String(200)),
        sa.Column("is_required", sa.Boolean(), default=True),
        sa.Column("validation_rules", JSONB, server_default="{}"),
        
        # Conditional display
        sa.Column("condition_field_id", UUID(as_uuid=True),
                  sa.ForeignKey("element_required_fields.id", ondelete="SET NULL")),
        sa.Column("condition_operator", sa.String(50)),
        sa.Column("condition_value", sa.String(200)),
        
        sa.Column("llm_instruction", sa.Text()),
        sa.Column("sort_order", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Create indexes AFTER table creation
    op.create_index(
        op.f("ix_element_required_fields_element_id"),
        "element_required_fields",
        ["element_id"]
    )
    op.create_index(
        op.f("ix_element_required_fields_sort_order"),
        "element_required_fields",
        ["sort_order"]
    )
    
    # Create constraints
    op.create_unique_constraint(
        op.f("uq_element_field_name"),
        "element_required_fields",
        ["element_id", "field_name"]
    )


def downgrade() -> None:
    """Remove element required fields table."""
    # Drop constraints first
    op.drop_constraint(
        op.f("uq_element_field_name"),
        "element_required_fields"
    )
    
    # Drop indexes
    op.drop_index(op.f("ix_element_required_fields_sort_order"))
    op.drop_index(op.f("ix_element_required_fields_element_id"))
    
    # Drop table last
    op.drop_table("element_required_fields")
```

### Migration Best Practices

**Always include downgrade()**:
```python
def downgrade() -> None:
    # NEVER leave as pass - always implement rollback
    op.drop_table("my_table")
```

**Use op.f() for naming** (Alembic auto-naming):
```python
op.create_index(
    op.f("ix_users_email"),  # Auto-generates: ix_users_email
    "users",
    ["email"]
)
```

**Drop in reverse order**:
```python
def downgrade() -> None:
    op.drop_constraint(...)  # 1. Constraints
    op.drop_index(...)        # 2. Indexes
    op.drop_table(...)        # 3. Table
```

**Use batch operations** for SQLite compatibility (testing):
```python
with op.batch_alter_table("users") as batch_op:
    batch_op.add_column(sa.Column("new_field", sa.String(50)))
```

---

## Connection & Session Management

### Async Engine Setup

```python
# database/connection.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from shared.config import get_settings

settings = get_settings()

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,           # Connection pool size
    max_overflow=20,        # Max extra connections during peak
    pool_pre_ping=True,     # Verify connection before use (prevents stale connections)
    echo=False,             # Set to True for SQL logging during development
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Keep objects usable after commit
    autocommit=False,
    autoflush=False,
)

# Alias for backward compatibility
async_session_factory = AsyncSessionLocal
```

### Session Context Manager

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_async_session():
    """
    Async context manager that yields a session.
    
    Usage:
        async with get_async_session() as session:
            result = await session.execute(select(User))
            user = result.scalar_one_or_none()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

### Usage in Routes/Services

```python
from database.connection import get_async_session

# In FastAPI route
@router.get("/users/{user_id}")
async def get_user(user_id: UUID):
    async with get_async_session() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "User not found")
        return user

# In service method
class UserService:
    async def get_active_users(self):
        async with get_async_session() as session:
            result = await session.execute(
                select(User)
                .where(User.is_active == True)
                .order_by(User.created_at.desc())
            )
            return result.scalars().all()
```

---

## Common Query Patterns

### Eager Loading with selectinload

```python
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Load category with all relationships
result = await session.execute(
    select(VehicleCategory)
    .options(
        selectinload(VehicleCategory.elements),
        selectinload(VehicleCategory.tiers),
        selectinload(VehicleCategory.warnings),
    )
    .where(VehicleCategory.slug == "motos-part")
)
category = result.scalar_one_or_none()

# Access loaded relationships (no additional queries)
for element in category.elements:
    print(element.name)
```

### Filtering Active Records

```python
# Soft-delete pattern
result = await session.execute(
    select(Element)
    .where(Element.category_id == category_id)
    .where(Element.is_active == True)
    .order_by(Element.sort_order)
)
active_elements = result.scalars().all()
```

### JSONB Queries

```python
# Contains check (PostgreSQL)
result = await session.execute(
    select(Element)
    .where(Element.keywords.contains(["escape", "silenciador"]))
)

# JSON path query
result = await session.execute(
    select(TariffTier)
    .where(TariffTier.classification_rules["min_elements"].astext.cast(Integer) > 5)
)
```

### Pagination

```python
# Offset/limit pagination
page = 1
page_size = 20

result = await session.execute(
    select(User)
    .order_by(User.created_at.desc())
    .offset((page - 1) * page_size)
    .limit(page_size)
)
users = result.scalars().all()

# Get total count
count_result = await session.execute(
    select(func.count()).select_from(User)
)
total = count_result.scalar()
```

### Upsert (ON CONFLICT)

```python
from sqlalchemy.dialects.postgresql import insert

# Insert or update
stmt = insert(Element).values(
    id=element_id,
    code="ESCAPE",
    name="Escape",
)
stmt = stmt.on_conflict_do_update(
    index_elements=[Element.id],
    set_={
        "name": stmt.excluded.name,
        "updated_at": datetime.now(UTC),
    }
)
await session.execute(stmt)
await session.commit()
```

---

## Seeds Architecture

### Deterministic UUID Generation (Idempotency)

**All seed data uses UUID v5** with a fixed namespace:

```python
# seeds/seed_utils.py
import uuid

SEED_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")

def element_uuid(category_slug: str, element_code: str) -> uuid.UUID:
    """Generate deterministic UUID for an element."""
    return uuid.uuid5(SEED_NAMESPACE, f"element:{category_slug}:{element_code}")

def tier_uuid(category_slug: str, tier_code: str) -> uuid.UUID:
    return uuid.uuid5(SEED_NAMESPACE, f"tier:{category_slug}:{tier_code}")

def warning_uuid(category_slug: str, warning_code: str) -> uuid.UUID:
    return uuid.uuid5(SEED_NAMESPACE, f"warning:{category_slug}:{warning_code}")

def category_uuid(category_slug: str) -> uuid.UUID:
    return uuid.uuid5(SEED_NAMESPACE, f"category:{category_slug}")
```

**Benefits**:
- Re-running seeds won't create duplicates
- Same input always generates same UUID
- Enables upsert logic (INSERT ... ON CONFLICT DO UPDATE)
- Predictable foreign key relationships

### Data Module Pattern

**File**: `seeds/data/motos_part.py` (2,222 lines)

```python
from decimal import Decimal
from database.seeds.data.common import (
    CategoryData, TierData, ElementData, WarningData,
    AdditionalServiceData, BaseDocumentationData, PromptSectionData
)

# Category slug (must be unique)
CATEGORY_SLUG = "motos-part"

# Category definition
CATEGORY: CategoryData = {
    "slug": CATEGORY_SLUG,
    "name": "Motocicletas",
    "client_type": "particular",
    "icon": "🏍️",
    "sort_order": 1,
    "description": "Homologaciones para motocicletas particulares",
}

# Tiers (6 tiers for motos-part)
TIERS: list[TierData] = [
    {
        "code": "T1",
        "name": "Proyecto Completo",
        "price": Decimal("140.00"),
        "description": "Incluye proyecto completo",
        "classification_rules": {
            "max_elements": 1,
            "must_include": ["PROYECTO"],
        },
        "min_elements": 1,
        "max_elements": 1,
    },
    {
        "code": "T2",
        "name": "Proyecto + Transformación Ligera",
        "price": Decimal("175.00"),
        "classification_rules": {...},
        "min_elements": 1,
        "max_elements": 2,
    },
    # ... T3-T6
]

# Elements (39 elements for motos-part)
ELEMENTS: list[ElementData] = [
    {
        "code": "ESCAPE",
        "name": "Escape",
        "description": "Sistema de escape completo o parcial",
        "keywords": ["escape", "tubo de escape", "silenciador", "colector"],
        "aliases": ["tubos de escape", "sistema de escape"],
        "multi_select_keywords": ["escape trasero", "escape delantero"],
        
        # Images
        "images": [
            {
                "image_type": "example",
                "url": "https://example.com/escape-example.jpg",
                "alt_text": "Ejemplo de escape homologado",
                "status": "active",
            },
            {
                "image_type": "required_document",
                "url": "https://example.com/escape-doc.jpg",
                "alt_text": "Documentación necesaria",
                "user_instruction": "Fotografía del número de homologación del escape",
            },
        ],
        
        # Warnings (dual system: creates inline + association)
        "warnings": [
            {
                "code": "ESCAPE_HOMOLOGACION",
                "message": "El escape debe estar homologado según normativa ECE R41",
                "severity": "warning",
                "trigger_conditions": {},
            }
        ],
        
        # Required fields
        "required_fields": [
            {
                "field_name": "marca",
                "field_type": "text",
                "label": "Marca del escape",
                "is_required": True,
                "validation_rules": {"min_length": 2},
            },
            {
                "field_name": "numero_homologacion",
                "field_type": "text",
                "label": "Número de homologación",
                "is_required": True,
                "llm_instruction": "Extraer del formato 'e11*41/00*0000*00'",
            },
        ],
        
        "question_hint": "¿Has modificado el sistema de escape de la moto?",
        "is_active": True,
    },
    # ... more elements
]

# Category-level warnings
CATEGORY_WARNINGS: list[WarningData] = [
    {
        "code": "CATEGORIA_MOTOS_GENERAL",
        "message": "Todas las modificaciones deben cumplir normativa ECE",
        "severity": "info",
        "trigger_conditions": {},
    }
]

# Additional services
ADDITIONAL_SERVICES: list[AdditionalServiceData] = [
    {
        "code": "CERTIFICADO_TALLER",
        "name": "Certificado de taller",
        "price": Decimal("45.00"),
        "description": "Certificación del taller que realizó las modificaciones",
    },
    {
        "code": "EXPEDIENTE_URGENTE",
        "name": "Tramitación urgente",
        "price": Decimal("60.00"),
    },
]

# Base documentation
BASE_DOCUMENTATION: list[BaseDocumentationData] = [
    {
        "title": "Ficha técnica original",
        "description": "Ficha técnica original del vehículo",
        "is_mandatory": True,
    },
    {
        "title": "Fotografías del vehículo",
        "description": "4 fotografías (frontal, trasera, laterales)",
        "is_mandatory": True,
    },
]

# Prompt sections
PROMPT_SECTIONS: list[PromptSectionData] = [
    {
        "section_type": "algorithm",
        "content": "Algoritmo de clasificación de tarifas para motos...",
        "version": 1,
    },
    {
        "section_type": "recognition_table",
        "content": "Tabla de reconocimiento de elementos...",
        "version": 1,
    },
]
```

### Tier Mappings (Single Source of Truth)

**File**: `seeds/data/tier_mappings.py` (273 lines)

Defines which elements belong to which tiers:

```python
# Motos particular tier mappings
MOTOS_PART_MAPPINGS = {
    "T1_ONLY_ELEMENTS": ["PROYECTO"],
    "T3_ELEMENTS": ["ESCAPE", "MANILLAR", "SUSPENSION_DEL", ...],
    "T4_BASE_ELEMENTS": ["CARENADO", "ASIENTO", "COLECTOR", ...],
    
    # Tier configurations
    "TIER_CONFIGS": {
        "T1": {
            "elements": ["PROYECTO"],
            "inherited_tiers": [],  # No inheritance
        },
        "T2": {
            "elements": [],
            "inherited_tiers": ["T1"],  # Inherits from T1
        },
        "T3": {
            "elements": ["ESCAPE", "MANILLAR", "SUSPENSION_DEL", ...],
            "inherited_tiers": ["T2"],  # Inherits from T2 (and transitively T1)
        },
        "T4": {
            "elements": ["CARENADO", "ASIENTO", "COLECTOR", ...],
            "inherited_tiers": ["T3"],
        },
        "T5": {
            "elements": [],
            "inherited_tiers": ["T4"],
        },
        "T6": {
            "elements": [],
            "inherited_tiers": ["T5"],
        },
    }
}

def get_tier_mapping(category_slug: str):
    """Get tier mappings for a category."""
    mappings = {
        "motos-part": MOTOS_PART_MAPPINGS,
        "aseicars-prof": ASEICARS_PROF_MAPPINGS,
    }
    return mappings.get(category_slug)
```

**Usage**: `InclusionSeeder` reads this to create `TierElementInclusion` records.

### Seeder Classes

#### BaseSeeder (133 lines)

Abstract base with uniform logging and upsert:

```python
# seeds/seeders/base.py
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Callable

logger = logging.getLogger(__name__)

class BaseSeeder:
    """Base class for all seeders with uniform logging and stats."""
    
    def __init__(self, name: str):
        self.name = name
        self.stats = {"created": 0, "updated": 0, "skipped": 0}
    
    def log_created(self, entity_type: str, code: str) -> None:
        self.stats["created"] += 1
        logger.info(f"  + {entity_type} {code}: Created")
    
    def log_updated(self, entity_type: str, code: str) -> None:
        self.stats["updated"] += 1
        logger.info(f"  ~ {entity_type} {code}: Updated")
    
    def log_stats(self) -> None:
        logger.info(
            f"✅ {self.name}: Created {self.stats['created']}, "
            f"Updated {self.stats['updated']}, "
            f"Skipped {self.stats['skipped']}"
        )
    
    async def upsert(
        self,
        session: AsyncSession,
        model_class: type,
        deterministic_id: Any,
        data: dict,
    ) -> tuple[Any, str]:
        """Insert or update a record."""
        existing = await session.get(model_class, deterministic_id)
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            return existing, "updated"
        
        instance = model_class(id=deterministic_id, **data)
        session.add(instance)
        return instance, "created"
    
    async def upsert_with_uuid_fn(
        self,
        session: AsyncSession,
        model_class: type,
        uuid_fn: Callable[[], Any],
        data: dict,
    ) -> tuple[Any, str]:
        """Insert or update using a UUID generation function."""
        deterministic_id = uuid_fn()
        return await self.upsert(session, model_class, deterministic_id, data)
```

#### CategorySeeder (267 lines)

Seeds category + tiers + category-level data:

```python
from database.seeds.seeders.base import BaseSeeder
from database.seeds.seed_utils import category_uuid, tier_uuid, warning_uuid

class CategorySeeder(BaseSeeder):
    def __init__(self, session: AsyncSession, data_module):
        super().__init__(f"CategorySeeder({data_module.CATEGORY_SLUG})")
        self.session = session
        self.data = data_module
    
    async def seed(self):
        """Seed category and all related data."""
        logger.info(f"🌱 Seeding category: {self.data.CATEGORY_SLUG}")
        
        # 1. Seed category
        await self._seed_category()
        await self.session.flush()
        
        # 2. Seed tiers
        await self._seed_tiers()
        await self.session.flush()
        
        # 3. Seed category warnings
        await self._seed_category_warnings()
        await self.session.flush()
        
        # 4. Seed additional services
        await self._seed_additional_services()
        await self.session.flush()
        
        # 5. Seed base documentation
        await self._seed_base_documentation()
        await self.session.flush()
        
        # 6. Seed prompt sections
        await self._seed_prompt_sections()
        await self.session.flush()
        
        self.log_stats()
```

#### ElementSeeder (304 lines)

**Two-pass seeding** to handle self-referential parent relationships:

```python
class ElementSeeder(BaseSeeder):
    async def seed(self):
        """Seed elements with two-pass approach."""
        logger.info(f"🌱 Seeding elements for: {self.category_slug}")
        
        # Pass 1: Create all elements (without parent resolution)
        for element_data in self.elements_data:
            await self._create_element(element_data, resolve_parent=False)
        await self.session.flush()
        
        # Pass 2: Resolve parent relationships
        for element_data in self.elements_data:
            if element_data.get("parent_code"):
                await self._resolve_parent(element_data)
        await self.session.flush()
        
        self.log_stats()
    
    async def _create_element(self, element_data, resolve_parent=True):
        """Create element with images, warnings, and required fields."""
        # 1. Upsert element
        element, status = await self.upsert_with_uuid_fn(...)
        
        # 2. Seed images
        for image_data in element_data.get("images", []):
            await self._seed_element_image(element.id, image_data)
        
        # 3. Seed warnings (DUAL SYSTEM)
        for warning_data in element_data.get("warnings", []):
            await self._seed_element_warning_dual(element.id, warning_data)
        
        # 4. Seed required fields
        for field_data in element_data.get("required_fields", []):
            await self._seed_required_field(element.id, field_data)
    
    async def _seed_element_warning_dual(self, element_id, warning_data):
        """Create warning in BOTH systems (inline + association)."""
        # System 1: Inline (warnings.element_id)
        warning, status = await self.upsert_with_uuid_fn(
            self.session,
            Warning,
            uuid_fn=lambda: warning_uuid(self.category_slug, warning_data["code"]),
            data={
                "code": warning_data["code"],
                "message": warning_data["message"],
                "severity": warning_data["severity"],
                "element_id": element_id,  # ← Inline FK
            },
        )
        
        # System 2: Association (element_warning_associations)
        await self.upsert_with_uuid_fn(
            self.session,
            ElementWarningAssociation,
            uuid_fn=lambda: element_warning_assoc_uuid(element_id, warning.id),
            data={
                "element_id": element_id,
                "warning_id": warning.id,
                "show_condition": "always",
                "threshold_quantity": None,
            },
        )
```

#### InclusionSeeder (328 lines)

Seeds tier-element relationships from `tier_mappings.py`:

```python
class InclusionSeeder(BaseSeeder):
    async def seed(self):
        """Seed tier-element inclusions."""
        tier_mappings = get_tier_mapping(self.category_slug)
        
        for tier_code, config in tier_mappings["TIER_CONFIGS"].items():
            tier_id = tier_uuid(self.category_slug, tier_code)
            
            # Seed element inclusions
            for element_code in config["elements"]:
                element_id = element_uuid(self.category_slug, element_code)
                await self._ensure_inclusion(tier_id, element_id=element_id)
            
            # Seed tier inheritance
            for inherited_tier_code in config["inherited_tiers"]:
                inherited_tier_id = tier_uuid(self.category_slug, inherited_tier_code)
                await self._ensure_inclusion(tier_id, included_tier_id=inherited_tier_id)
        
        self.log_stats()
```

---

## Dual Warning System

### Overview

Element warnings use **two representations** for compatibility:

1. **Inline**: `warnings.element_id` (FK) — Used by agent services
2. **Association**: `element_warning_associations` (M2M) — Used by admin panel

**Both are created automatically** by seeds.

### Why Two Systems?

**Historical**:
- Agent built first, queries `warnings.element_id` directly
- Admin panel needed M2M flexibility (`show_condition`, `threshold_quantity`)
- Maintaining both avoids breaking changes

### Database Schema

```sql
-- System 1: Inline (agent uses this)
CREATE TABLE warnings (
    id UUID PRIMARY KEY,
    code VARCHAR NOT NULL,
    message TEXT NOT NULL,
    severity VARCHAR NOT NULL,
    
    -- XOR scoping
    category_id UUID REFERENCES vehicle_categories(id),
    tier_id UUID REFERENCES tariff_tiers(id),
    element_id UUID REFERENCES elements(id),  -- ← Inline FK
    
    CHECK (
        (category_id IS NOT NULL AND tier_id IS NULL AND element_id IS NULL) OR
        (category_id IS NULL AND tier_id IS NOT NULL AND element_id IS NULL) OR
        (category_id IS NULL AND tier_id IS NULL AND element_id IS NOT NULL)
    )
);

-- System 2: Association (admin uses this)
CREATE TABLE element_warning_associations (
    id UUID PRIMARY KEY,
    element_id UUID REFERENCES elements(id),
    warning_id UUID REFERENCES warnings(id),
    show_condition VARCHAR,     -- always, on_exceed_max, on_below_min
    threshold_quantity INTEGER,
    UNIQUE(element_id, warning_id)
);
```

### Verification

```bash
python -m database.seeds.verify_warning_sync

# Expected output:
# ✅ SUCCESS: Both systems have 39 warnings (SYNCED)
```

See `database/seeds/WARNING_SYSTEM.md` for full documentation.

---

## Critical Rules

### General
- ALWAYS use UUID as primary key (`UUID(as_uuid=True)`)
- ALWAYS include `created_at` and `updated_at` timestamps
- ALWAYS use `DateTime(timezone=True)` for all timestamps
- ALWAYS use `lazy="selectin"` for relationships (async compatibility)
- NEVER use synchronous database operations

### Foreign Keys
- ALWAYS specify `ondelete` policy (`CASCADE` or `SET NULL`)
- ALWAYS create indexes on foreign key columns
- ALWAYS use proper constraint naming

### Migrations
- ALWAYS include `downgrade()` function (never leave as `pass`)
- ALWAYS create indexes AFTER creating tables
- ALWAYS use `op.f()` for constraint naming
- NEVER modify existing migrations (create new ones)
- ALWAYS drop constraints/indexes before dropping tables in downgrade()

### Seeds
- ALWAYS use deterministic UUIDs (UUID v5)
- ALWAYS use dual warning system (inline + association) for element warnings
- ALWAYS use `upsert_with_uuid_fn()` for idempotency
- NEVER hard-delete seed data (use `is_active=False`)

### Async Patterns
- ALWAYS use `selectinload()` for eager loading
- ALWAYS use `get_async_session()` context manager
- ALWAYS use `expire_on_commit=False` for session factory
- NEVER use `lazy="joined"` (use `lazy="selectin"`)

### JSONB
- ALWAYS use JSONB for flexible/dynamic data
- ALWAYS provide default values (`default=dict` or `default=list`)
- ALWAYS validate JSONB structure in application code (Pydantic)

---

## Commands

```bash
# Migrations
alembic revision -m "description"     # Create new migration
alembic upgrade head                  # Apply all migrations
alembic downgrade -1                  # Rollback one migration
alembic current                       # Show current version
alembic history                       # Show migration history

# Seeds
python -m database.seeds.run_all_seeds            # Seed all categories
python -m database.seeds.validate_elements_seed   # Validate seed data
python -m database.seeds.verify_warning_sync      # Verify dual warning system
python -m database.seeds.create_admin_user        # Create admin user

# Database
docker-compose exec postgres psql -U msia msia_db  # PostgreSQL CLI
```

---

## Resources

- [sqlalchemy-async skill](../sqlalchemy-async/SKILL.md) - Generic async SQLAlchemy patterns
- [msia-tariffs skill](../msia-tariffs/SKILL.md) - Tariff system specifics
- [database/AGENTS.md](../../database/AGENTS.md) - Component-level guidelines
- [WARNING_SYSTEM.md](../../database/seeds/WARNING_SYSTEM.md) - Dual warning architecture
