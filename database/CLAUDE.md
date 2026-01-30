# Database Component Guidelines

This directory contains SQLAlchemy models, Alembic migrations, and data seeds for the MSI-a application.

> For detailed patterns, invoke the skill: [msia-database](../skills/msia-database/SKILL.md)

## Auto-invoke Skills

When working in this directory, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Creating/modifying models | `msia-database` |
| Writing migrations | `msia-database` |
| Working with seeds | `msia-database` |
| Generic SQLAlchemy patterns | `sqlalchemy-async` |
| Working with tariff models | `msia-tariffs` |

---

## Directory Structure

```
database/
├── models.py                    # All 32 SQLAlchemy models (3,224 lines)
├── connection.py                # Async engine, session factory, pooling (88 lines)
├── __init__.py                  # Package exports
│
├── migrations/
│   └── apply_element_fixes.sql  # Manual SQL fixes for element data (273 lines)
│
├── seeds/
│   ├── __init__.py
│   ├── run_all_seeds.py         # Main orchestrator (123 lines)
│   ├── seed_utils.py            # Deterministic UUID v5 generation (132 lines)
│   ├── validate_elements_seed.py # Validation script (176 lines)
│   ├── verify_warning_sync.py   # Verify dual warning sync (152 lines)
│   ├── create_admin_user.py     # Create default admin user (74 lines)
│   ├── WARNING_SYSTEM.md        # Dual warning architecture docs (248 lines)
│   │
│   ├── data/                    # Data definitions (constants only, no logic)
│   │   ├── __init__.py          # Type exports
│   │   ├── common.py            # TypedDict definitions + shared constants (140 lines)
│   │   ├── motos_part.py        # Motos particular: CATEGORY, TIERS, ELEMENTS (2,222 lines)
│   │   ├── aseicars_prof.py     # Autocaravanas profesional data (817 lines)
│   │   └── tier_mappings.py     # Tier-element relationships (single source of truth, 273 lines)
│   │
│   └── seeders/                 # Reusable seeding logic
│       ├── __init__.py
│       ├── base.py              # BaseSeeder: uniform logging, upsert, stats (133 lines)
│       ├── category.py          # CategorySeeder: category, tiers, warnings, services (267 lines)
│       ├── element.py           # ElementSeeder: elements, images, dual warnings (304 lines)
│       └── inclusion.py         # InclusionSeeder: tier-element relationships (328 lines)
│
└── alembic/
    ├── env.py                   # Alembic environment config (97 lines)
    ├── script.py.mako           # Migration template (26 lines)
    └── versions/                # 34 migration files (4,490 total lines)
        ├── 001_initial_schema.py
        ├── 002_tariff_system.py
        ├── ...
        └── 033_llm_usage_metrics.py
```

---

## Database Schema Overview

**32 SQLAlchemy models** mapped to **32 PostgreSQL tables** in `models.py` (3,224 lines).

### Entity Relationship Diagram (Key Relationships)

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

---

## Complete Model Inventory (32 Models)

### Core Models (5)

| Model | Table | Purpose | Key Fields |
|-------|-------|---------|------------|
| `User` | `users` | WhatsApp users | `phone` (E.164), `client_type` (particular/professional), `chatwoot_contact_id`, JSONB `metadata` |
| `ConversationHistory` | `conversation_history` | Conversation metadata | `chatwoot_conversation_id` (unique), `message_count`, AI `summary` |
| `ConversationMessage` | `conversation_messages` | Individual messages | `role` (user/assistant), `content`, `has_images`, `chatwoot_message_id` |
| `Policy` | `policies` | Business policies/FAQ | `key`, `value` (markdown), `category` |
| `SystemSetting` | `system_settings` | App configuration | `key`, `value`, `value_type` (string/integer/boolean/json), `is_mutable` |

### Tariff System Models (11)

| Model | Table | Purpose | Key Fields |
|-------|-------|---------|------------|
| `VehicleCategory` | `vehicle_categories` | Vehicle categories by client type | `slug`, `name`, `client_type`, `icon`, `sort_order` |
| `TariffTier` | `tariff_tiers` | Pricing tiers (T1-T6) | `code`, `price` (Numeric), JSONB `classification_rules`, `min_elements`, `max_elements` |
| `BaseDocumentation` | `base_documentation` | Base required docs per category | `category_id`, `title`, `description`, `is_mandatory` |
| `Element` | `elements` | Homologable elements catalog | `code`, `name`, JSONB `keywords/aliases`, `parent_element_id` (self-ref), `variant_type`, `inherit_parent_data` |
| `ElementImage` | `element_images` | Element images | `image_type` (example/required_document/warning), `status` (active/placeholder), `user_instruction` |
| `ElementRequiredField` | `element_required_fields` | Required data fields per element | `field_name`, `field_type`, JSONB `validation_rules`, `condition_field_id` (circular ref check) |
| `TierElementInclusion` | `tier_element_inclusions` | Tier-element relationships | `tier_id`, `element_id` OR `included_tier_id` (tier inheritance), `min_quantity`, `max_quantity` |
| `ElementWarningAssociation` | `element_warning_associations` | Many-to-many element-warning | `element_id`, `warning_id`, `show_condition`, `threshold_quantity` |
| `Warning` | `warnings` | Scoped warnings | Targets: `category_id`, `tier_id`, OR `element_id` (XOR), JSONB `trigger_conditions`, `severity` |
| `AdditionalService` | `additional_services` | Extra services | `code`, `name`, `price` (Numeric), `category_id` (optional) |
| `TariffPromptSection` | `tariff_prompt_sections` | Editable AI prompt sections | `category_id`, `section_type` (algorithm/recognition_table), `content`, `version` |

### RAG System Models (4)

| Model | Table | Purpose | Key Fields |
|-------|-------|---------|------------|
| `RegulatoryDocument` | `regulatory_documents` | RAG document metadata | `title`, `document_type`, `file_hash` (SHA256 dedup), `status`, `extraction_method`, JSONB `section_mappings` |
| `DocumentChunk` | `document_chunks` | Semantic chunks | `chunk_index`, `qdrant_point_id`, `content_hash`, JSONB `page_numbers`, JSONB `heading_hierarchy` |
| `RAGQuery` | `rag_queries` | Query analytics | `query_hash`, performance metrics (`retrieval_ms`, `rerank_ms`, `llm_ms`), `was_cache_hit` |
| `QueryCitation` | `query_citations` | Query-chunk links | `query_id`, `chunk_id`, `rank`, `similarity_score`, `rerank_score`, `used_in_context` |

### Case Management Models (4)

| Model | Table | Purpose | Key Fields |
|-------|-------|---------|------------|
| `Case` | `cases` | Homologation cases (expedientes) | `user_id`, `category_id`, vehicle data (marca, modelo, matricula, bastidor), tariff, ITV, workshop, dimensions |
| `CaseImage` | `case_images` | User-uploaded case images | `case_id`, `display_name`, `element_code`, `chatwoot_message_id`, `is_valid` (tri-state), `validation_notes` |
| `CaseElementData` | `case_element_data` | Per-element collected data | `case_id`, `element_code`, JSONB `field_values`, `status` (pending_photos/pending_data/completed) |
| `Escalation` | `escalations` | Escalation to human agents | `conversation_id`, `reason`, `source` (tool_call/auto/error), `status`, JSONB `metadata` |

### Admin & Auth Models (3)

| Model | Table | Purpose | Key Fields |
|-------|-------|---------|------------|
| `AdminUser` | `admin_users` | Admin panel users | `username`, `password_hash` (bcrypt), `role` (admin/user), `is_active`, `created_by` (self-ref) |
| `AdminAccessLog` | `admin_access_log` | Login/logout tracking | `admin_user_id`, `action` (login/logout/login_failed), `ip_address`, `user_agent` |
| `UploadedImage` | `uploaded_images` | Uploaded image metadata | `filename`, `stored_filename`, `mime_type`, `width`, `height`, `category` |

### Monitoring & Audit Models (5)

| Model | Table | Purpose | Key Fields |
|-------|-------|---------|------------|
| `ContainerErrorLog` | `container_error_logs` | Docker container error logs | `service_name`, `level`, `stack_trace`, JSONB `context`, `status`, `resolved_by` |
| `TokenUsage` | `token_usage` | Monthly LLM token consumption | `year`, `month`, BigInteger `input_tokens/output_tokens`, `total_requests` |
| `LLMUsageMetric` | `llm_usage_metrics` | Hybrid LLM architecture metrics | `task_type`, `tier` (local_fast/cloud), `provider`, `latency_ms`, `estimated_cost_usd`, `fallback_used` |
| `ToolCallLog` | `tool_call_logs` | Agent tool call audit | `conversation_id`, `tool_name`, JSONB `parameters`, `result_type`, `execution_time_ms`, `iteration` |
| `ResponseConstraint` | `response_constraints` | Anti-hallucination rules | `detection_pattern` (regex), `required_tool`, `error_injection`, `priority`, `category_id` |
| `AuditLog` | `audit_log` | Change audit trail | `entity_type`, `entity_id`, `action` (create/update/delete), JSONB `changes`, `user_id` |

---

## Migration History (34 Migrations)

**Total migration lines**: 4,490

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 001 | `initial_schema.py` | 96 | Initial tables: users, conversations, policies, system_settings |
| 002 | `tariff_system.py` | 201 | Tariff system: vehicle_categories, tariff_tiers, base_documentation, audit_log |
| 003 | `tariff_restructure.py` | 225 | Restructure tariff tables |
| 004 | `customer_to_user.py` | 136 | Rename customer to user |
| 005 | `elem_docs_images.py` | 172 | Add element documentation and images |
| 006 | `admin_users.py` | 173 | Admin users and access logs |
| 007 | `rag_system.py` | 502 | RAG system: regulatory_documents, document_chunks, rag_queries, query_citations |
| 008 | `fix_rag_queries_fk.py` | 58 | Fix RAG queries foreign key |
| 009 | `escalations.py` | 112 | Escalations table |
| 010 | `panic_button_settings.py` | 76 | Panic button system settings |
| 011 | `section_mappings.py` | 36 | Section mappings for RAG documents |
| 012 | `element_system.py` | 310 | Full element system: elements, images, associations, inclusions |
| 013 | `separate_categories_by_type.py` | 106 | Separate categories by client type |
| 014 | `warnings_scoping.py` | 111 | Scope warnings to category/tier/element |
| 015 | `remove_element_documentation.py` | 103 | Remove deprecated element documentation |
| 016 | `cases.py` | 292 | Cases (expedientes) and case_images |
| 017 | `expand_case_fields.py` | 298 | Expand case fields (vehicle, workshop, dimensional) |
| 018 | `fix_field_lengths.py` | 41 | Fix field length constraints |
| 019 | `move_personal_data_to_user.py` | 190 | Move personal data from case to user |
| 020 | `container_error_logs.py` | 139 | Container error logs |
| 021 | `element_hierarchy.py` | 99 | Element hierarchy (parent_element_id, variant_type) |
| 022 | `element_question_hint.py` | 43 | Add question_hint to elements |
| 023 | `token_usage.py` | 119 | Token usage tracking |
| 024 | `case_image_chatwoot_msg_id.py` | 37 | Add chatwoot_message_id to case_images |
| 025 | `element_multi_select_keywords.py` | 106 | Multi-select keywords for elements |
| 026 | `element_inherit_parent_data.py` | 38 | Add inherit_parent_data flag to elements |
| 027 | `response_constraints.py` | 93 | Response constraints table |
| 028 | `element_image_status_and_docs.py` | 75 | Image status and docs fields |
| 029 | `tool_call_logs.py` | 50 | Tool call logging |
| 030 | `element_required_fields.py` | 135 | Element required fields |
| 031 | `add_chatwoot_contact_id_to_users.py` | 42 | Chatwoot contact ID on users |
| 032 | `unique_conversation_id.py` | 66 | Unique constraint on conversation_id |
| 033 | `llm_usage_metrics.py` | 160 | LLM usage metrics table |
| 034 | `add_conversation_messages_table.py` | 50 | Conversation messages table |

### Migration Conventions

**Naming**: `{number}_{description}.py`
- Use sequential numbers with leading zeros (001, 002, ...)
- Use snake_case for description
- Keep description concise but descriptive

**Structure**: Every migration MUST have:
```python
def upgrade() -> None:
    """Apply changes."""
    # Create tables, add columns, create indexes
    
def downgrade() -> None:
    """Revert changes."""
    # Drop indexes, drop columns, drop tables (reverse order)
```

**Best Practices**:
- ALWAYS include `downgrade()` (never leave as `pass`)
- Create indexes AFTER creating tables
- Use `batch_alter_table()` for SQLite compatibility (testing)
- Add foreign key constraints with explicit `ondelete` policy
- Use `op.f()` for naming constraints (Alembic auto-naming)

---

## Connection & Session Management

**File**: `connection.py` (88 lines)

### Async Engine Configuration

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,           # Connection pool size
    max_overflow=20,        # Max extra connections during peak
    pool_pre_ping=True,     # Verify connection before use
    echo=False,             # Set to True for SQL logging
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Keep objects usable after commit
    autocommit=False,
    autoflush=False,
)
```

### Session Factory Pattern

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_async_session():
    """
    Async context manager that yields a session.
    
    Usage:
        async with get_async_session() as session:
            result = await session.execute(select(User))
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

**Connection Pool Tuning**:
- `pool_size=10`: Standard for web apps (adjust based on concurrent load)
- `max_overflow=20`: Total 30 connections during peak
- `pool_pre_ping=True`: Prevents "connection closed" errors (slight overhead)

---

## Seeds Architecture

**Total seed lines**: ~4,887

### Overview

Seeds use a **data-driven architecture** with complete separation of data (constants) and logic (seeders):

```
Data Modules (seeds/data/)  →  Seeders (seeds/seeders/)  →  Database
    ↓                                   ↓
motos_part.py                   CategorySeeder
aseicars_prof.py          →     ElementSeeder         →  PostgreSQL
tier_mappings.py                InclusionSeeder
```

### Deterministic UUIDs (Idempotency)

**All seed data uses UUID v5** with a fixed namespace for idempotent seeding:

```python
# seeds/seed_utils.py
SEED_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")

def element_uuid(category_slug: str, element_code: str) -> uuid.UUID:
    """Generate deterministic UUID for an element."""
    return uuid.uuid5(SEED_NAMESPACE, f"element:{category_slug}:{element_code}")

def tier_uuid(category_slug: str, tier_code: str) -> uuid.UUID:
    return uuid.uuid5(SEED_NAMESPACE, f"tier:{category_slug}:{tier_code}")
```

**Benefits**:
- Re-running seeds won't create duplicates
- Updates existing records via `ON CONFLICT DO UPDATE`
- Enables predictable foreign key relationships

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
}

# Tiers (T1-T6)
TIERS: list[TierData] = [
    {
        "code": "T1",
        "name": "Tier 1",
        "price": Decimal("140.00"),
        "classification_rules": {...},
        "min_elements": 1,
        "max_elements": 1,
    },
    # ... more tiers
]

# Elements (39 elements for motos-part)
ELEMENTS: list[ElementData] = [
    {
        "code": "ESCAPE",
        "name": "Escape",
        "keywords": ["escape", "tubo de escape", "silenciador"],
        "aliases": ["tubos de escape", "sistema de escape"],
        "images": [
            {
                "image_type": "example",
                "url": "https://example.com/escape.jpg",
                "alt_text": "Ejemplo de escape",
            }
        ],
        "warnings": [  # ← Dual system: creates inline + association
            {
                "code": "ESCAPE_HOMOLOGACION",
                "message": "El escape debe estar homologado...",
                "severity": "warning",
            }
        ],
        "required_fields": [
            {
                "field_name": "marca",
                "field_type": "text",
                "is_required": True,
            }
        ],
    },
    # ... more elements
]

# Category warnings, services, docs, prompts
CATEGORY_WARNINGS: list[WarningData] = [...]
ADDITIONAL_SERVICES: list[AdditionalServiceData] = [...]
BASE_DOCUMENTATION: list[BaseDocumentationData] = [...]
PROMPT_SECTIONS: list[PromptSectionData] = [...]
```

### Tier Mappings (Single Source of Truth)

**File**: `seeds/data/tier_mappings.py` (273 lines)

Defines which elements belong to which tiers for each category:

```python
# Motos particular tier mappings
MOTOS_PART_MAPPINGS = {
    "T1_ONLY_ELEMENTS": ["PROYECTO"],  # Only T1
    "T3_ELEMENTS": ["ESCAPE", "MANILLAR", ...],  # T3 and above
    "T4_BASE_ELEMENTS": ["CARENADO", "ASIENTO", ...],  # T4-T6
    
    # Tier-specific configs
    "TIER_CONFIGS": {
        "T1": {
            "elements": ["PROYECTO"],
            "inherited_tiers": [],
        },
        "T2": {
            "elements": [],
            "inherited_tiers": ["T1"],  # Inherits from T1
        },
        "T3": {
            "elements": ["ESCAPE", "MANILLAR", ...],
            "inherited_tiers": ["T2"],
        },
        # ...
    }
}
```

**Benefits**:
- Single place to change tier-element relationships
- InclusionSeeder reads this to create `TierElementInclusion` records
- Supports tier inheritance via `inherited_tiers`

### Seeder Classes

#### BaseSeeder (133 lines)

Abstract base class with uniform logging and upsert logic:

```python
from database.seeds.seeders.base import BaseSeeder

class MySeeder(BaseSeeder):
    def __init__(self, session):
        super().__init__("MySeeder")  # Logger name
        self.session = session
    
    async def seed(self):
        # Uses self.upsert() or self.upsert_with_uuid_fn()
        pass
```

**Capabilities**:
- `upsert()`: Insert or update with conflict handling
- `upsert_with_uuid_fn()`: Upsert with deterministic UUID generation
- Stats tracking: `created`, `updated`, `skipped`
- Uniform logging: `logger.info(f"✅ {self.name}: Created X, Updated Y, Skipped Z")`

#### CategorySeeder (267 lines)

Seeds category + tiers + category-level data:

```python
from database.seeds.seeders.category import CategorySeeder

seeder = CategorySeeder(session, category_data_module)
await seeder.seed()
```

**6-step process** (with flush between steps):
1. Seed category
2. Seed tiers
3. Seed category warnings
4. Seed additional services
5. Seed base documentation
6. Seed prompt sections

#### ElementSeeder (304 lines)

Seeds elements + images + dual warnings:

```python
from database.seeds.seeders.element import ElementSeeder

seeder = ElementSeeder(session, category_slug, elements_data)
await seeder.seed()
```

**Two-pass seeding**:
1. **Pass 1**: Create all elements (without parent resolution)
2. **Pass 2**: Resolve `parent_element_id` relationships (after all elements exist)

**Dual warning system**:
- Creates warnings with `element_id` (inline)
- Creates `ElementWarningAssociation` entries (association)

#### InclusionSeeder (328 lines)

Seeds tier-element relationships:

```python
from database.seeds.seeders.inclusion import InclusionSeeder

seeder = InclusionSeeder(session, category_slug, tier_mappings)
await seeder.seed()
```

**Reads**: `tier_mappings.py` for element-tier relationships

**Creates**:
- `TierElementInclusion` with `element_id` (element inclusions)
- `TierElementInclusion` with `included_tier_id` (tier inheritance)

### Adding a New Category

**4-step process**:

1. **Create data module**: `seeds/data/nueva_categoria.py`
   ```python
   CATEGORY_SLUG = "nueva-cat"
   CATEGORY: CategoryData = {...}
   TIERS: list[TierData] = [...]
   ELEMENTS: list[ElementData] = [...]
   # ... etc
   ```

2. **Add tier mappings**: `seeds/data/tier_mappings.py`
   ```python
   NUEVA_CAT_MAPPINGS = {
       "TIER_CONFIGS": {...}
   }
   
   def get_tier_mapping(category_slug: str):
       if category_slug == "nueva-cat":
           return NUEVA_CAT_MAPPINGS
   ```

3. **Import in orchestrator**: `seeds/run_all_seeds.py`
   ```python
   from database.seeds.data import nueva_categoria
   
   async def main():
       # ...
       await seed_category(nueva_categoria)
   ```

4. **Run seeds**:
   ```bash
   python -m database.seeds.run_all_seeds
   ```

**No seeder modifications needed** - seeders are fully reusable.

---

## Element Warning System (Dual Architecture)

### Overview

Element warnings use a **dual system** for compatibility between agent services and admin panel:

1. **Inline Warnings**: `warnings.element_id` (FK to elements) - Used by agent/tariff services
2. **Association Warnings**: `element_warning_associations` (many-to-many) - Used by admin panel

**Both representations are created automatically** by seeds to maintain synchronization.

### Why Two Systems?

**Historical reasons**:
- Agent services were built first, querying warnings via `warnings.element_id` directly
- Admin panel later needed many-to-many flexibility (show_condition, threshold_quantity)
- Seeds create both to avoid breaking existing agent code

**Design decision**: Maintain both systems rather than refactor all agent services.

### Database Schema

```sql
-- System 1: Inline (agent uses this)
CREATE TABLE warnings (
    id UUID PRIMARY KEY,
    code VARCHAR NOT NULL,
    message TEXT NOT NULL,
    severity VARCHAR NOT NULL,  -- info, warning, error
    
    -- Scoping (XOR: only ONE of these can be set)
    category_id UUID REFERENCES vehicle_categories(id),  -- Category warning
    tier_id UUID REFERENCES tariff_tiers(id),            -- Tier warning
    element_id UUID REFERENCES elements(id),             -- Element warning
    
    trigger_conditions JSONB,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    
    CONSTRAINT warnings_scope_check CHECK (
        (category_id IS NOT NULL AND tier_id IS NULL AND element_id IS NULL) OR
        (category_id IS NULL AND tier_id IS NOT NULL AND element_id IS NULL) OR
        (category_id IS NULL AND tier_id IS NULL AND element_id IS NOT NULL)
    )
);

-- System 2: Associations (admin panel uses this)
CREATE TABLE element_warning_associations (
    id UUID PRIMARY KEY,
    element_id UUID REFERENCES elements(id) ON DELETE CASCADE,
    warning_id UUID REFERENCES warnings(id) ON DELETE CASCADE,
    
    -- Extra flexibility
    show_condition VARCHAR,      -- always, on_exceed_max, on_below_min
    threshold_quantity INTEGER,
    
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    
    UNIQUE(element_id, warning_id)
);
```

### How Seeds Work

`ElementSeeder` automatically creates both representations:

```python
# Step 1: Create warning with element_id (inline)
warning_id = await self.upsert_with_uuid_fn(
    Warning,
    uuid_fn=lambda: warning_uuid(category_slug, warning_data["code"]),
    data={
        "code": warning_data["code"],
        "message": warning_data["message"],
        "severity": warning_data["severity"],
        "element_id": element_id,  # ← Inline FK
    },
)

# Step 2: Create association (many-to-many)
await self.upsert_with_uuid_fn(
    ElementWarningAssociation,
    uuid_fn=lambda: assoc_uuid(element_id, warning_id),
    data={
        "element_id": element_id,
        "warning_id": warning_id,
        "show_condition": "always",
        "threshold_quantity": None,
    },
)
```

**Result**: Every element warning exists in BOTH systems.

### Verification

After running seeds, verify synchronization:

```bash
python -m database.seeds.verify_warning_sync

# Expected output:
# ✅ SUCCESS: Both systems have 39 warnings (SYNCED)
# 
# Inline warnings (via warnings.element_id):    39
# Association warnings (via associations):       39
# ✅ Counts match!
```

**Script checks**:
1. Count inline warnings (`SELECT COUNT(*) FROM warnings WHERE element_id IS NOT NULL`)
2. Count unique element-warning pairs in associations
3. Verify counts match
4. Sample data check (5 random warnings exist in both systems)

### Consumers

**Inline system** (agent services):
```python
# agent/services/tarifa_service.py
def get_warnings_by_scope(element_id: UUID):
    return await session.execute(
        select(Warning).where(Warning.element_id == element_id)
    )
```

**Association system** (admin panel):
```python
# agent/services/element_service.py
# api/routes/elements.py
def get_element_warnings(element_id: UUID):
    return await session.execute(
        select(Warning)
        .join(ElementWarningAssociation)
        .where(ElementWarningAssociation.element_id == element_id)
    )
```

### Adding Warnings to Elements

Simply add warnings to your element data - both systems created automatically:

```python
# seeds/data/motos_part.py
ELEMENTS: list[ElementData] = [
    {
        "code": "MY_ELEMENT",
        "name": "Mi Elemento",
        "warnings": [  # ← Just add here
            {
                "code": "MY_WARNING",
                "message": "Este elemento requiere...",
                "severity": "warning",
            }
        ]
    }
]
```

**No additional code needed** - `ElementSeeder` handles both inline + association creation.

### Documentation

See `database/seeds/WARNING_SYSTEM.md` for complete documentation (248 lines).

---

## Key Patterns

### Soft Delete Pattern

Models use `is_active` for soft deletion:

```python
class MyModel(Base):
    is_active: Mapped[bool] = mapped_column(default=True)

# Query only active records
stmt = select(MyModel).where(MyModel.is_active == True)

# Soft delete
my_record.is_active = False
await session.commit()
```

**Models using soft delete**: `RegulatoryDocument`, `AdminUser`, `Warning`, `Element`

### JSONB Field Patterns

Many models use JSONB for flexible/dynamic data:

```python
class Element(Base):
    keywords: Mapped[list[str]] = mapped_column(JSONB, default=list)
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

# Query JSONB (PostgreSQL)
stmt = select(Element).where(
    Element.keywords.contains(["escape"])
)

# Update JSONB
element.metadata = {"custom_field": "value"}
```

**JSONB fields**: `metadata`, `classification_rules`, `section_mappings`, `trigger_conditions`, `validation_rules`, `field_values`, `changes`, `parameters`, `context`, `page_numbers`, `heading_hierarchy`

### Self-Referential Hierarchy

`Element` supports parent-child relationships:

```python
class Element(Base):
    id: Mapped[UUID] = mapped_column(primary_key=True)
    parent_element_id: Mapped[UUID | None] = mapped_column(ForeignKey("elements.id"))
    
    # Variant system
    variant_type: Mapped[str | None]  # "color", "size", "model"
    variant_code: Mapped[str | None]  # "red", "large", "sport"
    
    # Inheritance
    inherit_parent_data: Mapped[bool] = mapped_column(default=False)
    
    # Relationships
    parent: Mapped["Element | None"] = relationship(
        "Element",
        remote_side=[id],
        back_populates="children",
        lazy="selectin"
    )
    children: Mapped[list["Element"]] = relationship(
        back_populates="parent",
        lazy="selectin"
    )
```

**Two-pass seeding**: Required to avoid circular FK issues.

### Conditional Field Display

`ElementRequiredField` supports conditional display:

```python
class ElementRequiredField(Base):
    element_id: Mapped[UUID] = mapped_column(ForeignKey("elements.id"))
    field_name: Mapped[str]
    field_type: Mapped[str]  # text, number, boolean, select
    
    # Conditional display
    condition_field_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("element_required_fields.id")  # Self-referential
    )
    condition_operator: Mapped[str | None]  # equals, not_equals, greater_than
    condition_value: Mapped[str | None]
```

**Example**: Show "color" field only if "has_custom_paint" is true.

**Circular reference prevention**: Validation prevents field A depending on field B that depends on field A.

### Tier Inheritance

`TierElementInclusion` supports tier-to-tier inheritance:

```python
class TierElementInclusion(Base):
    tier_id: Mapped[UUID] = mapped_column(ForeignKey("tariff_tiers.id"))
    
    # XOR: Either element OR tier
    element_id: Mapped[UUID | None] = mapped_column(ForeignKey("elements.id"))
    included_tier_id: Mapped[UUID | None] = mapped_column(ForeignKey("tariff_tiers.id"))
    
    min_quantity: Mapped[int] = mapped_column(default=1)
    max_quantity: Mapped[int | None]
```

**Example**: T2 inherits all elements from T1
```python
TierElementInclusion(
    tier_id=T2_ID,
    included_tier_id=T1_ID,  # Inherits from T1
    min_quantity=1,
)
```

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
python -m database.seeds.create_admin_user        # Create admin user (admin/admin123)

# Database
docker-compose exec postgres psql -U msia msia_db  # Access PostgreSQL CLI
```

---

## Critical Rules

### General
- ALWAYS use UUID as primary key (`UUID(as_uuid=True)`)
- ALWAYS include `created_at` and `updated_at` timestamps
- ALWAYS use `DateTime(timezone=True)` for all timestamps
- ALWAYS use `lazy="selectin"` for relationships (async compatibility)
- NEVER use synchronous database operations (use async/await)

### Foreign Keys
- ALWAYS specify `ondelete` policy (`CASCADE` or `SET NULL`)
- ALWAYS create indexes on foreign key columns
- ALWAYS use proper naming: `{table}_{column}_fkey`

### Migrations
- ALWAYS include `downgrade()` function (never leave as `pass`)
- ALWAYS create indexes AFTER creating tables
- ALWAYS use `op.f()` for constraint naming (Alembic auto-naming)
- NEVER modify existing migrations (create new ones)

### Seeds
- ALWAYS use deterministic UUIDs (UUID v5 with fixed namespace)
- ALWAYS use dual warning system (inline + association) for element warnings
- ALWAYS use `upsert_with_uuid_fn()` for idempotency
- NEVER hard-delete seed data (use `is_active=False`)

### Async Patterns
- ALWAYS use `selectinload()` for eager loading relationships
- ALWAYS use `get_async_session()` context manager
- NEVER use `lazy="joined"` (use `lazy="selectin"` instead)
- ALWAYS use `expire_on_commit=False` for session factory

### JSONB
- ALWAYS use JSONB for flexible/dynamic data (not TEXT with JSON strings)
- ALWAYS provide default values (`default=dict` or `default=list`)
- ALWAYS validate JSONB structure in application code (Pydantic)

---

## Resources

- [msia-database skill](../skills/msia-database/SKILL.md) - Complete patterns and examples
- [sqlalchemy-async skill](../skills/sqlalchemy-async/SKILL.md) - Generic async SQLAlchemy patterns
- [msia-tariffs skill](../skills/msia-tariffs/SKILL.md) - Tariff system specifics
- [WARNING_SYSTEM.md](seeds/WARNING_SYSTEM.md) - Dual warning architecture details
