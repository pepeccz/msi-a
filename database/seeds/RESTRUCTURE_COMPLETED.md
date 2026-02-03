# Motorcycle Seeds Restructuring - COMPLETED ✅

## Completion Date
**February 3, 2026**

## Summary

Successfully restructured the motorcycle homologation seeds (`motos_part.py`) with the following changes:

### 1. Parent Node Creation ✅

**FRENADO (Base Element)**
- Created parent element for brake system components
- Children: FRENADO_DISCOS, FRENADO_PINZAS, FRENADO_BOMBAS, FRENADO_LATIGUILLOS, FRENADO_DEPOSITO
- Moved shared keywords (brembo, nissin, galfer, etc.) to parent
- sort_order: 39

**CARROCERIA_EXT (Base Element)**
- Created parent element for bodywork components
- Children: CARENADO, GUARDABARROS_DEL, GUARDABARROS_TRAS, CARROCERIA
- Moved generic keywords to parent
- sort_order: 49

### 2. Keyword Cleanup ✅

- Removed brand names from brake component children (now in FRENADO parent)
- Removed generic positional keywords from SUSPENSION_TRAS ("trasera", "posterior")
- Made keywords element-specific, moved shared ones to parents

### 3. Required Fields Added ✅

**10 elements enhanced with ~25 new fields:**

1. **INTERMITENTES_DEL**: Added `altura_mm` field
2. **INTERMITENTES_TRAS**: Added `altura_mm` field  
3. **PILOTO_FRENO**: Added `marca` field (reordered sort_order)
4. **LUZ_MATRICULA**: Added `marca` field (reordered sort_order)
5. **CATADIOPTRICO**: Added `marca` field (reordered sort_order)
6. **ANTINIEBLAS**: Added `marca` field (reordered sort_order)
7. **MANDOS_AVANZADOS**: Complete replacement - separate brake/gear pedal materials
8. **MATRICULA**: Added 4 conditional fields:
   - `ubicacion_sin_brazo` (conditional on tipo_montaje)
   - `brazo_material` (conditional on tipo_montaje)
   - `brazo_tipo` (conditional on tipo_montaje)
   - `brazo_marca` (conditional on brazo_tipo - nested condition)
9. **VELOCIMETRO**: Added `ubicacion_captador_nuevo` (conditional on captador)
10. **LLANTAS**: Added `posicion` field (Delantera/Trasera/Ambas)

### 4. Warnings Added ✅

1. **ANTINIEBLAS**: Added `pictograma_obligatorio` warning
2. **LLANTAS**: Added `ensayo_neumatico` warning

### 5. New Element ✅

**ACCESORIO_GENERICO** (sort_order: 200)
- Catch-all element for unlisted modifications
- 5 required fields for manual evaluation
- Warning about manual technical evaluation
- Added to T4_BASE_ELEMENTS in tier_mappings.py

### 6. Tier Mappings Updated ✅

- Added `ACCESORIO_GENERICO` to T4_BASE_ELEMENTS
- Parent elements (FRENADO, CARROCERIA_EXT) NOT added (they're not billable)

## Files Modified

1. ✅ `database/seeds/data/motos_part.py` (2,222 → 2,416 lines)
2. ✅ `database/seeds/data/tier_mappings.py` (273 lines, 1 line changed)

## Files Created

1. ✅ `database/seeds/apply_restructure.py` - Automation script (577 lines)
2. ✅ `database/seeds/PLAN_CAMBIOS_MOTOS.md` - Change plan documentation
3. ✅ `database/seeds/RESTRUCTURE_COMPLETED.md` - This summary

## Next Steps (Pending)

### Step 3: Create Alembic Migration

Create `/home/autohomologacion/msi-a/database/alembic/versions/035_restructure_motos_elements.py`:

**Migration must include:**
1. Insert 2 new base elements (FRENADO, CARROCERIA_EXT) with deterministic UUIDs
2. Update `parent_element_id` for 9 child elements (5 brake + 4 bodywork)
3. Insert ~25 new `ElementRequiredField` records
4. Insert 3 new `Warning` records (2 new warnings + 1 for FRENADO_LATIGUILLOS)
5. Insert 3 new `ElementWarningAssociation` records (dual warning system)
6. Insert 1 new element (ACCESORIO_GENERICO) with 5 fields + 1 warning
7. Complete `downgrade()` to reverse all changes

**UUID Generation Pattern:**
```python
from database.seeds.seed_utils import element_uuid, warning_uuid, field_uuid

CATEGORY_SLUG = "motos-part"

# Base elements
FRENADO_ID = element_uuid(CATEGORY_SLUG, "FRENADO")
CARROCERIA_EXT_ID = element_uuid(CATEGORY_SLUG, "CARROCERIA_EXT")

# Warnings
WARNING_FRENADO_LAT_ID = warning_uuid(CATEGORY_SLUG, "frenado_latiguillos_especificacion")
WARNING_ACCESORIO_ID = warning_uuid(CATEGORY_SLUG, "accesorio_generico_evaluacion")

# Fields
FIELD_IDS = {
    "velocimetro_ubicacion_captador": field_uuid(CATEGORY_SLUG, "VELOCIMETRO", "ubicacion_captador_nuevo"),
    "matricula_ubicacion_sin_brazo": field_uuid(CATEGORY_SLUG, "MATRICULA", "ubicacion_sin_brazo"),
    # ... etc
}
```

### Step 4: Test Migration

```bash
alembic upgrade head    # Apply
alembic downgrade -1    # Test rollback  
alembic upgrade head    # Reapply
```

### Step 5: Validate Seeds

```bash
python -m database.seeds.validate_elements_seed
python -m database.seeds.verify_warning_sync
```

### Step 6: Optional Re-seed

```bash
python -m database.seeds.run_all_seeds
```

## Validation Checks

### Data Integrity
- [x] All parent-child relationships correctly defined
- [x] All conditional fields have proper `condition_field_key`, `condition_operator`, `condition_value`
- [x] No circular field dependencies
- [x] Sort orders properly updated after field insertions
- [x] New element added to tier mappings

### Completeness
- [x] All PDF form fields represented in required_fields
- [x] All tariff document warnings present
- [x] Catch-all element for unlisted modifications

### Consistency
- [x] Keywords are element-specific (shared ones moved to parents)
- [x] Warnings follow dual system (inline + association)
- [x] Field types match data requirements

## Reference Documents

1. **PDF Form**: `datos/Formularios/FORMULARIO DATOS MOTO MSI REV 2023-01-17_reducido.pdf`
2. **Tariff Document**: `datos/tarifas/2026 TARIFAS USUARIOS FINALES MOTO.pdf`
3. **Change Plan**: `database/seeds/PLAN_CAMBIOS_MOTOS.md`

## Notes

- Parent elements (FRENADO, CARROCERIA_EXT) with `is_base=True` are NOT billable elements themselves
- They exist only to provide hierarchy and shared keywords/warnings
- Only child elements appear in tier inclusions
- Automation script successfully applied 10/13 changes (3 required manual intervention due to regex patterns)

---

**Status**: Seeds restructuring complete. Migration creation pending.
