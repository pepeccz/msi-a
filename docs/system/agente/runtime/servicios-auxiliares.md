---
titulo: Servicios auxiliares del agente
ambito: agente
ultima_verificacion_commit:
ultima_verificacion_fecha: 2026-04-17
---

# Servicios auxiliares del agente

## Resumen

El agente tiene tres servicios auxiliares que no forman parte del flujo conversacional principal pero lo enriquecen: extracción de entidades del historial, seguimiento de conversión (contadores + nudges), y detección de digresiones. Ninguno bloquea la respuesta — son piezas de soporte que alimentan el contexto del LLM o redirigen el flujo.

| Servicio | Archivo | Rol |
|---------|---------|-----|
| `EntityExtractionService` | `agent/services/entity_extraction_service.py` | Extrae elementos, marca y modelo del historial de mensajes |
| Conversion Tracking | `agent/state/conversation_state.py:372-378` | Contadores de mensajes, presupuestos ofrecidos y nudges |
| `DigressionManager` | `agent/router/digression_manager.py` | Detecta mensajes off-topic en modos bloqueantes |

---

## EntityExtractionService

**Fuente**: `agent/services/entity_extraction_service.py`

**Propósito**: Extraer de forma barata entidades de conversación — elementos de vehículo mencionados, marca y modelo — para poblar `user_profile` o `mode_context` sin requerir que el LLM principal los mencione explícitamente.

### Qué extrae

- **`elementos`**: lista de elementos de vehículo mencionados (escape, suspensión, subchasis, faros, manillar, retrovisor, sillín, ruedas, etc.)
- **`marca`**: marca del vehículo (Honda, BMW, Yamaha, Kawasaki, Suzuki, Mercedes, Hymer…)
- **`modelo`**: modelo del vehículo (patrón `[A-Z]{2,}[\d]{2,}[A-Z]*`, ej. `CBF600`)

### Estrategia de extracción (2 niveles)

1. **LLM local (Tier 1)**: usa `TaskType.EXTRACTION` en el router híbrido (modelo Ollama local — gemma4 o qwen2.5). Prompt estructurado con los últimos `max_messages` mensajes. Espera JSON `{elementos, marca, modelo}`. Si falla el parseo o hay excepción → nivel 2.
2. **Regex fallback**: patrones básicos en español para elementos comunes, regex de marca (`Honda|BMW|...`) y regex de modelo (`[A-Z]{2,}[\d]{2,}[A-Z]*`). Mucho menos preciso pero nunca falla.

```python
# Uso típico
service = get_entity_extraction_service()  # Singleton
result = await service.extract_entities(message_history, max_messages=5)
# result = {"elementos": ["escape", "suspensión"], "marca": "Honda", "modelo": "CBF600"}
```

### Cuándo se llama

El servicio es **on-demand** — no se invoca automáticamente en cada turno. Se llama explícitamente desde los nodos o servicios que necesitan enriquecer el perfil del usuario (ej. al inicio de sesión para recuperar contexto). No tiene efecto de estado propio: los callers son responsables de persistir el resultado en `user_profile` o `mode_context`.

### Singleton

`get_entity_extraction_service()` retorna siempre la misma instancia. El router LLM se inicializa lazy en el primer uso.

---

## Conversion Tracking (contadores de conversión)

**Fuente**: `agent/state/conversation_state.py:372-378`

El `ConversationState` incluye tres contadores de funnel de ventas que el agente usa para decidir cuándo enviar un nudge:

| Campo | Tipo | Qué mide |
|-------|------|---------|
| `mode_message_count` | `int` | Mensajes enviados en el modo actual (reset en cada transición de modo) |
| `presupuesto_offered_count` | `int` | Cuántas veces se ofreció un presupuesto en la conversación |
| `last_nudge_message_count` | `int` | En qué número de mensaje (`mode_message_count`) se envió el último nudge |

### Cómo funcionan los nudges

Un **nudge** es un mensaje suave del bot para reconducir al usuario hacia la acción principal cuando lleva varios turnos sin avanzar. En PRE_EXPEDIENTE es especialmente relevante: si el usuario hace 3+ preguntas informativas sin pedir presupuesto, el bot puede incluir un nudge natural dentro de su respuesta.

El control del nudge está en el prompt de discovery (`agent/prompts/modes/pre_expediente_discovery.md:88-92`):

```
<nudge>
Si el usuario lleva 3+ mensajes de preguntas sin pedir presupuesto, incluye un nudge natural:
[ejemplo: "¿Querés que calculemos el precio para tu caso?"]
Un nudge cada 2 mensajes máximo. NUNCA tras una pausa explícita del usuario.
</nudge>
```

La lógica es así:
- `mode_message_count` crece con cada turno del modo actual
- `last_nudge_message_count` guarda en qué mensaje se mandó el último nudge
- Si `mode_message_count - last_nudge_message_count >= 2` → el LLM puede incluir un nudge en su respuesta

Los contadores también están registrados en `agent/state/mode_context_keys.py:242` (lista de claves de `mode_context` conocidas).

El modo EXPEDIENTE tiene su propio `nudge_message` configurado en `mode_transitions.py:88`: `"¿Estás teniendo dificultades? Puedo conectarte con un agente."`. Este se usa cuando el modo entra en timeout (configurable: `timeout_seconds=1800` en EXPEDIENTE).

---

## DigressionManager

**Fuente**: `agent/router/digression_manager.py`

**Propósito**: Antes de que el nodo del modo actual procese el mensaje, el router consulta al `DigressionManager` para saber si el mensaje es en realidad off-topic y debe redirigirse a otro modo.

### ¿Qué es una digresión?

Una digresión ocurre cuando el usuario, estando en un modo **bloqueante** (EXPEDIENTE_MODE, donde `allows_digression=False`), envía un mensaje que no corresponde al paso actual:

| Tipo | Patrón detectado | Redirect a |
|------|-----------------|-----------|
| `ESCALACION` | "persona", "humano", "agente", "hablar con alguien" | `ESCALATION` |
| `VIABILIDAD_OTRO` | "se puede también", "es posible además" | `PRE_EXPEDIENTE_MODE` |

> Nota: el tipo `CONSULTA_GENERAL` (preguntas como "¿cuánto tarda?") fue **comentado intencionalmente** en el código (`digression_manager.py:66-72`). Estas preguntas ahora se manejan inline por el modo actual según las instrucciones del prompt (`../prompts/expediente.md`), sin cambiar de modo. Esta decisión evita pérdida de contexto del expediente.

### Modos permisivos vs. bloqueantes

- **PRE_EXPEDIENTE_MODE**: `allows_digression=False` pero en práctica es permisivo — el bot responde todo inline sin redirigir.
- **EXPEDIENTE_MODE**: `allows_digression=False` y `blocking=True`. Las digresiones aquí sí se redirigen.
- **START**: sin check de digresión.

El `DigressionManager` solo actúa cuando `allows_digression=False` en el `ModeProperties` del modo actual (`mode_transitions.py:75-88`).

### Patrones en-contexto (no se redirigen)

Aunque el modo sea bloqueante, estos mensajes se consideran en-contexto y el DigressionManager los deja pasar al nodo del modo:

- "¿qué fotos/documentos necesito?"
- "¿cuánto era/sale/cuesta eso/el presupuesto?"
- "¿cuándo termina/se completa?"

### Singleton

`get_digression_manager()` retorna siempre la misma instancia. No tiene estado interno.

---

## Escenarios

### Extracción de entidades al inicio de sesión
- CUANDO el agente recibe un nuevo mensaje de un usuario con historial previo
- ENTONCES el nodo puede llamar `EntityExtractionService.extract_entities(messages[-5:])` para enriquecer el contexto antes de responder
- El resultado se puede persistir en `user_profile.{marca, modelo, elementos_vistos}` vía `_state_update`

### Nudge después de 3 preguntas sin acción
- CUANDO el usuario hace 3 preguntas informativas en PRE_EXPEDIENTE_DISCOVERY
- ENTONCES el LLM detecta que `mode_message_count >= 3` y `last_nudge_message_count` está lejos
- ENTONCES incluye naturalmente al final de su respuesta un nudge hacia el presupuesto
- El bot NO manda un mensaje separado — el nudge es parte de la respuesta del turno

### Digresión en EXPEDIENTE ("quiero hablar con una persona")
- CUANDO el usuario está en `collect_element_data` y escribe "quiero hablar con alguien"
- ENTONCES `DigressionManager.check()` detecta `ESCALACION` (patrón "hablar con alguien")
- ENTONCES el router en `conversation_graph.py` llama `validate_transition(EXPEDIENTE_MODE, ESCALATION)` → permitido
- ENTONCES `transition_mode()` guarda contexto, cambia a ESCALATION, y el siguiente turno es el flujo determinístico de handoff

### Pregunta off-topic tratada como in-context
- CUANDO el usuario en COLLECT_VEHICLE pregunta "¿cuánto era el presupuesto?"
- ENTONCES `DigressionManager._is_in_context()` lo identifica como en-contexto
- ENTONCES NO hay redirección; el nodo de EXPEDIENTE responde inline

---

## Reglas duras

- **`EntityExtractionService` nunca bloquea el flujo principal**: si el LLM falla, hace regex fallback. Si el regex falla, retorna `{elementos:[], marca:None, modelo:None}`. Nunca propaga excepciones.
- **Los contadores son `preserve_if_none`**: si el campo no está seteado en state, el reducer lo preserva (no lo sobreescribe con None). Los contadores nunca van hacia atrás.
- **DigressionManager no procesa el mensaje, solo decide dónde va**: la respuesta la genera siempre el nodo del modo destino.
- **`CONSULTA_GENERAL` no es digresión**: preguntas generales en EXPEDIENTE se responden inline. Nunca cambiar de modo para responder una pregunta informativa.
- **Los nudges son suaves y con límite de frecuencia**: máximo 1 nudge cada 2 mensajes. Nunca después de una pausa explícita del usuario ("vuelvo ahora", "un momento").

---

## Mapeo al código

| Componente | Archivo | Notas |
|-----------|---------|-------|
| `EntityExtractionService` | `agent/services/entity_extraction_service.py` | LLM local + regex fallback |
| `get_entity_extraction_service()` | `agent/services/entity_extraction_service.py:175` | Singleton |
| Conversion counters | `agent/state/conversation_state.py:372-378` | `mode_message_count`, `presupuesto_offered_count`, `last_nudge_message_count` |
| Nudge prompt | `agent/prompts/modes/pre_expediente_discovery.md:88-92` | Instrucciones al LLM |
| `DigressionManager` | `agent/router/digression_manager.py` | Patrones + in-context patterns |
| `get_digression_manager()` | `agent/router/digression_manager.py:204` | Singleton |
| Modo properties (timeout, nudge) | `agent/router/mode_transitions.py:75-88` | `blocking`, `allows_digression`, `nudge_message` |
| Invocación en router | `agent/graph/conversation_graph.py:529-545` | Se llama antes de despachar al nodo del modo |

---

## Fuera de alcance

- El router de intenciones (`intent_router.py`) — clasifica la intención inicial, no es un servicio auxiliar del agente en ejecución
- La lógica de fallback y reintentos por errores del LLM — ver `agent/fallback/`
- Los contadores de retry (`retry_count`, `consecutive_errors`) — son parte del estado de error, no de conversión
- Turn telemetry — ver `../../../infra/observabilidad/telemetria.md` (futuro Ola 3)
