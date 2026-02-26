# Plan: Fix Variant Keyword Overlap — Selección automática incorrecta de variantes

**Fecha**: 2026-02-20  
**Estado**: PENDIENTE APROBACIÓN  
**Prioridad**: Alta — afecta flujo principal de presupuestos (~90% tráfico)

---

## Resumen Ejecutivo

El agente selecciona automáticamente variantes específicas de un elemento cuando el usuario solo menciona el término genérico, sin preguntar primero. Esto ocurre porque los elementos hijo (variantes) tienen keywords idénticos o solapados con su padre, lo que hace que el scoring del `element_service` supere el threshold `HIGH_VARIANT_THRESHOLD = 1.2` con mensajes genéricos.

**Caso concreto observado**: Usuario dice "quiero homologar la placa solar de mi autocaravana" → agente selecciona directamente `PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR` sin preguntar "¿El regulador está en el interior o en el maletero?".

**Causa raíz**: Doble problema — datos incorrectos en BD (keywords solapados) + ausencia de validación en la lógica del `element_service` que garantice que un hijo nunca puntúe más que su padre con un mensaje que no especifica variante.

---

## Servicios Afectados

- [ ] Database — corrección de datos de elementos
- [ ] Agent — mejora defensiva en `element_service.py`
- [ ] API — ninguno
- [ ] Admin — ninguno
- [ ] Shared — ninguno

---

## Diagnóstico Completo

### Elementos afectados en `aseicars-prof`

| Elemento padre    | Problema                                          | Severidad |
|-------------------|---------------------------------------------------|-----------|
| `PLACA_SOLAR`     | Hijo `PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR` tiene 6 keywords idénticos al padre. Sin `variant_type`. | 🔴 CRÍTICO |
| `CLARABOYA`       | Hijo `CLARABOYA_PRUEBA` tiene 4 keywords del padre solapados. Sin `variant_type`. Sin `question_hint` en padre. Elemento de test. | 🔴 CRÍTICO |
| `GLP_INSTALACION` | Hijo `GLP_KIT_BOMB` comparte keyword "bombona" con el padre. Los otros hijos OK. | 🟡 MENOR |
| `BOLA_SIN_MMR`    | Padre sin `question_hint`. Tiene 1 hijo. | 🟡 MENOR |

### Elementos correctamente configurados (referencia)

`TOLDO_LAT`, `FAROS_LA`, `BOLA_REMOLQUE`, `CAMBIO_CLASIF`, `SUSP_NEUM` — keywords de hijos son específicos y no solapan con padre.

### Mecánica del fallo

```
Usuario: "placa solar de mi autocaravana"
tokens: ["placa", "solar", "autocaravana"]

Scoring PLACA_SOLAR (padre):
  Phase 1: "placa solar" (multi-word parcial) → 0.8 pts
  Phase 1: "solar" → 1.0 pts
  Total padre: ~1.8 pts

Scoring PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR (hijo):
  Phase 1: "placa solar" → 0.8 pts
  Phase 1: "solar" → 1.0 pts
  Phase 1: "placa solar regulador interior" → 0.4 pts (parcial)
  Total hijo: ~2.2 pts  ← supera HIGH_VARIANT_THRESHOLD=1.2

Resultado: hijo seleccionado directamente. Pregunta nunca hecha.
```

---

## Tareas por Servicio

### Database → database-dev

#### Tarea DB-1: Corregir keywords de `PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR`

**Problema**: Keywords genéricos del padre copiados en el hijo.  
**Acción**: Reemplazar por keywords específicos que un usuario diría SOLO si ya sabe que tiene regulador interior en mueble/maletero.

```sql
UPDATE elements 
SET 
    keywords = '["regulador interior", "regulador en mueble", "regulador en maletero", "regulador interior mueble", "maletero"]'::jsonb,
    variant_type = 'regulator_location',
    updated_at = NOW()
WHERE code = 'PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR'
AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof');
```

#### Tarea DB-2: Corregir keywords de `PLACA_SOLAR_SIMPLE`

**Problema**: Tiene `variant_type = 'regulator_visibility'` pero el otro hijo no tiene `variant_type`. Deben ser coherentes.  
**Acción**: Unificar `variant_type` al mismo valor para ambos hijos del mismo padre.

```sql
UPDATE elements 
SET 
    variant_type = 'regulator_location',
    updated_at = NOW()
WHERE code = 'PLACA_SOLAR_SIMPLE'
AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof');
```

#### Tarea DB-3: Desactivar/limpiar `CLARABOYA_PRUEBA`

**Problema**: Elemento de prueba con `is_active = false` pero keywords solapados con el padre. Ya está desactivado; confirmar y documentar.  
**Acción**: Verificar que `is_active = false`. Si en algún momento se reactiva, los keywords deben ser específicos. Actualizar keywords preventivamente.

```sql
UPDATE elements 
SET 
    keywords = '["claraboya con prueba", "prueba claraboya"]'::jsonb,
    updated_at = NOW()
WHERE code = 'CLARABOYA_PRUEBA'
AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof');
```

#### Tarea DB-4: Añadir `question_hint` al padre `CLARABOYA`

**Problema**: Padre sin `question_hint` — si el usuario llega al padre, no hay pregunta formulada.  
**Acción**: Definir la pregunta de variante.

```sql
UPDATE elements 
SET 
    question_hint = '¿La claraboya es adicional o estándar de fábrica?',
    updated_at = NOW()
WHERE code = 'CLARABOYA'
AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof');
```

#### Tarea DB-5: Corregir keyword "bombona" en `GLP_KIT_BOMB`

**Problema**: El padre `GLP_INSTALACION` tiene keyword "bombona" y el hijo `GLP_KIT_BOMB` también, causando solapamiento menor.  
**Acción**: Eliminar "bombona" del padre (es demasiado específico del hijo) o del hijo sustituirlo por términos más específicos.

```sql
-- Opción A: Quitar "bombona" del padre GLP_INSTALACION (preferida)
UPDATE elements 
SET 
    keywords = '["glp", "gas", "instalacion gas", "deposito glp", "autogas"]'::jsonb,
    updated_at = NOW()
WHERE code = 'GLP_INSTALACION'
AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof');
```

#### Tarea DB-6: Añadir `question_hint` al padre `BOLA_SIN_MMR`

**Problema**: `BOLA_SIN_MMR` es padre de `BRAZO_PORTA` pero no tiene `question_hint`.  
**Acción**: Evaluar si `BRAZO_PORTA` es realmente una variante o un elemento separado. Si es variante, añadir pregunta.

```sql
UPDATE elements 
SET 
    question_hint = '¿Deseas añadir también un brazo portaequipajes a la bola de remolque?',
    updated_at = NOW()
WHERE code = 'BOLA_SIN_MMR'
AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof');
```

**Interfaz DB**: Tabla `elements`, campos `keywords` (JSONB), `variant_type` (VARCHAR), `question_hint` (VARCHAR). No se requiere migración — son updates de datos, no de esquema.

---

### Agent → agent-dev

#### Tarea AG-1: Añadir validación defensiva en `element_service.py` — "Parent Guard"

**Problema**: El scoring actual no tiene en cuenta la jerarquía. Un hijo puede puntuar más que su padre con un mensaje genérico.  
**Acción**: Añadir una regla en `match_elements_with_unmatched()`: si un hijo supera `HIGH_VARIANT_THRESHOLD` pero su puntuación no supera significativamente la del padre (ratio < 1.3x), descartar el hijo y usar el padre para forzar la pregunta.

**Ubicación**: `agent/services/element_service.py`, función `match_elements_with_unmatched()`, sección "Decision: Use high-confidence variants".

**Lógica propuesta**:
```python
# NUEVO: Parent Guard
# Si un hijo matchea con alta confianza, verificar que supere al padre por margen suficiente.
# Si no, preferir el padre para que el agente haga la pregunta de variante.
PARENT_SUPERIORITY_RATIO = 1.3  # hijo debe puntuar 30% más que el padre

if variant_matches:
    # Calcular scores de los padres de esos variantes
    parent_scores = {
        elem.get("parent_element_id"): score
        for elem, score, _ in base_matches
        if elem.get("id") in {e.get("parent_element_id") for e, _, _ in variant_matches}
    }
    
    # Filtrar variantes que no superan suficientemente a su padre
    strong_variant_matches = []
    weak_variant_matches_parents = set()
    
    for elem, score, tokens in variant_matches:
        parent_id = elem.get("parent_element_id")
        parent_score = parent_scores.get(parent_id, 0)
        
        if parent_score > 0 and score < parent_score * PARENT_SUPERIORITY_RATIO:
            # Hijo no supera al padre por margen suficiente → usar padre
            weak_variant_matches_parents.add(parent_id)
        else:
            strong_variant_matches.append((elem, score, tokens))
    
    # Reintegrar padres de variantes débiles como base matches
    if weak_variant_matches_parents:
        for elem, score, tokens in base_matches:
            if elem.get("id") in weak_variant_matches_parents:
                # Añadir padre en lugar del hijo
                matches.append((elem, score))
    
    variant_matches = strong_variant_matches
```

**Contrato de interfaz**: La función mantiene su firma exacta. Solo cambia la lógica interna de decisión. El output sigue siendo `list[tuple[dict, float]]`.

#### Tarea AG-2: Test unitario para la regla "Parent Guard"

**Ubicación**: `tests/test_element_service.py` (existente) o nuevo `tests/test_element_variant_guard.py`.

**Casos a cubrir**:
1. Mensaje genérico ("placa solar") → debe retornar padre, no hijo
2. Mensaje específico ("placa solar con regulador en maletero") → debe retornar hijo directamente
3. Elemento sin variantes → comportamiento sin cambio
4. Variante con score muy superior al padre → debe retornar hijo (correcto)

---

## Dependencias entre Tareas

```
DB-1 → DB-2 (coherencia variant_type de ambos hijos de PLACA_SOLAR)
DB-3 → independiente (limpieza)
DB-4 → independiente
DB-5 → independiente  
DB-6 → independiente
AG-1 → independiente de DB (mejora defensiva)
AG-2 → depende de AG-1 (tests del código nuevo)
```

**Orden de ejecución recomendado**:
1. DB-1, DB-2, DB-3, DB-4, DB-5, DB-6 (en paralelo o secuencial — todos son UPDATEs)
2. AG-1 (mejora defensiva)
3. AG-2 (tests)

---

## Tests Requeridos

### Unit Tests (agent-dev / qa-dev)
- [ ] `test_generic_message_returns_parent_not_child` — mensaje genérico → padre
- [ ] `test_specific_message_returns_child_directly` — mensaje específico → hijo
- [ ] `test_parent_guard_ratio_threshold` — ratio exacto del threshold
- [ ] `test_no_variants_unaffected` — elementos sin hijos no cambian
- [ ] `test_glp_generic_returns_parent` — "instalación gas" → GLP_INSTALACION
- [ ] `test_placa_solar_generic_returns_parent` — "placa solar" → PLACA_SOLAR

### Integration Tests
- [ ] Conversación end-to-end: "placa solar" → pregunta variante → respuesta usuario → cotización correcta
- [ ] Verificar que `question_hint` se usa en la respuesta del agente

---

## Criterios de Aceptación

- [ ] Mensaje "quiero homologar la placa solar" → agente hace pregunta sobre regulador (no cotiza directamente)
- [ ] Mensaje "placa solar con regulador en maletero" → agente selecciona `PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR` directamente (sin preguntar)
- [ ] Mensaje "instalación de gas" → agente pregunta tipo (bombona/depósito/duocontrol)
- [ ] Mensaje "instalación de gas con bombona" → agente selecciona `GLP_KIT_BOMB` directamente
- [ ] Tests pasan con >90% coverage en `element_service.py`
- [ ] No se rompe ningún elemento que funcionaba correctamente (TOLDO_LAT, FAROS_LA, BOLA_REMOLQUE, etc.)

---

## Riesgos y Consideraciones

| Riesgo | Probabilidad | Mitigación |
|--------|-------------|------------|
| `PARENT_SUPERIORITY_RATIO = 1.3` demasiado estricto — deja de seleccionar variantes válidas | Media | Testear con casos reales antes de subir a producción. Ajustar ratio si necesario (1.2–1.5) |
| El `question_hint` del padre no se está usando en el prompt del agente | Baja | Verificar en `presupuesto_mode.py` que `question_hint` llega al LLM |
| Conversaciones activas en Redis con `PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR` ya en estado | Baja | Los cambios de BD afectan solo nuevas identificaciones. El checkpointer Redis preserva state activo |
| `CLARABOYA_PRUEBA` con `is_active=false` no afecta producción | Nula | Confirmar antes de ejecutar. No requiere acción urgente |

---

## Checklist de Verificación Pre-Deploy

- [ ] Ejecutar UPDATEs en staging primero
- [ ] Verificar con query de diagnóstico que overlapping_keywords = 0 para PLACA_SOLAR
- [ ] Correr tests unitarios: `pytest tests/test_element_service.py -v`
- [ ] Test manual de conversación en staging con "placa solar"
- [ ] Test manual de conversación en staging con "placa solar con regulador interior"
- [ ] Confirmar que TOLDO_LAT, FAROS_LA, BOLA_REMOLQUE siguen funcionando
- [ ] Restart del servicio `agent` (invalida cache de Redis de elementos)
- [ ] Verificar logs: debe aparecer `router_evaluating` → `pending_variants` en lugar de selección directa

---

## Notas de Implementación

### Sobre el `question_hint`
El campo `question_hint` existe en BD pero hay que verificar que `presupuesto_mode.py` lo incluye en el contexto del LLM cuando el agente devuelve un elemento padre con variantes. Si no está llegando al LLM, la corrección de datos sola no bastará.

### Sobre la query de diagnóstico post-fix
```sql
-- Verificar que no hay solapamiento después del fix
SELECT 
    parent.code,
    child.code as child_code,
    (
        SELECT array_agg(pk)
        FROM jsonb_array_elements_text(parent.keywords) pk
        WHERE child.keywords @> to_jsonb(pk)
    ) as overlapping_keywords
FROM elements child
JOIN elements parent ON child.parent_element_id = parent.id
JOIN vehicle_categories vc ON child.category_id = vc.id
WHERE vc.slug = 'aseicars-prof'
ORDER BY parent.code;
-- Resultado esperado: overlapping_keywords = NULL para todos
```

### Sobre la invalidación de cache
Tras ejecutar los UPDATEs en BD, el `element_service` cachea elementos en Redis. Es necesario invalidar la cache o reiniciar el agente para que los cambios surtan efecto inmediato.

```bash
docker-compose restart agent
```
