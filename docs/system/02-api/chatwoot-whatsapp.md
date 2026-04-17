---
titulo: Integración Chatwoot ↔ WhatsApp
ambito: api-chatwoot
ultima_verificacion_commit:
ultima_verificacion_fecha: 2026-04-17
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

### 3. Mensaje con imagen JPEG/PNG adjunta
- CUANDO el cliente envía una foto, la webhook contiene `attachments[]` con `file_type=image` y `data_url`
- ENTONCES se extrae la lista de adjuntos, se determina el MIME real (`image/jpeg`, `image/png`, etc.) a partir de la cabecera del binario — no sólo de la extensión ni del `file_type` de Chatwoot —, se preserva en `ChatwootAttachmentEvent` junto con el `file_type` original, y el adjunto viaja aguas abajo manteniendo su MIME real hasta storage y hasta la UI del admin panel. El agente, cuando el paso de recolección actual acepta prueba fotográfica, lo procesa como imagen.

### 4. Mensaje con PDF adjunto
- CUANDO el cliente envía un PDF (ej. permiso de circulación, informe técnico)
- ENTONCES se extrae con `file_type=document`, se determina el MIME real como `application/pdf`, se almacena en `ChatwootAttachmentEvent` con ese MIME preservado, y el adjunto viaja aguas abajo como PDF: NO se re-rotula como imagen, NO se le asigna un nombre sintético tipo `case_{id}_image_N`, y NO entra por un path que eventualmente renderice en visor de imagen. Si el paso de recolección actual acepta PDF (p. ej. documentación base, fotos de elemento), se guarda y se persiste con MIME `application/pdf`.

### 4.bis. Mezcla libre de imágenes y PDFs en el mismo paso
- CUANDO en un único paso de recolección (fotos de elemento o documentación base) el cliente envía una serie de adjuntos heterogénea — ej. dos JPG + un PDF de 4 páginas, en cualquier orden y en cualquier cantidad de mensajes
- ENTONCES cada adjunto se procesa independientemente con su MIME real: los JPG se validan como imagen, los PDF como PDF (incluyendo límite de 30 páginas vía `pikepdf`). El conteo que el sistema lleva para el paso (ej. "has recibido N archivos") suma todos los adjuntos recibidos, sin distinguir tipos y sin rechazar por heterogeneidad. No existe un flag de bypass ad-hoc (tipo `base_docs_pdf_bypass`) para PDFs: el manejo polimórfico es el camino normal.

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

7. **Attachments validados por tipo MIME y preservados end-to-end**: `file_type` (image, document, audio, video) viene del webhook. El MIME específico (`image/jpeg`, `image/png`, `application/pdf`, ...) se determina inspeccionando el binario al momento de validación (fuente de verdad sobre la extensión y sobre el `file_type` chatwootiano) y se persiste junto al asset. Ese MIME acompaña al asset en toda la cadena: storage (S3 o equivalente) guarda el `Content-Type` real, la tabla/record del attachment guarda el MIME real, la URL servida al admin panel sirve con el `Content-Type` correcto, y el nombre de archivo conserva su extensión real (`.pdf` si es PDF, `.jpg/.png` si es imagen). NO existe colapso a "image" cuando el adjunto es PDF. NO existe flag de bypass por paso de recolección que pretenda "hacer pasar" un PDF por imagen en un path común. El agente y la UI ramifican por MIME, no por heurística de nombre.

8. **Idempotencia TTL = 5 minutos**: después de 5 min, el mismo `message_id` podría procesarse nuevamente. Riesgo bajo porque el contexto conversacional lo detiene.

## Mapeo al código

- `api/routes/chatwoot.py:70-446` — Ruta POST `/webhook/chatwoot/{token}`, validación token, parsing, idempotencia SETNX, sincronización User, creación ConversationHistory, encolado en Redis Streams.
- `api/models/chatwoot_webhook.py` — Schemas Pydantic para webhook payload: `ChatwootWebhookPayload`, `ChatwootMessageEvent`, `ChatwootAttachmentEvent`, E.164 phone validation. Debe preservar el MIME real del adjunto y no colapsar PDFs a `image`.
- `shared/chatwoot_image_service.py` (y cualquier servicio equivalente de descarga/validación de adjuntos) — el path que actualmente valida imágenes debe ramificar por MIME: imagen → `validate_image_full()`; PDF → validación con `pikepdf` (hasta 30 páginas). La salida común es un asset con MIME preservado, no un `Image` uniforme. Cualquier flag tipo `base_docs_pdf_bypass` debe desaparecer: deja de existir como concepto, el ramo polimórfico reemplaza el bypass.
- Capa de almacenamiento de adjuntos de caso (S3 / filesystem / tabla de attachments) — guardar `mime_type` real y extensión real. Política de naming:
    - **Preferente**: preservar el nombre original del archivo cuando el attachment del webhook de Chatwoot lo traiga presente (caso típico: el cliente envía `permiso_circulacion.pdf` y ese nombre llega en el payload), sanitizando sólo lo necesario para seguridad del filesystem/URL.
    - **Fallback** cuando el webhook no trae nombre original: `case_{short}_doc_N.{ext}`, donde `{ext}` se deriva del MIME real (`application/pdf` → `.pdf`, `image/jpeg` → `.jpg`, `image/png` → `.png`). Queda PROHIBIDO el nombre `case_{id}_image_N` cuando el MIME sea `application/pdf`.
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
