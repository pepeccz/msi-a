-- ============================================================================
-- SQL Script to insert element_required_fields for Motocicletas category
-- Generated from motos_part.py seed data
-- ============================================================================
-- 
-- Run this script:
--    docker-compose exec -T postgres psql -U msia msia_db < scripts/insert_required_fields.sql
-- ============================================================================

BEGIN;

-- Clean up existing data first
DELETE FROM element_required_fields 
WHERE element_id IN (
    SELECT id FROM elements WHERE category_id = '6a57c85d-b915-5070-957b-1505e20c7474'
);

-- ============================================================================
-- SUBCHASIS - 3 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'descripcion_modificacion', 'En qué consiste la modificación', 'text', NULL, true, NULL, 'Recorte de 15cm del subchasis trasero', 'Pregunta al usuario en qué consiste exactamente la modificación del subchasis (recorte, sustitución, refuerzo, etc.)', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'SUBCHASIS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'medida_desde_tanque', 'Nueva medida desde el tanque (mm)', 'number', NULL, true, '{"min_value": 100, "max_value": 1500}', '450', 'Solicita la nueva medida en milímetros desde el tanque de combustible hasta el final del subchasis', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'SUBCHASIS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'nueva_longitud_total', 'Nueva longitud total del vehículo (mm)', 'number', NULL, false, '{"min_value": 1500, "max_value": 3000}', '2100', 'Si la modificación afecta a la longitud total del vehículo, solicita la nueva medida en milímetros', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'SUBCHASIS';

-- ============================================================================
-- ASIDEROS - 1 field
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'tipo_sustitucion', 'Tipo de sustitución', 'select', '["Piel", "Metálico"]', true, NULL, NULL, 'Pregunta si los nuevos asideros son de piel o metálicos', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'ASIDEROS';

-- ============================================================================
-- SUSPENSION_TRAS - 8 fields (2 conditional)
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'marca_muelle', 'Marca del muelle', 'text', NULL, true, NULL, 'Ohlins', 'Solicita la marca del muelle de la suspensión trasera', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'SUSPENSION_TRAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'modelo_muelle', 'Modelo del muelle', 'text', NULL, true, NULL, 'S46DR1', 'Solicita el modelo específico del muelle', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'SUSPENSION_TRAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'longitud_muelle', 'Longitud del muelle (mm)', 'number', NULL, true, '{"min_value": 100, "max_value": 500}', '280', 'Solicita la longitud del muelle en milímetros', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'SUSPENSION_TRAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'grosor_espira', 'Grosor de espira (mm)', 'number', NULL, true, '{"min_value": 5, "max_value": 30}', '12', 'Solicita el grosor de la espira del muelle en milímetros', 4, NOW(), NOW()
FROM elements e WHERE e.code = 'SUSPENSION_TRAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'diametro_muelle', 'Diámetro del muelle (mm)', 'number', NULL, true, '{"min_value": 30, "max_value": 100}', '46', 'Solicita el diámetro exterior del muelle en milímetros', 5, NOW(), NOW()
FROM elements e WHERE e.code = 'SUSPENSION_TRAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'cambio_amortiguador', '¿Se cambia también el amortiguador?', 'boolean', NULL, true, NULL, NULL, 'Pregunta si además del muelle también se sustituye el amortiguador', 6, NOW(), NOW()
FROM elements e WHERE e.code = 'SUSPENSION_TRAS';

-- Conditional fields for SUSPENSION_TRAS
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'marca_amortiguador', 'Marca del amortiguador', 'text', NULL, false, NULL, 'Ohlins', 'Si se cambia el amortiguador, solicita la marca', 7, 
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'cambio_amortiguador'),
    'equals', 'true', NOW(), NOW()
FROM elements e WHERE e.code = 'SUSPENSION_TRAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'modelo_amortiguador', 'Modelo del amortiguador', 'text', NULL, false, NULL, 'TTX GP', 'Si se cambia el amortiguador, solicita el modelo', 8,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'cambio_amortiguador'),
    'equals', 'true', NOW(), NOW()
FROM elements e WHERE e.code = 'SUSPENSION_TRAS';

-- ============================================================================
-- HORQUILLA - 8 fields (4 conditional)
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'procedencia', 'Procedencia de la horquilla', 'select', '["Otra moto", "Nueva"]', true, NULL, NULL, 'Pregunta si la horquilla es nueva o procede de otra motocicleta', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'HORQUILLA';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'marca', 'Marca', 'text', NULL, true, NULL, 'Showa', 'Solicita la marca de la horquilla', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'HORQUILLA';

-- Conditional: Otra moto
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'tipo', 'Tipo (si procede de otra moto)', 'text', NULL, false, NULL, 'USD invertida', 'Si procede de otra moto, solicita el tipo de horquilla', 3,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'procedencia'),
    'equals', 'Otra moto', NOW(), NOW()
FROM elements e WHERE e.code = 'HORQUILLA';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'denominacion', 'Denominación (si procede de otra moto)', 'text', NULL, false, NULL, 'CBR600RR', 'Si procede de otra moto, solicita la denominación del modelo de origen', 4,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'procedencia'),
    'equals', 'Otra moto', NOW(), NOW()
FROM elements e WHERE e.code = 'HORQUILLA';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'contrasena', 'Contraseña de homologación', 'text', NULL, false, NULL, 'e4*2002/24*0123', 'Si procede de otra moto, solicita la contraseña de homologación', 5,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'procedencia'),
    'equals', 'Otra moto', NOW(), NOW()
FROM elements e WHERE e.code = 'HORQUILLA';

-- Conditional: Nueva
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'modelo', 'Modelo (si es nueva)', 'text', NULL, false, NULL, 'BPF', 'Si es horquilla nueva, solicita el modelo', 6,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'procedencia'),
    'equals', 'Nueva', NOW(), NOW()
FROM elements e WHERE e.code = 'HORQUILLA';

-- Always required
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'distancia_entre_ejes', 'Nueva distancia entre ejes (mm)', 'number', NULL, true, '{"min_value": 1000, "max_value": 2000}', '1450', 'Solicita la nueva distancia entre ejes en milímetros (medir con cinta métrica)', 7, NOW(), NOW()
FROM elements e WHERE e.code = 'HORQUILLA';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'nueva_longitud', 'Nueva longitud total (mm)', 'number', NULL, true, '{"min_value": 1500, "max_value": 3000}', '2100', 'Solicita la nueva longitud total del vehículo en milímetros', 8, NOW(), NOW()
FROM elements e WHERE e.code = 'HORQUILLA';

-- ============================================================================
-- FRENADO_DISCOS - 3 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'marca_modelo', 'Marca/Modelo del disco', 'text', NULL, true, NULL, 'Brembo T-Drive', 'Solicita la marca y modelo del disco de freno', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'FRENADO_DISCOS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'diametro', 'Diámetro (mm)', 'number', NULL, true, '{"min_value": 150, "max_value": 400}', '320', 'Solicita el diámetro del disco en milímetros', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'FRENADO_DISCOS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'grosor', 'Grosor (mm)', 'number', NULL, true, '{"min_value": 2, "max_value": 15}', '5', 'Solicita el grosor del disco en milímetros', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'FRENADO_DISCOS';

-- ============================================================================
-- FRENADO_PINZAS - 2 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'marca', 'Marca', 'text', NULL, true, NULL, 'Brembo', 'Solicita la marca de las pinzas de freno', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'FRENADO_PINZAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'num_pistones', 'Número de pistones', 'number', NULL, true, '{"min_value": 1, "max_value": 8}', '4', 'Solicita el número de pistones de la pinza', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'FRENADO_PINZAS';

-- ============================================================================
-- FRENADO_BOMBAS - 3 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'delantera_marca', 'Marca bomba delantera', 'text', NULL, true, NULL, 'Brembo RCS', 'Solicita la marca de la bomba de freno delantera', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'FRENADO_BOMBAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'trasera_marca', 'Marca bomba trasera', 'text', NULL, false, NULL, 'Brembo PS13', 'Si se cambia también la trasera, solicita la marca', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'FRENADO_BOMBAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'grosor', 'Grosor', 'text', NULL, false, NULL, '19x18', 'Solicita el grosor o dimensiones de la bomba si lo conoce', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'FRENADO_BOMBAS';

-- ============================================================================
-- FRENADO_LATIGUILLOS - 2 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'delantera_marca', 'Marca latiguillo delantero', 'text', NULL, false, NULL, 'Goodridge', 'Solicita la marca del latiguillo delantero si aplica', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'FRENADO_LATIGUILLOS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'trasera_marca', 'Marca latiguillo trasero', 'text', NULL, false, NULL, 'HEL Performance', 'Solicita la marca del latiguillo trasero si aplica', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'FRENADO_LATIGUILLOS';

-- ============================================================================
-- FRENADO_DEPOSITO - 2 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'delantera_marca', 'Marca depósito delantero', 'text', NULL, false, NULL, 'Rizoma', 'Solicita la marca del depósito de líquido de frenos delantero', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'FRENADO_DEPOSITO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'trasera_marca', 'Marca depósito trasero', 'text', NULL, false, NULL, 'Brembo', 'Solicita la marca del depósito de líquido de frenos trasero si aplica', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'FRENADO_DEPOSITO';

-- ============================================================================
-- CARENADO - 8 fields (3 conditional)
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'tipo_modificacion', 'Tipo de modificación', 'select', '["Desmontaje", "Sustitución", "Instalación"]', true, NULL, NULL, 'Pregunta si se trata de desmontaje de carenado existente, sustitución por otro o instalación de carenado nuevo', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'CARENADO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'pieza1_descripcion', 'Pieza 1 - Descripción', 'text', NULL, true, NULL, 'Cúpula delantera', 'Solicita descripción de la primera pieza del carenado (cúpula, tapa lateral, colín, etc.)', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'CARENADO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'pieza1_medidas', 'Pieza 1 - Medidas (mm)', 'text', NULL, true, NULL, '450x300', 'Solicita las medidas aproximadas de la pieza en milímetros (largo x ancho)', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'CARENADO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'pieza1_material', 'Pieza 1 - Material', 'select', '["ABS", "Fibra de vidrio", "Fibra de carbono", "Polipropileno", "Otro"]', true, NULL, NULL, 'Pregunta el material de la pieza (ABS, fibra de vidrio, fibra de carbono, etc.)', 4, NOW(), NOW()
FROM elements e WHERE e.code = 'CARENADO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'mas_piezas', '¿Hay más piezas?', 'boolean', NULL, true, NULL, NULL, 'Pregunta si hay más piezas de carenado a incluir en la reforma', 5, NOW(), NOW()
FROM elements e WHERE e.code = 'CARENADO';

-- Conditional: mas_piezas = true
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'pieza2_descripcion', 'Pieza 2 - Descripción', 'text', NULL, false, NULL, 'Tapa lateral izquierda', 'Si hay más piezas, solicita la descripción de la segunda', 6,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'mas_piezas'),
    'equals', 'true', NOW(), NOW()
FROM elements e WHERE e.code = 'CARENADO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'pieza2_medidas', 'Pieza 2 - Medidas (mm)', 'text', NULL, false, NULL, '300x200', 'Si hay más piezas, solicita las medidas de la segunda', 7,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'mas_piezas'),
    'equals', 'true', NOW(), NOW()
FROM elements e WHERE e.code = 'CARENADO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'pieza2_material', 'Pieza 2 - Material', 'select', '["ABS", "Fibra de vidrio", "Fibra de carbono", "Polipropileno", "Otro"]', false, NULL, NULL, 'Si hay más piezas, pregunta el material de la segunda', 8,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'mas_piezas'),
    'equals', 'true', NOW(), NOW()
FROM elements e WHERE e.code = 'CARENADO';

-- ============================================================================
-- GUARDABARROS_DEL - 3 fields (1 conditional)
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'tipo_modificacion', 'Tipo de modificación', 'select', '["Sustitución", "Recorte", "Eliminación"]', true, NULL, NULL, 'Pregunta si se trata de sustitución, recorte o eliminación del guardabarros delantero', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'GUARDABARROS_DEL';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'material', 'Material (si sustitución)', 'select', '["ABS", "Fibra de vidrio", "Fibra de carbono", "Polipropileno", "Otro"]', false, NULL, NULL, 'Si es sustitución, pregunta el material del nuevo guardabarros', 2,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'tipo_modificacion'),
    'equals', 'Sustitución', NOW(), NOW()
FROM elements e WHERE e.code = 'GUARDABARROS_DEL';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'ancho_mm', 'Ancho del guardabarros (mm)', 'number', NULL, true, '{"min_value": 50, "max_value": 300}', '120', 'Solicita el ancho del guardabarros en milímetros (debe ser igual o mayor que el ancho del neumático)', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'GUARDABARROS_DEL';

-- ============================================================================
-- GUARDABARROS_TRAS - 3 fields (1 conditional)
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'tipo_modificacion', 'Tipo de modificación', 'select', '["Sustitución", "Recorte", "Eliminación"]', true, NULL, NULL, 'Pregunta si se trata de sustitución, recorte o eliminación del guardabarros trasero', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'GUARDABARROS_TRAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'material', 'Material (si sustitución)', 'select', '["ABS", "Fibra de vidrio", "Fibra de carbono", "Polipropileno", "Otro"]', false, NULL, NULL, 'Si es sustitución, pregunta el material del nuevo guardabarros', 2,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'tipo_modificacion'),
    'equals', 'Sustitución', NOW(), NOW()
FROM elements e WHERE e.code = 'GUARDABARROS_TRAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'ancho_mm', 'Ancho del guardabarros (mm)', 'number', NULL, true, '{"min_value": 50, "max_value": 350}', '180', 'Solicita el ancho del guardabarros en milímetros (debe ser igual o mayor que el ancho del neumático)', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'GUARDABARROS_TRAS';

-- ============================================================================
-- MANILLAR - 6 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'marca', 'Marca', 'text', NULL, true, NULL, 'Renthal', 'Solicita la marca del manillar', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'MANILLAR';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'modelo', 'Modelo', 'text', NULL, true, NULL, 'Fatbar 28mm', 'Solicita el modelo específico del manillar', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'MANILLAR';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'material', 'Material', 'select', '["Aluminio", "Acero", "Titanio", "Fibra de carbono"]', true, NULL, NULL, 'Pregunta el material del manillar (aluminio, acero, titanio, etc.)', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'MANILLAR';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'diametro_mm', 'Diámetro (mm)', 'number', NULL, true, '{"min_value": 18, "max_value": 35}', '28', 'Solicita el diámetro del tubo del manillar en milímetros (típico: 22mm o 28mm)', 4, NOW(), NOW()
FROM elements e WHERE e.code = 'MANILLAR';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'nuevo_ancho_mm', 'Nuevo ancho total (mm)', 'number', NULL, true, '{"min_value": 500, "max_value": 900}', '760', 'Solicita el nuevo ancho total del manillar en milímetros, medido de extremo a extremo (en manetas o puños, la medida más ancha). En motos desde 2016 (168/2013) máximo 380mm desde el eje', 5, NOW(), NOW()
FROM elements e WHERE e.code = 'MANILLAR';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'nueva_altura_mm', 'Nueva altura (mm)', 'number', NULL, true, '{"min_value": 0, "max_value": 300}', '85', 'Solicita la nueva altura del manillar respecto a las tijas en milímetros', 6, NOW(), NOW()
FROM elements e WHERE e.code = 'MANILLAR';

-- ============================================================================
-- TIJAS - 4 fields (1 conditional)
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'tipo', 'Tipo de modificación', 'select', '["Tijas completas", "Torretas/Risers"]', true, NULL, NULL, 'Pregunta si se trata de sustitución de tijas completas o solo instalación de torretas/risers elevadores', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'TIJAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'marca', 'Marca', 'text', NULL, true, NULL, 'ABM', 'Solicita la marca de las tijas o torretas', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'TIJAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'material', 'Material', 'select', '["Aluminio", "Acero", "Aluminio CNC"]', true, NULL, NULL, 'Pregunta el material de las tijas o torretas', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'TIJAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'altura_mm', 'Altura de elevación (mm)', 'number', NULL, false, '{"min_value": 10, "max_value": 100}', '30', 'Si son torretas/risers, solicita la altura de elevación en milímetros', 4,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'tipo'),
    'equals', 'Torretas/Risers', NOW(), NOW()
FROM elements e WHERE e.code = 'TIJAS';

-- ============================================================================
-- ESPEJOS - 1 field
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'contrasena_homologacion', 'Contraseña de homologación (ambos espejos)', 'text', NULL, true, NULL, 'e4*2003/97*0123', 'Solicita la contraseña de homologación de los espejos. IMPORTANTE: Debe ser IGUAL en ambos retrovisores', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'ESPEJOS';

-- ============================================================================
-- MANDOS_AVANZADOS - 2 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'marca', 'Marca', 'text', NULL, true, NULL, 'Gilles Tooling', 'Solicita la marca de los mandos avanzados', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'MANDOS_AVANZADOS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'material', 'Material', 'select', '["Aluminio", "Aluminio CNC", "Acero", "Titanio"]', true, NULL, NULL, 'Pregunta el material de los mandos avanzados', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'MANDOS_AVANZADOS';

-- ============================================================================
-- FARO_DELANTERO - 1 field
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'contrasena_homologacion', 'Contraseña de homologación', 'text', NULL, true, NULL, 'e4*2012/19*0456', 'Solicita la contraseña de homologación del faro (número E visible en el cristal o carcasa)', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'FARO_DELANTERO';

-- ============================================================================
-- INTERMITENTES_DEL - 3 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'contrasena_homologacion', 'Contraseña de homologación', 'text', NULL, true, NULL, 'e4*76/756*0012', 'Solicita la contraseña de homologación de los intermitentes delanteros', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'INTERMITENTES_DEL';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'distancia_bordes_mm', 'Distancia entre bordes interiores (mm)', 'number', NULL, true, '{"min_value": 200, "max_value": 600}', '280', 'Solicita la distancia en milímetros entre los bordes interiores de ambos intermitentes (mínimo 240mm)', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'INTERMITENTES_DEL';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'distancia_faro_mm', 'Distancia al faro principal (mm)', 'number', NULL, true, '{"min_value": 0, "max_value": 500}', '100', 'Solicita la distancia en milímetros desde el intermitente al faro principal', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'INTERMITENTES_DEL';

-- ============================================================================
-- INTERMITENTES_TRAS - 4 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'contrasena_homologacion', 'Contraseña de homologación', 'text', NULL, true, NULL, 'e4*76/756*0012', 'Solicita la contraseña de homologación de los intermitentes traseros', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'INTERMITENTES_TRAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'distancia_bordes_mm', 'Distancia entre bordes exteriores (mm)', 'number', NULL, true, '{"min_value": 50, "max_value": 500}', '150', 'Solicita la distancia en milímetros entre los bordes exteriores de ambos intermitentes (mínimo 75mm)', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'INTERMITENTES_TRAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'distancia_final_mm', 'Distancia al final del vehículo (mm)', 'number', NULL, true, '{"min_value": 0, "max_value": 400}', '250', 'Solicita la distancia en milímetros desde el intermitente hasta el final del vehículo (máximo 300mm)', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'INTERMITENTES_TRAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'integra_luz_freno', '¿Integra luz de freno?', 'boolean', NULL, true, NULL, NULL, 'Pregunta si los intermitentes traseros integran la luz de freno (cambia el ángulo requerido de 20 a 50 grados)', 4, NOW(), NOW()
FROM elements e WHERE e.code = 'INTERMITENTES_TRAS';

-- ============================================================================
-- PILOTO_FRENO - 3 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'contrasena_homologacion', 'Contraseña de homologación', 'text', NULL, true, NULL, 'e4*2008/89*0034', 'Solicita la contraseña de homologación del piloto de freno', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'PILOTO_FRENO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'altura_mm', 'Altura desde el suelo (mm)', 'number', NULL, true, '{"min_value": 250, "max_value": 1500}', '750', 'Solicita la altura del piloto de freno desde el suelo en milímetros', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'PILOTO_FRENO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'integra_intermitentes', '¿Integra intermitentes?', 'boolean', NULL, true, NULL, NULL, 'Pregunta si el piloto de freno integra los intermitentes traseros', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'PILOTO_FRENO';

-- ============================================================================
-- LUZ_MATRICULA - 3 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'contrasena_homologacion', 'Contraseña de homologación', 'text', NULL, true, NULL, 'e4*2012/19*0045', 'Solicita la contraseña de homologación de la luz de matrícula', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'LUZ_MATRICULA';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'altura_mm', 'Altura desde el suelo (mm)', 'number', NULL, true, '{"min_value": 200, "max_value": 1200}', '600', 'Solicita la altura de la luz de matrícula desde el suelo en milímetros', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'LUZ_MATRICULA';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'posicion', 'Posición respecto a matrícula', 'select', '["Superior", "Lateral", "Integrada en piloto"]', true, NULL, NULL, 'Pregunta la posición de la luz respecto a la matrícula', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'LUZ_MATRICULA';

-- ============================================================================
-- CATADIOPTRICO - 3 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'contrasena_homologacion', 'Contraseña de homologación', 'text', NULL, true, NULL, 'e4*3*0012', 'Solicita la contraseña de homologación del catadióptrico', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'CATADIOPTRICO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'altura_mm', 'Altura desde el suelo (mm)', 'number', NULL, true, '{"min_value": 200, "max_value": 1000}', '500', 'Solicita la altura del catadióptrico desde el suelo en milímetros (mínimo 250mm, máximo 900mm)', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'CATADIOPTRICO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'perpendicular', '¿Está perpendicular al suelo?', 'boolean', NULL, true, NULL, NULL, 'Confirma si el catadióptrico está montado perpendicular al suelo (requisito obligatorio)', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'CATADIOPTRICO';

-- ============================================================================
-- ANTINIEBLAS - 2 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'contrasena_homologacion', 'Contraseña de homologación', 'text', NULL, true, NULL, 'e4*2019/144*0123', 'Solicita la contraseña de homologación de las luces antiniebla', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'ANTINIEBLAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'tiene_pictograma', '¿El mando tiene pictograma homologado?', 'boolean', NULL, true, NULL, NULL, 'Confirma si el botón de encendido tiene el pictograma homologado de niebla (requisito obligatorio)', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'ANTINIEBLAS';

-- ============================================================================
-- MANDOS_MANILLAR - 6 fields (2 conditional)
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'pina_izquierda', '¿Se cambia piña izquierda?', 'boolean', NULL, true, NULL, NULL, 'Pregunta si se sustituye la piña izquierda del manillar (luces, intermitentes, claxon)', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'MANDOS_MANILLAR';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'pina_izquierda_marca', 'Marca piña izquierda', 'text', NULL, false, NULL, 'Domino', 'Si se cambia la piña izquierda, solicita la marca', 2,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'pina_izquierda'),
    'equals', 'true', NOW(), NOW()
FROM elements e WHERE e.code = 'MANDOS_MANILLAR';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'pina_derecha', '¿Se cambia piña derecha?', 'boolean', NULL, true, NULL, NULL, 'Pregunta si se sustituye la piña derecha del manillar (arranque, paro motor)', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'MANDOS_MANILLAR';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'pina_derecha_marca', 'Marca piña derecha', 'text', NULL, false, NULL, 'Domino', 'Si se cambia la piña derecha, solicita la marca', 4,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'pina_derecha'),
    'equals', 'true', NOW(), NOW()
FROM elements e WHERE e.code = 'MANDOS_MANILLAR';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'testigos_independientes', '¿Se añaden testigos independientes?', 'boolean', NULL, true, NULL, NULL, 'Pregunta si se instalan testigos luminosos independientes', 5, NOW(), NOW()
FROM elements e WHERE e.code = 'MANDOS_MANILLAR';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'pictogramas_homologados', '¿Los mandos tienen pictogramas homologados?', 'boolean', NULL, true, NULL, NULL, 'Confirma si los nuevos mandos disponen de pictogramas homologados según su función (requisito obligatorio)', 6, NOW(), NOW()
FROM elements e WHERE e.code = 'MANDOS_MANILLAR';

-- ============================================================================
-- CLAUSOR - 1 field
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'nueva_ubicacion', 'Nueva ubicación', 'text', NULL, true, NULL, 'Lateral izquierdo del depósito', 'Solicita la descripción de la nueva ubicación del clausor/llave de arranque', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'CLAUSOR';

-- ============================================================================
-- STARTER - 1 field
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'nueva_ubicacion', 'Nueva ubicación', 'text', NULL, true, NULL, 'En el manillar', 'Solicita la descripción de la nueva ubicación del starter/cebador', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'STARTER';

-- ============================================================================
-- LLANTAS - 4 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'posicion', 'Posición', 'select', '["Delantera", "Trasera", "Ambas"]', true, NULL, NULL, 'Pregunta si se cambia la llanta delantera, trasera o ambas', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'LLANTAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'marca', 'Marca', 'text', NULL, true, NULL, 'Marchesini', 'Solicita la marca de las llantas', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'LLANTAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'medidas_del', 'Medidas llanta delantera', 'text', NULL, false, NULL, '3.50x17', 'Si se cambia la llanta delantera, solicita las medidas (ancho x diámetro)', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'LLANTAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'medidas_tras', 'Medidas llanta trasera', 'text', NULL, false, NULL, '5.50x17', 'Si se cambia la llanta trasera, solicita las medidas (ancho x diámetro)', 4, NOW(), NOW()
FROM elements e WHERE e.code = 'LLANTAS';

-- ============================================================================
-- NEUMATICOS - 8 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'posicion', 'Posición', 'select', '["Delantero", "Trasero", "Ambos"]', true, NULL, NULL, 'Pregunta si se cambia el neumático delantero, trasero o ambos', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'NEUMATICOS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'medidas_del', 'Medidas neumático delantero', 'text', NULL, false, NULL, '120/70-17', 'Si se cambia el neumático delantero, solicita las medidas (ancho/perfil-diámetro)', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'NEUMATICOS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'indice_carga_del', 'Índice de carga delantero', 'text', NULL, false, NULL, '58', 'Si se cambia el delantero, solicita el índice de carga', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'NEUMATICOS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'indice_velocidad_del', 'Índice de velocidad delantero', 'text', NULL, false, NULL, 'W', 'Si se cambia el delantero, solicita el índice de velocidad (letra)', 4, NOW(), NOW()
FROM elements e WHERE e.code = 'NEUMATICOS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'medidas_tras', 'Medidas neumático trasero', 'text', NULL, false, NULL, '180/55-17', 'Si se cambia el neumático trasero, solicita las medidas (ancho/perfil-diámetro)', 5, NOW(), NOW()
FROM elements e WHERE e.code = 'NEUMATICOS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'indice_carga_tras', 'Índice de carga trasero', 'text', NULL, false, NULL, '73', 'Si se cambia el trasero, solicita el índice de carga', 6, NOW(), NOW()
FROM elements e WHERE e.code = 'NEUMATICOS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'indice_velocidad_tras', 'Índice de velocidad trasero', 'text', NULL, false, NULL, 'W', 'Si se cambia el trasero, solicita el índice de velocidad (letra)', 7, NOW(), NOW()
FROM elements e WHERE e.code = 'NEUMATICOS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'ms_mixto', '¿Es neumático M+S (mixto/trail)?', 'boolean', NULL, true, NULL, NULL, 'Pregunta si los neumáticos son M+S (uso mixto/trail)', 8, NOW(), NOW()
FROM elements e WHERE e.code = 'NEUMATICOS';

-- ============================================================================
-- DEPOSITO - 4 fields (2 conditional)
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'procedencia', 'Procedencia del depósito', 'select', '["Nuevo", "De otra moto", "Modificado"]', true, NULL, NULL, 'Pregunta si el depósito es nuevo, procede de otra moto o es el original modificado', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'DEPOSITO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'contrasena_homologacion', 'Contraseña de homologación', 'text', NULL, false, NULL, 'e4*2015/136*0078', 'Si es depósito nuevo, solicita la contraseña de homologación de la etiqueta', 2,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'procedencia'),
    'equals', 'Nuevo', NOW(), NOW()
FROM elements e WHERE e.code = 'DEPOSITO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'capacidad_litros', 'Capacidad (litros)', 'number', NULL, true, '{"min_value": 3, "max_value": 50}', '18', 'Solicita la capacidad del depósito en litros', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'DEPOSITO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'descripcion_modificacion', 'Descripción de la modificación', 'text', NULL, false, NULL, 'Modificación del soporte de fijación', 'Si es depósito modificado, describe en qué consiste la modificación', 4,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'procedencia'),
    'equals', 'Modificado', NOW(), NOW()
FROM elements e WHERE e.code = 'DEPOSITO';

-- ============================================================================
-- VELOCIMETRO - 6 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'marca', 'Marca', 'text', NULL, true, NULL, 'Koso', 'Solicita la marca del velocímetro/cuadro de instrumentos', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'VELOCIMETRO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'modelo', 'Modelo', 'text', NULL, true, NULL, 'RX2N', 'Solicita el modelo específico del velocímetro', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'VELOCIMETRO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'contrasena_homologacion', 'Contraseña de homologación', 'text', NULL, true, NULL, 'e4*2000/7*0456', 'Solicita la contraseña de homologación del velocímetro', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'VELOCIMETRO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'tipo_display', 'Tipo de display', 'select', '["Digital", "Analógico"]', true, NULL, NULL, 'Pregunta si el velocímetro es digital o analógico (analógico puede llevar recargo de laboratorio)', 4, NOW(), NOW()
FROM elements e WHERE e.code = 'VELOCIMETRO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'testigos_luminosos', '¿Incluye todos los testigos luminosos?', 'boolean', NULL, true, NULL, NULL, 'Confirma si el velocímetro incluye los testigos luminosos obligatorios (intermitentes, luces largas, neutro, etc.)', 5, NOW(), NOW()
FROM elements e WHERE e.code = 'VELOCIMETRO';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'captador', 'Captador de velocidad', 'select', '["Se mantiene el original", "Nuevo captador"]', true, NULL, NULL, 'Pregunta si se mantiene el captador de velocidad original o se instala uno nuevo', 6, NOW(), NOW()
FROM elements e WHERE e.code = 'VELOCIMETRO';

-- ============================================================================
-- MATRICULA - 5 fields (1 conditional)
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'tipo_montaje', 'Tipo de montaje', 'select', '["Sin brazo (portamatrículas corto)", "Con brazo lateral"]', true, NULL, NULL, 'Pregunta si el nuevo emplazamiento es sin brazo (portamatrículas corto bajo el colín) o con brazo lateral', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'MATRICULA';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'nueva_longitud_mm', 'Nueva longitud total del vehículo (mm)', 'number', NULL, true, '{"min_value": 1500, "max_value": 3000}', '2050', 'Solicita la nueva longitud desde la rueda delantera hasta la parte más trasera del vehículo (sin contar escapes) en milímetros', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'MATRICULA';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'distancia_final_mm', 'Distancia matrícula al final (mm)', 'number', NULL, true, '{"min_value": 0, "max_value": 400}', '250', 'Solicita la distancia en milímetros desde la matrícula hasta el final del vehículo (máximo 300mm)', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'MATRICULA';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'matricula_antigua', '¿Es matrícula antigua (larga)?', 'boolean', NULL, true, NULL, NULL, 'Pregunta si el vehículo tiene matrícula antigua (formato largo)', 4, NOW(), NOW()
FROM elements e WHERE e.code = 'MATRICULA';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_field_id, condition_operator, condition_value, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'burlete_goma', '¿Tiene burlete de goma o portamatrículas protector?', 'boolean', NULL, false, NULL, NULL, 'Si es matrícula antigua, confirma si tiene burlete de goma o portamatrículas para proteger los bordes', 5,
    (SELECT id FROM element_required_fields WHERE element_id = e.id AND field_key = 'matricula_antigua'),
    'equals', 'true', NOW(), NOW()
FROM elements e WHERE e.code = 'MATRICULA';

-- ============================================================================
-- ESTRIBERAS - 3 fields
-- ============================================================================
INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'marca', 'Marca', 'text', NULL, true, NULL, 'Rizoma', 'Solicita la marca de las estriberas', 1, NOW(), NOW()
FROM elements e WHERE e.code = 'ESTRIBERAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'material', 'Material', 'select', '["Aluminio", "Aluminio CNC", "Acero", "Titanio"]', true, NULL, NULL, 'Pregunta el material de las estriberas', 2, NOW(), NOW()
FROM elements e WHERE e.code = 'ESTRIBERAS';

INSERT INTO element_required_fields (id, element_id, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, created_at, updated_at)
SELECT gen_random_uuid(), e.id, 'ubicacion', 'Ubicación', 'select', '["Conductor", "Pasajero", "Ambas"]', true, NULL, NULL, 'Pregunta si las estriberas son del conductor, pasajero o ambas', 3, NOW(), NOW()
FROM elements e WHERE e.code = 'ESTRIBERAS';

COMMIT;

-- ============================================================================
-- Verify insertion
-- ============================================================================
SELECT 
    e.code as element_code,
    e.name as element_name,
    COUNT(erf.id) as field_count
FROM elements e
LEFT JOIN element_required_fields erf ON e.id = erf.element_id
WHERE e.category_id = '6a57c85d-b915-5070-957b-1505e20c7474'
  AND erf.id IS NOT NULL
GROUP BY e.code, e.name
ORDER BY e.code;

-- Show total
SELECT COUNT(*) as total_fields FROM element_required_fields 
WHERE element_id IN (SELECT id FROM elements WHERE category_id = '6a57c85d-b915-5070-957b-1505e20c7474');
