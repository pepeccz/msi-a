---
titulo: Integración Chatwoot ↔ WhatsApp
ambito: api-chatwoot
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Integración Chatwoot ↔ WhatsApp

## Resumen

WhatsApp → Chatwoot es el **canal único de entrada** de mensajes. Chatwoot actúa como intermediario entre Meta WhatsApp Business y nuestro sistema: recibe webhooks, gestiona contactos bidireccionalmente, y almacena el historial de conversación. El agente consume mensajes desde Redis Streams (persistencia asincrónica) y responde al cliente enviando mensajes de vuelta vía Chatwoot API.

El flujo es determinístico: validación de token → idempotencia → parsing del webhook → sincronización de usuario → encolado en Redis → consumo por el agente → envío de respuesta. Las imágenes adjuntas se extraen y validan; la **ventana de 24h de Meta** se respeta mediante validación del estado conversacional (si fuera de 24h, requiere template preaprobado).

## Escenarios

### 1. Primer mensaje entrante — cliente nuevo
- CUANDO un teléfono nunca antes visto envía su primer mensaje WhatsApp
- ENTONCES la webhook llega a `/webhook/chatwoot/{token}`, se valida token, se extrae info del cliente (nombre, teléfono), se crea automáticamente `User` en DB con `client_type=particular`, se crea `ConversationHistory`, y el mensaje se encola en `incoming_messages:` stream de Redis con `user_id` vinculado.

### 2. Cliente recurrente — sincronización incremental
- CUANDO un teléfono conocido envía un mensaje posterior
- ENTONCES la webhook detecta el `User` existente, sincroniza cambios de nombre/email desde Chatwoot, y el mensaje se encola manteniendo la sesión existente y el `ConversationHistory`.

### 3. Mensaje con imagen JPEG adjunta
- CUANDO el cliente envía una foto, la webhook contiene `attachments[]` con `file_type=image` y `data_url`
- ENTONCES se extrae la lista de adjuntos, se valida tipo MIME, se preserva en `ChatwootAttachmentEvent`, y se pasa al agente (quien en EXPEDIENTE mode puede procesarla como prueba de elemento).

### 4. Mensaje con PDF adjunto
- CUANDO el cliente envía un PDF (ej. recepción técnica)
- ENTONCES se extrae con `file_type=document`, se almacena en `ChatwootAttachmentEvent`, y el agente puede derivarlo a RAG o archivarlo según el contexto.

### 5. Ventana de 24h Meta abierta — mensaje saliente directo
- CUANDO el cliente escribió hace 2 horas y el agente responde
- ENTONCES Chatwoot valida que `conversation.updated_at` esté dentro de 24h, y usa `send_message()` directo (no template) vía API, normalizando el texto para WhatsApp.

### 6. Fuera de ventana de 24h Meta — template required
- CUANDO pasaron 25h desde el último mensaje del cliente y el agente necesita contactar
- ENTONCES debe usar `send_template_message()` con nombre de template preaprobado en Meta, parámetros dinámicos, y categoría UTILITY/MARKETING.

### 7. Cliente nuevo con tipo "professional" — sincronización de tipo
- CUANDO un primer mensaje incluye custom attribute `tipo=Profesional` en Chatwoot
- ENTONCES se crea el `User` con `client_type=professional` en lugar de `particular`, afectando luego la selección de categorías y tarifas disponibles.

### 8. Retomo de cliente 1 mes después — mantención de contexto
- CUANDO un cliente vuelve meses después y la conversación existente sigue siendo la misma ID en Chatwoot
- ENTONCES `ConversationHistory` ya existe, se reutiliza sin duplicación, y el agente puede (opcionalmente) cargar un `DraftQuote` anterior para recuperar contexto de precio.

### 9. Panic button activado — bloqueo automático del bot
- CUANDO la primera webhook de un cliente nuevo llega pero la setting `agent_enabled=false` está activa
- ENTONCES la ruta detecta esto, setea `atencion_automatica=false`, el bot no procesa, y se envía auto-respuesta de fuera de servicio.

### 10. Duplicación de webhook (idempotencia)
- CUANDO Chatwoot reenvía el mismo webhook dos veces dentro de 5 minutos (retry por timeout nuestro)
- ENTONCES Redis SETNX en clave `idempotency:chatwoot:{message_id}` evita procesar dos veces; el segundo webhook retorna 200 OK sin encolar.

## Reglas duras

1. **Ventana de 24h Meta es boundary hard**: si el cliente no escribió hace > 24h, NO usar `send_message()`. Forzar `send_template_message()` con template preaprobado o no responder hasta que el cliente vuelva a escribir.

2. **Token en URL vs API token — dos tokens distintos**: el webhook endpoint usa `CHATWOOT_WEBHOOK_TOKEN` (secreto en URL path para autenticación). API calls usan `CHATWOOT_API_TOKEN` (Bearer header). Nunca mezclar.

3. **Chatwoot es intermediario ÚNICO**: el agente NO comunica directamente con Meta (WhatsApp Cloud API). Todo entra/sale vía Chatwoot. Si Chatwoot falla, la conversación se congela (no hay fallback directo).

4. **Sincronización bidireccional de contacto**: cuando el cliente edita su nombre en WhatsApp, la siguiente webhook sincroniza a `User.first_name/last_name`. PERO `client_type` se establece en creation y nunca se reescribe desde Chatwoot (es atributo del servidor, no del cliente).

5. **`atencion_automatica` es toggle maestro**: si está `False`, la webhook ignora el mensaje completamente (retorna 200 OK). Si es `None` (primera vez), detecta panic button ANTES de setearla, y si panic está activo, setea a `False` automáticamente.

6. **`ConversationHistory` es write-once por conversation_id**: nunca duplicar filas; si existe, se reutiliza. Validar `unique=True` en `conversation_id`.

7. **Attachments validados por tipo MIME**: `file_type` (image, document, audio, video) viene del webhook, no se infiere. El agente decide qué hacer con cada tipo.

8. **Idempotencia TTL = 5 minutos**: después de 5 min, el mismo `message_id` podría procesarse nuevamente. Riesgo bajo porque el contexto conversacional lo detiene.

## Mapeo al código

- `api/routes/chatwoot.py:70-446` — Ruta POST `/webhook/chatwoot/{token}`, validación token, parsing, idempotencia SETNX, sincronización User, creación ConversationHistory, encolado en Redis Streams.
- `api/models/chatwoot_webhook.py` — Schemas Pydantic para webhook payload: `ChatwootWebhookPayload`, `ChatwootMessageEvent`, `ChatwootAttachmentEvent`, E.164 phone validation.
- `shared/chatwoot_client.py:358-654` — `ChatwootClient.send_message()` (directo en ventana), `send_template_message()` (fuera de ventana), `send_images()` (batch con delay), manejo de contactos/conversaciones.
- `shared/chatwoot_sync.py` — `sync_user_to_chatwoot()` (bidireccional name/email/tipo), `sync_agent_to_chatwoot()` (agentes a Chatwoot Platform API).
- `agent/main.py:79-85` — Identity regex guard para EU AI Act (prevenir duplicación de "asistente con IA").
- `shared/redis_client.py` — `add_to_stream()`, `INCOMING_STREAM`, `publish_to_channel()` (fallback pub/sub).
- Redis key: `idempotency:chatwoot:{message_id}`, TTL 300s, SETNX semantics.
- `agent/router/intent_router.py` — consume el mensaje y clasifica el modo.

## Fuera de alcance

- Lógica de respuesta del agente (responsabilidad de `agent/` modes)
- Creación de casos/expedientes (EXPEDIENTE mode)
- RAG query (otro scope: `api/services/rag_service.py`)
- Admin panel gestión de Chatwoot settings (otro scope: `api/routes/admin.py`)
- Sincronización de conversaciones históricas desde Chatwoot (one-way incoming, no backfill)
