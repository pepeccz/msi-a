# Testing Checklist - Motorcycle Seeds Restructuring

## Pre-Migration Checks ✅

- [x] Seed data updated (`motos_part.py`) - 2,416 lines
- [x] Tier mappings updated (`tier_mappings.py`) - ACCESORIO_GENERICO added
- [x] Migration created (`035_restructure_motos_elements.py`) - 1,016 lines
- [x] Migration syntax validated - No errors
- [x] UUID generation verified - Deterministic UUIDs working
- [x] Documentation created - 5 markdown files

## Migration Testing (You Need to Do This)

### Step 1: Backup Current Database ⏳

```bash
# Create backup before testing
docker-compose exec postgres pg_dump -U msia msia_db > backup_pre_migration_$(date +%Y%m%d).sql

# Verify backup was created
ls -lh backup_pre_migration_*.sql
```

- [ ] Database backup created
- [ ] Backup file size > 0 bytes

### Step 2: Check Current Migration State ⏳

```bash
# Check current migration version
alembic current

# Expected: 7dc32f4a106a (or another recent one, but NOT 035_restructure_motos_elements)
```

- [ ] Current migration identified
- [ ] Migration list shows all previous migrations applied

### Step 3: Apply Migration ⏳

```bash
# Apply the new migration
alembic upgrade head

# Expected output:
# INFO  [alembic.runtime.migration] Running upgrade 7dc32f4a106a -> 035_restructure_motos_elements
```

- [ ] Migration executed without errors
- [ ] No SQL constraint violations
- [ ] No duplicate key errors

### Step 4: Verify with Automated Script ⏳

```bash
# Run verification script
python3 database/seeds/verify_restructure.py

# Expected: All 6 checks pass
```

**Checks performed:**
- [ ] ✅ Elementos base (FRENADO, CARROCERIA_EXT)
- [ ] ✅ Relaciones padre-hijo (9 elementos)
- [ ] ✅ Campos nuevos (19 campos)
- [ ] ✅ Warnings (4 warnings)
- [ ] ✅ Asociaciones warning-element (4 assocs)
- [ ] ✅ ACCESORIO_GENERICO completo

### Step 5: Manual Database Inspection ⏳

```bash
# Connect to database
docker-compose exec postgres psql -U msia msia_db
```

**Check 1: Base elements exist**
```sql
SELECT code, name, is_base, parent_element_id, sort_order 
FROM elements 
WHERE code IN ('FRENADO', 'CARROCERIA_EXT')
ORDER BY sort_order;
```
- [ ] 2 rows returned
- [ ] Both have `is_base = true`
- [ ] Both have `parent_element_id = NULL`

**Check 2: Children have parents**
```sql
SELECT e1.code as child_code, e2.code as parent_code
FROM elements e1
LEFT JOIN elements e2 ON e1.parent_element_id = e2.id
WHERE e1.code IN ('FRENADO_DISCOS', 'FRENADO_PINZAS', 'CARENADO', 'GUARDABARROS_DEL')
ORDER BY e1.code;
```
- [ ] 4 rows returned
- [ ] All have non-null parent_code
- [ ] Brake children → FRENADO
- [ ] Bodywork children → CARROCERIA_EXT

**Check 3: New fields exist**
```sql
SELECT e.code, f.field_key, f.field_label, f.is_required, f.condition_field_key
FROM element_required_fields f
JOIN elements e ON f.element_id = e.id
WHERE e.code = 'VELOCIMETRO' AND f.field_key = 'ubicacion_captador_nuevo';
```
- [ ] 1 row returned
- [ ] `is_required = false`
- [ ] `condition_field_key = 'captador'`

**Check 4: ACCESORIO_GENERICO is complete**
```sql
SELECT 
    e.code,
    e.name,
    e.sort_order,
    (SELECT COUNT(*) FROM element_required_fields WHERE element_id = e.id) as field_count,
    (SELECT COUNT(*) FROM warnings WHERE element_id = e.id) as warning_count
FROM elements e
WHERE e.code = 'ACCESORIO_GENERICO';
```
- [ ] 1 row returned
- [ ] `sort_order = 200`
- [ ] `field_count = 5`
- [ ] `warning_count = 1`

**Check 5: Dual warning system**
```sql
-- Inline warnings
SELECT code, message, element_id IS NOT NULL as has_element_id
FROM warnings
WHERE code LIKE 'frenado_latiguillos%'
   OR code LIKE 'antinieblas_pictograma%'
   OR code LIKE 'llantas_ensayo%'
   OR code LIKE 'accesorio_generico%'
ORDER BY code;

-- Associations
SELECT w.code, e.code as element_code, ewa.show_condition
FROM element_warning_associations ewa
JOIN warnings w ON ewa.warning_id = w.id
JOIN elements e ON ewa.element_id = e.id
WHERE w.code IN (
    'frenado_latiguillos_especificacion',
    'antinieblas_pictograma_obligatorio',
    'llantas_ensayo_neumatico',
    'accesorio_generico_evaluacion'
)
ORDER BY w.code;
```
- [ ] 4 inline warnings found
- [ ] All have `has_element_id = true`
- [ ] 4 associations found
- [ ] All have `show_condition = 'always'`

```sql
\q  -- Exit PostgreSQL
```

### Step 6: Test Migration Rollback ⏳

```bash
# Rollback the migration
alembic downgrade -1

# Expected output:
# INFO  [alembic.runtime.migration] Running downgrade 035_restructure_motos_elements -> 7dc32f4a106a
```

- [ ] Downgrade executed without errors
- [ ] No foreign key constraint violations

**Verify data was removed:**
```bash
docker-compose exec postgres psql -U msia msia_db -c \
  "SELECT COUNT(*) as count FROM elements WHERE code IN ('FRENADO', 'CARROCERIA_EXT', 'ACCESORIO_GENERICO');"
```
- [ ] Count = 0 (all removed)

```bash
# Check current migration state
alembic current
```
- [ ] Shows previous migration (7dc32f4a106a)

### Step 7: Re-apply Migration ⏳

```bash
# Re-apply the migration
alembic upgrade head

# Verify final state
alembic current
```
- [ ] Migration re-applied successfully
- [ ] Current migration is `035_restructure_motos_elements (head)`

### Step 8: Optional - Validate Seeds ⏳

```bash
# Validate seed data structure
python3 -m database.seeds.validate_elements_seed

# Verify dual warning system
python3 -m database.seeds.verify_warning_sync
```

- [ ] validate_elements_seed passes
- [ ] verify_warning_sync shows systems in sync

### Step 9: Optional - Re-seed Database ⏳

⚠️ **WARNING**: Only do this on a development database without production data!

```bash
# Full re-seed (deletes all existing seed data)
python3 -m database.seeds.run_all_seeds

# Expected: CategorySeeder, ElementSeeder, InclusionSeeder all succeed
```

- [ ] Seeding completed without errors
- [ ] No UUID constraint violations
- [ ] All elements created/updated

## Post-Migration Verification ⏳

### Agent Behavior Changes Expected

Once migration is applied, the agent will:

1. **Ask new questions** for the 19 new required_fields when collecting element data
2. **Show new warnings** for FRENADO_LATIGUILLOS, ANTINIEBLAS, LLANTAS
3. **Recognize ACCESORIO_GENERICO** as catch-all for unlisted modifications
4. **Conditional fields work** - only ask brazo_material if tipo_montaje = "Con brazo lateral"

### Test with Real Agent (Manual Testing)

- [ ] Create test case with VELOCIMETRO → Agent asks for ubicacion_captador_nuevo conditionally
- [ ] Create test case with LLANTAS → Agent shows ensayo warning
- [ ] Create test case with unknown element → Agent identifies as ACCESORIO_GENERICO
- [ ] Create test case with MATRICULA → Agent asks 4 conditional fields correctly

## Cleanup ⏳

After all tests pass:

```bash
# Optional: Remove automation script (no longer needed)
rm database/seeds/apply_restructure.py

# Keep documentation for reference
ls database/seeds/*.md
```

- [ ] Automation script removed (optional)
- [ ] Documentation files kept for reference

## Rollback Plan (If Something Fails)

If migration causes issues in production:

```bash
# 1. Restore from backup
docker-compose exec -T postgres psql -U msia msia_db < backup_pre_migration_YYYYMMDD.sql

# 2. Mark migration as not applied
alembic stamp 7dc32f4a106a

# 3. Verify state
alembic current
# Should show: 7dc32f4a106a
```

## Final Checklist ✅

- [ ] All automated checks pass
- [ ] All manual SQL checks pass
- [ ] Migration rollback works correctly
- [ ] Migration re-apply works correctly
- [ ] Documentation reviewed
- [ ] Team notified of changes
- [ ] Agent tested with new fields/warnings

---

**Status**: Ready for testing ✅

**Next**: Follow steps 1-9 in order. Stop if any check fails and debug before continuing.
