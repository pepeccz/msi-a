# Motorcycle Seeds Restructuring - Next Steps

## Current Status: Seeds Updated ✅, Migration Created ✅

All seed data has been updated and the Alembic migration has been created. Now you need to **test and apply the migration** to an existing database.

## Step-by-Step Instructions

### 1. Review the Migration

```bash
# Read the migration file
cat database/alembic/versions/035_restructure_motos_elements.py

# Key points to verify:
# - Uses deterministic UUIDs (matches seed_utils.py pattern)
# - Creates 2 base elements (FRENADO, CARROCERIA_EXT)
# - Updates 9 child elements with parent_element_id
# - Inserts 19 new required_fields
# - Inserts 4 new warnings
# - Inserts 4 new element_warning_associations
# - Inserts 1 new element (ACCESORIO_GENERICO) with 5 fields
# - Complete downgrade() that reverses everything
```

### 2. Test Migration on Development Database

```bash
# Apply the migration
alembic upgrade head

# Expected output:
# INFO  [alembic.runtime.migration] Running upgrade 7dc32f4a106a -> 035_restructure_motos_elements, Restructure motorcycle elements: add parent nodes, fields, warnings

# Verify migration was applied
alembic current

# Expected: 035_restructure_motos_elements (head)
```

### 3. Verify Database Changes

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U msia msia_db

# Check new base elements exist
SELECT code, name, is_base, parent_element_id, sort_order 
FROM elements 
WHERE code IN ('FRENADO', 'CARROCERIA_EXT')
ORDER BY sort_order;

# Expected: 2 rows with is_base=true, parent_element_id=NULL

# Check child elements have parent_element_id set
SELECT code, name, parent_element_id 
FROM elements 
WHERE code IN ('FRENADO_DISCOS', 'FRENADO_PINZAS', 'CARENADO', 'GUARDABARROS_DEL')
ORDER BY code;

# Expected: 4 rows with non-null parent_element_id

# Check new required fields were added
SELECT e.code, f.field_key, f.field_label, f.is_required
FROM element_required_fields f
JOIN elements e ON f.element_id = e.id
WHERE f.field_key IN ('altura_mm', 'ubicacion_captador_nuevo', 'posicion', 'descripcion_elemento')
ORDER BY e.code, f.field_key;

# Expected: Multiple rows for new fields

# Check warnings were created
SELECT code, message, element_id IS NOT NULL as has_element
FROM warnings
WHERE code IN ('frenado_latiguillos_especificacion', 'antinieblas_pictograma_obligatorio', 
               'llantas_ensayo_neumatico', 'accesorio_generico_evaluacion')
ORDER BY code;

# Expected: 4 rows with has_element=true

# Check ACCESORIO_GENERICO exists
SELECT code, name, sort_order FROM elements WHERE code = 'ACCESORIO_GENERICO';

# Expected: 1 row with sort_order=200

# Exit PostgreSQL
\q
```

### 4. Test Migration Rollback

```bash
# Test downgrade (rollback)
alembic downgrade -1

# Expected output:
# INFO  [alembic.runtime.migration] Running downgrade 035_restructure_motos_elements -> 7dc32f4a106a, Restructure motorcycle elements: add parent nodes, fields, warnings

# Verify rollback
alembic current

# Expected: 7dc32f4a106a

# Verify data was removed
docker-compose exec postgres psql -U msia msia_db -c "SELECT COUNT(*) FROM elements WHERE code IN ('FRENADO', 'CARROCERIA_EXT', 'ACCESORIO_GENERICO');"

# Expected: count = 0

# Exit
```

### 5. Re-apply Migration

```bash
# Re-apply after successful rollback test
alembic upgrade head

# Verify final state
alembic current
# Expected: 035_restructure_motos_elements (head)
```

### 6. Validate Seeds (Optional but Recommended)

```bash
# Validate element seed structure
python3 -m database.seeds.validate_elements_seed

# Expected: All validations pass

# Verify dual warning system
python3 -m database.seeds.verify_warning_sync

# Expected: ✅ SUCCESS: Both systems have X warnings (SYNCED)
```

### 7. Re-seed Database (Optional - Only if Starting Fresh)

⚠️ **WARNING**: This will DELETE and recreate all seed data. Only do this if you're working on a development database with no production data.

```bash
python3 -m database.seeds.run_all_seeds

# Expected:
# ✅ CategorySeeder [motos-part]: Created X, Updated Y, Skipped Z
# ✅ ElementSeeder [motos-part]: Created X, Updated Y, Skipped Z
# ✅ InclusionSeeder [motos-part]: Created X, Updated Y, Skipped Z
# ... etc
```

## Troubleshooting

### Migration Fails: "Duplicate key value violates unique constraint"

**Cause**: Migration UUIDs don't match existing data from seeds.

**Solution**: 
1. Check if seeds were already run with the new data
2. If yes, the migration is redundant - mark it as applied without running:
   ```bash
   alembic stamp head
   ```

### Migration Fails: "Column does not exist"

**Cause**: Database schema is out of sync.

**Solution**:
1. Check current migration version: `alembic current`
2. Ensure you're on `7dc32f4a106a` before running 035
3. If not, apply pending migrations: `alembic upgrade head` (but skip 035 first)

### Downgrade Fails: "Foreign key constraint violation"

**Cause**: Other tables reference the data being deleted.

**Solution**:
1. Check if there's case data using the new elements
2. If yes, you can't rollback without losing that data
3. Consider keeping the migration applied

### Field UUID Mismatch in Seeds vs Migration

**Cause**: field_uuid() function produces different UUIDs.

**Solution**:
1. Both use same SEED_NAMESPACE and pattern
2. Verify the migration file uses exact same function
3. If mismatch persists, update migration UUIDs to match seeds

## What to Expect After Migration

1. **2 new parent elements**: FRENADO, CARROCERIA_EXT (won't appear in tariff calculations, only for hierarchy)
2. **9 child elements updated**: Now have parent_element_id set
3. **19 new required_fields**: Agent will ask these questions during case collection
4. **4 new warnings**: Will be shown to users when relevant elements are selected
5. **1 new element**: ACCESORIO_GENERICO as catch-all for unlisted modifications

## Files Modified in This Work

1. ✅ `database/seeds/data/motos_part.py` - Seed data updated
2. ✅ `database/seeds/data/tier_mappings.py` - ACCESORIO_GENERICO added to T4
3. ✅ `database/alembic/versions/035_restructure_motos_elements.py` - Migration created
4. ✅ `database/seeds/apply_restructure.py` - Automation script (can be deleted after work)
5. ✅ `database/seeds/PLAN_CAMBIOS_MOTOS.md` - Change plan documentation
6. ✅ `database/seeds/RESTRUCTURE_COMPLETED.md` - Completion summary
7. ✅ `database/seeds/NEXT_STEPS.md` - This file

## Reference

- **PDF Form**: `datos/Formularios/FORMULARIO DATOS MOTO MSI REV 2023-01-17_reducido.pdf`
- **Tariff PDF**: `datos/tarifas/2026 TARIFAS USUARIOS FINALES MOTO.pdf`
- **Seed Utils**: `database/seeds/seed_utils.py` (deterministic UUID functions)
- **Database AGENTS.md**: `database/AGENTS.md` (patterns and conventions)

---

**Ready to proceed?** Start with Step 1 (review migration), then Step 2 (test on dev database).
