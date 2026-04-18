---
titulo: Cliente — identidad, sincronización Chatwoot, tipos
ambito: core
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Cliente — identidad, sincronización Chatwoot, tipos

## Resumen

Un **Cliente** es cualquier persona o empresa que contacta a MSI Automotive por WhatsApp. En MSI-a se representa como la entidad `User` en base de datos y se crea automáticamente al llegar el primer mensaje: el sistema extrae nombre y teléfono del webhook de Chatwoot y genera el registro sin intervención manual.

El Cliente es el ancla de todo lo demás: las conversaciones, los presupuestos y los expedientes siempre pertenecen a un `User`. El tipo de cliente (`particular` o `professional`) determina qué categorías del catálogo se le ofrecen y a qué tarifas tiene acceso. Una vez que ese tipo queda fijado en la primera creación, el sistema no lo sobreescribe desde Chatwoot; solo puede modificarse desde el panel admin.

## Escenarios

### Escenario 1 — Cliente nuevo (primer mensaje)
CUANDO un teléfono nunca visto envía su primer mensaje por WhatsApp
ENTONCES el webhook crea automáticamente un `User` en DB con `client_type=particular`, teléfono en formato E164 (`+34XXXXXXXXX`), nombre extraído del perfil de Chatwoot, y se genera un `ConversationHistory` vinculado. El cliente nunca sabe que su registro fue creado.

### Escenario 2 — Cliente recurrente (sincronización incremental)
CUANDO un teléfono ya registrado vuelve a escribir
ENTONCES el webhook detecta el `User` existente, sincroniza cambios de nombre/email desde Chatwoot si los hay, y encola el mensaje en Redis Streams manteniendo el `user_id` original. No se crea un `User` duplicado.

### Escenario 7 — Cliente con tipo "professional"
CUANDO el primer mensaje de un contacto llega con el custom attribute `tipo=Profesional` en Chatwoot
ENTONCES el `User` se crea con `client_type=professional`. En consultas posteriores, el catálogo filtra categorías por `client_type=professional` (ej. `motos-prof`, `aseicars-prof`) y las tarifas profesionales aplican en lugar de las de particulares.

### Escenario 8 — Cambio de nombre del cliente
CUANDO el cliente actualiza su nombre en WhatsApp y vuelve a escribir
ENTONCES el webhook sincroniza `User.first_name / last_name` con el nuevo valor de Chatwoot. El `client_type` NO cambia: es atributo del servidor, no del cliente.

### Escenario — Bloqueo de sobreescritura de tipo
CUANDO un expediente ya está en curso para ese `User`
ENTONCES el sistema rechaza cualquier cambio de `client_type` vía webhook o API pública. El tipo solo puede modificarse desde el panel admin con rol explícito.

## Reglas duras

1. **Teléfono siempre en E164**: el campo `User.phone` se almacena y valida en formato E164 (`+` + código de país + número, sin espacios). Es la clave de unicidad para deduplicar usuarios.
2. **Creación automática en primer mensaje**: el webhook crea el `User` sin intervención del operador. No existe flujo de "registro de cliente" manual obligatorio para iniciar una conversación.
3. **Sincronización bidireccional de nombre/email**: nombre y email se sincronizan desde Chatwoot en cada webhook. `client_type` se establece en creación y nunca se reescribe desde Chatwoot.
4. **`client_type` inmutable post-expediente**: una vez que hay un `Case` asociado al `User`, el `client_type` no puede cambiar vía webhook ni API pública. Solo edición manual desde el panel admin (ADR a documentar).
5. **Unicidad por teléfono**: constraint `UNIQUE` en `User.phone`. Si llega un webhook con el mismo teléfono, se actualiza el registro existente, nunca se inserta uno nuevo.

## Mapeo al código

- `api/routes/chatwoot.py:70-446` — webhook handler; crea o actualiza `User` en cada mensaje entrante, extrae teléfono, nombre, `client_type` desde payload Chatwoot.
- `shared/chatwoot_sync.py` — `sync_user_to_chatwoot()` (sincronización bidireccional de nombre/email/tipo); verificar paths reales antes de implementar (verificar).
- `database/models.py` — modelo `User` (id UUID v5, phone VARCHAR E164 UNIQUE, first_name, last_name, email, `client_type` ENUM `particular`/`professional`, is_active, created_at).

## Fuera de alcance

- Canal de entrada WhatsApp y gestión del webhook (→ `../../infra/canal-whatsapp/webhook.md` — no existe aún, Ola 3).
- Ciclo de vida de `ConversationHistory` (→ `../conversaciones/definicion.md`).
- Tarifas y catálogo por `client_type` (→ `../catalogo/definicion.md`, `../tarifas/calculo.md`).
