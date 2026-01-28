-- SQL script to apply element fixes for SUSPENSION_DEL, ESCAPE, CARROCERIA, CABALLETE
-- Run with: docker-compose exec postgres psql -U msia msia_db -f /path/to/this/file.sql
-- Or copy-paste into psql

BEGIN;

-- ============================================================================
-- 1. Update SUSPENSION_DEL keywords (remove generic terms)
-- ============================================================================
UPDATE elements 
SET keywords = '["suspension delantera", "barras suspension", "muelles barras", "barras de horquilla", "muelles suspension", "fork springs", "barras interiores", "muelles interiores"]'::jsonb
WHERE code = 'SUSPENSION_DEL'
  AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part');

-- ============================================================================
-- 2. Add required_fields for SUSPENSION_DEL
-- ============================================================================
-- First delete existing required_fields for this element (if any)
DELETE FROM element_required_fields 
WHERE element_id = (
    SELECT id FROM elements 
    WHERE code = 'SUSPENSION_DEL' 
      AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part')
);

-- Insert new required_fields
INSERT INTO element_required_fields (
    id, element_id, field_key, field_label, field_type, options, is_required, 
    validation_rules, example_value, llm_instruction, sort_order,
    condition_field_key, condition_operator, condition_value
)
SELECT 
    gen_random_uuid(),
    e.id,
    'tipo_modificacion',
    'Tipo de modificacion',
    'select',
    '["Barras de horquilla", "Muelles interiores", "Ambos"]'::jsonb,
    true,
    NULL,
    NULL,
    'Pregunta si la modificacion es de las barras de horquilla, los muelles interiores o ambos',
    1,
    NULL, NULL, NULL
FROM elements e
WHERE e.code = 'SUSPENSION_DEL' 
  AND e.category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part');

INSERT INTO element_required_fields (
    id, element_id, field_key, field_label, field_type, options, is_required, 
    validation_rules, example_value, llm_instruction, sort_order,
    condition_field_key, condition_operator, condition_value
)
SELECT 
    gen_random_uuid(),
    e.id,
    'marca',
    'Marca',
    'text',
    NULL,
    true,
    NULL,
    'Ohlins',
    'Solicita la marca de las barras o muelles',
    2,
    NULL, NULL, NULL
FROM elements e
WHERE e.code = 'SUSPENSION_DEL' 
  AND e.category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part');

INSERT INTO element_required_fields (
    id, element_id, field_key, field_label, field_type, options, is_required, 
    validation_rules, example_value, llm_instruction, sort_order,
    condition_field_key, condition_operator, condition_value
)
SELECT 
    gen_random_uuid(),
    e.id,
    'modelo',
    'Modelo',
    'text',
    NULL,
    false,
    NULL,
    'NIX22',
    'Solicita el modelo especifico si lo conoce',
    3,
    NULL, NULL, NULL
FROM elements e
WHERE e.code = 'SUSPENSION_DEL' 
  AND e.category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part');

-- ============================================================================
-- 3. Add required_fields for ESCAPE
-- ============================================================================
DELETE FROM element_required_fields 
WHERE element_id = (
    SELECT id FROM elements 
    WHERE code = 'ESCAPE' 
      AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part')
);

INSERT INTO element_required_fields (
    id, element_id, field_key, field_label, field_type, options, is_required, 
    validation_rules, example_value, llm_instruction, sort_order,
    condition_field_key, condition_operator, condition_value
)
SELECT 
    gen_random_uuid(),
    e.id,
    'marca_modelo',
    'Marca y modelo del escape',
    'text',
    NULL,
    true,
    NULL,
    'Akrapovic Slip-On',
    'Solicita la marca y modelo del escape (ej: Akrapovic, Yoshimura, Arrow, etc.)',
    1,
    NULL, NULL, NULL
FROM elements e
WHERE e.code = 'ESCAPE' 
  AND e.category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part');

INSERT INTO element_required_fields (
    id, element_id, field_key, field_label, field_type, options, is_required, 
    validation_rules, example_value, llm_instruction, sort_order,
    condition_field_key, condition_operator, condition_value
)
SELECT 
    gen_random_uuid(),
    e.id,
    'homologacion_visible',
    'Tiene numero E visible?',
    'boolean',
    NULL,
    true,
    NULL,
    NULL,
    'Confirma si el escape tiene visible el numero de homologacion (E seguido de numero)',
    2,
    NULL, NULL, NULL
FROM elements e
WHERE e.code = 'ESCAPE' 
  AND e.category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part');

-- ============================================================================
-- 4. Add required_fields for CARROCERIA
-- ============================================================================
DELETE FROM element_required_fields 
WHERE element_id = (
    SELECT id FROM elements 
    WHERE code = 'CARROCERIA' 
      AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part')
);

INSERT INTO element_required_fields (
    id, element_id, field_key, field_label, field_type, options, is_required, 
    validation_rules, example_value, llm_instruction, sort_order,
    condition_field_key, condition_operator, condition_value
)
SELECT 
    gen_random_uuid(),
    e.id,
    'descripcion',
    'Descripcion de la pieza',
    'text',
    NULL,
    true,
    NULL,
    'Quilla inferior',
    'Solicita una descripcion de la pieza de carroceria a modificar',
    1,
    NULL, NULL, NULL
FROM elements e
WHERE e.code = 'CARROCERIA' 
  AND e.category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part');

INSERT INTO element_required_fields (
    id, element_id, field_key, field_label, field_type, options, is_required, 
    validation_rules, example_value, llm_instruction, sort_order,
    condition_field_key, condition_operator, condition_value
)
SELECT 
    gen_random_uuid(),
    e.id,
    'material',
    'Material',
    'select',
    '["ABS", "Fibra de vidrio", "Fibra de carbono", "Polipropileno", "Otro"]'::jsonb,
    true,
    NULL,
    NULL,
    'Pregunta el material de la pieza',
    2,
    NULL, NULL, NULL
FROM elements e
WHERE e.code = 'CARROCERIA' 
  AND e.category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part');

-- ============================================================================
-- 5. Add required_fields for CABALLETE
-- ============================================================================
DELETE FROM element_required_fields 
WHERE element_id = (
    SELECT id FROM elements 
    WHERE code = 'CABALLETE' 
      AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part')
);

INSERT INTO element_required_fields (
    id, element_id, field_key, field_label, field_type, options, is_required, 
    validation_rules, example_value, llm_instruction, sort_order,
    condition_field_key, condition_operator, condition_value
)
SELECT 
    gen_random_uuid(),
    e.id,
    'tipo_modificacion',
    'Tipo de modificacion',
    'select',
    '["Eliminacion", "Sustitucion"]'::jsonb,
    true,
    NULL,
    NULL,
    'Pregunta si se elimina el caballete o se sustituye por otro',
    1,
    NULL, NULL, NULL
FROM elements e
WHERE e.code = 'CABALLETE' 
  AND e.category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part');

INSERT INTO element_required_fields (
    id, element_id, field_key, field_label, field_type, options, is_required, 
    validation_rules, example_value, llm_instruction, sort_order,
    condition_field_key, condition_operator, condition_value
)
SELECT 
    gen_random_uuid(),
    e.id,
    'tipo_caballete',
    'Tipo de caballete',
    'select',
    '["Central", "Lateral"]'::jsonb,
    true,
    NULL,
    NULL,
    'Pregunta si es el caballete central o lateral',
    2,
    NULL, NULL, NULL
FROM elements e
WHERE e.code = 'CABALLETE' 
  AND e.category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part');

-- ============================================================================
-- Verification queries
-- ============================================================================
SELECT 'SUSPENSION_DEL keywords updated:' as info, keywords 
FROM elements 
WHERE code = 'SUSPENSION_DEL' 
  AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part');

SELECT 'Required fields count by element:' as info;
SELECT e.code, COUNT(rf.id) as field_count
FROM elements e
LEFT JOIN element_required_fields rf ON rf.element_id = e.id
WHERE e.code IN ('SUSPENSION_DEL', 'ESCAPE', 'CARROCERIA', 'CABALLETE')
  AND e.category_id = (SELECT id FROM vehicle_categories WHERE slug = 'motos-part')
GROUP BY e.code
ORDER BY e.code;

COMMIT;
