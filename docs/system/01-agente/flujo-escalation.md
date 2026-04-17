---
titulo: Flujo ESCALATION
ambito: escalation
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Flujo ESCALATION

## Resumen

`ESCALATION` es un modo **terminal** con flujo determinístico de 6 pasos que desactiva el bot automáticamente e involucra a un agente humano de MSI Automotive. **No hay retorno automático al agente**: una vez escalado, el caso pasa a un inbox de Chatwoot donde un humano toma el control.

**Cuándo entra**: cuando una herramienta (ej. `escalar_a_humano` en PRE_EXPEDIENTE o EXPEDIENTE) retorna `_transition_to: ESCALATION`, o cuando el sistema detecta un error recurrente (fallback automático).

**Por qué es terminal**: el Bot Attribute `atencion_automatica` se setea a `False` en Chatwoot, bloqueando todos los mensajes futuros del bot. Solo un agente humano (o admin) puede reactivarlo manualmente.

## Escenarios

### 1. Escalación por solicitud explícita del cliente
- CUANDO el usuario escribe "quiero hablar con una persona" / "un agente" / "humano" en PRE_EXPEDIENTE o EXPEDIENTE
- ENTONCES el intent_router clasifica como `ESCALAR`, la herramienta `escalar_a_humano` se invoca, se ejecuta `perform_escalation()` con `source=tool_call`, la conversación se etiqueta con "escalado" en Chatwoot, el bot se desactiva, y se envía un mensaje confirmando la escalación.

### 2. Escalación por error recurrente
- CUANDO en un sub-modo de EXPEDIENTE el usuario falla 3+ veces seguidas en validación, o el sistema registra 3+ errores consecutivos
- ENTONCES el sistema (fallback_handler o post_tool_hook) invoca automáticamente `escalar_a_humano` con `es_error_tecnico=False`, `source=fallback`, que ejecuta `perform_escalation()` y termina la sesión.

### 3. Escalación por error técnico del sistema
- CUANDO ocurre una excepción inesperada dentro del tool loop (ej. DB unavailable, timeout en LLM)
- ENTONCES el error_handler captura la excepción, invoca `escalation_service.perform_escalation()` directamente con `is_technical_error=True`, `source=panic`, que etiqueta con "escalado" + "error-tecnico" en Chatwoot, y notifica al usuario.

### 4. Prevención de escalación duplicada
- CUANDO se recibe una segunda solicitud de escalación dentro de 5 minutos para la misma conversación
- ENTONCES `perform_escalation()` detecta una fila Escalation existente con `triggered_at > now() - 5m`, retorna el `escalation_id` previo, establece `duplicate_prevented=True`, e ignora silenciosamente la segunda solicitud (no duplica en Chatwoot).

### 5. Desactivación del bot (paso CRITICAL)
- CUANDO `perform_escalation()` ejecuta STEP 2
- ENTONCES llama a `ChatwootClient.update_conversation_attributes(atencion_automatica=False)`. Este es el único paso CRITICAL; si falla, se loguea como ERROR pero se continúa (la escalación no se bloquea).

### 6. Asignación a equipo (best-effort)
- CUANDO se intenta asignar la conversación a un equipo via `ChatwootClient.assign_to_team(team_id=...)`
- ENTONCES es "best-effort" — si falla (permisos insuficientes del bot token), se loguea como DEBUG (esperado a fallar) y se continúa. El agente humano la verá en el inbox de todas formas.

### 7. Nota privada con contexto
- CUANDO `perform_escalation()` ejecuta STEP 4
- ENTONCES construye una nota privada con: tipo escalación, motivo, fuente, usuario, timestamp, escalation_id, y la inserta vía `ChatwootClient.add_private_note()`. Si falla, se loguea WARNING pero no bloquea.

### 8. Persistencia en BD (logging)
- CUANDO todos los pasos previos completan
- ENTONCES se crea una fila Escalation en PostgreSQL con: `conversation_id`, `user_id`, `reason`, `source`, `status=pending`, `metadata_` con contexto, permitiendo auditoría y follow-up posterior.

## Reglas duras

1. **ESCALATION es terminal en esta sesión**: una vez escalado, el usuario NO vuelve automáticamente al agente. Solo un humano o un admin puede reactivar `atencion_automatica=True` en Chatwoot.

2. **6 pasos determinísticos, sin ramificación**: (1) Duplicate check → (2) Disable bot (CRITICAL) → (3) Labels → (4) Note → (5) Team assign (best-effort) → (6) DB save. Todos los pasos corren, sin early exit, salvo en duplicate.

3. **Disable bot es el único paso CRITICAL**: si `update_conversation_attributes(atencion_automatica=False)` falla, se loguea ERROR pero se continúa. Sin esto, el sistema se vuelve sensible a fallos de Chatwoot.

4. **Ventana de deduplicación es 5 minutos**: si hay una Escalation en BD con `triggered_at > now() - 300s` para la misma `conversation_id`, se retorna la escalación anterior SIN crear una nueva entrada.

5. **No hay escalación automática SIN justificación**: toda escalación DEBE incluir un `reason` legible (ej. "El usuario lo solicitó", "Error técnico recurrente", "Fuera de alcance"). Nunca se escala con reason vacío.

6. **Chatwoot team assignment es "best-effort"**: si el bot token no tiene permiso `assign_to_team`, el error se loguea DEBUG (no WARNING) y se continúa. El inbox del equipo la verá de todas formas por las labels.

7. **Labels son "escalado" ± "error-tecnico"**: todas las escalaciones obtienen label "escalado". Si `is_technical_error=True`, también se añade "error-tecnico". No se mezclan otras labels.

8. **source enumera el origen**: valores válidos — "tool_call" (usuario pidió), "auto" (recurso agotado), "fallback" (error recurrente), "panic" (error técnico no recuperable). Grabado en BD para auditoría.

## Mapeo al código

### Servicio de escalación (orquestación completa)
- `agent/services/escalation_service.py:36-291` — `perform_escalation()` (6 pasos)

### Herramienta pública
- `agent/tools/shared_tools.py:56-124` — `escalar_a_humano(motivo, es_error_tecnico, contexto, config)`

### Cliente Chatwoot (integración)
- `shared/chatwoot_client.py` — `ChatwootClient.update_conversation_attributes()`, `add_labels()`, `add_private_note()`, `assign_to_team()`

### Persistencia
- `database/models.py` — `Escalation` (id, conversation_id, user_id, reason, source, status, metadata_, triggered_at)

### Fallback handler (auto-escalación en errores)
- `agent/fallback/fallback_handler.py` — invoca `escalar_a_humano` después de N reintentos fallidos

### Router de transiciones (whitelist)
- `agent/router/mode_transitions.py:28-43` — `ALLOWED_TRANSITIONS` marca ESCALATION como reachable desde PRE_EXPEDIENTE y EXPEDIENTE

### Despliegue en graph
- `agent/graph/conversation_graph.py` — nodo `escalation_node` que invoca `perform_escalation()` y retorna terminal

## Fuera de alcance

- `agent/modes/pre_expediente_mode.py` — lógica de PRE_EXPEDIENTE (otro scope)
- `agent/modes/expediente_mode.py` — lógica de EXPEDIENTE (otro scope)
- `shared/chatwoot_client.py` — método implementations (tocado solo vía change transversal)
- `api/**` — backend API (otro scope)
- `admin-panel/**` — UI admin (otro scope)
