---
titulo: Cliente — escenarios de ciclo de vida y casos borde
ambito: core
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Cliente — escenarios de ciclo de vida y casos borde

## Resumen

Este archivo complementa `definicion.md` con los casos borde del ciclo de vida de un Cliente: situaciones que no ocurren en el flujo feliz pero que el sistema debe manejar de forma predecible. Los escenarios cubren clientes que regresan con datos cambiados, clientes professional con acceso diferenciado, y situaciones donde la sincronización con Chatwoot puede entrar en conflicto con el estado interno.

## Escenarios

### Escenario E1 — Cliente nuevo, primer mensaje, creación automática
CUANDO un número de WhatsApp nunca visto envía cualquier mensaje (texto, imagen, audio)
ENTONCES el webhook parsea el payload, extrae `phone` (E164), `name` (perfil Chatwoot), y `client_type` (default `particular` salvo custom attribute `tipo=Profesional`). Se inserta `User` con esos datos. Si la inserción falla por duplicado en `phone` (race condition de dos webhooks simultáneos), la segunda inserción ignora el error (upsert semántico) y continúa con el `User` ya existente.

### Escenario E2 — Cliente recurrente, sincronización incremental
CUANDO un teléfono conocido escribe un nuevo mensaje después de días o semanas
ENTONCES el webhook carga el `User` existente por `phone`. Si el nombre en Chatwoot cambió respecto del nombre en DB, se actualiza `User.first_name / last_name`. Si el email está presente en Chatwoot y difiere del email en DB, se actualiza. El `user_id` no cambia, el historial de conversaciones se preserva, el `client_type` no se toca.

### Escenario E3 — Cliente professional (tipo diferenciado)
CUANDO el contacto en Chatwoot tiene el custom attribute `tipo=Profesional` al momento de su primer webhook
ENTONCES el `User` se crea con `client_type=professional`. Las categorías disponibles para ese usuario son las del catálogo filtradas por `client_type=professional`. Las tarifas professional pueden diferir en precio y en elementos incluidos respecto de las de particular. Si el mismo teléfono más adelante llega SIN el custom attribute, el `client_type` ya establecido no se cambia.

### Escenario E4 — Intento de cambio de tipo durante expediente activo
CUANDO un operador del panel intenta cambiar el `client_type` de un `User` que tiene un `Case` con `status=collecting` o `status=pending_review`
ENTONCES el sistema rechaza la operación con un error claro: "No se puede cambiar el tipo de cliente mientras hay un expediente activo." El operador debe esperar a que el expediente se cierre o escale antes de modificar el tipo.

### Escenario E5 — Cliente bloquea bot (panic activado)
CUANDO la setting `agent_enabled=false` está activa al llegar el primer webhook de un contacto
ENTONCES el webhook crea igualmente el `User` (para tener registro), setea `atencion_automatica=false` en la conversación, y envía auto-respuesta de fuera de servicio. El bot no procesa el mensaje. El `User` queda en DB para cuando el panic se desactive.

### Escenario E6 — Race condition de webhook duplicado
CUANDO Chatwoot reenvía el mismo webhook dos veces dentro de 5 minutos
ENTONCES la clave Redis `idempotency:chatwoot:{message_id}` (SETNX, TTL 300s) bloquea el segundo procesamiento. El `User` y el `ConversationHistory` no se crean dos veces. El segundo webhook retorna 200 OK sin encolar el mensaje.

## Reglas duras

1. **Deduplicación de `User` por teléfono E164**: ningún flujo crea dos `User` con el mismo `phone`. El upsert semántico del webhook es la garantía.
2. **`client_type` se escribe en creación, no se sobreescribe por webhook**: los webhooks subsiguientes pueden cambiar nombre/email pero nunca `client_type`.
3. **La creación de `User` es prerequisito del encolado**: el `user_id` debe estar disponible antes de encolar el mensaje en Redis Streams. Si la creación falla, el mensaje no se encola (no existe procesamiento sin identidad de usuario).
4. **El panic button no bloquea la creación del `User`**: el registro existe incluso si `atencion_automatica=false`. Garantiza trazabilidad.

## Mapeo al código

- `api/routes/chatwoot.py:70-446` — lógica de deduplicación de `User`, upsert, extracción de `client_type` desde custom attributes Chatwoot.
- `database/models.py` — constraint `UNIQUE(phone)` en modelo `User`.
- `shared/chatwoot_sync.py` — sincronización incremental de nombre/email (verificar).

## Fuera de alcance

- Gestión de conversaciones (→ `../conversaciones/definicion.md`).
- Tarifas diferenciadas por `client_type` (→ `../tarifas/calculo.md`).
- Idempotencia completa del webhook (→ `../../infra/canal-whatsapp/webhook.md` — no existe aún, Ola 3).
