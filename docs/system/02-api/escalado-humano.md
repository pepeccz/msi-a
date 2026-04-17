---
titulo: Escalado a operador humano vía Chatwoot
ambito: api-escalado
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Escalado a operador humano vía Chatwoot

## Resumen

El **escalado a operador humano** es el flujo cuando el bot no puede resolver (ambigüedad, error técnico, solicitud explícita). Es **determinístico en 6 pasos**: (1) prevención de duplicados en ventana de 5 min, (2) desactivar bot en Chatwoot, (3) etiquetar conversación, (4) agregar nota privada con contexto, (5) intentar asignar a equipo (best-effort), (6) persistir Escalation en BD.

El resultado es siempre **terminal**: el agente detiene el flujo conversacional, nunca resume automáticamente, y el operador humano toma el control.

> **Nota**: este MD describe el mecanismo técnico de handoff. Para el flujo del modo ESCALATION (entrada desde PRE_EXPEDIENTE/EXPEDIENTE, transiciones), ver `01-agente/flujo-escalation.md`.

## Escenarios

### 1. Escalado voluntario del cliente
- CUANDO el cliente escribe "Prefiero hablar con una persona" (intent clasificado como `ESCALAR`)
- ENTONCES la tool `escalar_a_humano` ejecuta `perform_escalation(reason="Solicitud de escalación")`, desactiva el bot, etiqueta "escalado", guarda `Escalation.status="pending"`, y el próximo turno del agente NO ejecuta herramientas (el cliente va directo a operador).

### 2. Error técnico detectado por el agente
- CUANDO el agente intenta calcular tarifa pero la DB retorna 500 o timeout
- ENTONCES fallback en `agent/fallback/` llama `perform_escalation(is_technical_error=True, source="fallback")`, setea etiqueta "error-tecnico" + "escalado", y guarda con `priority=high` en metadata.

### 3. Escalado por triggering condition
- CUANDO el cliente acumula 3 intentos fallidos de resolver variante consecutivos
- ENTONCES el agente (vía prompt + tool filtering) ofrece escalado: *"¿Prefieres que te ponga con alguien?"*. Cliente acepta → tool `escalar_a_humano` con `reason="Múltiples intentos fallidos de variante"`.

### 4. Operador toma la conversación
- CUANDO el operador humano entra a la conversación en Chatwoot y escribe un mensaje
- ENTONCES la webhook detecta que `Chatwoot.assigned_agent` está seteado (no NULL), y el mensaje se dirige al operador, NO al agente (gate en `conversation_graph`).

### 5. Operador devuelve al bot (si es posible)
- CUANDO el operador resuelve el problema y escribe "Devolviendo al bot"
- ENTONCES el operador o admin ejecuta acción manual: setea `atencion_automatica=true` en Chatwoot, borra "escalado" label, y el siguiente mensaje del cliente vuelve al agente. Operador guarda nota privada del contexto resuelto.

### 6. Timeout sin respuesta del operador
- CUANDO pasaron 48h desde el escalado y el operador nunca respondió (caso raro pero posible)
- ENTONCES el campo `Escalation.resolved_at` sigue NULL, admin puede detectar e investigar. El cliente puede escribir nuevamente (reactivar conversación).

### 7. Escalado duplicado en ventana de 5 min
- CUANDO el cliente escribe 3 veces "Quiero hablar con alguien" muy rápido, el agente llama `escalar_a_humano` 3 veces en 2 minutos
- ENTONCES `perform_escalation` detecta `duplicate_window=5min` vía DB query, retorna `duplicate_prevented=true`, reutiliza `escalation_id` anterior, y una sola Escalation se crea.

### 8. Escalado con contexto de elemento
- CUANDO el cliente está en EXPEDIENTE mode (`collect_element_data`) y no puede completar fotos de un elemento tras 5 intentos
- ENTONCES escala con `reason="No puedo completar fotos de {element_name}"`, agent guarda `metadata_.element_code=ESCAPE`, operador sabe exactamente qué estaba pasando.

## Reglas duras

1. **Escalado es TERMINAL, NO auto-resume**: una vez seteado `atencion_automatica=false`, el agente NUNCA intenta responder. Solo un admin/operador puede manual setear true nuevamente.

2. **Desactivar bot es CRITICAL**: paso 2 debe completar incluso si 3-5 fallan. Si desactivar bot falla, no continuar; mejor no escalar que escalar parcialmente.

3. **Marcas de escalado en Chatwoot DEBEN existir**: `add_labels(["escalado"])` + private note. Sin estas, el operador no sabe que fue escalado por bot (podría parecer conversación normal delegada).

4. **BD record es persistencia de verdad**: si Chatwoot endpoint cae pero la Escalation se guardó en BD, podemos retryear manualmente. Inversamente, si DB cae, intentamos al menos Chatwoot (best-effort).

5. **Duplicate window es 5 minutos exacto**: no 4:59 ni 5:01. Query: `WHERE triggered_at > NOW() - INTERVAL '5 minutes'`. Re-escalado después de 5min crea nuevo registro.

6. **`escalation_id` es UUID4 (random)**: se genera al momento, único por escalado. Puede referenciarse en operador UI.

7. **`status` siempre inicia en 'pending'**: nunca 'resolved' en creación. Operador marca 'resolved' o 'cancelled' manualmente.

8. **Team assignment es best-effort**: si `CHATWOOT_TEAM_GROUP_ID` no está configurado, simplemente no intentar. Si falla, log warning pero no abortar.

## Mapeo al código

- `agent/services/escalation_service.py:36-292` — `perform_escalation()` función maestra, 6-step flow con try/except en cada paso, duplicate check vía DB query (línea 72-98), Chatwoot update de `atencion_automatica=False` (línea 127-134), labels (línea 149-157), private note (línea 168-198), team assignment (línea 204-221), Escalation DB record creation (línea 228-250).
- `agent/tools/shared_tools.py:56` — `escalar_a_humano` tool, Pydantic args_schema, llama `perform_escalation()`, devuelve dict con `success`, `escalation_id`, `message`.
- `database/models.py` — `Escalation` model: `conversation_id`, `user_id`, `reason`, `source` (tool_call/auto/fallback), `status` (pending/resolved/cancelled), `triggered_at`, JSONB `metadata_` con `user_phone`, `priority`, `is_technical_error`.
- `agent/graph/conversation_graph.py` — Conditional edge que detecta `current_mode="ESCALATION"` y enruta a `escalation_node`.
- Chatwoot API calls: `update_conversation_attributes(conversation_id, {"atencion_automatica": False})`, `add_labels()`, `add_private_note()`, `assign_to_team()`.

## Fuera de alcance

- Interfaz de operador en Chatwoot (admin UI, otro scope)
- Workflow de resolución manual de escalaciones (proceso operativo)
- Reactivación automática del bot (decisión manual de operador o feature futura)
- Notificaciones push a operadores (infra, otro scope)
