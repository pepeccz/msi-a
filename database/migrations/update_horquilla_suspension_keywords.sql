-- ============================================================================
-- Update HORQUILLA and SUSPENSION_DEL keywords to reduce ambiguity
-- ============================================================================
-- Executed: 2026-02-03
-- Reason: Eliminate ambiguous "horquilla" keyword that causes false positives
--         when users say "barras de horquilla" (should match SUSPENSION_DEL)
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. Update HORQUILLA keywords (remove ambiguous "horquilla" alone)
-- ============================================================================

UPDATE elements
SET 
    keywords = '[
        "horquilla completa",
        "cambio horquilla completa",
        "horquilla entera",
        "tren delantero",
        "tren delantero completo",
        "cambio tren delantero",
        "distancia entre ejes",
        "distancia ejes",
        "nueva distancia ejes",
        "horquilla de otra moto",
        "horquilla nueva",
        "horquilla diferente",
        "horquilla invertida",
        "horquilla convencional",
        "upside down fork",
        "cambio de horquilla por otra",
        "sustitucion horquilla completa"
    ]'::jsonb,
    updated_at = NOW()
WHERE code = 'HORQUILLA'
  AND category_id IN (
      SELECT id FROM vehicle_categories WHERE slug = 'motos-part'
  );

-- Verify HORQUILLA update
SELECT 
    code, 
    name,
    jsonb_array_length(keywords) as keyword_count,
    keywords::text as keywords_preview
FROM elements 
WHERE code = 'HORQUILLA'
  AND category_id IN (SELECT id FROM vehicle_categories WHERE slug = 'motos-part');


-- ============================================================================
-- 2. Update SUSPENSION_DEL keywords (add specificity)
-- ============================================================================

UPDATE elements
SET 
    keywords = '[
        "suspension delantera",
        "barras suspension delantera",
        "muelles suspension delantera",
        "barras de horquilla",
        "barras interiores horquilla",
        "barras interiores",
        "muelles barras",
        "muelles horquilla",
        "muelles suspension",
        "muelles interiores",
        "fork springs",
        "cartuchos suspension",
        "cartuchos horquilla",
        "solo barras",
        "solo muelles",
        "cambio barras",
        "cambio muelles"
    ]'::jsonb,
    updated_at = NOW()
WHERE code = 'SUSPENSION_DEL'
  AND category_id IN (
      SELECT id FROM vehicle_categories WHERE slug = 'motos-part'
  );

-- Verify SUSPENSION_DEL update
SELECT 
    code, 
    name,
    jsonb_array_length(keywords) as keyword_count,
    keywords::text as keywords_preview
FROM elements 
WHERE code = 'SUSPENSION_DEL'
  AND category_id IN (SELECT id FROM vehicle_categories WHERE slug = 'motos-part');


-- ============================================================================
-- 3. Verification: Check for keyword overlap
-- ============================================================================

\echo ''
\echo '============================================================================'
\echo 'VERIFICATION: Keyword Analysis'
\echo '============================================================================'

-- Show current keywords for both elements
SELECT 
    code,
    name,
    jsonb_array_length(keywords) as total_keywords
FROM elements
WHERE code IN ('HORQUILLA', 'SUSPENSION_DEL')
  AND category_id IN (SELECT id FROM vehicle_categories WHERE slug = 'motos-part')
ORDER BY code;

\echo ''
\echo 'Changes applied:'
\echo '- HORQUILLA: Removed ambiguous "horquilla" keyword'
\echo '- HORQUILLA: Added specific keywords (invertida, convencional, upside down)'
\echo '- SUSPENSION_DEL: Added specificity (solo barras, solo muelles, cartuchos)'
\echo ''
\echo 'Expected behavior:'
\echo '- "horquilla completa" → HORQUILLA ✓'
\echo '- "cambio horquilla completa" → HORQUILLA ✓'
\echo '- "barras de horquilla" → SUSPENSION_DEL ✓'
\echo '- "muelles horquilla" → SUSPENSION_DEL ✓'
\echo '- "solo muelles" → SUSPENSION_DEL ✓'
\echo ''

COMMIT;

-- ============================================================================
-- ROLLBACK (if needed):
-- ============================================================================
-- BEGIN;
-- UPDATE elements SET keywords = '["horquilla completa", "horquilla", "tren delantero", "tren delantero completo", "cambio horquilla", "distancia entre ejes", "distancia ejes", "horquilla de otra moto", "horquilla nueva"]'::jsonb WHERE code = 'HORQUILLA';
-- UPDATE elements SET keywords = '["suspension delantera", "barras suspension", "muelles barras", "barras de horquilla", "muelles suspension", "fork springs", "barras interiores", "muelles interiores"]'::jsonb WHERE code = 'SUSPENSION_DEL';
-- COMMIT;
