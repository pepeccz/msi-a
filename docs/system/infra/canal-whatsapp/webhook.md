---
titulo: Canal WhatsApp — webhook entrante (Chatwoot)
ambito: infra
ultima_verificacion_commit:
ultima_verificacion_fecha: 2026-04-17
---

# Canal WhatsApp — webhook entrante (Chatwoot)

## Resumen

WhatsApp → Chatwoot es el **canal único de entrada** de mensajes al sistema. Cada mensaje enviado por un cliente en WhatsApp llega como un HTTP POST a nuestro webhook vía Chatwoot. El flujo es determinístico: validación del token → idempotencia con SETNX en Redis → parsing del payload → sincronización de usuario (ver cross-ref) → encolado en Redis Streams → consumo posterior por el agente.

Chatwoot actúa como intermediario entre Meta WhatsApp Business y nuestro sistema: recibe los webhooks de Meta, gestiona el contacto bidireccional, y almacena el historial de conversación en su propia BD. El agente downstream no habla directamente con Meta.

## Escenarios

### 1. Mensaje entrante — flujo completo
- CUANDO llega un POST a `/webhook/chatwoot/{token}`
- ENTONCES: se valida que el token en la URL coincida con `CHATWOOT_WEBHOOK_TOKEN`; si no coincide, se retorna 401 inmediatamente sin procesar. Si coincide, se extrae el `message_id` del payload.

### 2. Idempotencia — webhook duplicado
- CUANDO Chatwoot reenvía el mismo webhook dos veces dentro de 5 minutos (retry por timeout nuestro)
- ENTONCES Redis ejecuta SETNX en la clave `idempotency:chatwoot:{message_id}` con TTL 300s. Si la clave ya existía (SETNX devolvió 0), el handler retorna 200 OK sin encolar. El segundo webhook es silenciado.

### 3. Mensaje de texto — encolado en Streams
- CUANDO el webhook pasa validación de token e idempotencia y el mensaje es de texto puro
- ENTONCES se parsea el payload Pydantic (`ChatwootWebhookPayload`), se sincroniza el usuario (ver `../../core/clientes/definicion.md`), y el mensaje se agrega al Redis Stream `incoming_messages:` con `XADD`, vinculando el `user_id` resuelto.

### 4. Mensaje con imagen adjunta
- CUANDO el cliente envía una foto y la webhook contiene `attachments[]` con `file_type=image`
- ENTONCES se extrae la lista de adjuntos, se determina el MIME real a partir de la cabecera del binario (no de la extensión ni del `file_type` Chatwoot), se preserva en `ChatwootAttachmentEvent`, y el adjunto viaja aguas abajo con su MIME real hasta storage y hasta la UI del panel. Ver `../../core/adjuntos/polimorfismo.md` para reglas completas de MIME y naming.

### 5. Mensaje con PDF adjunto
- CUANDO el cliente envía un PDF (`file_type=document`)
- ENTONCES se determina MIME real como `application/pdf`, se almacena en `ChatwootAttachmentEvent`, y el adjunto viaja aguas abajo como PDF. NO se re-rotula como imagen, NO se le asigna nombre sintético `case_{id}_image_N`, NO entra por un path que renderice en visor de imagen. Ver `../../core/adjuntos/polimorfismo.md` y `../seguridad-adjuntos/validacion.md` para las validaciones técnicas.

### 6. Mezcla de imágenes y PDFs en el mismo paso
- CUANDO en un paso de recolección el cliente envía una serie heterogénea (ej. dos JPG + un PDF) en cualquier orden y en cualquier cantidad de mensajes
- ENTONCES cada adjunto se procesa independientemente por MIME: JPG como imagen, PDF como PDF. El conteo del paso suma todos los adjuntos sin distinguir tipos. No existe flag de bypass ad-hoc para hacer pasar un PDF por imagen.

### 7. `atencion_automatica=false` — panic button
- CUANDO la primera webhook de un cliente nuevo llega pero la setting `agent_enabled=false` está activa
- ENTONCES la ruta detecta esto, setea `atencion_automatica=false`, el bot no procesa el mensaje, y se envía auto-respuesta de fuera de servicio. Para webhooks posteriores con `atencion_automatica=False` explícito, el handler retorna 200 OK sin encolar.

### 8. TTL de idempotencia expirado
- CUANDO el mismo `message_id` llega después de más de 5 minutos
- ENTONCES Redis no encuentra la clave (`SETNX=1`), el mensaje se procesa nuevamente. Riesgo bajo en la práctica: el contexto conversacional en LangGraph actúa como segunda barrera.

## Reglas duras

1. **Token en URL vs API token — dos tokens distintos**: `CHATWOOT_WEBHOOK_TOKEN` autentica el endpoint webhook (en el path de la URL). `CHATWOOT_API_TOKEN` se usa en las llamadas de vuelta a la API de Chatwoot (Bearer header). Nunca mezclar.
2. **Idempotencia TTL = 5 minutos**: clave Redis `idempotency:chatwoot:{message_id}`, SETNX semántico. Después de 5 min el mismo `message_id` puede ser procesado de nuevo.
3. **`atencion_automatica` es toggle maestro**: si está `False`, la ruta retorna 200 OK sin procesar. Si es `None` (primera vez), detecta panic button ANTES de setearla.
4. **`ConversationHistory` es write-once por `conversation_id`**: nunca duplicar filas; si existe, reutilizar. `conversation_id` tiene índice `unique=True`.
5. **Chatwoot es intermediario único**: el agente NO comunica directamente con Meta. Todo entra vía Chatwoot. Si Chatwoot falla, la conversación se congela (no hay fallback directo a Meta).

## Mapeo al código

- `api/routes/chatwoot.py:70-446` — POST `/webhook/chatwoot/{token}`: validación token, parsing Pydantic, SETNX idempotencia, sincronización User, creación ConversationHistory, XADD a Redis Streams.
- `api/models/chatwoot_webhook.py` — Schemas Pydantic: `ChatwootWebhookPayload`, `ChatwootMessageEvent`, `ChatwootAttachmentEvent`, validación E.164. Preserva MIME real del adjunto.
- `shared/redis_client.py` — `add_to_stream()`, constante `INCOMING_STREAM`, `publish_to_channel()` (fallback pub/sub).
- Redis key de idempotencia: `idempotency:chatwoot:{message_id}`, TTL 300s, SETNX.
- `agent/router/intent_router.py` — consumer del Stream que clasifica el modo.

## Fuera de alcance

- Sincronización de usuario (`api/routes/chatwoot.py` sección sync): documentada en `../../core/clientes/definicion.md`
- Adjuntos polimórficos (reglas MIME, naming, validación): documentados en `../../core/adjuntos/polimorfismo.md` y `../seguridad-adjuntos/validacion.md`
- Respuestas salientes hacia WhatsApp: documentadas en `./respuestas-salientes.md`
- Lógica de respuesta del agente: responsabilidad de `agent/` modes
- Creación de casos/expedientes: EXPEDIENTE mode
- Admin panel gestión de Chatwoot settings: `api/routes/admin.py`
