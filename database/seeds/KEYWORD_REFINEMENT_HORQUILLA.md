# Refinamiento de Keywords: HORQUILLA vs SUSPENSION_DEL

**Fecha**: 2026-02-03  
**Motivo**: Eliminar ambigüedad entre elementos relacionados que causaba identificación incorrecta por el agente

---

## Problema Identificado

### Ambigüedad en Keyword: `"horquilla"`

**Elemento HORQUILLA** contenía la keyword genérica `"horquilla"` que causaba **falsos positivos** cuando usuarios mencionaban:
- "barras de horquilla" → Debería identificar **SUSPENSION_DEL** (solo barras internas)
- "muelles de horquilla" → Debería identificar **SUSPENSION_DEL** (solo muelles internos)

Pero el agente podía confundirse y sugerir **HORQUILLA** (cambio completo) en vez de **SUSPENSION_DEL**.

---

## Diferencias Entre Elementos

| Aspecto | HORQUILLA | SUSPENSION_DEL |
|---------|-----------|----------------|
| **Alcance** | Cambio COMPLETO del tren delantero | Solo componentes INTERNOS |
| **Incluye** | Toda la estructura externa + interna | Solo barras o muelles internos |
| **Geometría** | Modifica distancia entre ejes | NO modifica geometría |
| **Ensayo** | Puede requerir ensayo de frenada (+375 EUR) | NO requiere ensayo |
| **Ejemplo** | "Poner horquilla de R6 en mi Bandit" | "Poner muelles Ohlins en mi horquilla" |

---

## Cambios Aplicados

### HORQUILLA (Antes):
```python
"keywords": [
    "horquilla completa", 
    "horquilla",  # ← GENÉRICA (problema)
    "tren delantero",
    "tren delantero completo", 
    "cambio horquilla",
    "distancia entre ejes", 
    "distancia ejes",
    "horquilla de otra moto", 
    "horquilla nueva"
]
```

### HORQUILLA (Después):
```python
"keywords": [
    # Eliminada keyword genérica "horquilla"
    "horquilla completa",
    "cambio horquilla completa",
    "horquilla entera",
    "tren delantero",
    "tren delantero completo",
    "cambio tren delantero",
    # Contexto geométrico
    "distancia entre ejes",
    "distancia ejes",
    "nueva distancia ejes",
    # Procedencia
    "horquilla de otra moto",
    "horquilla nueva",
    "horquilla diferente",
    # Tipos específicos
    "horquilla invertida",
    "horquilla convencional",
    "upside down fork",
    "cambio de horquilla por otra",
    "sustitucion horquilla completa",
]
```

**Cambios clave**:
- ❌ Eliminada: `"horquilla"` (demasiado genérica)
- ✅ Agregadas: Keywords más específicas que indican cambio COMPLETO
- ✅ Agregadas: Tipos de horquilla (invertida, convencional, upside down)

---

### SUSPENSION_DEL (Antes):
```python
"keywords": [
    "suspension delantera", 
    "barras suspension", 
    "muelles barras",
    "barras de horquilla", 
    "muelles suspension", 
    "fork springs",
    "barras interiores", 
    "muelles interiores"
]
```

### SUSPENSION_DEL (Después):
```python
"keywords": [
    "suspension delantera",
    "barras suspension delantera",
    "muelles suspension delantera",
    # Específico a barras
    "barras de horquilla",
    "barras interiores horquilla",
    "barras interiores",
    # Específico a muelles
    "muelles barras",
    "muelles horquilla",
    "muelles suspension",
    "muelles interiores",
    "fork springs",
    # Cartuchos (componente interno)
    "cartuchos suspension",
    "cartuchos horquilla",
    # Indicadores de alcance limitado
    "solo barras",
    "solo muelles",
    "cambio barras",
    "cambio muelles",
]
```

**Cambios clave**:
- ✅ Agregadas: Keywords con calificadores (suspension delantera, interiores, etc.)
- ✅ Agregadas: Indicadores de alcance limitado ("solo barras", "solo muelles")
- ✅ Agregadas: "cartuchos" (término técnico para componentes internos)

---

## Comportamiento Esperado

### ✅ Casos que ahora se identifican CORRECTAMENTE:

| Frase del Usuario | Elemento Correcto | Razón |
|-------------------|-------------------|-------|
| "horquilla completa" | HORQUILLA | Keyword específica |
| "cambio horquilla completa" | HORQUILLA | Keyword específica |
| "horquilla invertida" | HORQUILLA | Keyword específica (tipo) |
| "upside down fork" | HORQUILLA | Keyword específica (tipo) |
| "barras de horquilla" | SUSPENSION_DEL | Keyword específica (componente interno) |
| "muelles horquilla" | SUSPENSION_DEL | Keyword específica (componente interno) |
| "solo muelles" | SUSPENSION_DEL | Indicador de alcance limitado |
| "cartuchos suspension" | SUSPENSION_DEL | Término técnico (componente interno) |

### ❌ Casos ambiguos que ANTES fallaban:

| Frase | Antes | Después |
|-------|-------|---------|
| "quiero cambiar las barras" | Ambiguo (podía sugerir HORQUILLA) | SUSPENSION_DEL ✓ |
| "poner muelles más duros" | Ambiguo (podía sugerir HORQUILLA) | SUSPENSION_DEL ✓ |

---

## Aplicación de Cambios

### 1. Seeds (Ya aplicado)
```bash
# Archivo modificado:
database/seeds/data/motos_part.py
```

### 2. Base de Datos (Ejecutar SQL)
```bash
docker-compose exec -T postgres psql -U msia msia_db < database/migrations/update_horquilla_suspension_keywords.sql
```

### 3. Verificación
```sql
-- Ver keywords actualizadas
SELECT 
    code, 
    name,
    jsonb_array_length(keywords) as total_keywords,
    jsonb_pretty(keywords) as keywords
FROM elements 
WHERE code IN ('HORQUILLA', 'SUSPENSION_DEL')
  AND category_id IN (SELECT id FROM vehicle_categories WHERE slug = 'motos-part');
```

---

## Impacto en el Sistema

### Componentes Afectados:

1. **Agent** (`agent/tools/element_tools.py`)
   - `identificar_elementos_tool()` - Usa keywords para matching
   - Mejor precisión en identificación

2. **Seeds** (`database/seeds/data/motos_part.py`)
   - Source of truth para futuras re-seeds
   - Keywords ya actualizadas

3. **Database** (`elements` table)
   - Actualización SQL requerida para reflejar cambios

### NO Afectados:

- ❌ Estructura de base de datos (no cambia schema)
- ❌ API endpoints (no cambian contratos)
- ❌ Admin panel UI (no cambia interfaz)
- ❌ Tariff calculations (no cambia pricing)

---

## Testing Recomendado

### Test Cases:

```python
# Test 1: Horquilla completa
input: "Quiero poner la horquilla de una R6"
expected: HORQUILLA

# Test 2: Solo barras
input: "Cambiar las barras de la horquilla por unas Ohlins"
expected: SUSPENSION_DEL

# Test 3: Solo muelles
input: "Poner muelles más duros en mi horquilla"
expected: SUSPENSION_DEL

# Test 4: Horquilla invertida
input: "Cambiar a horquilla invertida"
expected: HORQUILLA

# Test 5: Cartuchos (técnico)
input: "Instalar cartuchos de suspension Ohlins"
expected: SUSPENSION_DEL
```

---

## Rollback (Si es necesario)

```sql
BEGIN;

-- Revertir HORQUILLA
UPDATE elements 
SET keywords = '[
    "horquilla completa", "horquilla", "tren delantero",
    "tren delantero completo", "cambio horquilla",
    "distancia entre ejes", "distancia ejes",
    "horquilla de otra moto", "horquilla nueva"
]'::jsonb 
WHERE code = 'HORQUILLA';

-- Revertir SUSPENSION_DEL
UPDATE elements 
SET keywords = '[
    "suspension delantera", "barras suspension", "muelles barras",
    "barras de horquilla", "muelles suspension", "fork springs",
    "barras interiores", "muelles interiores"
]'::jsonb 
WHERE code = 'SUSPENSION_DEL';

COMMIT;
```

---

## Métricas de Éxito

Para medir el impacto:

1. **Precisión de Identificación**
   - Revisar `tool_call_logs` tabla
   - Contar cuántas veces se identifica correctamente cada elemento
   - Meta: >95% de identificaciones correctas

2. **Escalations**
   - Revisar escalaciones por "elemento incorrecto"
   - Meta: Reducción >50% en escalaciones relacionadas con horquilla/suspension

3. **User Corrections**
   - Contar cuántas veces el agente pregunta "¿Te refieres a X o Y?"
   - Meta: Reducción en ambigüedades reportadas

---

## Referencias

- [Element Tools](../../agent/tools/element_tools.py) - Implementación de matching
- [Element Seeds](./data/motos_part.py) - Source of truth
- [SQL Migration](../migrations/update_horquilla_suspension_keywords.sql) - Script de actualización
