# Importador de Imágenes de Elementos

Script para analizar y vincular imágenes de `docs/images_old/` a elementos de autocaravanas en la base de datos.

## Funcionamiento

### Paso 1: Análisis con Gemini 2.0 Flash (Vision)

El script usa **Google Gemini 2.0 Flash** vía OpenRouter (gratuito) para:
1. Leer cada imagen visualmente
2. Identificar el elemento de autocaravana correspondiente
3. Extraer título y descripción del texto visible
4. Asignar nivel de confianza (high/medium/low)

### Paso 2: Importación a Base de Datos

Tras revisar el análisis:
1. Copia imágenes a `uploads/images/` con nombres UUID
2. Crea registros en `element_images` tabla
3. Vincula cada imagen con su elemento correspondiente

## Requisitos

```bash
# Variable de entorno requerida (ya configurada en .env)
OPENROUTER_API_KEY=sk-or-v1-...

# Dependencias (ya instaladas en requirements.txt)
pip install httpx pillow sqlalchemy
```

## Uso

```bash
# Ejecutar desde raíz del proyecto
python -m database.seeds.analyze_and_import_images
```

### Flujo de ejecución:

```
📷 Analizando: fadd9db8-4583-40d5-a61b-d71bc8953ba5.png
[1/82] ✅ TOLDO_LAT identificado (confianza: high)
...
[82/82] ✅ PLACA_SOLAR identificado (confianza: high)

✅ Análisis completo guardado en: database/seeds/image_analysis_results.json

======================================================================
RESUMEN DEL ANÁLISIS
======================================================================
Total imágenes analizadas: 82
Desconocidas: 3
Errores: 0

Por nivel de confianza:
  Alta: 75
  Media: 4
  Baja: 0

Por elemento:
  TOLDO_LAT: 12
  PLACA_SOLAR: 15
  ESCALON_ELEC: 8
  ...

======================================================================
PASO 2: IMPORTACIÓN A BASE DE DATOS
======================================================================

¿Continuar con la importación a la base de datos? (s/n): s

📦 Importando imágenes a la base de datos...
📋 Encontrados 20 elementos en categoría aseicars-prof
✅ TOLDO_LAT: 4d15ea54...jpg → Foto de instalación toldo lateral
...

📊 Importación completada:
   ✅ Importadas: 79
   ⏭️  Omitidas: 3
   ❌ Errores: 0

✅ Proceso completado exitosamente
```

## Resultados

### Archivo de análisis generado

`database/seeds/image_analysis_results.json`:

```json
{
  "total_images": 82,
  "analysis": [
    {
      "original_filename": "fadd9db8-4583-40d5-a61b-d71bc8953ba5.png",
      "element_code": "TOLDO_LAT",
      "confidence": "high",
      "title": "Foto de instalación",
      "description": "Toldo lateral Dometic con instrucciones de medición de galibo",
      "text_found": ["FOTO DE INSTALACION", "toldo", "galibo"]
    },
    ...
  ],
  "summary": {
    "total": 82,
    "by_element": {
      "TOLDO_LAT": 12,
      "PLACA_SOLAR": 15,
      ...
    },
    "by_confidence": {
      "high": 75,
      "medium": 4,
      "low": 0
    },
    "unknown": 3,
    "errors": 0
  }
}
```

### Cambios en base de datos

**Tabla afectada**: `element_images`

```sql
-- Ejemplo de registro creado
INSERT INTO element_images (
    id, 
    element_id, 
    image_url, 
    image_type, 
    title, 
    description, 
    sort_order, 
    status, 
    is_required
) VALUES (
    '550e8400-e29b-41d4-a716-446655440000',
    'element_id_del_toldo',
    '/images/4d15ea54-b126-427c-816b-4ac5a926f5e9.jpg',
    'example',
    'Foto de instalación',
    'Toldo lateral Dometic con instrucciones...',
    1,
    'active',
    false
);
```

**Archivos copiados**: `uploads/images/{uuid}.{ext}`

## Rate Limiting

- **OpenRouter (Gemini 2.0 Flash)**: Límites generosos (gratis)
- **Script delay**: 2 segundos entre imágenes
- **Tiempo estimado**: ~3 minutos para 82 imágenes

## Costes

**Gemini 2.0 Flash Exp** vía OpenRouter:
- **GRATIS** - Modelo experimental sin coste
- Sin límites de tokens significativos para este volumen

**Total estimado**: **$0.00** ✅

## Verificación Post-Importación

```sql
-- Ver imágenes importadas por elemento
SELECT 
    e.code,
    e.name,
    COUNT(ei.id) as num_images
FROM elements e
LEFT JOIN element_images ei ON ei.element_id = e.id
WHERE ei.status = 'active'
GROUP BY e.code, e.name
ORDER BY num_images DESC;

-- Ver imágenes de un elemento específico
SELECT 
    ei.title,
    ei.description,
    ei.image_url,
    ei.sort_order
FROM element_images ei
JOIN elements e ON ei.element_id = e.id
WHERE e.code = 'TOLDO_LAT'
ORDER BY ei.sort_order;
```

## Troubleshooting

### Error: "OPENROUTER_API_KEY no está configurada"
```bash
# Agregar a .env
OPENROUTER_API_KEY=sk-or-v1-...
```

### Error: "Categoría 'aseicars-prof' no encontrada"
```bash
# Ejecutar seeds primero
python -m database.seeds.run_all_seeds
```

### Error: "Permission denied" en uploads/images
```bash
mkdir -p uploads/images
chmod 755 uploads/images
```

### Imágenes desconocidas
Revisa `image_analysis_results.json` para ver cuáles no se identificaron y asígnalas manualmente:

```python
# Actualizar manualmente
UPDATE element_images 
SET element_id = 'elemento_correcto_id'
WHERE image_url = '/images/filename.jpg';
```

## Notas Importantes

1. **Backup**: El script NO modifica las imágenes originales en `docs/images_old/`
2. **Idempotencia**: Puedes ejecutar el script múltiples veces (creará nuevos registros cada vez)
3. **Validación**: Revisa `image_analysis_results.json` antes de confirmar la importación
4. **Manual override**: Puedes editar el JSON y re-ejecutar solo el paso de importación

## Configuración Avanzada

### Mapeo personalizado de elementos

Edita `ELEMENT_MAPPING` en el script:

```python
ELEMENT_MAPPING = {
    "ESCALON_ELEC": ["escalon", "peldano", "escalera electrica"],
    "TOLDO_LAT": ["toldo", "toldo lateral", "galibo"],
    # Añadir más keywords...
}
```

### Cambiar destino de imágenes

Edita `settings.IMAGE_UPLOAD_DIR` en `.env`:

```bash
IMAGE_UPLOAD_DIR=./uploads/custom_images
```

---

**Creado**: Febrero 2026  
**Autor**: MSI-a Database Dev Team
