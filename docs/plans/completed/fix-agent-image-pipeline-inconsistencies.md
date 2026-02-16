# Plan: Fix Agent Image Pipeline & Message Ordering Inconsistencies

## Resumen Ejecutivo

El flujo completo del agente desde PRESUPUESTO_MODE → EXPEDIENTE_MODE → recolección de fotos de elementos presenta **6 problemas verificados** contra código fuente. Este plan propone soluciones de raíz (no parches) organizadas en 3 fases.

### Contexto de la Investigación

Se trazaron las rutas de ejecución exactas usando 4 subagentes investigadores que leyeron ~8,000 líneas de código fuente. Cada problema se verificó con números de línea exactos. Algunas hipótesis iniciales se **descartaron** tras verificación (ver sección "Hipótesis Descartadas").

---

## Servicios Afectados

- [x] Agent (`agent/main.py`, `agent/services/image_handling.py`, `agent/modes/presupuesto_mode.py`, `agent/tools/element_data_tools.py`, `agent/tools/image_tools.py`)
- [x] Agent Prompts (`agent/prompts/modes/presupuesto_mode.md`, `agent/prompts/core/07_pricing_rules.md`)
- [ ] API
- [ ] Database
- [ ] Admin Panel
- [ ] Shared

---

## Problemas Verificados (con evidencia)

### P1: Race Condition — Batch Worker envía mensaje DESPUÉS de que "listo" fue procesado

**Gravedad**: ALTA  
**Reproducibilidad**: Cada vez que el usuario dice "listo" como texto puro (sin imagen adjunta)

**Lo que experimenta el usuario**:
1. Dice "listo" → agente procesa y avanza al siguiente paso
2. 2-3 segundos después → llega mensaje: *"He recibido X imagen(es). Cuando hayas enviado todas las fotos, escribe 'listo'."*

**Causa raíz verificada**: Cuando "listo" llega sin imágenes adjuntas:

- `main.py:166` → `image_attachments = []` → NO entra al bloque de imágenes (línea 167)
- `main.py:216` → `reset_batch_counter()` **NUNCA se ejecuta** (está dentro del bloque de imágenes)
- `main.py:265-269` → `reconcile_on_completion()` se ejecuta, pero esta función **NO llama a `reset_batch_counter()`** (verificado: 0 invocaciones en `image_handling.py:487-590`)
- La key Redis `image_batch:{conversation_id}` **persiste**
- El batch worker (`image_handling.py:651`) detecta `elapsed >= 15s` → envía mensaje de confirmación al usuario
- El batch worker **NO adquiere conversation lock** (0 resultados buscando `get_conversation_lock` en `image_handling.py`)
- El batch worker **NO verifica si "listo" ya fue procesado**

**Evidencia de líneas**:
- `main.py:166-167`: Check de image_attachments
- `main.py:215-216`: reset_batch_counter solo si hay imágenes + es completion
- `main.py:265-269`: reconcile_on_completion sin reset
- `image_handling.py:211`: Definición de reset_batch_counter (única)
- `image_handling.py:487-590`: reconcile_on_completion (no contiene llamada a reset)
- `image_handling.py:651`: Check de elapsed en worker
- `image_handling.py:758`: Worker envía mensaje a Chatwoot

---

### P2: Reconciliación de imágenes pierde `element_code` 

**Gravedad**: ALTA  
**Reproducibilidad**: Cuando se reconcilian imágenes con webhooks tardíos

**Lo que experimenta el usuario**: Las imágenes reconciliadas quedan sin `element_code` en la DB (como genéricas en vez de asociadas al elemento).

**Causa raíz verificada**: En `image_handling.py:440,456`:

```python
element_code=None  # Reconciled images lose element context
```

Hay un **comentario explícito** del desarrollador reconociendo el problema. La función `reconcile_conversation_images()` no recibe ni propaga `element_code`. Las imágenes reconciliadas siempre se guardan con `element_code=None`.

**Contraste**: `save_images_silently()` SÍ recibe y propaga `element_code` (línea 286-307). El problema es solo en la reconciliación.

**Nota**: La hipótesis original de que el checkpoint estaba "stale" fue **descartada**. El checkpoint se lee correctamente en la mayoría de los casos. El bug real es que la reconciliación nunca usa `element_code`.

---

### P3: `follow_up_message` duplica contenido del `ai_response`

**Gravedad**: MEDIA  
**Reproducibilidad**: ~90% de interacciones que llegan a fase de imágenes

**Lo que experimenta el usuario**: Recibe la pregunta "¿Quieres abrir expediente?" DOS veces — una en el texto del agente y otra 5s después tras las imágenes.

**Causa raíz verificada**: Es un problema de **diseño del prompt**, no de código:

1. El prompt (`presupuesto_mode.md:209-221`) instruye al LLM a ofrecer opciones A/B en su texto de respuesta
2. El prompt (`presupuesto_mode.md:224-229` y `07_pricing_rules.md:62`) instruye al LLM a pasar `follow_up_message="¿Te gustaría que abramos el expediente?"` como parámetro a `enviar_imagenes_ejemplo()`
3. El LLM obedece ambas instrucciones → genera la pregunta en `ai_response` Y en `follow_up_message`

**Flujo de envío** (`main.py`):
- Línea 366: Envía `ai_response` (ya contiene la pregunta)
- Línea 410: Envía imágenes
- Línea 422-428: Espera 5s → envía `follow_up_message` (repite la pregunta)

El LLM no tiene consciencia de que son dos canales de entrega separados.

---

### P4: `confirmar_fotos_elemento()` no verifica que existan fotos

**Gravedad**: ALTA  
**Reproducibilidad**: Cuando el usuario dice "listo" antes de que las fotos se procesen por webhook

**Lo que experimenta el usuario**: El agente acepta las fotos como "confirmadas" cuando podrían no haberse guardado aún en la DB (por latencia de webhook).

**Causa raíz verificada**: La función `confirmar_fotos_elemento()` (`element_data_tools.py:742-975`):
- NO consulta `CaseImage` para verificar cuántas fotos hay del elemento
- `_get_case_image_count()` (línea 1197) existe y se usa en `confirmar_documentacion_base()` (línea 1327) pero **NO** en `confirmar_fotos_elemento()`
- No hay en todo el codebase una query que filtre `CaseImage` por `element_code` específico

---

### P5: Reconciliación bloquea respuesta al usuario 5-15 segundos

**Gravedad**: MEDIA  
**Reproducibilidad**: Cada vez que el usuario dice "listo"

**Causa raíz verificada**: `reconcile_on_completion()` (`image_handling.py:535,558`) contiene:
- `await asyncio.sleep(5)` — línea 535, delay obligatorio
- `await asyncio.sleep(10)` — línea 558, condicional si primera reconciliación encontró imágenes
- Total posible: **15 segundos** de delay antes de invocar el grafo (`main.py:306`)

Estos delays **ceden el event loop**, lo cual agrava P1 (el batch worker puede ejecutar durante estos sleeps).

---

### P6: Auto-creación de case sin validación element→category

**Gravedad**: BAJA  
**Reproducibilidad**: Edge case, raramente en producción

**Causa raíz verificada**: `expediente_mode.py:479-498` — auto-create case toma `element_codes` del `mode_context` sin validar que pertenezcan a la categoría actual.

---

## Hipótesis Descartadas

### ❌ "El checkpoint está stale y element_code viene como None"
**Verificación**: El checkpoint se lee correctamente en `main.py:170` ANTES de invocar el grafo. Refleja el estado del último turno completado. En el flujo normal de `collect_element_data`, el checkpoint tiene el `expediente_sub_mode` y `current_element_index` correctos. El bug de `element_code=None` no está en el checkpoint stale sino en la reconciliación que no propaga `element_code`.

### ❌ "Las imágenes se guardan como documentación base"
**Verificación**: `save_images_silently()` siempre guarda con `image_type="user_upload"` (línea 308). No existe el valor `"base_documentation"`. Las imágenes con `element_code=None` quedan como "genéricas", no como "documentación base". La confusión del usuario puede venir del LLM mencionando "documentación base" durante la transición de sub-modo.

---

## Tareas por Servicio

### Fase 1: Fixes Críticos (P1 + P4) → agent-dev

**Objetivo**: Eliminar la race condition del batch worker y la validación faltante de fotos.

#### Tarea 1.1: Fix race condition del batch worker

**Archivos**: `agent/main.py`  
**Cambio**: Añadir `reset_batch_counter()` en el path de "listo" sin imágenes

```python
# main.py, línea ~265 - CAMBIAR DE:
if user_message and is_completion_message(user_message):
    checkpointer = get_redis_checkpointer()
    await reconcile_on_completion(
        redis_client, checkpointer, conversation_id,
    )

# A:
if user_message and is_completion_message(user_message):
    # Reset batch counter FIRST to prevent worker from sending stale confirmation
    await reset_batch_counter(redis_client, conversation_id)
    checkpointer = get_redis_checkpointer()
    await reconcile_on_completion(
        redis_client, checkpointer, conversation_id,
    )
```

**Por qué ANTES**: El `reset_batch_counter()` debe ejecutarse ANTES de `reconcile_on_completion()` porque esta última contiene `asyncio.sleep(5)` que cede el event loop al batch worker. Si el reset viene después, la ventana de race condition persiste.

**Criterio de aceptación**: Tras decir "listo", el usuario NO recibe el mensaje "He recibido X imagen(es). Escribe 'listo'".

#### Tarea 1.2: Validar existencia de fotos en `confirmar_fotos_elemento()`

**Archivos**: `agent/tools/element_data_tools.py`  
**Cambio**: Añadir verificación de image count filtrando por `element_code`

Crear función `_get_element_image_count(case_id, element_code)` que haga:
```python
select(func.count()).select_from(CaseImage).where(
    CaseImage.case_id == uuid.UUID(case_id),
    CaseImage.element_code == element_code
)
```

Llamarla desde `confirmar_fotos_elemento()` antes de confirmar:
```python
element_images = await _get_element_image_count(case_id, element_code)
if element_images == 0:
    return {
        "success": False,
        "message": f"No he recibido fotos para {element_code}. Envía las fotos y escribe 'listo' cuando termines.",
    }
```

**Patrón a seguir**: `confirmar_documentacion_base()` (línea 1327) ya implementa este patrón con `_get_case_image_count()` global.

**Criterio de aceptación**: Si el usuario dice "listo" sin haber enviado fotos del elemento actual, el agente pide las fotos de nuevo.

---

### Fase 2: Mejoras de UX (P3 + P5) → agent-dev

**Objetivo**: Eliminar mensajes duplicados y reducir tiempos de espera.

#### Tarea 2.1: Eliminar duplicación de follow_up_message

**Archivos**: 
- `agent/prompts/modes/presupuesto_mode.md`
- `agent/prompts/core/07_pricing_rules.md`
- `agent/main.py` (guardia de seguridad)

**Cambio en prompts**: Reestructurar la instrucción para que el LLM:
1. En su `ai_response` incluya SOLO: precio + warnings + "Te envío fotos de ejemplo:" (sin opciones A/B)
2. El `follow_up_message` se encargue de: "Ahora tienes dos opciones: A) ... B) ..."

Cambiar en `presupuesto_mode.md` la sección de Paso 5 (líneas 209-236) para separar claramente qué va en cada canal:
```
### Paso 5: Enviar imágenes de ejemplo
1. Tu mensaje de texto (ai_response) debe TERMINAR en "Te envío las fotos de ejemplo:" 
   NO incluyas opciones A/B aquí.
2. Llama: enviar_imagenes_ejemplo(
     tipo="presupuesto",
     follow_up_message="Ahora tienes dos opciones:\nA) ¿Quieres que te muestre más detalles?\nB) ¿Quieres abrir el expediente?"
   )
3. El follow_up se enviará DESPUÉS de las imágenes automáticamente.
```

**Guardia de seguridad en main.py** (línea ~421): Si `ai_response` contiene keywords del `follow_up_message` (ej: ambos contienen "expediente" + "?"), suprimir el `follow_up`:

```python
if follow_up:
    # Deduplicate: skip follow_up if ai_response already contains similar question
    ai_lower = ai_response_clean.lower()
    fu_lower = follow_up.lower()
    overlap_keywords = ["expediente", "opción", "opcion"]
    has_overlap = any(kw in ai_lower and kw in fu_lower for kw in overlap_keywords)
    if has_overlap and "?" in ai_lower:
        logger.info("follow_up suppressed: ai_response already contains similar content")
    else:
        await asyncio.sleep(5.0)
        follow_up_clean = strip_markdown_for_whatsapp(follow_up)
        await chatwoot.send_message(...)
```

**Criterio de aceptación**: El usuario recibe: texto → imágenes → pregunta post-imágenes. Sin contenido repetido.

#### Tarea 2.2: Hacer reconciliación no-bloqueante

**Archivos**: `agent/main.py`  
**Cambio**: Ejecutar `reconcile_on_completion()` como background task en vez de bloqueante

```python
# main.py, línea ~265 - CAMBIAR DE:
if user_message and is_completion_message(user_message):
    await reset_batch_counter(redis_client, conversation_id)
    checkpointer = get_redis_checkpointer()
    await reconcile_on_completion(redis_client, checkpointer, conversation_id)

# A:
if user_message and is_completion_message(user_message):
    await reset_batch_counter(redis_client, conversation_id)
    # Run reconciliation in background — don't block the response
    checkpointer = get_redis_checkpointer()
    asyncio.create_task(
        _safe_reconcile(redis_client, checkpointer, conversation_id)
    )
```

Con wrapper seguro:
```python
async def _safe_reconcile(redis_client, checkpointer, conversation_id):
    try:
        await reconcile_on_completion(redis_client, checkpointer, conversation_id)
    except Exception as e:
        logger.error(f"Background reconciliation failed: {e}", exc_info=True)
```

**Trade-off**: Las imágenes reconciliadas podrían llegar a la DB DESPUÉS de que el grafo ya procesó "listo". Pero dado que la reconciliación es una red de seguridad (las imágenes ya deberían estar guardadas por `save_images_silently`), esto es aceptable.

**Criterio de aceptación**: El usuario recibe respuesta inmediata al decir "listo" (sin delay de 5-15s).

---

### Fase 3: Mejora de integridad de datos (P2) → agent-dev

**Objetivo**: Propagar element_code a la reconciliación.

#### Tarea 3.1: Pasar element_code a reconciliación de imágenes

**Archivos**: `agent/services/image_handling.py`  
**Cambio**: 

1. Modificar `reconcile_conversation_images()` para aceptar `element_code` como parámetro
2. Propagarlo a `save_images_silently()` interno (si lo usa) o directamente al `CaseImage` que crea
3. En los puntos de llamada (batch worker línea 691, reconcile_on_completion), obtener `element_code` del `mode_context`

Flujo de propagación:
```
batch worker (image_handling.py:691) 
  → lee mode_context del checkpoint (ya lo hace en línea 675-678)
  → extrae element_code via get_current_element_code(mode_context)
  → pasa a reconcile_conversation_images(..., element_code=element_code)
    → crea CaseImage con element_code correcto (en vez de None)
```

**Criterio de aceptación**: Imágenes reconciliadas tienen `element_code` correcto en la DB.

---

## Dependencias entre Tareas

```
Fase 1 (Crítica):
  1.1 (batch race condition) → SIN dependencias
  1.2 (validar fotos)        → SIN dependencias

Fase 2 (UX):
  2.1 (follow_up duplicado)  → SIN dependencias  
  2.2 (reconciliación async) → DEPENDE de 1.1 (el reset debe ejecutarse ANTES)

Fase 3 (Integridad):
  3.1 (element_code reconciliación) → SIN dependencias
```

Todas las tareas de Fase 1 pueden ejecutarse en paralelo. Tarea 2.2 depende de que 1.1 esté completa.

---

## Tests Requeridos

### Tests unitarios (agent-dev + qa-dev)

- [ ] **test_reset_batch_on_listo_text_only**: Enviar "listo" sin imágenes → verificar que batch counter se borra de Redis ANTES de reconciliación
- [ ] **test_batch_worker_skips_reset_key**: Batch worker no envía mensaje si la key fue borrada
- [ ] **test_element_image_count_filter**: `_get_element_image_count(case_id, "SUBCHASIS")` cuenta solo imágenes con ese element_code
- [ ] **test_confirmar_fotos_sin_fotos**: `confirmar_fotos_elemento()` retorna error si 0 fotos del elemento en DB
- [ ] **test_confirmar_fotos_con_fotos**: `confirmar_fotos_elemento()` retorna success si >= 1 foto del elemento
- [ ] **test_reconcile_propagates_element_code**: Imágenes reconciliadas tienen element_code no-None
- [ ] **test_follow_up_suppressed_on_overlap**: Si ai_response contiene "expediente?", follow_up se suprime

### Tests de integración (qa-dev)

- [ ] **test_full_flow_subchasis**: Flujo completo: presupuesto → confirmar → expediente → enviar fotos → listo → datos técnicos. Sin mensajes duplicados ni desordenados.
- [ ] **test_batch_worker_race_condition**: Simular timing de "listo" justo cuando batch timeout expira → no debe haber mensaje duplicado del worker

---

## Criterios de Aceptación Globales

- [ ] El usuario NUNCA recibe "Escribe 'listo'" DESPUÉS de haber escrito "listo"
- [ ] Las fotos de elementos se guardan con `element_code` correcto en TODOS los paths (directo y reconciliación)
- [ ] El usuario no recibe la misma pregunta dos veces (ai_response vs follow_up)
- [ ] `confirmar_fotos_elemento()` verifica que existan fotos del elemento antes de confirmar
- [ ] El delay entre decir "listo" y recibir respuesta es < 5 segundos (no 15-20)
- [ ] Todos los tests pasan con coverage > 90% en archivos modificados

---

## Checklist de Verificación Pre-Deploy

- [ ] Tests unitarios pasan (pytest)
- [ ] Sin regresiones en flujo de presupuesto (test manual con conversación completa)
- [ ] Sin regresiones en flujo de expediente (test manual: fotos → listo → datos)
- [ ] Logs verificados: no aparece "Sending batch confirmation" después de "listo" procesado
- [ ] Redis keys se limpian correctamente (no quedan `image_batch:*` huérfanas)

---

## Estimación de Esfuerzo

| Fase | Tarea | Complejidad | Estimación |
|------|-------|-------------|------------|
| 1 | 1.1 Reset batch counter | Baja | 30 min |
| 1 | 1.2 Validar fotos elemento | Baja-Media | 1h |
| 2 | 2.1 Fix follow_up duplicado | Media | 2h (prompts + guardia) |
| 2 | 2.2 Reconciliación async | Media | 1h |
| 3 | 3.1 Element_code en reconciliación | Media | 2h |
| - | Tests | Media | 3h |
| **Total** | | | **~9.5h** |

---

## Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Fix de prompt no es respetado por LLM | Media | Bajo | Guardia en código (Tarea 2.1) como safety net |
| Reconciliación async pierde imágenes | Baja | Medio | save_images_silently ya las guarda; reconciliación es backup |
| Tests flaky por timing | Media | Bajo | Usar mocks para asyncio.sleep y Redis |

---

## Resumen de Archivos a Modificar

| Archivo | Tareas | Tipo de cambio |
|---------|--------|----------------|
| `agent/main.py` | 1.1, 2.1, 2.2 | Lógica de procesamiento |
| `agent/tools/element_data_tools.py` | 1.2 | Nueva función + validación |
| `agent/services/image_handling.py` | 3.1 | Propagación de parámetro |
| `agent/prompts/modes/presupuesto_mode.md` | 2.1 | Reestructuración de instrucciones |
| `agent/prompts/core/07_pricing_rules.md` | 2.1 | Clarificación de instrucciones |
| `tests/` (nuevos) | ALL | 7 unit tests + 2 integration tests |
