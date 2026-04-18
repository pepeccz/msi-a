---
titulo: Flujo de escalado — handoff humano
ambito: agente
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Flujo de escalado — handoff humano

## Resumen

`ESCALATION` es un modo **terminal** que desactiva el bot automáticamente y transfiere el hilo conversacional a un operador humano de MSI Automotive vía Chatwoot. **No hay retorno automático al agente**: una vez escalado, el caso pasa al inbox humano y solo un agente o admin puede reactivarlo manualmente.

El mecanismo es **determinístico en 6 pasos**: (1) prevención de duplicados en ventana de 5 min, (2) desactivar bot en Chatwoot (`atencion_automatica=False`), (3) etiquetar conversación, (4) agregar nota privada con contexto, (5) intentar asignar a equipo (best-effort), (6) persistir fila `Escalation` en PostgreSQL. El escalado puede originarse por solicitud explícita del cliente, error recurrente del sistema, o excepción técnica no recuperable.

## Escenarios

### 1. Escalación por solicitud explícita del cliente
- CUANDO el usuario escribe "quiero hablar con una persona" / "un agente" / "humano" en PRE_EXPEDIENTE o EXPEDIENTE
- ENTONCES el intent_router clasifica como `ESCALAR`, la herramienta `escalar_a_humano` se invoca, se ejecuta `perform_escalation()` con `source=tool_call`, la conversación se etiqueta con "escalado" en Chatwoot, el bot se desactiva, y se envía un mensaje confirmando la escalación.

### 2. Escalación voluntaria desde contexto de EXPEDIENTE
- CUANDO el cliente acumula 3 intentos fallidos de resolver variante o datos consecutivos en EXPEDIENTE
- ENTONCES el agente (vía prompt + tool filtering) ofrece escalado: *"¿Prefieres que te ponga con alguien del equipo?"*. Si el cliente acepta, llama a `escalar_a_humano` con `reason="Múltiples intentos fallidos"`.

### 3. Escalación por error recurrente (auto)
- CUANDO en un sub-modo de EXPEDIENTE el usuario falla 3+ veces seguidas en validación, o el sistema registra 3+ errores consecutivos
- ENTONCES el sistema (fallback_handler o post_tool_hook) invoca automáticamente `escalar_a_humano` con `es_error_tecnico=False`, `source=fallback`, que ejecuta `perform_escalation()` y termina la sesión.

### 4. Escalación por error técnico del sistema
- CUANDO ocurre una excepción inesperada dentro del tool loop (ej. DB unavailable, timeout en LLM)
- ENTONCES el error_handler captura la excepción, invoca `escalation_service.perform_escalation()` directamente con `is_technical_error=True`, `source=panic`, que etiqueta con "escalado" + "error-tecnico" en Chatwoot, y notifica al usuario.

### 5. Prevención de escalación duplicada
- CUANDO se recibe una segunda solicitud de escalación dentro de 5 minutos para la misma conversación
- ENTONCES `perform_escalation()` detecta una fila Escalation existente con `triggered_at > now() - 5m`, retorna el `escalation_id` previo, establece `duplicate_prevented=True`, e ignora silenciosamente la segunda solicitud (no duplica en Chatwoot).

### 6. Desactivación del bot (paso CRITICAL)
- CUANDO `perform_escalation()` ejecuta STEP 2
- ENTONCES llama a `ChatwootClient.update_conversation_attributes(atencion_automatica=False)`. Este es el único paso CRITICAL; si falla, se loguea como ERROR pero se continúa (la escalación no se bloquea).

### 7. Asignación a equipo (best-effort)
- CUANDO se intenta asignar la conversación a un equipo vía `ChatwootClient.assign_to_team(team_id=...)`
- ENTONCES es "best-effort" — si falla (permisos insuficientes del bot token), se loguea como DEBUG (esperado a fallar) y se continúa. El agente humano la verá en el inbox de todas formas.

### 8. Nota privada con contexto
- CUANDO `perform_escalation()` ejecuta STEP 4
- ENTONCES construye una nota privada con: tipo escalación, motivo, fuente, usuario, timestamp, escalation_id, y la inserta vía `ChatwootClient.add_private_note()`. Sin esta nota, el operador no sabe que fue escalado por el bot (podría parecer conversación delegada manualmente).

### 9. Persistencia en BD (logging y auditoría)
- CUANDO todos los pasos previos completan
- ENTONCES se crea una fila Escalation en PostgreSQL con: `conversation_id`, `user_id`, `reason`, `source`, `status=pending`, `metadata_` con contexto (user_phone, priority, is_technical_error), permitiendo auditoría y follow-up posterior. El campo `resolved_at` arranca en NULL.

### 10. Operador toma la conversación
- CUANDO el operador humano entra a la conversación en Chatwoot y escribe un mensaje
- ENTONCES la webhook detecta que `Chatwoot.assigned_agent` está seteado (no NULL), y el mensaje se dirige al operador, NO al agente (gate en `conversation_graph`).

### 11. Operador devuelve al bot (manual)
- CUANDO el operador resuelve el problema y quiere reactivar el bot
- ENTONCES el operador o admin ejecuta acción manual: setea `atencion_automatica=true` en Chatwoot, borra la label "escalado", y el siguiente mensaje del cliente vuelve al agente. El operador guarda nota privada del contexto resuelto.

### 12. Timeout sin respuesta del operador
- CUANDO pasaron 48h desde el escalado y el operador nunca respondió
- ENTONCES el campo `Escalation.resolved_at` sigue NULL. Admin puede detectar e investigar vía panel. El cliente puede escribir nuevamente (reactivar conversación).

### 13. Escalado con contexto de elemento específico
- CUANDO el cliente está en EXPEDIENTE mode y no puede completar fotos de un elemento tras 5 intentos
- ENTONCES escala con `reason="No puedo completar fotos de {element_name}"`, agent guarda `metadata_.element_code=<CODE>` en la fila Escalation, operador sabe exactamente qué estaba pasando.

## Flujo conversacional

El escalado produce una experiencia determinística para el usuario:

1. **Bot recibe la señal** (solicitud del cliente, fallback automático, o pánico técnico).
2. **Bot responde** al cliente con un mensaje confirmando que lo deriva con el equipo humano: *"Voy a conectarte con una persona de nuestro equipo. Revisarán tu caso en breve."*
3. **El hilo queda silenciado** del lado del bot: cualquier mensaje posterior del cliente llega al inbox de Chatwoot pero el bot no responde automáticamente.
4. **El operador ve el hilo** etiquetado con "escalado" + nota privada que describe el contexto (tipo escalación, motivo, elemento en curso si aplica, escalation_id).
5. **Transición limpia**: si el cliente escribe algo antes de que el operador responda, el mensaje queda guardado en Chatwoot y el operador lo ve al abrir el hilo.

El mensaje textual que el bot envía al escalar NO se hardcodea aquí — está en `agent/prompts/core.md` y en `agent/tools/shared_tools.py`. Lo que este spec garantiza es que **ese turno siempre ocurre** antes de desactivar el bot.

## Handoff técnico

Los 6 pasos de `perform_escalation()` en orden inviolable:

| Step | Acción | Criticidad | Si falla |
|------|--------|-----------|----------|
| 1 | Duplicate check (BD query `triggered_at > now()-5min`) | CRITICAL | Retorna el `escalation_id` anterior, no continúa |
| 2 | `update_conversation_attributes(atencion_automatica=False)` | CRITICAL | Log ERROR, continúa (no abortar) |
| 3 | `add_labels(["escalado"])` + `"error-tecnico"` si aplica | NORMAL | Log WARNING, continúa |
| 4 | `add_private_note(contexto)` | NORMAL | Log WARNING, continúa |
| 5 | `assign_to_team(CHATWOOT_TEAM_GROUP_ID)` | BEST-EFFORT | Log DEBUG, continúa |
| 6 | Crear fila `Escalation` en PostgreSQL | CRITICAL | Fallo de BD → no abortar Chatwoot ya hecho, reintento diferido |

**Invariante**: si el paso 2 fue ejecutado (bot desactivado en Chatwoot), el flujo no se puede revertir mecánicamente. Pasos 3-6 pueden fallar parcialmente sin afectar al operador.

**Headers de Chatwoot relevantes**: `Authorization: Bearer <CHATWOOT_BOT_TOKEN>`, `Content-Type: application/json`, endpoint `/api/v1/accounts/{account_id}/conversations/{id}/...`.

## Reglas duras

1. **ESCALATION es terminal en esta sesión**: una vez escalado, el usuario NO vuelve automáticamente al agente. Solo un humano o un admin puede reactivar `atencion_automatica=True` en Chatwoot.

2. **6 pasos determinísticos, sin ramificación**: (1) Duplicate check → (2) Disable bot (CRITICAL) → (3) Labels → (4) Note → (5) Team assign (best-effort) → (6) DB save. Todos los pasos corren, sin early exit, salvo en duplicate.

3. **Disable bot es el único paso CRITICAL que puede detener el flujo**: si falla, se loguea ERROR pero se continúa. Sin `atencion_automatica=False`, el sistema sigue respondiendo al cliente.

4. **Ventana de deduplicación es 5 minutos exacto**: query `WHERE triggered_at > NOW() - INTERVAL '5 minutes'`. Re-escalado después de 5min crea nuevo registro.

5. **No hay escalación automática SIN justificación**: toda escalación DEBE incluir un `reason` legible. Nunca se escala con reason vacío.

6. **Chatwoot team assignment es "best-effort"**: si el bot token no tiene permiso `assign_to_team`, el error se loguea DEBUG (no WARNING) y se continúa. El inbox del equipo la verá por las labels.

7. **Labels son "escalado" ± "error-tecnico"**: todas las escalaciones obtienen label "escalado". Si `is_technical_error=True`, también se añade "error-tecnico". No se mezclan otras labels.

8. **`source` enumera el origen**: valores válidos — `"tool_call"` (usuario pidió), `"auto"` (recurso agotado), `"fallback"` (error recurrente), `"panic"` (error técnico no recuperable). Grabado en BD para auditoría.

9. **`status` siempre inicia en `'pending'`**: nunca `'resolved'` en creación. Operador marca `'resolved'` o `'cancelled'` manualmente.

10. **Escalación SOLO desde sub-modos/tools, nunca desde entry_router**: el único camino a ESCALATION es una herramienta que retorna `_transition_to: ESCALATION`. entry_router NO despacha directamente a escalación.

11. **Marcas de escalado en Chatwoot DEBEN existir**: `add_labels(["escalado"])` + private note. Sin estas, el operador no sabe que fue escalado por el bot.

12. **BD record es persistencia de verdad**: si Chatwoot endpoint cae pero la Escalation se guardó en BD, se puede reintentar manualmente. Inversamente, si DB cae, se intentan al menos los pasos de Chatwoot.

## Mapeo al código

### Servicio de escalación (orquestación completa)
- `agent/services/escalation_service.py:36-292` — `perform_escalation()` (6 pasos, try/except por paso, duplicate check línea 72-98, disable bot línea 127-134, labels línea 149-157, private note línea 168-198, team assign línea 204-221, DB record línea 228-250)

### Herramienta pública
- `agent/tools/shared_tools.py:56-124` — `escalar_a_humano(motivo, es_error_tecnico, contexto, config)` — Pydantic args_schema, llama `perform_escalation()`, devuelve dict con `success`, `escalation_id`, `message`

### Cliente Chatwoot (integración)
- `shared/chatwoot_client.py` — `ChatwootClient.update_conversation_attributes()`, `add_labels()`, `add_private_note()`, `assign_to_team()`

### Persistencia
- `database/models.py` — `Escalation` model: `conversation_id`, `user_id`, `reason`, `source` (tool_call/auto/fallback), `status` (pending/resolved/cancelled), `triggered_at`, JSONB `metadata_` con `user_phone`, `priority`, `is_technical_error`

### Fallback handler (auto-escalación en errores)
- `agent/fallback/fallback_handler.py` — invoca `escalar_a_humano` después de N reintentos fallidos

### Router de transiciones (whitelist)
- `agent/router/mode_transitions.py:28-43` — `ALLOWED_TRANSITIONS` marca ESCALATION como reachable desde PRE_EXPEDIENTE y EXPEDIENTE

### Despliegue en graph
- `agent/graph/conversation_graph.py` — nodo `escalation_node` que invoca `perform_escalation()` y retorna terminal; conditional edge que detecta `current_mode="ESCALATION"`

## Fuera de alcance

- `agent/modes/pre_expediente_mode.py` — lógica de PRE_EXPEDIENTE (otro scope)
- `agent/modes/expediente_mode.py` — lógica de EXPEDIENTE (otro scope)
- `shared/chatwoot_client.py` — implementaciones de métodos (tocado solo vía change transversal)
- `admin-panel/**` — UI admin (otro scope)
- Interfaz de operador en Chatwoot (admin UI, proceso operativo)
- Workflow de resolución manual de escalaciones (proceso operativo, no spec técnico)
- Reactivación automática del bot (decisión manual de operador o feature futura)
- Notificaciones push a operadores (infra, otro scope)
- Cross-refs a `../../../infra/canal-whatsapp/webhook.md` (futuro Ola 3 — webhook de Chatwoot que recibe mensajes del operador)
