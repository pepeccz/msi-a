# Element Warning System - Dual Architecture

## Overview

Element warnings in MSI-a are stored using a **dual system** to maintain compatibility between different parts of the application:

1. **Inline Warnings** - `warnings.element_id` (FK to elements)
2. **Association Warnings** - `element_warning_associations` (many-to-many table)

## Why Two Systems?

### Historical Context

The system evolved with two different approaches:
- Agent/tariff services query warnings directly via `warnings.element_id`
- Admin panel and newer APIs use the association table for flexibility

### Synchronization Strategy

Rather than migrate all code to one system (breaking existing functionality), the seeds **create both representations** automatically, ensuring:
- ✅ Agent services work correctly
- ✅ Admin panel displays warnings
- ✅ No data inconsistencies
- ✅ No breaking changes needed

## Database Schema

```
┌─────────────────────┐
│   warnings          │
├─────────────────────┤
│ id (PK)             │
│ code                │
│ message             │
│ element_id (FK)     │──► System 1: INLINE (agent uses this)
│ category_id (FK)    │
│ tier_id (FK)        │
└─────────────────────┘

┌─────────────────────────────────────┐
│ element_warning_associations        │  System 2: ASSOCIATIONS (admin uses this)
├─────────────────────────────────────┤
│ id (PK)                             │
│ element_id (FK) ────────────►       │
│ warning_id (FK) ────────────►       │
│ show_condition                      │  (Extra flexibility for admin)
│ threshold_quantity                  │
└─────────────────────────────────────┘
```

## How Seeds Work

### ElementSeeder Workflow

```python
# For each element with warnings:
for elem_data in elements:
    # 1. Create element
    element = Element(...)

    # 2. Create inline warnings (warnings.element_id)
    for warning_data in elem_data.get("warnings", []):
        warning = Warning(
            element_id=element.id,  # ← Inline system
            code=warning_data["code"],
            message=warning_data["message"],
            ...
        )

    # 3. Create associations (element_warning_associations)
    for warning_data in elem_data.get("warnings", []):
        association = ElementWarningAssociation(
            element_id=element.id,
            warning_id=warning.id,
            show_condition="always",  # ← Association system
            threshold_quantity=None,
        )
```

### Key Points

- Seeds create **both** representations for every element warning
- Uses deterministic UUIDs for idempotency
- Checks for existing records to avoid duplicates
- Logs statistics for both systems

## Usage in Code

### Agent Services (Using Inline)

```python
# agent/services/tarifa_service.py
warnings = await session.execute(
    select(Warning).where(Warning.element_id == element_id)
)
```

### Admin Panel (Using Associations)

```python
# api/routes/elements.py
associations = await session.execute(
    select(ElementWarningAssociation)
    .where(ElementWarningAssociation.element_id == element_id)
    .options(selectinload(ElementWarningAssociation.warning))
)
```

## Verification

After running seeds, verify synchronization:

```bash
python -m database.seeds.verify_warning_sync
```

Expected output:
```
✓ Inline warnings: 63
✓ Association warnings: 63
✅ SUCCESS: Both systems have 63 warnings (SYNCED)
```

### Manual SQL Verification

```sql
-- Count inline warnings
SELECT COUNT(*) FROM warnings WHERE element_id IS NOT NULL;

-- Count associations
SELECT COUNT(*) FROM element_warning_associations;

-- Verify relationships
SELECT
    e.code AS element_code,
    w.code AS warning_code,
    CASE WHEN w.element_id IS NOT NULL THEN '✓' ELSE '✗' END AS inline,
    CASE WHEN ewa.id IS NOT NULL THEN '✓' ELSE '✗' END AS association
FROM elements e
LEFT JOIN warnings w ON w.element_id = e.id
LEFT JOIN element_warning_associations ewa
    ON ewa.element_id = e.id AND ewa.warning_id = w.id
WHERE w.id IS NOT NULL
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

**No additional code needed** - both inline and association will be created automatically.

### Updating Existing Warnings

Warnings are **upserted** on each seed run:
- Existing warnings are updated (message, severity, etc.)
- Missing associations are created
- Deterministic UUIDs ensure same IDs across runs

## Future Improvements

### Option A: Keep Dual System (Current)
- **Pros**: No breaking changes, works for all consumers
- **Cons**: Slight duplication, more complex to understand

### Option B: Migrate to Single System
- Unify all code to use associations only
- Add `warnings` relationship to Element model
- Requires updating agent services
- More work upfront, cleaner long-term

**Current recommendation**: Keep dual system until major refactor.

## Affected Files

### Seeds
- `database/seeds/seeders/element.py` - Creates both representations
- `database/seeds/verify_warning_sync.py` - Verification script

### Data Files
- `database/seeds/data/motos_part.py` - Element definitions with warnings
- `database/seeds/data/aseicars_prof.py` - Element definitions with warnings

### Consumers (Inline)
- `agent/services/tarifa_service.py:543-599` - `get_warnings_by_scope()`

### Consumers (Associations)
- `agent/services/element_service.py:395-479` - `get_element_warnings()`
- `api/routes/elements.py:810-838` - `GET /elements/{id}/warnings`

## Troubleshooting

### Admin Panel Not Showing Warnings

**Symptom**: Warnings exist in database but don't appear in admin panel

**Diagnosis**:
```bash
python -m database.seeds.verify_warning_sync
```

**Fix**:
```bash
# Re-run seeds to create missing associations
python -m database.seeds.run_all_seeds
```

### Mismatched Counts

**Symptom**: Inline count ≠ Association count

**Cause**: Seeds were interrupted or only partially ran

**Fix**:
```bash
# Clear and re-run
docker-compose exec postgres psql -U msia msia_db -c "DELETE FROM element_warning_associations;"
python -m database.seeds.run_all_seeds
```

## Summary

- **Two systems**: inline (`warnings.element_id`) + associations (`element_warning_associations`)
- **Seeds create both** automatically for all element warnings
- **No code changes needed** when adding warnings to data files
- **Verification script** available to check synchronization
- **Both systems work** - agent and admin panel are compatible
