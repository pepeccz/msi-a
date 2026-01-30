# Solución al Problema de `guardar_datos_elemento` Ignorando Campos

**Fecha:** 29 de enero de 2026  
**Problema:** El LLM estaba enviando nombres de campos incorrectos a `guardar_datos_elemento()`, causando que los datos se ignoraran silenciosamente.

## Análisis del Problema

### Causa Raíz Identificada

El LLM **NO recibía los `field_key` exactos** que debía usar, solo recibía las etiquetas amigables (`field_label`). Por ejemplo:

- **Recibía:** "En qué consiste la modificación"
- **Inventaba:** `modificacion` o `tipo_modificacion`
- **Correcto:** `descripcion_modificacion`

### Comportamiento Observado en Logs

```
[guardar_datos_elemento] Ignored fields: ['modificacion', 'longitud_total']
[guardar_datos_elemento] Ignored fields: ['tipo_modificacion', 'longitud_total']
[guardar_datos_elemento] Ignored fields: ['modificacion', 'medida_recorte', 'nueva_medida_desde_tanque']
```

El usuario respondía correctamente pero los datos no se guardaban porque el LLM usaba nombres incorrectos.

### Campos Reales de SUBCHASIS en la Base de Datos

| field_key | field_label |
|-----------|-------------|
| `descripcion_modificacion` | En qué consiste la modificación |
| `medida_desde_tanque` | Nueva medida desde el tanque (mm) |
| `nueva_longitud_total` | Nueva longitud total del vehículo (mm) |

## Solución Implementada

### 1. Modificado `format_batch_prompt()` (collection_mode.py)

**Antes:**
```python
line = f"{i}. {field['field_label']}"
```

**Después:**
```python
line = f"{i}. {field['field_label']} [USAR field_key: '{field['field_key']}']"
```

**Resultado:** El LLM ahora ve:
```
1. En qué consiste la modificación [USAR field_key: 'descripcion_modificacion']
2. Nueva medida desde el tanque (mm) [USAR field_key: 'medida_desde_tanque']
3. Nueva longitud total del vehículo (mm) [USAR field_key: 'nueva_longitud_total']
```

### 2. Mejorado mensaje de error en `guardar_datos_elemento()` (element_data_tools.py)

**Antes:** Warning silencioso en logs
```python
response["warning"] = f"⚠️ CAMPOS NO RECONOCIDOS IGNORADOS: {ignored_fields}..."
```

**Después:** Error crítico que fuerza corrección
```python
response["success"] = False  # ¡Cambiado a False!
response["error"] = f"CAMPOS INCORRECTOS: {', '.join(ignored_fields)}"
response["message"] = (
    f"❌ ERROR CRÍTICO: Los campos {ignored_fields} NO EXISTEN...\n"
    f"DEBES usar EXACTAMENTE estos field_key:\n"
    f"{valid_field_keys}\n"
    f"Vuelve a llamar guardar_datos_elemento() con los field_key correctos."
)
```

### 3. Mejorado mensajes en modo SEQUENTIAL

**En `confirmar_fotos_elemento()`:**
```python
response["message"] = (
    f"Fotos de {element.name} confirmadas. Ahora necesito algunos datos.\n\n"
    f"📋 CAMPO A RECOGER:\n"
    f"• Nombre: {field_label}\n"
    f"• Field key a usar: '{field_key}'\n"
    f"• Pregunta al usuario: {instruction}{options_text}{example_text}\n\n"
    f"⚠️ IMPORTANTE: Al guardar con guardar_datos_elemento(), USA EXACTAMENTE el field_key '{field_key}'"
)
```

**En `guardar_datos_elemento()` para siguiente campo:**
```python
response["message"] = (
    f"✅ Datos guardados.\n\n"
    f"📋 SIGUIENTE CAMPO:\n"
    f"• Nombre: {field_label}\n"
    f"• Field key: '{field_key}'\n"
    f"• Pregunta: {instruction}{options_text}{example_text}\n\n"
    f"⚠️ Al guardar, usa field_key='{field_key}'"
)
```

## Archivos Modificados

1. **`agent/services/collection_mode.py`**
   - Función `format_batch_prompt()` - Línea ~285

2. **`agent/tools/element_data_tools.py`**
   - Función `guardar_datos_elemento()` - Líneas ~627-645 (manejo de campos ignorados + early return)
   - Función `guardar_datos_elemento()` - Líneas ~677-695 (mensaje siguiente campo SEQUENTIAL)
   - Función `confirmar_fotos_elemento()` - Líneas ~814-826 (mensaje inicial SEQUENTIAL)

## Bug Fix Adicional (29 Enero 16:31)

### Problema Detectado
El mensaje de error de campos ignorados se sobrescribía con "✅ Datos guardados" porque el bloque de "campos pendientes" se ejecutaba después del bloque de error.

### Solución
Añadido `return response` después de detectar campos ignorados (early return) para evitar que el mensaje de error se sobrescriba.

**Código modificado (línea ~645):**
```python
if ignored_fields:
    # ... construcción del mensaje de error ...
    response["success"] = False
    # EARLY RETURN - Don't process further logic if fields were ignored
    return response  # ← Añadido
```

**Resultado:**
- ✅ El mensaje ahora muestra correctamente el error crítico
- ✅ No se sobrescribe con "✅ Datos guardados"
- ✅ El admin panel mostrará el error correcto con el mensaje apropiado

## Impacto Esperado

### Antes de la Solución
1. Usuario: "recorte del asiento trasero 2. 430 3. 2300 mm"
2. LLM: `guardar_datos_elemento({"modificacion": "...", "longitud_total": 2300})`
3. Sistema: Ignora silenciosamente ambos campos ❌
4. LLM: Vuelve a preguntar lo mismo (bucle infinito)

### Después de la Solución
1. LLM recibe: "Campo: 'descripcion_modificacion'" en el prompt
2. Usuario: "recorte del asiento trasero 2. 430 3. 2300 mm"
3. LLM: `guardar_datos_elemento({"descripcion_modificacion": "...", "nueva_longitud_total": 2300})`
4. Sistema: Guarda correctamente ✅

### Si LLM Aún Usa Campos Incorrectos
1. LLM: `guardar_datos_elemento({"modificacion": "..."})`
2. Sistema: **`success: False`** con mensaje CRÍTICO mostrando los field_keys válidos
3. LLM: Se ve forzado a corregir y volver a llamar con los keys correctos

## Ventajas de Esta Solución

1. **Preventiva:** El LLM ve los field_keys exactos ANTES de guardar
2. **Correctiva:** Si aún se equivoca, recibe error crítico con los keys válidos
3. **Clara:** Mensajes estructurados y explícitos, no ambiguos
4. **No Invasiva:** No requiere cambios en la base de datos ni en los modelos
5. **Compatible:** Funciona con los tres modos (SEQUENTIAL, BATCH, HYBRID)

## Testing Recomendado

1. Reiniciar el agente para cargar los cambios
2. Crear un nuevo expediente con SUBCHASIS
3. Verificar que el LLM:
   - Recibe los field_keys en el prompt
   - Usa los field_keys correctos al guardar
   - Si se equivoca, recibe error y corrige

## Notas Adicionales

- Los LSP warnings sobre imports no resueltos son normales en este proyecto
- La sintaxis Python fue verificada con `py_compile`
- Esta solución también previene problemas similares con otros elementos que tengan campos con nombres complejos

---

**Autor:** Claude (Anthropic)  
**Validado:** Sintaxis Python correcta ✅
