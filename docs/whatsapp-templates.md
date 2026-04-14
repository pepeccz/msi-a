# Plantillas de WhatsApp — MSI Automotive

## Por que son necesarias

La API de WhatsApp Business (Meta Cloud API) tiene una **ventana de 24 horas**: solo se pueden enviar mensajes de texto libre mientras el cliente haya escrito en las ultimas 24h. Pasado ese tiempo, el unico modo de contactar al cliente es con una **plantilla aprobada por Meta**.

Esto afecta directamente al flujo post-expediente:
- El agente IA finaliza el expediente y avisa al cliente
- Un agente humano de MSI toma el caso (puede tardar >24h)
- El agente humano necesita notificar al cliente

Sin plantillas, si pasan >24h el mensaje del agente humano **falla silenciosamente**.

---

## Plantillas del sistema

### 1. `expediente_tomado`

**Cuando se envia**: Automaticamente cuando un agente humano toma un expediente desde el panel de administracion (`Tomar expediente`).

**Codigo que lo dispara**: `api/routes/cases.py` → `take_case()` → `ChatwootClient.send_template_message()`

**Setting**: `WHATSAPP_TEMPLATE_CASE_ASSIGNED` (default: `"expediente_tomado"`)

| Campo | Valor |
|-------|-------|
| Categoria | `UTILITY` |
| Idioma | `es` (espanol) |
| Variables | `{{1}}` = nombre del cliente, `{{2}}` = nombre del agente, `{{3}}` = email del cliente |

**Texto de la plantilla**:

```
Hola {{1}}, soy {{2}} de MSI Automotive. He tomado tu expediente de homologacion y te escribire a {{3}} para los proximos pasos. Si prefieres seguir por WhatsApp, responde a este mensaje.
```

**Comportamiento**: Best-effort. Si el envio falla (plantilla no aprobada, error de red), el caso se toma igualmente. Se registra un warning en los logs.

---

### 2. `expediente_resuelto`

**Cuando se envia**: Automaticamente cuando un agente humano resuelve un expediente desde el panel de administracion (`Resolver expediente`).

**Codigo que lo dispara**: `api/routes/cases.py` → `resolve_case()` → `_reactivate_bot()` → `ChatwootClient.send_template_message()`

**Setting**: `WHATSAPP_TEMPLATE_CASE_COMPLETED` (default: `"expediente_resuelto"`)

| Campo | Valor |
|-------|-------|
| Categoria | `UTILITY` |
| Idioma | `es` (espanol) |
| Variables | `{{1}}` = nombre del cliente, `{{2}}` = email del cliente |

**Texto de la plantilla**:

```
Hola {{1}}, tu homologacion esta completada. Revisa tu email {{2}} para las instrucciones de recogida e ITV. Gracias por confiar en MSI Automotive.
```

**Comportamiento**: Template-first con fallback. Si el template falla, se envia un mensaje de texto plano (que solo funciona dentro de la ventana de 24h). Si ambos fallan, se registra en logs.

---

## Como crear las plantillas en Meta Business Manager

### Requisitos previos

- Acceso a [Meta Business Manager](https://business.facebook.com/)
- Cuenta de WhatsApp Business verificada
- Numero de telefono vinculado a la WhatsApp Business API

### Paso a paso

#### 1. Acceder al gestor de plantillas

1. Ir a [business.facebook.com](https://business.facebook.com/)
2. En el menu lateral: **WhatsApp** → **Configuracion de la cuenta** → **Plantillas de mensajes**
3. O directamente: **WhatsApp Manager** → **Message Templates**

#### 2. Crear `expediente_tomado`

1. Click en **Crear plantilla**
2. Configurar:
   - **Nombre**: `expediente_tomado`
   - **Categoria**: `Utility` (Utilidad)
   - **Idioma**: `Spanish (es)` — Espanol
3. En el editor del cuerpo del mensaje:
   ```
   Hola {{1}}, soy {{2}} de MSI Automotive. He tomado tu expediente de homologacion y te escribire a {{3}} para los proximos pasos. Si prefieres seguir por WhatsApp, responde a este mensaje.
   ```
4. Anadir las variables de ejemplo (Meta las requiere para la revision):
   - `{{1}}`: `Pepe`
   - `{{2}}`: `Carlos`
   - `{{3}}`: `pepe@email.com`
5. **Opcional pero recomendado**: Anadir un boton de respuesta rapida:
   - Tipo: **Quick Reply**
   - Texto del boton: `Continuar por WhatsApp`
6. Click en **Enviar para revision**

#### 3. Crear `expediente_resuelto`

1. Click en **Crear plantilla**
2. Configurar:
   - **Nombre**: `expediente_resuelto`
   - **Categoria**: `Utility` (Utilidad)
   - **Idioma**: `Spanish (es)` — Espanol
3. En el editor del cuerpo del mensaje:
   ```
   Hola {{1}}, tu homologacion esta completada. Revisa tu email {{2}} para las instrucciones de recogida e ITV. Gracias por confiar en MSI Automotive.
   ```
4. Variables de ejemplo:
   - `{{1}}`: `Pepe`
   - `{{2}}`: `pepe@email.com`
5. Click en **Enviar para revision**

#### 4. Esperar aprobacion

- Las plantillas de categoria **Utility** suelen aprobarse en **minutos a pocas horas**.
- Si se rechazan, los motivos comunes son:
  - Contenido demasiado generico o vago
  - Falta de contexto en las variables de ejemplo
  - Contenido que parece promocional (usar Utility, no Marketing)
- Se puede volver a enviar corrigiendo el motivo de rechazo.

#### 5. Verificar en Chatwoot

Una vez aprobadas:
1. Ir al panel de Chatwoot → **Settings** → **Inboxes** → inbox de WhatsApp
2. En la seccion de templates, verificar que aparecen `expediente_tomado` y `expediente_resuelto`
3. Chatwoot sincroniza las plantillas automaticamente (puede tardar unos minutos)

---

## Configuracion en el sistema

Las plantillas se referencian por nombre en `shared/config.py`:

```python
WHATSAPP_TEMPLATE_CASE_ASSIGNED = "expediente_tomado"
WHATSAPP_TEMPLATE_CASE_COMPLETED = "expediente_resuelto"
```

Si necesitas cambiar el nombre de una plantilla (por ejemplo, porque Meta rechazo el nombre original), actualiza el valor en el `.env` del servidor:

```env
WHATSAPP_TEMPLATE_CASE_ASSIGNED=expediente_tomado_v2
WHATSAPP_TEMPLATE_CASE_COMPLETED=expediente_resuelto_v2
```

No requiere cambios en el codigo.

---

## Formato de variables (referencia tecnica)

El sistema envia las variables como un dict con claves posicionales (`"1"`, `"2"`, `"3"`) que Chatwoot mapea a `{{1}}`, `{{2}}`, `{{3}}` en la plantilla de Meta:

```python
body_params={"1": "Pepe", "2": "Carlos", "3": "pepe@email.com"}
```

El payload que Chatwoot envia a la API de Meta:

```json
{
  "content": "Template: expediente_tomado",
  "message_type": "outgoing",
  "template_params": {
    "name": "expediente_tomado",
    "category": "UTILITY",
    "language": "es",
    "processed_params": {
      "body": {"1": "Pepe", "2": "Carlos", "3": "pepe@email.com"}
    }
  }
}
```

---

## Costes

| Concepto | Coste aproximado |
|----------|-----------------|
| Template Utility (fuera de ventana 24h) | ~0.035 EUR por conversacion |
| Template Utility (dentro de ventana 24h) | Gratis (cubierto por la conversacion de servicio) |
| Primeras 1,000 conversaciones de servicio/mes | Gratis |

Con un volumen estimado de 50 expedientes/mes, el coste de templates es de **~1.75 EUR/mes** en el peor caso.

---

## Plantillas futuras (pendientes de implementar)

Estas plantillas no estan implementadas en el codigo pero podrian ser utiles:

| Nombre propuesto | Uso | Variables |
|-----------------|-----|-----------|
| `expediente_recordatorio` | Recordar al cliente que tiene documentacion pendiente | `{{1}}` nombre, `{{2}}` que falta |
| `ventana_expirando` | Pedir al cliente que responda antes de que cierre la ventana 24h | `{{1}}` nombre |
| `expediente_info_adicional` | Agente humano necesita mas informacion | `{{1}}` nombre, `{{2}}` que se necesita |

---

**Ultima actualizacion**: Abril 2026
