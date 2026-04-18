---
titulo: Estado conversacional y persistencia
ambito: agente
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Estado conversacional y persistencia

## Resumen

`ConversationState` es el esquema central de LangGraph que persiste todo el estado de una conversación en Redis. Usa **reducers Annotated** (`merge_dicts`, `preserve_if_none`, `add_messages`) para resolver cómo se fusionan updates parciales con el checkpoint previo.

La persistencia es **turn-by-turn** vía `ModeAwareTTLSaver` (AsyncRedisSaver de LangGraph). El estado incluye:

- **Identity** — user_id, user_phone, conversation_id, client_type
- **Navigation** — current_mode, mode_history
- **Context** — mode_context (nested dict de datos por modo)
- **Messages** — historial LLM-visible
- **Drafts** — draft_contexts para guardar estado cuando cambiás de modo (y recuperarlo al volver)

La **fuente de verdad para finalizaciones** es siempre PostgreSQL (Case, CaseElementData), nunca mode_context.

## Escenarios

### 1. Primer mensaje: inicialización de state
- CUANDO el usuario envía el primer mensaje
- ENTONCES `main.py` construye `state_input` con `{conversation_id, user_id, user_message, incoming_attachments, ...}`, SIN mode_context ni messages (es el primer turno). LangGraph aplica reducers: `preserve_if_none` mantiene values existentes, `merge_dicts` combina dicts, `add_messages` añade el nuevo HumanMessage.

### 2. Persistencia turn-by-turn a Redis
- CUANDO un node retorna state updates
- ENTONCES LangGraph invoca `ModeAwareTTLSaver.aput()`, que (1) persiste el checkpoint completo en Redis, (2) extrae `current_mode`, (3) aplica TTL según `ttl_by_mode[current_mode]` (ej. PRE_EXPEDIENTE=240min, EXPEDIENTE=10080min=7 días).

### 3. Recuperación tras timeout (7 días en EXPEDIENTE)
- CUANDO el usuario reaparece 4 días después en EXPEDIENTE
- ENTONCES Redis checkpoint EXISTE (TTL no expirado), se carga automáticamente, preprocess_node lo valida, `mode_context` se rehidrata con todos los datos previos, y se continúa en el sub-modo donde se dejó.

### 4. Recuperación tras expiración del checkpoint (> 7 días)
- CUANDO el checkpoint Redis expira pero el Case sigue activo en PostgreSQL
- ENTONCES preprocess_node detecta `current_mode=EXPEDIENTE` pero no hay checkpoint ("ghost mode"), consulta PostgreSQL, encuentra un Case activo, inyecta `pending_recovery_case` en mode_context, y entry_router de expediente lo detecta y rehidrata.

### 5. Cambio de modo → draft_contexts
- CUANDO el usuario está en PRE_EXPEDIENTE (con elements, presupuesto, etc.) y transiciona a EXPEDIENTE
- ENTONCES el modo PRE antes de retornar `_transition_to: EXPEDIENTE_MODE` hace un snapshot de `mode_context` en `draft_contexts["PRE_EXPEDIENTE_MODE"]`. Si el usuario luego vuelve a PRE (ej. desde REVIEW en EXPEDIENTE), el contexto anterior está intacto.

### 6. Transición a EXPEDIENTE consume el draft
- CUANDO EXPEDIENTE_MODE entry_router se ejecuta
- ENTONCES lee `draft_contexts["PRE_EXPEDIENTE_MODE"]` si existe, hereda campos (elementos_confirmados, tarifa_calculada, precio_comunicado, vehiculo, etc.), `initialize_expediente()` usa estos datos para crear el Case, y limpia el draft.

### 7. Compactación de messages (schema ready, no implementado)
- CUANDO la lista `messages` crece > N items (futuro)
- ENTONCES `maybe_summarize_node` en conversation_graph podrá summarizar los primeros N mensajes, reemplazar con 1 AIMessage summary, truncar la lista. El estado sigue chico en Redis.

### 8. Tombstone para resolver stale keys
- CUANDO un node necesita limpiar una key de mode_context (ej. `pending_recovery_case` tras consumirlo)
- ENTONCES retorna `mode_context["pending_recovery_case"] = None`. El reducer `merge_dicts` interpreta None como "delete", produciendo un merged dict SIN la clave. Sin esto, el checkpoint anterior resucita la clave. (ADR-010.)

### 9. ContextVar no es cache → releé state
- CUANDO una herramienta hace `get_tool_state(config)` después de mutar la BD
- ENTONCES obtiene un snapshot del state del RunnableConfig, NO la ContextVar (que puede estar stale). Nunca reutiliza estado leído hace 2 llamadas atrás.

### 10. DraftQuote: auto-preservación del presupuesto
- CUANDO se calcula una tarifa en PRE_EXPEDIENTE
- ENTONCES `_upsert_draft_quote()` guarda un DraftQuote activo en BD (desactiva los anteriores). Cuando el cliente vuelve horas después, se carga automáticamente en mode_context vía `_load_active_draft_quote_into_context()`.

## Reglas duras

1. **`merge_dicts` NUNCA sobrescribe con None a menos que esté explícito**: si current={a:1, b:2} y update={a:3}, result={a:3, b:2}. Si update={a:None}, result={b:2}. Sin None, b persiste.

2. **`preserve_if_none` mantiene valores persistentes**: para fields como current_mode, user_id, si el node no retorna el valor, se preserva el checkpoint. Previene "perder" datos entre turnos.

3. **`add_messages` es APPEND-ONLY**: nunca sobrescribe el historial. Cada LLM loop agrega AIMessage + HumanMessage nuevo. Mensajes previos son inviolables.

4. **mode_context es per-mode, no global**: cada vez que cambiás de modo, se hace un snapshot en `draft_contexts[modo_anterior]`, y se carga un mode_context nuevo. Sin sangrado entre modos.

5. **Checkpoint Redis es fuente de verdad SOLO para navegación**: bits de identidad (user_id, conversation_id), current_mode, mode_history. Para datos finales (elements, personal, vehicle), la fuente de verdad es PostgreSQL.

6. **`finalizar_expediente` DEBE leer de BD, NUNCA de mode_context**: `Case.element_codes`, `Case.category_id`, `Case.tariff_amount` se leen vía selectinload de ORM. No confiar en mode_context. (ADR-010.)

7. **No stale ContextVar reads tras DB writes**: después de `_update_fsm_state(session, ...)` que persiste en BD, usar el dict que retorna esa función, NO `_get_mode_context()` de nuevo (stale).

8. **DraftQuote upsert limpia automáticamente**: al calcular presupuesto, `_upsert_draft_quote()` desactiva DraftQuotes previos (`is_active=False`) para esa conversation. Solo 1 draft activo a la vez.

9. **TTL por modo es invariante una vez escrito el checkpoint**: PRE_EXPEDIENTE=240min, EXPEDIENTE=10080min, ESCALATION=120min. Si un checkpoint dice mode=EXPEDIENTE, su TTL es 10080min.

10. **`preserve_if_none` nunca "resucita"**: si un valor fue None en un turno, el siguiente turno que NO lo actualice lo mantiene None. No hay resurrección automática desde checkpoint anterior.

## Catálogo de state fields

### Identity (`preserve_if_none`)
| Key | Type | Notas |
|-----|------|-------|
| conversation_id | str | Chatwoot conversation ID |
| user_id | str | UUID de User |
| user_phone | str | Teléfono identificador |
| user_name | str | Nombre del cliente |
| client_type | str | "particular" o "professional" |

### Navigation (`preserve_if_none` + `append_unique_list`)
| Key | Type | Reducer | Notas |
|-----|------|---------|-------|
| current_mode | str | preserve_if_none | START, PRE_EXPEDIENTE_MODE, EXPEDIENTE_MODE, ESCALATION, COMPLETED |
| previous_mode | str | preserve_if_none | Modo anterior (para logs) |
| mode_history | list[str] | append_unique_list | `[PRE_EXPEDIENTE_MODE, EXPEDIENTE_MODE, ...]` |

### Messages (`add_messages`)
| Key | Type | Notas |
|-----|------|-------|
| messages | list[BaseMessage] | Historial LLM-visible (HumanMessage + AIMessage) |

### Context (`merge_dicts`)
| Key | Type | Notas |
|-----|------|-------|
| mode_context | dict | Datos por modo (precio_comunicado, case_id, element_codes, etc.) |
| draft_contexts | dict[mode → context] | Snapshots de mode_context al cambiar modos |
| user_profile | dict | Datos durables del user (no cambian entre modos) |
| conversation_summary | str | Resumen (futuro, compaction feature) |

### Control & Retry
| Key | Type | Reducer | Notas |
|-----|------|---------|-------|
| retry_state | dict | merge_retry_state | `{retry_count, consecutive_errors, last_error_type, ...}` |
| incoming_attachments | list | preserve_if_none | Archivos subidos este turno |
| pending_images | dict | merge_dicts | Images queued para WhatsApp (async) |
| agent_disabled | bool | preserve_if_none | Escalado: bot desactivado en Chatwoot |

### Flags & Metadata (`preserve_if_none`)
| Key | Type | Notas |
|-----|------|-------|
| escalation_triggered | bool | True si ya escalado |
| expediente_intro_sent | bool | True una vez emitido overview |
| presupuesto_images_shown | bool | True si ya mostradas imágenes en PRE |

### Outbound Messages (replace semantics — sin reducer `add_messages`)
| Key | Type | Reducer | Notas |
|-----|------|---------|-------|
| pending_outbound_messages | list[str] | plain overwrite | Mensajes de sistema encolados para enviar a WhatsApp **antes** del `ai_response`. `main.py` los despacha vía Chatwoot y luego limpia el canal con `aupdate_state(..., {"pending_outbound_messages": []})`. No usa `add_messages` — semántica de reemplazo para evitar re-envíos al rehidrar el checkpoint. Ejemplo: overview introductorio de EXPEDIENTE (los 6 pasos). |

## Mapeo al código

### State schema
- `agent/state/conversation_state.py` — `ConversationState` TypedDict + reducers (`merge_dicts`, `preserve_if_none`, `add_messages`, `append_unique_list`, `merge_retry_state`)
- `agent/state/context_models.py` — `SharedContext` y modelos Pydantic para validación

### SharedContext — campos tipados

`SharedContext` es un `TypedDict(total=False)` que vive en `shared_context` de `ConversationState`. Persiste datos entre transiciones de modo que no deben limpiarse. Todos los campos listados aquí están **declarados como anotaciones tipadas** en el TypedDict (no son claves libres de dict).

| Campo | Tipo | Escrito por | Notas |
|-------|------|-------------|-------|
| element_codes | list[str] | herramientas de elementos | Códigos confirmados |
| tarifa_calculada | dict \| None | calcular_tarifa_con_elementos | Resultado completo de tarifa |
| categoria_slug | str \| None | herramientas de elementos | Slug de categoría MSI |
| precio_comunicado | bool | calcular_tarifa_con_elementos | True al comunicar precio |
| imagenes_enviadas | bool | enviar_imagenes_ejemplo | True al enviar imágenes |
| imagenes_enviadas_codigos | list[str] | enviar_imagenes_ejemplo | Códigos cuyas imágenes fueron enviadas |
| vehiculo | dict \| None | herramientas de elementos | Datos del vehículo identificado |
| elementos_confirmados | list[dict] | herramientas de elementos | Lista de elementos con datos completos |
| presupuesto_images_shown | bool | herramientas de imágenes | True si las imágenes del presupuesto se mostraron |
| warnings_acknowledged | bool | confirmar_presupuesto / iniciar_expediente hook | **Campo tipado** — True cuando el cliente confirmó conocer las advertencias y quiere abrir expediente. Escrito en PRE_EXPEDIENTE_MODE, propagado a `ExpedienteState` via `parent_to_expediente()` al entrar al subgraph EXPEDIENTE. Aparece en `_MODE_RUNTIME_KEYS` de `mode_context_keys.py` para habilitar esa propagación. |

### Checkpointer (persistencia Redis)
- `agent/state/checkpointer.py:64-200` — `ModeAwareTTLSaver` (AsyncRedisSaver + TTL dinámico)
- `agent/state/checkpointer.py:30-62` — `initialize_redis_indexes()`

### DraftQuote

El presupuesto borrador vive como parte del ConversationState. Para la definición completa de la entidad (campos, validez, reglas de negocio), ver [`../../core/presupuestos/draft-quote.md`](../../core/presupuestos/draft-quote.md). En `ConversationState` solo se persiste el draft en curso mientras la conversación está activa; la persistencia de DraftQuote confirmado es responsabilidad del servicio de presupuestos.

- `agent/tools/draft_quote_service.py:47-108` — `_upsert_draft_quote()`, `_deactivate_draft_quote()`, `_load_active_draft_quote_into_context()`

### Helpers (acceso seguro)
- `agent/state/helpers.py:get_tool_state(config)` — extrae state desde RunnableConfig (preferred vs ContextVar)
- `agent/state/helpers.py:format_messages_for_llm()` — formatea messages para el system prompt

### Boundary (ExpedienteState)
- `agent/modes/expediente_state.py:99-240` — TypedDict aislado para el subgrafo (no usa merge_dicts)
- `agent/modes/expediente_state.py:530-653` — mappings bidireccionales (parent ↔ subgrafo)

### Reducers en graph
- `agent/graph/conversation_graph.py` — StateGraph declara reducers en state_schema

## Fuera de alcance

- `database/models.py` — esquema ORM (otro scope)
- `shared/config.py` — configuración global (otro scope)
- `agent/main.py` — consumer de Redis Streams, limpieza de state_input (scope transversal)
