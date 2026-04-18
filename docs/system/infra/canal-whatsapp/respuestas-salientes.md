---
titulo: Canal WhatsApp — respuestas salientes
ambito: infra
ultima_verificacion_commit:
ultima_verificacion_fecha: 2026-04-17
---

# Canal WhatsApp — respuestas salientes

## Resumen

Toda respuesta del sistema hacia el cliente WhatsApp pasa por Chatwoot como intermediario único. El agente llama a `ChatwootClient` para enviar mensajes; Chatwoot los entrega a Meta WhatsApp Business. La restricción más importante es la **ventana de 24 horas de Meta**: si el cliente no escribió en las últimas 24h, solo se puede usar un template preaprobado. Fuera de esa ventana, `send_message()` directo está disponible.

El sistema también tiene un mecanismo de degradación (*panic button*) para detener el bot automáticamente ante situaciones de emergencia operacional.

## Escenarios

### 1. Ventana de 24h abierta — mensaje directo
- CUANDO el cliente escribió hace menos de 24 horas y el agente genera una respuesta
- ENTONCES `ChatwootClient.send_message()` envía el texto directamente vía la API de Chatwoot, normalizando el contenido para WhatsApp (saltos de línea, caracteres especiales). No se requiere template.

### 2. Fuera de ventana de 24h — template obligatorio
- CUANDO pasaron más de 24h desde el último mensaje del cliente y el agente necesita iniciar contacto
- ENTONCES se debe usar `ChatwootClient.send_template_message()` con nombre de template preaprobado en Meta Business Manager, parámetros dinámicos, y categoría UTILITY o MARKETING según corresponda. Usar `send_message()` en este caso resulta en error de Meta.

### 3. Envío de imágenes en batch
- CUANDO el agente necesita enviar múltiples imágenes de ejemplo (ej. fotos de referencia de homologación)
- ENTONCES `ChatwootClient.send_images()` envía las imágenes secuencialmente con un delay configurable entre ellas para evitar flooding del canal.

### 4. Panic button activado — bot silenciado
- CUANDO `atencion_automatica=False` para una conversación
- ENTONCES el sistema no genera ni envía ninguna respuesta de agente. Si es la primera vez (transición de `None` a `False`), puede enviar una auto-respuesta de fuera de servicio antes de silenciarse.

### 5. Chatwoot falla al enviar
- CUANDO `ChatwootClient.send_message()` recibe un error HTTP de la API de Chatwoot
- ENTONCES la excepción se propaga al nodo del agente que inició el envío. No hay fallback automático a Meta directo. La conversación puede quedar sin respuesta hasta que Chatwoot se recupere.

### 6. Respuesta de escalación a agente humano
- CUANDO el agente transiciona a `ESCALATION_MODE`
- ENTONCES el último mensaje enviado indica al cliente que será atendido por un humano. Después de ese envío el bot deja de procesar mensajes del hilo (modo terminal).

## Reglas duras

1. **Ventana de 24h Meta es boundary hard**: si el cliente no escribió hace > 24h, NO usar `send_message()`. Forzar `send_template_message()` con template preaprobado o no responder hasta que el cliente vuelva a escribir.
2. **Chatwoot es intermediario único**: el agente NO comunica directamente con Meta (WhatsApp Cloud API). Si Chatwoot falla, no hay fallback directo.
3. **`atencion_automatica` es toggle maestro**: cuando está `False`, ningún mensaje de agente se envía. El toggle lo setean el webhook (panic button) o el admin panel; el agente no lo modifica por su cuenta.
4. **Templates deben estar preaprobados en Meta**: antes de llamar `send_template_message()` con un nuevo nombre de template, el template debe existir y estar aprobado en Meta Business Manager del número asociado a Chatwoot.

## Mapeo al código

- `shared/chatwoot_client.py:358-654` — `ChatwootClient.send_message()` (dentro de ventana), `send_template_message()` (fuera de ventana), `send_images()` (batch con delay), gestión de contactos y conversaciones.
- `api/routes/chatwoot.py` — sección que detecta `atencion_automatica` y bloquea el pipeline antes de encolar.
- `agent/main.py:79-85` — Identity regex guard para EU AI Act (previene duplicación del texto "asistente con IA" en respuestas sucesivas).

## Fuera de alcance

- Webhook entrante (recepción de mensajes): documentado en `./webhook.md`
- Lógica de qué responder (contenido): responsabilidad de `agent/modes/**`
- Sincronización bidireccional de contactos Chatwoot: `shared/chatwoot_sync.py`
- Templates disponibles y su contenido: gestión en Meta Business Manager, fuera del codebase
- Admin panel toggle de `atencion_automatica`: `api/routes/admin.py`
