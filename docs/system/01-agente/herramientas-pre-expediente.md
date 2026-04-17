---
titulo: Herramientas disponibles en PRE_EXPEDIENTE
ambito: pre-expediente
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Herramientas disponibles en PRE_EXPEDIENTE

## Resumen

El agente en modo PRE_EXPEDIENTE tiene acceso a **11 herramientas** (tools). Cada una hace una cosa concreta y devuelve al bot información estructurada para que tome la siguiente decisión. Las herramientas son llamadas por el LLM (no por el usuario) según el contexto.

Algunas herramientas están **condicionadas**: un sistema de 4 puertas (gates) las puede retirar del set disponible según el state actual. Por ejemplo: si hay una variante pendiente, el bot solo ve 2 herramientas (resolver variante + escalar).

## Escenarios

### Bot identifica un elemento simple
- CUANDO el cliente describe qué quiere homologar
- ENTONCES el bot usa `identificar_y_resolver_elementos` con la descripción libre.

### Bot resuelve una variante
- CUANDO existe una pregunta de variante pendiente y el cliente responde
- ENTONCES el bot usa `seleccionar_variante_por_respuesta` — **nunca** re-usa `identificar_y_resolver_elementos` en este caso (doble regla: código lo fuerza, prompt lo dice).

### Bot calcula un presupuesto
- CUANDO se han identificado todos los elementos y resuelto todas las variantes
- ENTONCES el bot usa `calcular_tarifa_con_elementos` con `skip_validation=True` — no vuelve a validar cosas ya validadas por identificación.

### Bot confirma y transiciona a EXPEDIENTE
- CUANDO el cliente acepta abrir el expediente
- ENTONCES el bot usa `confirmar_presupuesto`, que valida preconditions (precio comunicado, tarifa presente) y devuelve la señal de transición.

## Reglas duras

- **Nunca re-identificar en respuesta a variante**. Usar `seleccionar_variante_por_respuesta`, no `identificar_y_resolver_elementos`.
- **Siempre `skip_validation=True`** al calcular tarifa después de haber identificado. Ya está validado.
- **`enviar_imagenes_ejemplo` solo si hay tarifa calculada** con URLs (GATE 5 lo retira si no).
- **`confirmar_presupuesto` falla si preconditions no se cumplen**: precio comunicado y tarifa presente.
- Cambios de state que hacen los tools: siempre vía el dict `_state_update` devuelto. **Nunca** mutación directa de state. (Canal canónico ADR-005.)

## Catálogo completo

### 1. `identificar_y_resolver_elementos`
**Qué hace**: Parsea la descripción libre del cliente y devuelve (a) elementos listos para presupuestar, (b) elementos con variantes pendientes que requieren pregunta, (c) términos no reconocidos.

**Cuándo se usa**: Primera identificación o adición de nuevos elementos después del presupuesto.

**Mapeo**: `agent/tools/element_tools.py:1267`

### 2. `seleccionar_variante_por_respuesta`
**Qué hace**: Dado un código base de elemento y una respuesta del cliente, resuelve la variante correcta y actualiza `pending_variants`.

**Cuándo se usa**: Exclusivamente cuando hay variante pendiente y el cliente ha respondido. Soporta 3 formatos de retorno: single, multi-select, multi-unit allocation.

**Mapeo**: `agent/tools/element_tools.py:151`

### 3. `calcular_tarifa_con_elementos`
**Qué hace**: Dado un conjunto de códigos de elemento y una categoría, calcula el precio exacto con warnings, inclusiones, y URLs de imágenes ejemplo.

**Cuándo se usa**: Cuando todos los elementos están identificados y variantes resueltas. Siempre con `skip_validation=True`.

**Forma del retorno (clave interna)**: La documentación de cada elemento se devuelve bajo la clave `_documentacion` (prefijo `_` = uso interno). El LLM no debe listar esta documentación en su respuesta — ya fue comunicada en la fase de identificación. El consumidor interno de inicio de expediente la lee desde `_documentacion`. (Clave antigua `documentacion` sin prefijo sigue siendo reconocida como fallback para state checkpointados previos.)

**Mapeo**: `agent/tools/element_tools.py:619`

### 4. `enviar_imagenes_ejemplo`
**Qué hace**: Encola el envío de imágenes ejemplo al cliente (tipo `presupuesto` o `elemento`). El envío real pasa por Chatwoot después.

**Cuándo se usa**: Solo cuando el cliente las pide explícitamente, **después** del presupuesto. GATE 5 la retira si no hay tarifa con URLs.

**Mapeo**: `agent/tools/image_tools.py:113`

### 5. `confirmar_presupuesto`
**Qué hace**: Valida preconditions (precio comunicado, tarifa presente), y si pasan devuelve un `_state_update._transition_to: "EXPEDIENTE_MODE"`. Además escribe `shared_context["warnings_acknowledged"] = True` vía `_state_update["shared_context"]`.

**Nota de tipo**: `warnings_acknowledged` es un **campo tipado** declarado en `SharedContext` (`agent/state/context_models.py`) como `warnings_acknowledged: bool`. No es una clave libre de dict — tiene anotación explícita en el TypedDict. Esto garantiza que mypy/pyright validen asignaciones y que la documentación del esquema sea precisa.

**Propósito**: señaliza que el cliente confirmó conocer las advertencias y quiere abrir expediente. Gracias a esto, los warnings comunicados en PRE_EXPEDIENTE NO se repiten al entrar a EXPEDIENTE_MODE.

**Cuándo se usa**: Cliente dice "sí, empezamos" o equivalente después de ver precio/fotos.

**Mapeo**: `agent/tools/transition_tools.py:24-116`

### 6. `listar_categorias`
**Qué hace**: Devuelve la lista de categorías de vehículos activas (coches, motos, etc.).

**Cuándo se usa**: Cuando el bot necesita orientar al cliente sobre qué categorías existen, o cuando no infiere la categoría del mensaje.

**Mapeo**: `agent/tools/tarifa_tools.py:39`

### 7. `listar_elementos`
**Qué hace**: Devuelve la lista de elementos homologables para una categoría concreta.

**Cuándo se usa**: Cuando el cliente pregunta "¿qué se puede homologar en [categoría]?" o equivalente.

**Mapeo**: `agent/tools/element_tools.py:95`

### 8. `obtener_servicios_adicionales`
**Qué hace**: Devuelve servicios adicionales ofrecidos (extras al presupuesto base).

**Cuándo se usa**: Consulta informativa del cliente o cuando el bot quiere sugerir extras relevantes.

**Mapeo**: `agent/tools/tarifa_tools.py:164`

### 9. `identificar_tipo_vehiculo`
**Qué hace**: Clasifica el vehículo a partir de una descripción libre de marca/modelo.

**Cuándo se usa**: Cuando el cliente menciona marca/modelo y el bot necesita confirmar la categoría.

**Mapeo**: `agent/tools/vehicle_tools.py:25`

### 10. `listar_tarifas`
**Qué hace**: Dado el slug de una categoría de vehículo y el tipo de cliente (`particular` / `professional`), devuelve la lista de tiers de precio disponibles con nombre, precio sin IVA, condiciones de aplicación y keywords de clasificación.

**Cuándo se usa**: Cliente pregunta "¿qué tipos de homologación hay para motos?" o "¿cuánto cuesta el servicio premium para autocaravanas?". También útil cuando el bot quiere orientar al cliente sobre opciones antes de identificar elementos específicos.

**Argumentos**: `categoria_vehiculo` (slug exacto: `"aseicars"`, `"motos"`) · `tipo_cliente` (default `"particular"`)

**Mapeo**: `agent/tools/tarifa_tools.py:96`

### 11. `escalar_a_humano`
**Qué hace**: Señala transición a modo ESCALATION. El operador humano toma el hilo en Chatwoot.

**Cuándo se usa**: Cliente lo pide, bot detecta situación fuera de scope, o se agotan los intentos de resolver ambigüedad.

**Mapeo**: `agent/tools/shared_tools.py:56`

## Sistema de 4 gates (filtrado dinámico)

El método `_get_tools_with_filtering` en `pre_expediente_mode.py:372-440` aplica filtros por prioridad:

| Gate | Condición | Efecto |
|------|-----------|--------|
| **GATE 1** (highest) | Hay variantes pendientes (`pending_variants` con status != resolved) | Solo se exponen: `seleccionar_variante_por_respuesta` + `escalar_a_humano`. El resto se retira. |
| **GATE 2** | Variante resuelta recientemente + tarifa no calculada aún | Se prioriza `calcular_tarifa_con_elementos` en el set |
| **GATE 3** | Vehículo no identificado y cliente describe marca/modelo | Se prioriza `identificar_tipo_vehiculo` |
| **GATE 5** | No hay tarifa con URLs de imágenes | Se retira `enviar_imagenes_ejemplo` del set |

(Nota: GATE 4 en el código actual es placeholder; se mantiene la numeración histórica.)

## Mapeo al código

- `agent/modes/pre_expediente_mode.py:372-440` — `_get_tools_with_filtering` con los gates
- `agent/modes/pre_expediente_mode.py:933-977` — `_get_pre_expediente_tools` base set
- `agent/modes/pre_expediente_mode.py:395-405` — GATE 1 (variant lock)
- `agent/modes/pre_expediente_mode.py:410-422` — GATE 5 (images precondition)
- `agent/tools/tool_manager.py` — registro global de tools
- `agent/tools/schemas.py` — schemas Pydantic de inputs/outputs de tools
- `agent/tools/types.py` — tipos compartidos entre tools
- Archivos por tool: ver "Catálogo completo" arriba

## Fuera de alcance

- `agent/tools/case_tools.py` — tools de EXPEDIENTE (creación/hidratación de caso)
- `agent/tools/element_data_tools.py` — recolección de datos de elemento, exclusiva de EXPEDIENTE
- `agent/tools/draft_quote_service.py` — servicio interno de DraftQuote (tocar solo desde el modo, no como tool)
- Cambiar la lógica de gates sin cambiar también el flujo en `flujo-pre-expediente.md` — los gates son parte del flujo, no una cosa aparte
