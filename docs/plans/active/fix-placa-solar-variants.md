# Plan: Fix Completo Variantes PLACA_SOLAR

**Fecha**: 2026-02-20
**Estado**: PENDIENTE APROBACIÓN
**Prioridad**: Alta — afecta precio y flujo de conversación en producción
**Relacionado con**: `fix-variant-keyword-overlap.md` (completado)

---

## Resumen Ejecutivo

El elemento `PLACA_SOLAR` en `aseicars-prof` tiene 6 problemas interrelacionados:

1. **Solo 2 variantes cuando el negocio necesita 3** — los casos B y C tienen documentación distinta
2. **`question_hint` semánticamente incorrecto** — genera ambigüedad que requiere 2 rondas de aclaración
3. **Keywords de `PLACA_SOLAR_SIMPLE` incorrectos** — describe ubicación, no el concepto de "regulador existente"
4. **`PLACA_SOLAR_SIMPLE` no está en los tiers correctos** — precio potencialmente 4-5x incorrecto (270€ vs 59€)
5. **Bug de código**: `presupuesto_mode.py` busca `data.get("success")` pero la tool retorna `selected_variant` → `pending_variants` nunca se limpia → 3 iteraciones en vez de 1
6. **Nombre redundante**: `PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR` tiene el prefijo repetido

### Las 3 variantes reales del negocio

| Variante | Descripción técnica                                                 | Documentación distinta |
|----------|---------------------------------------------------------------------|------------------------|
| **A**    | Conectada a regulador ya existente en el vehículo (máx. 2 placas)  | Sí                     |
| **B**    | Regulador nuevo, oculto (en armario o tras última fila de asientos) | Sí                     |
| **C**    | Regulador nuevo, visible en zona de pasajeros                       | Sí                     |

Las variantes B y C tienen el mismo precio (mismo tier) pero distinta documentación requerida.
El precio no va por elemento sino por tier (conjunto de elementos) — sistema confirmado por investigación.

---

## Servicios Afectados

- [ ] Database — nueva variante C + corrección datos variante A y B + fix tier inclusions
- [ ] Agent (code) — fix bug `pending_variants` en `presupuesto_mode.py`
- [ ] API — ninguno
- [ ] Admin — ninguno

---

## Tareas Database → `database-dev`

### DB-1: Corregir nombre y keywords de `PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR` (variante B)

**Antes**: nombre redundante, keywords de ubicación incorrectos
**Después**: nombre claro, keywords que un usuario diría si ya sabe que tiene regulador nuevo en mueble

```sql
-- Verificar estado actual
SELECT code, name, keywords, variant_code FROM elements
WHERE code = 'PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR'
AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof');

-- Actualizar
UPDATE elements SET
    name = 'Placa solar con regulador oculto (armario o tras última fila)',
    keywords = '["regulador en armario", "armario", "regulador oculto", "tras ultima fila", "detras asientos", "mueble cocina", "regulador en mueble", "regulador en maletero"]'::jsonb,
    variant_code = 'REGULADOR_OCULTO',
    updated_at = NOW()
WHERE code = 'PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR'
AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof');
```

### DB-2: Corregir nombre y keywords de `PLACA_SOLAR_SIMPLE` (variante A)

**Antes**: keywords describen ubicación física, no el concepto de "regulador ya existente"
**Después**: keywords que un usuario diría si ya tiene regulador en el vehículo

```sql
-- Verificar estado actual
SELECT code, name, keywords, variant_code FROM elements
WHERE code = 'PLACA_SOLAR_SIMPLE'
AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof');

-- Actualizar
UPDATE elements SET
    name = 'Placa solar conectada a regulador existente del vehículo',
    keywords = '["regulador existente", "ya tiene regulador", "regulador del vehiculo", "regulador propio", "regulador ya instalado", "conectada a regulador", "maximo dos placas", "aprovecha regulador"]'::jsonb,
    variant_code = 'REGULADOR_EXISTENTE',
    updated_at = NOW()
WHERE code = 'PLACA_SOLAR_SIMPLE'
AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof');
```

### DB-3: Crear variante C — `PLACA_SOLAR_REGULADOR_VISIBLE`

**Nueva variante**: regulador nuevo visible en zona de pasajeros. Hereda imágenes y warnings del padre.

Usar UUID determinístico v5 con namespace del proyecto:

```python
import uuid
SEED_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # del seed_utils.py
new_id = uuid.uuid5(SEED_NAMESPACE, "element:aseicars-prof:PLACA_SOLAR_REGULADOR_VISIBLE")
```

```sql
-- Obtener datos necesarios
SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof';
SELECT id FROM elements WHERE code = 'PLACA_SOLAR' AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof');

-- Insertar nueva variante C
-- Usar el UUID determinístico calculado con seed_utils
INSERT INTO elements (
    id,
    code,
    name,
    variant_type,
    variant_code,
    keywords,
    aliases,
    parent_element_id,
    category_id,
    is_active,
    inherit_parent_data,
    created_at,
    updated_at
) VALUES (
    -- UUID v5 determinístico calculado con seed_utils
    uuid_generate_v5('6ba7b810-9dad-11d1-80b4-00c04fd430c8'::uuid, 'element:aseicars-prof:PLACA_SOLAR_REGULADOR_VISIBLE'),
    'PLACA_SOLAR_REGULADOR_VISIBLE',
    'Placa solar con regulador visible en zona de pasajeros',
    'regulator_location',
    'REGULADOR_VISIBLE',
    '["regulador visible", "a la vista", "visible en habitaculo", "regulador en zona pasajeros", "se ve el regulador", "regulador a la vista", "zona pasajeros"]'::jsonb,
    '[]'::jsonb,
    (SELECT id FROM elements WHERE code = 'PLACA_SOLAR' AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof')),
    (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof'),
    true,
    true,  -- hereda imágenes y warnings del padre
    NOW(),
    NOW()
);

-- Verificar inserción
SELECT code, name, variant_type, variant_code, parent_element_id FROM elements
WHERE code = 'PLACA_SOLAR_REGULADOR_VISIBLE';
```

**NOTA**: Si `uuid_generate_v5` no está disponible en la BD, calcular el UUID en Python con `seed_utils.py` e insertar el valor literal.

### DB-4: Corregir `question_hint` del padre `PLACA_SOLAR`

**Antes**: pregunta binaria que no cubre los 3 casos
**Después**: pregunta de 3 opciones claras alineadas con la realidad del negocio

```sql
UPDATE elements SET
    question_hint = '¿Cómo está configurada la instalación de la placa solar? A) Conectada a un regulador que ya existe en el vehículo (máximo 2 placas). B) Con regulador nuevo instalado en armario o detrás de la última fila de asientos (oculto). C) Con regulador nuevo visible en la zona donde van los pasajeros.',
    updated_at = NOW()
WHERE code = 'PLACA_SOLAR'
AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof');
```

### DB-5: Añadir `PLACA_SOLAR_SIMPLE` a los tiers correctos (fix precio crítico)

**Problema**: `PLACA_SOLAR_SIMPLE` solo está en T1 (270€). Debería estar en T6 (59€) como mínimo.
**Acción**: Insertar en `tier_element_inclusions` para los mismos tiers que `PLACA_SOLAR`.

```sql
-- Ver en qué tiers está PLACA_SOLAR actualmente
SELECT tt.name as tier_name, tt.id as tier_id, t.name as tariff_name
FROM tier_element_inclusions tei
JOIN tariff_tiers tt ON tei.tier_id = tt.id
JOIN tariffs t ON tt.tariff_id = t.id
JOIN elements e ON tei.element_id = e.id
WHERE e.code = 'PLACA_SOLAR'
AND t.category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof')
ORDER BY tt.name;

-- Obtener el ID de PLACA_SOLAR_SIMPLE
SELECT id FROM elements
WHERE code = 'PLACA_SOLAR_SIMPLE'
AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof');

-- Insertar PLACA_SOLAR_SIMPLE en los mismos tiers que PLACA_SOLAR
-- (Ejecutar una INSERT por cada tier donde esté PLACA_SOLAR, usando UUIDs v5 determinísticos)
-- El database-dev debe calcular los UUIDs con seed_utils o usar gen_random_uuid() si no hay conflicto

INSERT INTO tier_element_inclusions (id, tier_id, element_id, created_at)
SELECT
    gen_random_uuid(),
    tei.tier_id,
    (SELECT id FROM elements WHERE code = 'PLACA_SOLAR_SIMPLE' AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof')),
    NOW()
FROM tier_element_inclusions tei
JOIN elements e ON tei.element_id = e.id
WHERE e.code = 'PLACA_SOLAR'
AND tei.tier_id IN (
    SELECT tt.id FROM tariff_tiers tt
    JOIN tariffs t ON tt.tariff_id = t.id
    WHERE t.category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof')
)
ON CONFLICT DO NOTHING;
```

### DB-6: Añadir `PLACA_SOLAR_REGULADOR_VISIBLE` a los mismos tiers (nueva variante C)

```sql
-- Insertar nueva variante C en los mismos tiers que PLACA_SOLAR
INSERT INTO tier_element_inclusions (id, tier_id, element_id, created_at)
SELECT
    gen_random_uuid(),
    tei.tier_id,
    (SELECT id FROM elements WHERE code = 'PLACA_SOLAR_REGULADOR_VISIBLE' AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof')),
    NOW()
FROM tier_element_inclusions tei
JOIN elements e ON tei.element_id = e.id
WHERE e.code = 'PLACA_SOLAR'
AND tei.tier_id IN (
    SELECT tt.id FROM tariff_tiers tt
    JOIN tariffs t ON tt.tariff_id = t.id
    WHERE t.category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof')
)
ON CONFLICT DO NOTHING;
```

### DB-7: Actualizar `tier_mappings.py` para que los seeds sean idempotentes

**Archivo**: `database/seeds/data/tier_mappings.py`

Añadir `PLACA_SOLAR_SIMPLE`, `PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR` y `PLACA_SOLAR_REGULADOR_VISIBLE` a las listas de elementos correspondientes en `ASEICARS_PROF_MAPPINGS`.

Esto garantiza que si se re-corren los seeds en el futuro, las correcciones persistan.

---

## Tareas Agent → `agent-dev`

### AG-1: Fix bug `pending_variants` en `presupuesto_mode.py`

**Archivo**: `agent/modes/presupuesto_mode.py`
**Función**: `_extract_context_from_tool()`, bloque `elif tool_name == "seleccionar_variante_por_respuesta":`

**Problema** (línea ~715):
```python
# INCORRECTO — busca campos que no existen en el response exitoso
if data.get("success") or data.get("codigo"):
    updates["pending_variants"] = []
```

**Fix**:
```python
# CORRECTO — la tool retorna "selected_variant" (singular) o "selected_variants" (multi)
# También manejar el caso de error (cuando retorna "error") para NO limpiar pending_variants
has_selection = (
    data.get("selected_variant") or        # selección única exitosa
    data.get("selected_variants") or       # multi-selección exitosa
    data.get("success") or                 # compatibilidad futura
    data.get("codigo")                     # compatibilidad legacy
)

if has_selection:
    updates["pending_variants"] = []
    # Extraer código de selección única
    code = (
        data.get("selected_variant") or
        data.get("codigo") or
        data.get("code")
    )
    if code:
        updates["elemento_confirmado"] = {
            "code": code,
            "name": data.get("name") or data.get("nombre", code),
        }
    # Manejar multi-selección (selected_variants es una lista)
    elif data.get("selected_variants"):
        codes = data["selected_variants"]
        updates["element_codes"] = codes
        updates["elemento_confirmado"] = {
            "code": codes[0],
            "name": data.get("names", [codes[0]])[0],
        }
# Si hay "error" en el response, NO limpiar pending_variants (mantener bloqueado)
```

**Verificar** que el bloque completo queda así y no rompe casos existentes:
- Selección única exitosa → `pending_variants = []`, `elemento_confirmado` actualizado
- Multi-selección exitosa → `pending_variants = []`, `element_codes` actualizado
- Error de matching → `pending_variants` intacto (sigue bloqueando `calcular_tarifa`)
- Confidence bajo (retorna error) → `pending_variants` intacto

### AG-2: Test unitario para el fix del bug

**Archivo**: `tests/test_presupuesto_mode_variant_resolution.py` (nuevo)

Casos a cubrir:
1. `seleccionar_variante_por_respuesta` retorna `selected_variant` → `pending_variants` se limpia
2. `seleccionar_variante_por_respuesta` retorna `error` → `pending_variants` permanece
3. `seleccionar_variante_por_respuesta` retorna `selected_variants` (multi) → `pending_variants` se limpia
4. Flujo completo: `identificar` → `seleccionar` → `calcular` sin bloqueo (integración mínima)

---

## Orden de Ejecución

```
DB-1, DB-2           (en paralelo — corrección de variantes existentes)
     ↓
DB-3                 (crear variante C — depende de que B esté corregida primero para coherencia)
     ↓
DB-4                 (actualizar question_hint — depende de tener las 3 variantes creadas)
     ↓
DB-5, DB-6           (en paralelo — fix tier inclusions para A y C)
     ↓
DB-7                 (actualizar seeds — independiente de BD pero debe ir al final)
     ↓
AG-1                 (fix bug código — independiente de BD)
     ↓
AG-2                 (tests — depende de AG-1)
     ↓
restart agent        (invalidar cache Redis)
```

---

## Criterios de Aceptación

- [ ] Mensaje "placa solar" → agente hace pregunta con **3 opciones claras** (A, B, C)
- [ ] Respuesta "tengo un regulador que ya tiene el camper" → selecciona `PLACA_SOLAR_SIMPLE` directamente
- [ ] Respuesta "lo tengo en el armario bajo la cama" → selecciona `PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR` directamente
- [ ] Respuesta "el regulador está visible en el salón" → selecciona `PLACA_SOLAR_REGULADOR_VISIBLE` directamente
- [ ] El flujo completo se resuelve en **máximo 2 turnos** (pregunta + respuesta), no 3
- [ ] `calcular_tarifa` NO se bloquea tras `seleccionar_variante` exitoso
- [ ] `PLACA_SOLAR_SIMPLE` sola → precio T6 (59€ prof / 75€ part), sin warning "Elements not in tier"
- [ ] Tests pasan: `pytest tests/test_presupuesto_mode_variant_resolution.py -v`
- [ ] `PLACA_SOLAR_REGULADOR_VISIBLE` hereda imágenes y warnings de `PLACA_SOLAR` (`inherit_parent_data = true`)

---

## Riesgos y Consideraciones

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| `uuid_generate_v5` no disponible en PostgreSQL | Media | Calcular UUID en Python con seed_utils y usar valor literal en INSERT |
| Conversaciones activas con `pending_variants` en Redis al momento del fix | Baja | El fix de código solo afecta nuevas evaluaciones; state existente en Redis se resolverá en el próximo turno |
| `tier_element_inclusions` tiene constraint unique que falla en INSERT | Baja | `ON CONFLICT DO NOTHING` ya lo cubre |
| La variante C necesita documentación específica diferente → ¿hay campo en BD para esto? | A verificar | Revisar si `Element` tiene campo `documentation_notes` o similar; si no, usar `description` |
| Regresión en elementos que funcionan correctamente (TOLDO_LAT, BOLA_REMOLQUE) | Baja | AG-2 tests cubren regresión; Parent Guard ya testeado |

---

## Query de Verificación Post-Fix

```sql
-- Verificar que las 3 variantes están en los tiers correctos
SELECT
    e.code,
    e.name,
    e.variant_code,
    array_agg(tt.name ORDER BY tt.name) as tiers
FROM elements e
LEFT JOIN tier_element_inclusions tei ON tei.element_id = e.id
LEFT JOIN tariff_tiers tt ON tei.tier_id = tt.id
JOIN vehicle_categories vc ON e.category_id = vc.id
WHERE vc.slug = 'aseicars-prof'
AND (e.code ILIKE '%PLACA_SOLAR%')
GROUP BY e.code, e.name, e.variant_code
ORDER BY e.parent_element_id NULLS FIRST, e.code;

-- Resultado esperado:
-- PLACA_SOLAR                          | {T1,T2,T3,T4,T5,T6}
-- PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR | {T1,T2,T3,T4,T5,T6}
-- PLACA_SOLAR_REGULADOR_VISIBLE        | {T1,T2,T3,T4,T5,T6}
-- PLACA_SOLAR_SIMPLE                   | {T1,T2,T3,T4,T5,T6}
```

---

## Notas de Implementación

### Sobre el campo `documentation_notes`
Verificar si existe en el modelo `Element`. Si no existe, la información de documentación diferente por variante puede ir en el campo `description` o requerir un nuevo campo. **Esto es un punto de investigación para el database-dev antes de ejecutar DB-3.**

### Sobre los seeds
`DB-7` actualiza `tier_mappings.py` para que los seeds sean idempotentes. Esto es especialmente importante porque si alguien re-corre `run_all_seeds.py` en el futuro, no debe revertir las correcciones de BD.

### Sobre `inherit_parent_data = true`
La nueva variante C con `inherit_parent_data = true` heredará automáticamente imágenes y warnings del padre `PLACA_SOLAR`. Esto es el comportamiento correcto — no necesita imágenes ni warnings propios.

---

**Creado por**: Zanovix (análisis) + investigador-dev (sistema de tarifas)
**Fecha**: 2026-02-20
**Sesión**: Fix completo variantes PLACA_SOLAR post-Parent Guard
