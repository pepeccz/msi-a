---
titulo: Modos del agente conversacional
ambito: agente
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Modos del agente conversacional

## Resumen

El agente de MSI-a opera en **modos** — estados macro de la conversación que determinan qué prompts se cargan, qué herramientas están disponibles, y qué reglas de negocio aplican. En un momento dado, el agente está en exactamente un modo. Las transiciones entre modos son explícitas: una herramienta específica las declara, y el grafo de LangGraph las ejecuta.

Hay **dos modos activos** (el cliente puede estar en cualquiera de ellos conversando) y **dos modos terminales** (al que se entra, no se sale normalmente):

| Modo | Qué hace | Tráfico aprox. | Spec detallado |
|------|----------|----------------|----------------|
| **PRE_EXPEDIENTE** | Educa, orienta, presupuesta, muestra fotos de ejemplo | ~90% | [`../flujos/pre-expediente/flujo.md`](../flujos/pre-expediente/flujo.md) |
| **EXPEDIENTE** | Recoge datos formales del caso en 6 sub-modos: elemento → base docs → personal → vehículo → taller → revisión | ~10% | [`../flujos/expediente/flujo.md`](../flujos/expediente/flujo.md) |
| **ESCALATION** | Handoff determinístico a operador humano vía Chatwoot (terminal) | variable | [`../flujos/escalado/flujo.md`](../flujos/escalado/flujo.md) |
| **COMPLETED** | Expediente finalizado — declarado en el enum pero **no usado como modo activo** actualmente (ver nota abajo) | — | — |

**Otros specs relacionados del agente**:
- [`../router/intenciones.md`](../router/intenciones.md) — cómo se decide a qué modo entrar (11 intents)
- [`../estado/conversacional.md`](../estado/conversacional.md) — ConversationState, persistencia Redis, drafts
- [`../herramientas/pre-expediente.md`](../herramientas/pre-expediente.md) y [`../herramientas/expediente.md`](../herramientas/expediente.md) — catálogos de tools por modo
- [`../prompts/pre-expediente.md`](../prompts/pre-expediente.md) y [`../prompts/expediente.md`](../prompts/expediente.md) — qué prompt carga en cada fase

## Nota sobre COMPLETED

`COMPLETED` está declarado como valor válido del enum `ConversationMode` en `conversation_state.py:213` y tiene registro en la tabla de transiciones permitidas (`mode_transitions.py:38-42`: `"EXPEDIENTE_MODE" → "COMPLETED"` permitida; `"COMPLETED": []` — terminal). No tiene aún un toolset propio definido — la selección por modo se hace en `pre_expediente_mode.py::_get_pre_expediente_tools()` y `submodos/_shared.py::_get_*_tools()`, y `COMPLETED` aún no aparece ahí (consistente con la nota de abajo: ningún código activo produce esa transición).

**Importante**: a fecha de verificación (2026-04-17), **ningún código activo produce una transición `_transition_to: "COMPLETED"`**. El router en `conversation_graph.py:682` contempla el caso (`if current_mode in ("COMPLETED", "START"): return END`), pero `finalizar_expediente` no dispara ese transition — el bot pasa a ESCALATION (handoff humano) en lugar de COMPLETED. `COMPLETED` parece diseñado para una futura implementación de flujo post-expediente autónomo, donde el bot volvería a estar disponible para consultas sin handoff humano.

---

## Escenarios

### Transición PRE_EXPEDIENTE → EXPEDIENTE
- CUANDO el cliente está en PRE_EXPEDIENTE, ya ha visto su presupuesto calculado, y responde afirmativamente a la CTA "¿Empezamos con el expediente?"
- ENTONCES el bot llama `confirmar_presupuesto`, el grafo detecta el transition, se cambia a EXPEDIENTE, y el próximo mensaje del bot es la primera petición formal de datos.

### Transición (cualquier modo) → ESCALATION
- CUANDO el cliente pide explícitamente hablar con una persona, O el bot detecta 3+ errores consecutivos en el mismo modo, O aparece una situación fuera de scope (legal, financiera compleja, queja)
- ENTONCES el bot llama `escalar_a_humano`, la conversación se marca como escalada en Chatwoot, el operador humano recibe el hilo completo, y el bot deja de responder automáticamente.

### Modo inicial por defecto
- CUANDO un cliente nuevo envía su primer mensaje
- ENTONCES el agente entra automáticamente en PRE_EXPEDIENTE (no hay otro modo inicial posible).

### Retoma de conversación (recovery)
- CUANDO un cliente vuelve a escribir tras horas o días y tenía una conversación previa persistida
- ENTONCES el agente recupera el último modo y estado vía Redis checkpointer, y continúa desde donde quedó (con posible soft-reminder del presupuesto previo si había uno).

## Reglas duras

- Un cliente **siempre está en exactamente un modo**. No hay "entre modos" ni modos paralelos.
- La transición de modo **solo ocurre a través de una herramienta** que devuelve `_state_update._transition_to: "NUEVO_MODO"`. Nunca por edición directa de state, nunca por heurística de texto.
- **ESCALATION es terminal**: una vez escalado, el agente no vuelve a responder automáticamente en ese hilo (aunque la conversación siga).
- **COMPLETED es terminal declarado, no alcanzado hoy**: el enum lo incluye, el router lo contempla, pero ninguna herramienta lo produce en producción. No asumir que el cliente puede llegar a COMPLETED — ver nota arriba.
- El modo inicial **siempre es PRE_EXPEDIENTE** para clientes nuevos. No existe ruta directa a EXPEDIENTE sin pasar antes por PRE_EXPEDIENTE.
- Las fases internas dentro de un modo (ej. DISCOVERY / PRICING / POST_PRICE en PRE_EXPEDIENTE) se resuelven por **inspección de state**, no por enums de modo. El modo sigue siendo el mismo.

## Mapeo al código

- `agent/graph/conversation_graph.py` — define el StateGraph completo con los nodos por modo y las transiciones condicionales
- `agent/modes/base_mode.py` — clase base `BaseModeNode` con lógica compartida (tool loop, error counter, mode_context)
- `agent/modes/pre_expediente_mode.py:282-562` — `PreExpedienteModeNode`
- `agent/modes/expediente_mode.py` — `ExpedienteModeNode` (no documentado en este prototipo)
- `agent/modes/presupuesto_mode.py` — modo histórico en transición
- `agent/router/intent_router.py` — clasificador de intenciones que determina el modo inicial cuando es ambiguo
- `agent/state/conversation_state.py:251-306` — `ModeContextData` con los campos de state compartidos

## Fuera de alcance

- `agent/tools/**` — los tools no son parte del modelo de modos (ver `../herramientas/pre-expediente.md`)
- `agent/prompts/**` — los prompts no son parte del modelo de modos (ver `../prompts/pre-expediente.md`)
- Cambios al diseño del grafo a nivel LangGraph no-determinista — escape del scope de modos, es diseño de infraestructura conversacional
