---
titulo: ConversationHistory — entidad write-once, ciclo de vida
ambito: core
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# ConversationHistory — entidad write-once, ciclo de vida

## Resumen

`ConversationHistory` es el registro que vincula un `User` con una conversación específica de Chatwoot. Se crea automáticamente al llegar el primer mensaje de un número, usando el `conversation_id` de Chatwoot como clave de unicidad. Una vez creado, el registro **no se duplica**: si el mismo `conversation_id` vuelve a aparecer (cliente recurrente, webhook repetido), el sistema reutiliza la fila existente.

Su rol es de nexo de identidad: no almacena los mensajes individuales ni el estado del agente (eso vive en Redis con el checkpoint de LangGraph), sino que provee el ancla para asociar `DraftQuote`, `Case` y el historial de mensajes consultable desde el panel admin. Un cliente puede tener múltiples conversaciones a lo largo del tiempo, cada una con su propio `ConversationHistory`.

## Escenarios

### Escenario 1 — Creación en primer mensaje
CUANDO llega el primer webhook de un teléfono con un `conversation_id` nuevo
ENTONCES se inserta una fila `ConversationHistory` con ese `conversation_id`, el `user_id` del `User` ya creado (o creado en el mismo webhook), y `created_at` = ahora. Si ya existe una fila con ese `conversation_id` (por webhook duplicado), se reutiliza sin insertar una nueva.

### Escenario 2 — Cliente recurrente, misma conversación Chatwoot
CUANDO el mismo `conversation_id` de Chatwoot aparece en un webhook posterior (cliente que vuelve meses después)
ENTONCES el sistema detecta que `ConversationHistory` ya existe para ese `conversation_id`, no inserta duplicado, y el mensaje se asocia a la conversación existente. El agente puede recuperar el `DraftQuote` asociado para rehidratar contexto de precio.

### Escenario 3 — Consulta de mensajes desde panel admin
CUANDO un operador abre la página de una conversación en el panel (`/conversations/[id]`)
ENTONCES el panel llama `GET /api/admin/conversations/{conversation_id}/messages` usando el `conversation_id` de la fila `ConversationHistory`. Devuelve mensajes paginados en orden cronológico con `role`, `content`, `created_at`, `has_images`, `image_count`.

### Escenario 4 — Vínculo con DraftQuote
CUANDO en PRE_EXPEDIENTE el agente calcula un presupuesto para una conversación
ENTONCES se crea o actualiza un `DraftQuote` con `conversation_id` como clave de FK. Si el cliente vuelve días después por el mismo `conversation_id`, el `DraftQuote` activo se carga automáticamente para rehidratar el contexto de precio sin que el cliente tenga que repetir su consulta.

### Escenario 5 — Lifecycle: conversación completada
CUANDO un expediente asociado a una conversación alcanza `status=pending_review`
ENTONCES la `ConversationHistory` se mantiene en DB con la misma fila (no se borra ni se archiva automáticamente). El panel admin muestra la conversación como completada. El historial queda disponible para auditoría.

## Reglas duras

1. **Write-once por `conversation_id`**: nunca se insertan dos filas `ConversationHistory` con el mismo `conversation_id`. Constraint `UNIQUE(conversation_id)` en DB.
2. **FK a `User` obligatoria**: toda `ConversationHistory` tiene un `user_id` válido. No existe conversación sin cliente conocido.
3. **No almacena mensajes individuales**: los mensajes viven en el modelo `ConversationMessage` (o similar) y en Redis checkpoint. `ConversationHistory` es solo el ancla de identidad.
4. **Soft delete si aplica**: si una conversación se "resetea" desde el panel admin, el reset coordinado (DB → Redis → Files → Chatwoot) borra los datos asociados con el orden correcto. La fila `ConversationHistory` puede eliminarse como parte de ese reset, no de forma aislada.

## Mapeo al código

- `api/routes/chatwoot.py:70-446` — crea `ConversationHistory` en primer webhook, detecta existente en webhooks subsiguientes.
- `database/models.py` — modelo `ConversationHistory` (id UUID, conversation_id VARCHAR UNIQUE, user_id FK → User, created_at, updated_at).
- `api/routes/conversation_messages.py` — endpoints `GET /api/admin/conversations/{id}/messages` y `/messages/stats` (usan `conversation_id` de `ConversationHistory` como clave).
- `api/services/conversation_reset_coordinator.py` — reset coordinado que puede borrar la fila como parte del flujo DB-first.

## Fuera de alcance

- Estado conversacional del agente (checkpoint LangGraph en Redis → `../../agente/flujos/estado-conversacional.md` futuro).
- Presupuestos asociados a la conversación (→ `../presupuestos/draft-quote.md`).
- Canal de entrada WhatsApp (→ `../../infra/canal-whatsapp/webhook.md` — no existe aún, Ola 3).
