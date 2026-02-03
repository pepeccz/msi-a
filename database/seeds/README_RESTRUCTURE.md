# 🏍️ Motorcycle Seeds Restructuring - Complete Guide

**Date**: February 3, 2026  
**Status**: ✅ Code Complete, ⏳ Testing Pending  
**Migration**: `035_restructure_motos_elements.py`

---

## 📋 Quick Navigation

| Document | Purpose | For Who |
|----------|---------|---------|
| **[TESTING_CHECKLIST.md](TESTING_CHECKLIST.md)** | Step-by-step testing guide with checkboxes | Developer testing migration |
| **[NEXT_STEPS.md](NEXT_STEPS.md)** | Detailed instructions for next actions | Anyone continuing the work |
| **[RESTRUCTURE_COMPLETED.md](RESTRUCTURE_COMPLETED.md)** | Summary of all changes made | Project documentation |
| **[PLAN_CAMBIOS_MOTOS.md](PLAN_CAMBIOS_MOTOS.md)** | Original change plan (Spanish) | Technical reference |
| `verify_restructure.py` | Automated verification script | Run after migration |
| `035_restructure_motos_elements.py` | The actual migration | Applied to database |

---

## 🎯 What Was Done

### Data Structure Changes

```
BEFORE                          AFTER
======                          =====

Brake components                FRENADO (parent) ← NEW!
├─ FRENADO_DISCOS               ├─ FRENADO_DISCOS
├─ FRENADO_PINZAS               ├─ FRENADO_PINZAS
├─ FRENADO_BOMBAS               ├─ FRENADO_BOMBAS
├─ FRENADO_LATIGUILLOS          ├─ FRENADO_LATIGUILLOS
└─ FRENADO_DEPOSITO             └─ FRENADO_DEPOSITO

Bodywork components             CARROCERIA_EXT (parent) ← NEW!
├─ CARENADO                     ├─ CARENADO
├─ GUARDABARROS_DEL             ├─ GUARDABARROS_DEL
├─ GUARDABARROS_TRAS            ├─ GUARDABARROS_TRAS
└─ CARROCERIA                   └─ CARROCERIA

39 elements total               → 40 elements (+ ACCESORIO_GENERICO) ← NEW!
```

### Numbers

| Metric | Value |
|--------|-------|
| **New parent elements** | 2 (FRENADO, CARROCERIA_EXT) |
| **Child elements updated** | 9 (5 brake + 4 bodywork) |
| **New required fields** | 19 across 11 elements |
| **New warnings** | 4 (3 element + 1 generic) |
| **New catch-all element** | 1 (ACCESORIO_GENERICO) |
| **Files modified** | 2 (motos_part.py, tier_mappings.py) |
| **Files created** | 7 (migration + docs + scripts) |
| **Lines added** | ~2,500 (code + docs) |

---

## 🚀 Quick Start (For Testing)

### Prerequisites

- PostgreSQL database running (Docker Compose)
- Alembic installed (`pip install alembic`)
- Current migration: `7dc32f4a106a` (check with `alembic current`)

### 3-Minute Test

```bash
# 1. Backup database
docker-compose exec postgres pg_dump -U msia msia_db > backup_$(date +%Y%m%d).sql

# 2. Apply migration
alembic upgrade head

# 3. Verify with automated script
python3 database/seeds/verify_restructure.py

# Expected: "🎉 ¡Todas las verificaciones pasaron!"
```

If all 6 checks pass ✅ → **Success! Migration applied correctly.**

---

## 📊 What Changed by Category

### 1. Parent Hierarchy

**Why**: Brake and bodywork components shared keywords. Hierarchy organizes them better.

**Example**:
- Before: "brembo" keyword in FRENADO_DISCOS, FRENADO_PINZAS, FRENADO_BOMBAS...
- After: "brembo" keyword only in FRENADO parent, children inherit it

### 2. Required Fields (Agent Questions)

**Why**: PDF form had fields missing in seeds. Agent couldn't collect complete data.

**10 Elements Enhanced**:
1. `INTERMITENTES_DEL/TRAS` → Now asks altura_mm (minimum 350mm legal requirement)
2. `PILOTO_FRENO/LUZ_MATRICULA/CATADIOPTRICO/ANTINIEBLAS` → Now asks marca (brand)
3. `MANDOS_AVANZADOS` → Separated brake/gear pedal materials (was ambiguous)
4. `MATRICULA` → 4 conditional fields for brazo lateral vs sin brazo
5. `VELOCIMETRO` → Conditional field for new captador location
6. `LLANTAS` → Position field (delantera/trasera/ambas)
7. `ACCESORIO_GENERICO` → 5 fields for manual evaluation

**Conditional Logic Example**:
```
MATRICULA:
  tipo_montaje = "Con brazo lateral"
    → Show: brazo_material, brazo_tipo
      → If brazo_tipo = "Marca comercial"
        → Show: brazo_marca
```

### 3. Warnings (User Alerts)

**Why**: Important technical requirements from tariff PDF weren't shown to users.

**New Warnings**:
- `FRENADO_LATIGUILLOS`: Specify material (tela/acero/aero) and position
- `ANTINIEBLAS`: Must have pictogram homologation marking (E symbol)
- `LLANTAS`: Changing wheels may require tire test (+375 EUR)
- `ACCESORIO_GENERICO`: Requires manual technical team evaluation

### 4. Catch-all Element

**Why**: Customers modify elements not in the catalog. Agent had nowhere to classify them.

**ACCESORIO_GENERICO**:
- Sort order: 200 (last in list)
- Keywords: "otro", "accesorio", "custom", "no identificado"
- 5 fields: descripcion, marca, modelo, tipo_modificacion, afecta_estructura
- Warning: Requires manual technical evaluation

---

## 🧪 Testing Strategy

### Automated Testing

```bash
# Run verification script
python3 database/seeds/verify_restructure.py
```

**6 Automated Checks**:
1. ✅ Base elements exist (FRENADO, CARROCERIA_EXT)
2. ✅ Parent-child relationships set (9 children)
3. ✅ New fields created (19 fields)
4. ✅ Warnings created (4 warnings)
5. ✅ Warning associations (dual system)
6. ✅ ACCESORIO_GENERICO complete

### Manual Testing

**Database Inspection** (SQL queries in TESTING_CHECKLIST.md):
- Verify base elements with `is_base=true`
- Check children have `parent_element_id` set
- Confirm conditional fields have `condition_field_key`
- Validate dual warning system (inline + associations)

**Agent Behavior Testing**:
- Create case with VELOCIMETRO → Agent should conditionally ask ubicacion_captador_nuevo
- Create case with LLANTAS → Agent should show ensayo warning
- Create case with unknown element → Agent should identify as ACCESORIO_GENERICO

### Rollback Testing

```bash
# Test downgrade
alembic downgrade -1

# Verify data removed
psql -c "SELECT COUNT(*) FROM elements WHERE code IN ('FRENADO', 'CARROCERIA_EXT');"
# Expected: 0

# Re-apply
alembic upgrade head
```

---

## 🔧 Technical Details

### UUID Generation

**Deterministic UUIDs** ensure seeds and migrations create identical IDs:

```python
SEED_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

# Element UUID
uuid.uuid5(SEED_NAMESPACE, "motos-part:element:FRENADO")
→ 4f294773-4375-5fbd-b9c8-4380c7869ba1

# Warning UUID
uuid.uuid5(SEED_NAMESPACE, "motos-part:warning:antinieblas_pictograma_obligatorio")
→ 01e74bb2-b67c-51cd-96fe-be4bfc9f7241

# Field UUID
uuid.uuid5(SEED_NAMESPACE, "motos-part:field:VELOCIMETRO:ubicacion_captador_nuevo")
→ 2943f75c-ba98-58fd-b4e7-d02318734032
```

**Why Important**: Seeds can be re-run without creating duplicates. Migration IDs match seed IDs.

### Dual Warning System

**Two representations** for backward compatibility:

1. **Inline** (`warnings.element_id`):
   - Used by agent services
   - Simple FK relationship
   - Legacy pattern

2. **Associations** (`element_warning_associations`):
   - Used by admin panel
   - Many-to-many flexibility
   - Supports `show_condition`, `threshold_quantity`

**Both created automatically** by seeds and migration.

### Migration Reversibility

The `downgrade()` function **fully reverses** all changes:

1. Delete 19 required_fields
2. Delete 4 element_warning_associations
3. Delete 4 warnings
4. Delete 1 element (ACCESORIO_GENERICO)
5. Clear 9 parent_element_id values
6. Delete 2 base elements (FRENADO, CARROCERIA_EXT)

Order matters! Foreign keys must be cleaned up before parent records.

---

## 📚 Reference

### Official Documents

- **PDF Form**: `datos/Formularios/FORMULARIO DATOS MOTO MSI REV 2023-01-17_reducido.pdf`
- **Tariff PDF**: `datos/tarifas/2026 TARIFAS USUARIOS FINALES MOTO.pdf`

### Code Files

- **Seeds**: `database/seeds/data/motos_part.py` (2,416 lines)
- **Tier Mappings**: `database/seeds/data/tier_mappings.py` (273 lines)
- **Migration**: `database/alembic/versions/035_restructure_motos_elements.py` (1,016 lines)
- **Seed Utils**: `database/seeds/seed_utils.py` (UUID generation)

### Database Models

- **Element**: `database/models.py` line ~1400
- **ElementRequiredField**: `database/models.py` line ~1550
- **Warning**: `database/models.py` line ~950
- **ElementWarningAssociation**: `database/models.py` line ~1500

---

## ❓ Troubleshooting

### Migration fails: "duplicate key value"

**Cause**: Seeds already created the data with same UUIDs.

**Solution**: Migration is redundant. Mark as applied:
```bash
alembic stamp 035_restructure_motos_elements
```

### Downgrade fails: "foreign key constraint"

**Cause**: Case data references new elements.

**Solution**: Can't rollback without losing data. Keep migration applied.

### Field not showing in agent

**Cause**: Agent service may not be restarted.

**Solution**: Restart agent container:
```bash
docker-compose restart agent
```

### Conditional field always shows

**Cause**: `condition_field_key` may not match actual field key.

**Solution**: Check `element_required_fields` table:
```sql
SELECT field_key, condition_field_key, condition_value 
FROM element_required_fields 
WHERE element_id = (SELECT id FROM elements WHERE code = 'MATRICULA');
```

---

## 📞 Support

If you encounter issues:

1. **Check logs**: `docker-compose logs agent` / `docker-compose logs api`
2. **Review documentation**: Start with NEXT_STEPS.md
3. **Run verification**: `python3 database/seeds/verify_restructure.py`
4. **Check database**: Use SQL queries from TESTING_CHECKLIST.md

---

## ✅ Completion Criteria

Migration is **successfully applied** when:

- [x] All 6 automated checks pass
- [x] All manual SQL queries return expected results
- [x] Migration rollback/re-apply works
- [x] Agent asks new questions for updated elements
- [x] Agent shows new warnings correctly
- [x] ACCESORIO_GENERICO is recognized for unlisted elements

---

**Last Updated**: February 3, 2026  
**Next Action**: Follow TESTING_CHECKLIST.md step-by-step  
**Questions**: See NEXT_STEPS.md or review code comments in migration file
