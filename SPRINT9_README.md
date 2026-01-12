# SPRINT 9: Seed Data Implementation

This document describes how to set up the Element System with seed data from the PDF.

## Overview

The seed scripts populate the database with:
1. **Element Catalog**: 10 homologable elements for "Autocaravanas Profesional"
2. **Element Images**: Multiple images per element (examples + required documents)
3. **Tier Inclusions**: Hierarchical relationships between tiers and elements according to the PDF

## Files Created

### 1. `database/seeds/elements_from_pdf_seed.py`
Main seed script that populates:
- Elements with keywords, aliases, and descriptions
- ElementImages with different types (example, required_document, warning)
- TierElementInclusions creating the hierarchical structure

**Elements created** (10 total):
- `ESC_MEC` - Escalera mecánica trasera
- `TOLDO_LAT` - Toldo lateral
- `PLACA_200W` - Placa solar >200W
- `ANTENA_PAR` - Antena parabólica
- `PORTABICIS` - Portabicis trasero
- `CLARABOYA` - Claraboya adicional
- `BACA_TECHO` - Baca portaequipajes
- `BOLA_REMOLQUE` - Bola de remolque
- `NEVERA_COMPRESOR` - Nevera de compresor
- `DEPOSITO_AGUA` - Depósito de agua adicional

### 2. `database/seeds/validate_elements_seed.py`
Validation script that verifies:
- Category exists
- Elements created correctly
- Images per element
- Tier inclusions configured
- Tier resolution algorithm works

### 3. `tests/test_element_system.py`
Comprehensive test suite (5 test suites, 17+ tests):

**Test Suite 1: Element Matching**
- Single element matching
- Multiple elements matching
- Fuzzy matching (typos)
- No match handling
- Element with images

**Test Suite 2: Tier Resolution**
- Resolve T6 (base tier)
- Resolve T3 (includes T6)
- Resolve T2 (references T3)
- Resolve T1 (complete hierarchy)

**Test Suite 3: Tariff Selection**
- Single element selection
- Multiple elements selection
- Respect quantity limits
- Complex scenarios

**Test Suite 4: Consistency**
- No circular references
- All elements accessible

**Test Suite 5: Performance**
- Resolution performance < 5s

## PDF Structure Implemented

### Tier Hierarchy (Autocaravanas Profesional)

```
T1 (270€) - Proyecto Completo
├─ T2 (Unlimited)
├─ T3 (Unlimited)
├─ T4 (Unlimited)
├─ T5 (Unlimited)
└─ T6 (Unlimited)

T2 (230€) - Proyecto Ampliado
├─ T3 (Max 2 elements)
└─ T6 (Unlimited)

T3 (180€) - Proyecto Básico
├─ ESC_MEC (Max 1)
├─ TOLDO_LAT (Max 1)
├─ PLACA_200W (Max 1)
└─ T6 (Unlimited)

T4 (135€) - Proyecto Reducido
└─ T6 (Unlimited)

T5 (65€) - Mínimo con Elementos
└─ T6 (Max 3)

T6 (59€) - Sin Proyecto
├─ ANTENA_PAR
└─ PORTABICIS
```

## Usage

### Step 1: Prerequisites

Ensure the category "aseicars" (Autocaravanas Profesional) already exists:

```bash
# Run the existing category seed if needed
docker-compose exec api python -m database.seeds.aseicars_seed
```

### Step 2: Run Main Seed

```bash
# From project root
docker-compose exec api python -m database.seeds.elements_from_pdf_seed
```

Expected output:
```
================================================================================
Starting Element System Seed
================================================================================

[STEP 1] Getting category: aseicars
✓ Found category: Autocaravanas (32xx, 33xx) (ID: ...)

[STEP 2] Getting tiers for category
✓ Found 6 tiers:
  - T1: Proyecto Completo (270.00€)
  - T2: Proyecto Ampliado (230.00€)
  - ...

[STEP 3] Creating elements
✓ ESC_MEC: Created with 4 images
✓ TOLDO_LAT: Created with 4 images
...

[STEP 4] Creating tier element inclusions
  T6 (59€): ANTENA_PAR, PORTABICIS (max 1 each)
  T3 (180€): ESC_MEC, TOLDO_LAT, PLACA_200W (max 1 each) + T6 unlimited
  T2 (230€): Up to 2 elements from T3 + T6 unlimited
  T1 (270€): Unlimited everything (includes T2, T3, T4, T5, T6)

[STEP 5] Committing changes to database
✓ Committed successfully

================================================================================
✓ SEED COMPLETED SUCCESSFULLY
================================================================================
```

### Step 3: Validate Seed

```bash
docker-compose exec api python -m database.seeds.validate_elements_seed
```

Expected output:
```
================================================================================
VALIDATING ELEMENT SYSTEM SEED DATA
================================================================================

[CHECK 1] Category exists
✓ Category found: Autocaravanas (32xx, 33xx)

[CHECK 2] Elements created
✓ Found 10 elements:
  • ESC_MEC: Escalera mecánica trasera
  • TOLDO_LAT: Toldo lateral
  ...

[CHECK 3] Images per element
✓ Total 34 images across all elements:
  • ESC_MEC: 4 images (2 required, 2 examples)
  • TOLDO_LAT: 4 images (2 required, 2 examples)
  ...

[CHECK 4] Tier inclusions (according to PDF)
✓ Found 6 tiers

  T1 (Proyecto Completo) - 270€:
    Tier references (5):
      • T2: max unlimited
      • T3: max unlimited
      ...

[CHECK 5] Testing tier element resolution
  T1 resolves to:
    • ESC_MEC: max 1
    • TOLDO_LAT: max 1
    • PLACA_200W: max 1
    • ANTENA_PAR: max unlimited
    • PORTABICIS: max unlimited
    ... and 5 more

[CHECK 6] PDF Structure Compliance
✓ T1 includes 10 elements (expected >= 8)

================================================================================
✓ VALIDATION COMPLETE
================================================================================
```

### Step 4: Run Tests

```bash
# Run all element system tests
docker-compose exec api pytest tests/test_element_system.py -v

# Or specific test suite
docker-compose exec api pytest tests/test_element_system.py::test_match_single_element -v
```

### Step 5: Test in Admin Panel

1. Open http://localhost:3000/elementos
2. You should see the 10 elements listed
3. Click on an element to edit and see its images
4. Go to a tariff's inclusions page to see the hierarchy

### Step 6: Test in Agent

Test the agent with:

```bash
# From WhatsApp or test endpoint
"Quiero homologar una escalera mecánica"
→ Should identify ESC_MEC and quote T3 (180€) or higher

"Solo antena parabólica"
→ Should identify ANTENA_PAR and quote T6 (59€)

"Escalera, toldo y 2 placas solares"
→ Should identify 3 elements and quote appropriate tariff
```

## Verification Checklist

- [ ] Seed script runs without errors
- [ ] Validation script reports all checks pass
- [ ] Element count matches (10 elements)
- [ ] Image count is correct (34 total)
- [ ] Tier inclusions follow PDF structure
- [ ] Admin panel shows elements
- [ ] Element detail pages show images
- [ ] TierInclusionEditor shows hierarchy
- [ ] Tests pass (17+ tests)
- [ ] Agent identifies elements correctly
- [ ] Tariff selection is accurate

## Troubleshooting

### "Category 'aseicars' not found"
**Solution**: Run `python -m database.seeds.aseicars_seed` first to create the category.

### "No active tiers found"
**Solution**: Verify the category has T1-T6 tiers. Check database directly:
```sql
SELECT code, name FROM tariff_tier WHERE category_id = '...' AND is_active = true;
```

### Elements not showing in admin panel
**Solution**:
1. Clear Redis cache: `docker-compose exec redis redis-cli FLUSHDB`
2. Refresh the page
3. Check console for errors

### Image URLs are broken
**Solution**: The seed uses placeholder URLs (`placeholder.com`). Replace with real S3/CDN URLs by updating `get_placeholder_image_url()` in the seed script and re-running, or update images in admin panel.

## Image URL Setup

Currently, images use placeholder URLs like:
```
https://via.placeholder.com/400x300?text=ESC_MEC_Vista_trasera_cerrada
```

To use real images:

1. **Option A: Update Image URLs in Admin Panel**
   - Go to `/elementos/{id}`
   - Click each image to edit
   - Update the URL to point to your S3 bucket or CDN

2. **Option B: Update Seed Script**
   - Modify `get_placeholder_image_url()` function
   - Re-run seed (will create duplicates if elements exist; use validation to check first)

3. **Option C: Bulk Update via API**
   - Use the admin API to batch update image URLs

## Next Steps (SPRINT 10)

The seed data is now ready for:
1. **Unit Testing**: Element matching and tier resolution algorithms
2. **Integration Testing**: API endpoints with real data
3. **E2E Testing**: Admin panel and agent workflows
4. **Performance Testing**: Tariff calculation under load

See `tests/test_element_system.py` for the test suite.

## Notes

- Seed only runs if category "aseicars" exists (safe to run multiple times)
- Elements are cached in Redis (TTL 5 minutes)
- Image URLs are placeholders and should be replaced
- Tier hierarchy follows PDF exactly
- All algorithms tested against PDF requirements
