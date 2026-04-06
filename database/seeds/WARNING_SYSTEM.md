# Element Warning System — M2M Architecture

## Overview

Element warnings in MSI-a are stored using a **single M2M system** via
`element_warning_associations`. The legacy `warnings.element_id` inline FK was
removed in migration **042_unify_warning_system** (Batch C of simplify-infrastructure).

## Database Schema

```
┌─────────────────────┐
│   warnings          │
├─────────────────────┤
│ id (PK)             │
│ code                │
│ message             │
│ category_id (FK)    │  ← Category-scoped warning (XOR with tier_id)
│ tier_id (FK)        │  ← Tier-scoped warning (XOR with category_id)
│ trigger_conditions  │
│ severity            │
│ is_active           │
└─────────────────────┘
         ▲
         │ warning_id
┌────────────────────────────────────┐
│  element_warning_associations      │  ← Element scoping (M2M)
├────────────────────────────────────┤
│ id (PK)                            │
│ element_id (FK) ──► elements       │
│ warning_id (FK) ──► warnings       │
│ show_condition                     │  always | on_exceed_max | on_below_min
│ threshold_quantity                 │
└────────────────────────────────────┘
```

## How Seeds Work

`ElementSeeder._seed_element_warnings_m2m()` handles both steps atomically:

```python
# For each element warning in seed data:

# 1. Upsert the Warning record (no element_id — global/unscoped or category/tier)
warning = Warning(
    id=warning_id,
    code=warn_data["code"],
    message=warn_data["message"],
    severity=warn_data.get("severity", "warning"),
    category_id=None,
    tier_id=None,
    trigger_conditions=warn_data.get("trigger_conditions"),
)

# 2. Create M2M association to express element scoping
association = ElementWarningAssociation(
    element_id=element.id,
    warning_id=warning_id,
    show_condition="always",
    threshold_quantity=None,
)
```

### Key Points

- Seeds create Warning + ElementWarningAssociation for every element warning
- Uses deterministic UUIDs for idempotency
- Checks for existing records to avoid duplicates
- Logs statistics for warnings created and associations created

## Usage in Code

### Agent Services

```python
# agent/services/tarifa_service.py — get_warnings_by_scope()
if element_id:
    scope_conditions.append(
        Warning.id.in_(
            select(ElementWarningAssociation.warning_id).where(
                ElementWarningAssociation.element_id == PyUUID(element_id)
            )
        )
    )

# agent/services/element_state_service.py
warn_result = await session.execute(
    select(Warning)
    .where(
        Warning.id.in_(
            select(ElementWarningAssociation.warning_id).where(
                ElementWarningAssociation.element_id == element.id
            )
        )
    )
    .where(Warning.is_active == True)
)
```

### Admin Panel

```python
# api/routes/elements.py
associations = await session.execute(
    select(ElementWarningAssociation)
    .where(ElementWarningAssociation.element_id == element_id)
    .options(selectinload(ElementWarningAssociation.warning))
)
```

## Verification

After running seeds, verify associations:

```bash
python -m database.seeds.verify_warning_sync
```

Expected output:
```
✓ Total warnings in warnings table: N
✓ Element-warning associations (element_warning_associations): N
✅ N element-warning associations present
✓ Elements with at least one warning: N
✅ No orphaned associations found
```

### Manual SQL Verification

```sql
-- Count associations
SELECT COUNT(*) FROM element_warning_associations;

-- Verify relationships
SELECT
    e.code AS element_code,
    w.code AS warning_code,
    ewa.show_condition
FROM element_warning_associations ewa
JOIN elements e ON e.id = ewa.element_id
JOIN warnings w ON w.id = ewa.warning_id
LIMIT 10;
```

## Maintenance

### Adding New Element Warnings

When adding warnings to elements in `seeds/data/*.py`:

```python
# seeds/data/motos_part.py
ELEMENTS: list[ElementData] = [
    {
        "code": "MY_ELEMENT",
        "name": "My Element",
        # ...
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

**No additional code needed** — `ElementSeeder._seed_element_warnings_m2m()` creates
both the Warning record and its association automatically.

### Updating Existing Warnings

Warnings are **upserted** on each seed run:
- Existing warnings are updated (message, severity, etc.)
- Missing associations are created
- Deterministic UUIDs ensure same IDs across runs

## Migration History

| Migration | Change |
|-----------|--------|
| `014_warnings_scoping.py` | Added `element_id`, `category_id`, `tier_id` scope fields to warnings |
| `042_unify_warning_system.py` | Dropped `element_id` from warnings; unified to M2M only |

## Affected Files

### Seeds
- `database/seeds/seeders/element.py` — Creates Warning + association (M2M only)
- `database/seeds/verify_warning_sync.py` — Verification script

### Data Files
- `database/seeds/data/motos_part.py` — Element definitions with warnings
- `database/seeds/data/aseicars_prof.py` — Element definitions with warnings

### Consumers
- `agent/services/tarifa_service.py` — `get_warnings_by_scope()` uses M2M subquery
- `agent/services/element_state_service.py` — loads warnings via M2M join
- `api/routes/elements.py` — `GET /elements/{id}/warnings` uses associations
