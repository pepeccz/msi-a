---
titulo: Flujo PRE_EXPEDIENTE
ambito: agente
ultima_verificacion_commit:
ultima_verificacion_fecha: 2026-04-17
---

# Flujo PRE_EXPEDIENTE

## Resumen

`PRE_EXPEDIENTE` es el modo dominante del agente (~90% del tráfico). Cubre toda la conversación **previa** a que el cliente se comprometa a abrir un expediente formal: saludo, identificación de qué quiere homologar, orientación sobre documentación, presupuesto, envío de ejemplos de fotos, y confirmación.

Internamente tiene **tres fases resueltas por state** (no por enum): **DISCOVERY** (sin elementos identificados todavía), **PRICING** (elementos identificados, precio no comunicado), y **POST_PRICE** (precio ya comunicado, cliente decidiendo). La fase se deriva automáticamente del contenido de `mode_context` y determina qué prompt de modo se carga en cada turno.

La salida de este modo es siempre o bien una transición a `EXPEDIENTE` (cliente acepta), o bien a `ESCALATION` (se pide intervención humana).

## Escenarios

### 1. Primer mensaje general
- CUANDO el cliente envía su primer mensaje con una pregunta genérica (ej. "Hola, ¿qué es la homologación?")
- ENTONCES el bot responde con "¡Hola! Soy el asistente con IA de MSI Automotive" (identificación obligatoria EU AI Act), explica brevemente en 1-2 frases, y cierra con la CTA 1: *"¿Quieres que te ayude con alguna homologación?"*

### 2. Cliente describe un elemento sin variantes
- CUANDO el cliente describe lo que quiere homologar y el elemento no tiene variantes (ej. "Quiero homologar un escape de moto")
- ENTONCES el bot identifica el elemento, presenta la documentación requerida en formato conciso, y cierra con la CTA 3: *"¿Te muestro ejemplos de cómo deben ser las fotos o te calculo el presupuesto?"*

### 3. Cliente describe un elemento con variantes
- CUANDO el cliente describe algo que tiene variantes (ej. "Suspensión" → delantera/trasera)
- ENTONCES el bot identifica el elemento, detecta que hay variantes pendientes, presenta las opciones, y hace la pregunta. Mientras haya variantes pendientes, el bot **solo puede** ofrecer resolver la variante o escalar — cualquier otra conversación queda bloqueada.

### 4. Cliente responde a pregunta de variante
- CUANDO el bot tiene una variante pendiente y el cliente responde con una opción válida (ej. "trasera" con confianza ≥ 0.7)
- ENTONCES el bot resuelve la variante, el bloqueo de herramientas se levanta, y el bot puede continuar: si no quedan variantes pendientes, procede a calcular el presupuesto o preguntar.

### 5. Respuesta ambigua a variante
- CUANDO el cliente responde a una pregunta de variante con algo ambiguo ("una de las dos", confianza < 0.7)
- ENTONCES el bot **no** aplica la selección (hay umbral duro de 0.7), reformula la pregunta mostrando las opciones claramente. Tras 2 intentos fallidos, ofrece escalado humano.

### 6. Cálculo de presupuesto
- CUANDO todas las variantes están resueltas y el cliente pide precio (o el bot infiere que es el momento)
- ENTONCES el bot llama a la herramienta de cálculo con `skip_validation=True`, recibe el precio y las URLs de imágenes de ejemplo, y comunica el presupuesto en formato: *"El presupuesto es de [X]€ +IVA. [Warnings opcionales]"*. Cierra con la CTA 4: *"¿Te enseño ejemplos de las fotos que necesitaremos o abrimos el expediente directamente?"*

### 7. Cliente pide ver fotos ejemplo
- CUANDO el cliente, ya con el precio comunicado, pide ver fotos de ejemplo ("muéstrame fotos", "ejemplos")
- ENTONCES el bot llama a la herramienta de envío de imágenes (tipo `presupuesto`), las imágenes se envían por WhatsApp **antes** del mensaje de texto, y el mensaje de texto cierra con la CTA 5: *"¿Empezamos con el expediente?"*

### 7.bis. Enforcement determinístico de CTA 5 post-imágenes
- CUANDO en un turno se ejecutó exitosamente `enviar_imagenes_ejemplo` (o las imágenes ya se habían enviado en un turno anterior) Y `precio_comunicado=True` Y `mode_context.imagenes_enviadas_codigos` contiene al menos un código
- ENTONCES el texto final del turno emitido al cliente DEBE terminar exactamente con el literal de CTA 5 (*"¿Empezamos con el expediente?"*). Queda PROHIBIDO que el turno cierre con:
  - Una reformulación de la CTA 5 (ej. *"¿Quieres que abramos el expediente?"*).
  - La CTA 5 acompañada de alternativas o bifurcaciones (ej. *"¿Empezamos con el expediente o prefieres que te explique cómo tienen que ser las fotos?"*).
  - Una CTA distinta (CTA 1, 2, 3 o 4) aunque sea textualmente canónica.
  - Una pregunta abierta sin CTA.
- La garantía NO puede depender únicamente del prompt. Debe existir un enforcement post-tool-loop en código: al finalizar el turno, si se cumplen las precondiciones de esta regla y el texto saliente no termina con la CTA 5 canónica, el mode node **anexa** la CTA 5 al final del texto generado por el LLM (no lo sustituye) antes de enviarlo a Chatwoot. El texto del LLM normalmente incluye información útil (resumen de precio, advertencias, contexto); se preserva intacto y sólo se fuerza el cierre canónico. Caso exótico: si el LLM produjo texto vacío o solo whitespace, el enforcement emite la CTA 5 como contenido único del turno. El comportamiento observable es: el último `ai_response` del turno contiene la cadena exacta de CTA 5 como cierre y no contiene otras preguntas posteriores.

### 8. Cliente añade un elemento después del precio
- CUANDO el cliente, tras ver un presupuesto, pide añadir otro elemento (ej. "también quiero homologar el faro")
- ENTONCES el bot identifica el nuevo elemento, **añade** el código a los existentes (no reemplaza), recalcula el presupuesto con todos los elementos, comunica la diferencia de precio (*"Al añadir el faro, sube de 410€ a 520€ +IVA"*), y refresca la CTA 4.

### 9. Cliente confirma y transiciona a EXPEDIENTE
- CUANDO el cliente, tras el flujo completo (presupuesto visto, opcionalmente fotos vistas), responde afirmativamente a la CTA 5
- ENTONCES el bot llama a `confirmar_presupuesto`, la herramienta valida preconditions (precio comunicado + presupuesto calculado), escribe `shared_context.warnings_acknowledged = True` (los warnings ya se comunicaron en PRE, no hay que repetirlos en EXPEDIENTE), devuelve un transition a EXPEDIENTE, y el próximo turno ya está en modo EXPEDIENTE con su primera petición formal de datos.

### 10. Recuperación de sesión vía DraftQuote
- CUANDO un cliente vuelve horas después y pregunta sobre el presupuesto previo ("¿cuánto era?")
- ENTONCES el bot carga automáticamente el DraftQuote de la sesión previa, el mode_context se rehidrata con el precio, categoría y elementos, y el bot responde directamente sin recalcular: *"Era [X]€ +IVA por [elementos]. ¿Abrimos el expediente o prefieres cambiar algo?"*

### 11. Error en identificación de elemento
- CUANDO el cliente describe algo que el sistema no puede mapear a un elemento concreto (ej. "ese aparato rojo del coche")
- ENTONCES el bot responde con una reformulación pidiendo más contexto — **no** pollute el state con elementos incorrectos. El modo sigue en DISCOVERY.

### 12. Escalado tras 3 intentos fallidos de variante
- CUANDO tras 2 reformulaciones de pregunta de variante el cliente sigue sin resolver, O cuando se acumulan 3+ errores consecutivos en el modo
- ENTONCES el bot ofrece escalado explícito: *"¿Prefieres que te ponga en contacto con alguien del equipo?"*. Si el cliente acepta, llama a `escalar_a_humano` y transiciona a ESCALATION.

## Reglas duras

1. **Precio antes que imágenes**. NUNCA enviar imágenes de ejemplo sin haber comunicado el precio primero. Esto se enforce tanto en prompts (`core.md`) como en código (GATE 5 en `pre_expediente_mode.py` remueve la tool `enviar_imagenes_ejemplo` del toolset si no hay tarifa calculada con URLs).

2. **5 CTAs canónicas únicas**. El bot usa **solamente** una de las 5 CTAs definidas textualmente en los prompts. Prohibido inventar, adaptar, reformular o mezclar. Las 5 CTAs:
   - CTA 1 (pre-discovery, sin elementos): *"¿Quieres que te ayude con alguna homologación?"*
   - CTA 2 (post-exploración): *"¿Te interesa alguno? Puedo darte el precio exacto."*
   - CTA 3 (elementos identificados, sin precio): *"¿Te muestro ejemplos de cómo deben ser las fotos o te calculo el presupuesto?"*
   - CTA 4 (precio recién calculado): *"¿Te enseño ejemplos de las fotos que necesitaremos o abrimos el expediente directamente?"*
   - CTA 5 (post-imágenes): *"¿Empezamos con el expediente?"*

3. **Identidad en primer turno obligatoria**. La frase "¡Hola! Soy el asistente con IA de MSI Automotive" aparece exactamente una vez al principio del primer mensaje al cliente. Un guard en `main.py` detecta y previene duplicaciones.

4. **Bloqueo de variante pendiente**. Cuando hay una variante sin resolver, las únicas herramientas disponibles son `seleccionar_variante_por_respuesta` y `escalar_a_humano`. El bot no puede identificar nuevos elementos, calcular tarifas, ni enviar imágenes hasta resolver la variante.

5. **Merge aditivo de elementos**. Cuando el cliente añade elementos tras ya tener algunos identificados, los códigos se fusionan (unión), no se reemplazan. Esto permite presupuestos acumulativos.

6. **Tarifa calculada = fuente de verdad de códigos**. Después de calcular una tarifa, los códigos en `element_codes` se sincronizan desde la respuesta del tool (no se mantienen los de entrada). Esto garantiza normalización.

7. **Umbral de confianza de variante = 0.7**. Respuestas ambiguas con confianza < 0.7 no aplican (excepto en modo multi-select explícito). Se reformula la pregunta.

8. **`precio_comunicado` se setea DESPUÉS del tool loop**. No lo setea la tool: lo setea el mode node al finalizar el turno, solo si `calcular_tarifa` fue llamada en ese turno. Esto evita falsos positivos cuando el LLM responde preguntas random con tarifa antigua en contexto.

9. **CTA 5 es determinística post-imágenes (anexar, no sustituir)**. La selección de CTA no se delega al LLM cuando ya hay imágenes enviadas y precio comunicado. El mode node, tras el tool loop, inspecciona `mode_context.imagenes_enviadas_codigos` y `precio_comunicado`: si ambos son truthy, garantiza que el texto saliente termine con CTA 5 exacta **anexándola al final del texto del LLM, no sustituyéndolo**. El texto previo del LLM (precio, advertencias, contexto útil) se preserva; sólo se fuerza el cierre canónico. Excepción: si el LLM produjo texto vacío o sólo whitespace, el enforcement emite la CTA 5 como contenido único del turno. Esta regla convierte el cierre post-imágenes en un invariante del turno, no en una sugerencia de prompt.

## Mapeo al código

### Modo principal
- `agent/modes/pre_expediente_mode.py:282-562` — clase `PreExpedienteModeNode`, entry point `_process_with_tool_loop`, max tokens = 3000
- `agent/modes/pre_expediente_mode.py:372-440` — `_get_tools_with_filtering`, sistema de 4 GATES de filtrado de herramientas
- `agent/modes/pre_expediente_mode.py:551-561` — setter de `precio_comunicado` post-loop
- `agent/modes/pre_expediente_mode.py` (post-loop, mismo bloque que setea `precio_comunicado`) — enforcement determinístico de CTA 5: cuando `precio_comunicado=True` y `imagenes_enviadas_codigos` tiene códigos, si el `ai_response` del LLM no termina ya con la CTA 5 canónica, **anexarla** al final preservando el texto previo (no sustituir). Si el `ai_response` está vacío o sólo whitespace, emitir la CTA 5 como contenido único. Observable en tests: `turn.ai_response.rstrip().endswith("¿Empezamos con el expediente?")` cuando las precondiciones se cumplen, y el texto previo del LLM (si existió y no era vacío) sigue presente antes de la CTA 5.
- `agent/modes/base_mode.py` — `BaseModeNode`, lógica compartida de tool loop y error counter

### Entrada al modo
- `agent/router/intent_router.py:36-65` — clasificador híbrido keyword + LLM
- `agent/graph/conversation_graph.py` — conditional edges hacia `NODE_PRE_EXPEDIENTE`

### State
- `agent/state/conversation_state.py:251-306` — `ModeContextData` con campos: `categoria_slug`, `element_codes`, `pending_variants`, `tarifa_calculada`, `precio_comunicado`, `imagenes_enviadas_codigos`, `elementos_confirmados`, `vehiculo`, `_client_type`, `_is_first_interaction`

### Prompts (ver también [`../../prompts/pre-expediente.md`](../../prompts/pre-expediente.md))
- `agent/prompts/core.md` — identidad, voz, reglas transversales (siempre cargado)
- `agent/prompts/modes/pre_expediente_discovery.md` — fase DISCOVERY
- `agent/prompts/modes/pre_expediente_pricing.md` — fase PRICING
- `agent/prompts/modes/pre_expediente_post_price.md` — fase POST_PRICE
- `agent/prompts/loader.py:107-172` — función `assemble_system_prompt` y `_resolve_mode_key` que selecciona la fase

### Herramientas (ver también [`../../herramientas/pre-expediente.md`](../../herramientas/pre-expediente.md))
- `agent/tools/element_tools.py` — identificación, variantes, cálculo de tarifa
- `agent/tools/image_tools.py` — envío de imágenes ejemplo
- `agent/tools/transition_tools.py:24-116` — `confirmar_presupuesto`
- `agent/tools/shared_tools.py:56` — `escalar_a_humano`
- `agent/tools/tarifa_tools.py` — listar categorías, servicios adicionales
- `agent/tools/vehicle_tools.py:25` — `identificar_tipo_vehiculo`

### Guard de identidad (EU AI Act)
- `agent/main.py:79` — `_IDENTITY_RE` regex guard
- `agent/main.py` — `_apply_identity_guard(ai_response, is_first_interaction)` función pura extraída del inline block. Contrato:
  - Si `is_first_interaction=False`: passthrough sin modificación.
  - Si la respuesta no contiene la frase de identidad: la antepone (caso raro — el LLM no incluyó el saludo obligatorio).
  - Si la respuesta contiene ≥2 ocurrencias: colapsa a una sola (deduplica la identidad repetida).
  - Si hay exactamente 1 ocurrencia: verifica ventana de 250 chars (`_SCAN_WINDOW`) para detectar `\n\n` + "Hola" duplicado generado por el LLM; lo elimina si lo encuentra. Constante `_DUPLICATE_GREETING_RE` define el patrón.
- `agent/prompts/loader.py:188-196` — inyección de bloque "🚨 PRIMERA INTERACCIÓN" en `format_mode_context()`. Contrato:
  - **Incluye**: la frase legal `¡Hola! Soy el asistente con IA de MSI Automotive` + referencia a `Reglamento UE 2024/1689`.
  - **PROHIBIDO**: `"Saluda siempre"` fue eliminado — causaba que el LLM generase un segundo párrafo de saludo tras la identificación (AP-5).
  - **Añadido**: directiva `PROHIBIDO añadir otro saludo` que aclara que la frase de identificación YA es el saludo; el LLM debe continuar directo con el contenido útil.

## Fuera de alcance

Los siguientes archivos **no deben modificarse** en cambios cuyo scope sea el flujo PRE_EXPEDIENTE. Si un cambio requiere tocarlos, es un cambio de otro scope (probablemente transversal o de EXPEDIENTE).

- `agent/modes/expediente_mode.py` — modo EXPEDIENTE, scope distinto
- `agent/modes/expediente_nodes.py` — submodos de EXPEDIENTE
- `agent/modes/submodos/**` — submodos específicos de EXPEDIENTE
- `agent/modes/presupuesto_mode.py` — modo legado en transición (tocar sólo vía change dedicado de cleanup)
- `agent/tools/case_tools.py` — tools de creación de caso, exclusivo de EXPEDIENTE
- `agent/tools/element_data_tools.py` — recolección de datos de elemento, exclusivo de EXPEDIENTE
- `api/**` — backend API, otro scope
- `admin-panel/**` — UI admin, otro scope
- `database/**` — modelos de DB, otro scope
- `shared/**` — clientes compartidos (Chatwoot, LLM router), tocar sólo vía change transversal
