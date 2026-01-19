-- ============================================================================
-- SQL Script: Actualizar Rutas de Imágenes en Elementos
-- ============================================================================
--
-- Este script actualiza las rutas de imágenes en la tabla element_images
-- para relacionar cada elemento con sus imágenes físicas correspondientes.
--
-- IMPORTANTE: Ejecutar DESPUÉS de cargar las seeds de elementos
--
-- Uso:
--   psql -U msia msia_db < UPDATE_IMAGENES_ELEMENTOS.sql
--
-- ============================================================================

-- ============================================================================
-- MOTOS (motos-part)
-- ============================================================================

-- Sistema de Frenado
UPDATE element_images SET image_url = '/datos/Imagenes/Motos/06_Sistema_Frenado/sistemaFrenado_discos.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'FRENADO_DISCOS');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/06_Sistema_Frenado/sistemaFrenado_pinzas.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'FRENADO_PINZAS');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/06_Sistema_Frenado/sistemaFrenado_bombasFreno.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'FRENADO_BOMBAS');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/06_Sistema_Frenado/sistemaFrenado_latiguillosMetalicos.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'FRENADO_LATIGUILLOS');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/06_Sistema_Frenado/sistemaFrenado_depositoLiquidoFreno.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'FRENADO_DEPOSITO');

-- Carrocería
UPDATE element_images SET image_url = '/datos/Imagenes/Motos/03_Carrocería/carenado.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'CARENADO');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/03_Carrocería/guardabarros_delantero.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'GUARDABARROS_DEL');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/03_Carrocería/guardabarros_trasero.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'GUARDABARROS_TRAS');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/02_Vistas_Exteriores/4vistas.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'CARROCERIA');

-- Chasis y Estructura
UPDATE element_images SET image_url = '/datos/Imagenes/Motos/04_Chasis_y_Estructura/subchasis.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'SUBCHASIS');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/04_Chasis_y_Estructura/asideros.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'ASIDEROS');

-- Suspensión
UPDATE element_images SET image_url = '/datos/Imagenes/Motos/05_Suspensión/suspension_delantera.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'SUSPENSION_DEL');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/05_Suspensión/suspension_trasera.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'SUSPENSION_TRAS');

-- Dirección y Manillar
UPDATE element_images SET image_url = '/datos/Imagenes/Motos/07_Dirección_y_Manillar/manillar.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'MANILLAR');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/07_Dirección_y_Manillar/espejosRetrovisores.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'ESPEJOS');

-- Alumbrado y Señalización
UPDATE element_images SET image_url = '/datos/Imagenes/Motos/10_Alumbrado_y_Señalización/alumbrado_faroDelantero.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'FARO_DELANTERO');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/10_Alumbrado_y_Señalización/alumbrado_IntermitentesDelanteros.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'INTERMITENTES_DEL');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/10_Alumbrado_y_Señalización/alumbrado_IntermitentesTraseros.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'INTERMITENTES_TRAS');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/10_Alumbrado_y_Señalización/alumbrado_catadioptrico.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'CATADIOPTRICO');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/10_Alumbrado_y_Señalización/alumbrado_antinieblas.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'ANTINIEBLAS');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/10_Alumbrado_y_Señalización/alumbrado_pilotoFrenoTrasero.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'PILOTO_FRENO');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/10_Alumbrado_y_Señalización/alumbrado_luzMatricula.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'LUZ_MATRICULA');

-- Mandos y Controles
UPDATE element_images SET image_url = '/datos/Imagenes/Motos/11_Mandos_y_Controles/mandosAvanzados.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'MANDOS_AVANZADOS');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/11_Mandos_y_Controles/mandosYtestigosmanillar.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'MANDOS_MANILLAR');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/11_Mandos_y_Controles/clausorYllaveArranque.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'CLAUSOR');

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/11_Mandos_y_Controles/starter.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'STARTER');

-- Instrumentación
UPDATE element_images SET image_url = '/datos/Imagenes/Motos/08_Instrumentación/velocimetro.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'VELOCIMETRO');

-- Matrícula
UPDATE element_images SET image_url = '/datos/Imagenes/Motos/09_Matrícula/emplazamientoMatricula.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'MATRICULA');

-- Elementos Conductores
UPDATE element_images SET image_url = '/datos/Imagenes/Motos/12_Elementos_Conductores/estriberas.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'ESTRIBERAS');

-- Ruedas y Neumáticos (imagen delantera para LLANTAS y NEUMATICOS)
UPDATE element_images SET image_url = '/datos/Imagenes/Motos/13_Ruedas_y_Neumáticos/neumatico_llantaDelantera.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'LLANTAS')
  AND sort_order = 1;

UPDATE element_images SET image_url = '/datos/Imagenes/Motos/13_Ruedas_y_Neumáticos/neumatico_llantaDelantera.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'NEUMATICOS')
  AND sort_order = 1;


-- ============================================================================
-- AUTOCARAVANAS (aseicars-prof)
-- ============================================================================

-- Escalón Eléctrico
UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/06_Escalon_Electrico/escalon_electrico.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'ESCALON_ELEC');

-- Toldos
UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/04_Toldos/toldo.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'TOLDO_LAT');

UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/04_Toldos/toldo.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'TOLDO_SIMPLE');

UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/04_Toldos/toldo_galibos.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'TOLDO_GALIBO')
  AND sort_order = 1;

-- Placas Solares (todas usan la misma imagen)
UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/03_Placas_Solares/placas_solarres.png'
WHERE element_id IN (
  SELECT id FROM elements
  WHERE code IN ('PLACA_SOLAR', 'PLACA_SOLAR_SIMPLE', 'PLACA_SOLAR_MALETERO')
);

-- Antena Parabólica
UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/07_Antena_Parabolica/Antena_Parabolica.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'ANTENA_PAR');

-- Aire Acondicionado
UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/05_Aire_Acondicionado/aireAcondicionado.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'AIRE_ACONDI');

-- Portamotos
UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/08_Portamotos/portamotos.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'PORTAMOTOS');

-- Suspensión Neumática
UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/09_Suspension_Neumatica/suspension_neumatica.png'
WHERE element_id IN (
  SELECT id FROM elements
  WHERE code IN ('SUSP_NEUM', 'SUSP_NEUM_EST')
);

UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/09_Suspension_Neumatica/suspension_neumatica_fullair_1.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'SUSP_NEUM_FULL')
  AND sort_order = 1;

-- Kit Elevación
UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/10_Kit_Elevacion/kit_elevacion.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'KIT_ESTAB');

-- Bola de Remolque
UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/11_Bola_Remolque/bolaRemolque_sinMMR.png'
WHERE element_id IN (
  SELECT id FROM elements
  WHERE code IN ('BOLA_REMOLQUE', 'BOLA_SIN_MMR')
);

UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/11_Bola_Remolque/bolaRemolque_conMMR.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'BOLA_CON_MMR');

UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/11_Bola_Remolque/brazoRemolque.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'BRAZO_PORTA');

-- Aumento MMTA
UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/12_Aumento_MMTA/aumentoMMTA.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'AUMENTO_MMTA');

-- GLP / Gas (todas las variantes usan la misma imagen)
UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/13_GLP_Gas/glpEnAc.png'
WHERE element_id IN (
  SELECT id FROM elements
  WHERE code IN ('GLP_INSTALACION', 'GLP_KIT_BOMB', 'GLP_DEPOSITO', 'GLP_DUOCONTROL')
);

-- Aumento de Plazas
UPDATE element_images SET image_url = '/datos/Imagenes/Autocaravanas/14_Aumento_Plazas/aumento_plazas.png'
WHERE element_id IN (SELECT id FROM elements WHERE code = 'AUMENTO_PLAZAS');


-- ============================================================================
-- VERIFICACIÓN
-- ============================================================================

-- Contar imágenes actualizadas
SELECT
  'Motos' as categoria,
  COUNT(*) as imagenes_actualizadas
FROM element_images ei
JOIN elements e ON e.id = ei.element_id
JOIN vehicle_categories vc ON vc.id = e.category_id
WHERE vc.slug = 'motos-part'
  AND ei.image_url LIKE '/datos/Imagenes/%'

UNION ALL

SELECT
  'Autocaravanas' as categoria,
  COUNT(*) as imagenes_actualizadas
FROM element_images ei
JOIN elements e ON e.id = ei.element_id
JOIN vehicle_categories vc ON vc.id = e.category_id
WHERE vc.slug = 'aseicars-prof'
  AND ei.image_url LIKE '/datos/Imagenes/%';

-- Elementos sin imagen actualizada
SELECT
  e.code,
  e.name,
  vc.slug as categoria,
  ei.image_url
FROM elements e
JOIN vehicle_categories vc ON vc.id = e.category_id
LEFT JOIN element_images ei ON ei.element_id = e.id
WHERE ei.image_url NOT LIKE '/datos/Imagenes/%'
   OR ei.image_url IS NULL
ORDER BY vc.slug, e.code;
