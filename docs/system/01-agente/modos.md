---
titulo: Modos del agente conversacional
ambito: agente
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Modos del agente conversacional

## Resumen

El agente de MSI-a opera en **modos** — estados macro de la conversación que determinan qué prompts se cargan, qué herramientas están disponibles, y qué reglas de negocio aplican. En un momento dado, el agente está en exactamente un modo. Las transiciones entre modos son explícitas: una herramienta específica las declara, y el grafo de LangGraph las ejecuta.

Hay **dos modos activos** (el cliente puede estar en cualquiera de ellos conversando) y **un modo terminal** (al que se entra, no se sale):

| Modo | Qué hace | Tráfico aprox. | Spec detallado |
|------|----------|----------------|----------------|
| **PRE_EXPEDIENTE** | Educa, orienta, presupuesta, muestra fotos de ejemplo | ~90% | [`flujo-pre-expediente.md`](./flujo-pre-expediente.md) |
| **EXPEDIENTE** | Recoge datos formales del caso en 6 sub-modos: elemento → base docs → personal → vehículo → taller → revisión | ~10% | [`flujo-expediente.md`](./flujo-expediente.md) |
| **ESCALATION** | Handoff determinístico a operador humano vía Chatwoot (terminal) | variable | [`flujo-escalation.md`](./flujo-escalation.md) |

**Otros specs relacionados del agente**:
- [`router-e-intenciones.md`](./router-e-intenciones.md) — cómo se decide a qué modo entrar (11 intents)
- [`estado-conversacional.md`](./estado-conversacional.md) — ConversationState, persistencia Redis, drafts
- [`herramientas-pre-expediente.md`](./herramientas-pre-expediente.md) y [`herramientas-expediente.md`](./herramientas-expediente.md) — catálogos de tools por modo
- [`prompts-pre-expediente.md`](./prompts-pre-expediente.md) y [`prompts-expediente.md`](./prompts-expediente.md) — qué prompt carga en cada fase

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

- `agent/tools/**` — los tools no son parte del modelo de modos (ver `herramientas-pre-expediente.md`)
- `agent/prompts/**` — los prompts no son parte del modelo de modos (ver `prompts-pre-expediente.md`)
- Cambios al diseño del grafo a nivel LangGraph no-determinista — escape del scope de modos, es diseño de infraestructura conversacional
