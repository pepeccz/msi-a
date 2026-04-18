---
titulo: Adjuntos polimórficos — imágenes y PDFs como ciudadanos de primera clase
ambito: core
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Adjuntos polimórficos — imágenes y PDFs como ciudadanos de primera clase

## Resumen

**HOME CANÓNICO** de las reglas de adjuntos en MSI-a. Este archivo reemplaza la dispersión de reglas que antes vivían repetidas en `chatwoot-whatsapp.md` (regla 7), `flujo-expediente.md` (regla 13) y `paginas-y-flujos.md` (regla 13 y escenario 16.bis).

En MSI-a, un adjunto puede ser una imagen (JPG, PNG, WebP) o un PDF (permiso de circulación, ficha técnica, informe técnico). Ambos tipos son **ciudadanos de primera clase del mismo sistema de attachments**: se reciben por el mismo canal, se validan por paths específicos por tipo, se almacenan con su MIME real, y se visualizan con visores distintos en el panel admin. No existe una abstracción "imagen" que colapse PDFs; no existe un flag de bypass que haga pasar un PDF por el camino de imagen.

El MIME real es la fuente de verdad en toda la cadena: desde el webhook de Chatwoot hasta la URL servida en el panel. Extensión de archivo y `file_type` de Chatwoot son hints, no autoridad.

## Escenarios

### Escenario E1 — Cliente adjunta imagen en paso de recolección
CUANDO el cliente envía un JPG, PNG o WebP durante un paso de recolección de EXPEDIENTE (fotos de elemento o documentación base)
ENTONCES el webhook extrae el adjunto, determina el MIME real inspeccionando el binario (no confiando en la extensión ni en el `file_type` de Chatwoot), lo almacena con `Content-Type: image/jpeg` (o `image/png`, `image/webp` según corresponda), preservando el nombre original del archivo si viene en el payload. El adjunto suma al conteo del paso. El visor en el panel lo renderiza como imagen (lightbox/preview).

### Escenario E2 — Cliente adjunta PDF en paso de recolección
CUANDO el cliente envía un PDF (ej. `permiso_circulacion.pdf`) durante un paso de recolección
ENTONCES el webhook determina MIME real = `application/pdf`, lo almacena con `Content-Type: application/pdf`. El nombre de archivo se preserva si viene en el payload; si no, el fallback es `case_{short}_doc_N.pdf` (extensión `.pdf` derivada del MIME, nunca `case_{id}_image_N`). El PDF pasa por validación `pikepdf` (límite 30 páginas). El adjunto suma al conteo del paso igual que una imagen. El visor en el panel lo renderiza con visor PDF (iframe/embed), nunca como imagen.

### Escenario E3 — Mezcla de imágenes y PDFs en el mismo paso
CUANDO en un único paso de recolección el cliente envía adjuntos heterogéneos en cualquier orden (ej. dos JPG + un PDF en tres mensajes separados)
ENTONCES cada adjunto se procesa independientemente con su MIME real: los JPG por el path de imagen, el PDF por el path de PDF. El conteo del paso suma todos los adjuntos sin distinguir tipos. No hay rechazo por heterogeneidad. No hay flag de bypass ad-hoc: el manejo polimórfico es el camino normal, no la excepción.

### Escenario E4 — Validación rechaza MIME mentiroso
CUANDO un archivo llega con extensión `.jpg` pero su binario es en realidad un PDF (o viceversa)
ENTONCES el sistema inspecciona el binario y determina el MIME real. El archivo se procesa según ese MIME real, ignorando la extensión. Si el MIME real no es soportado (ni `image/*` aceptado ni `application/pdf`), el adjunto se rechaza con mensaje al cliente indicando el tipo no soportado. Ningún archivo se almacena con un MIME que no corresponda a su contenido real.

### Escenario E5 — Operador visualiza adjunto en panel admin
CUANDO un operador hace click en un adjunto desde la vista de conversación o detalle de caso
ENTONCES el panel lee el MIME real del asset (ya preservado en el backend desde la recepción). Si `image/*` → abre lightbox de imagen. Si `application/pdf` → abre visor PDF (iframe/embed dentro del panel o en nueva pestaña). El nombre visible y el nombre de descarga respetan la extensión real y el nombre original del cliente. Nunca se fuerza un PDF en un `<img>` ni en un visor de imagen genérico.

### Escenario E6 — SSRF: URL de adjunto desde Chatwoot
CUANDO el sistema necesita descargar el binario del adjunto desde la URL provista por Chatwoot
ENTONCES la URL pasa primero por `validate_url()` de `shared/image_security.py` antes de cualquier descarga HTTP. Si la URL no supera la validación SSRF, el adjunto se rechaza sin descarga.

## Reglas duras

1. **MIME real preservado end-to-end**: el MIME se determina inspeccionando el binario al momento de validación. Es la fuente de verdad sobre la extensión y sobre el `file_type` de Chatwoot. Ese MIME acompaña al asset en toda la cadena: storage (`Content-Type` real), tabla/record del attachment (`mime_type` real), URL servida al panel (`Content-Type` correcto), extensión del nombre de archivo (`.pdf` si PDF, `.jpg/.png` si imagen).
2. **Naming prohibido**: un archivo con MIME `application/pdf` NO puede almacenarse ni servirse con nombre `case_{id}_image_N` ni con `Content-Type: image/*`. Queda prohibido sin excepciones.
3. **Conteo unificado**: los contadores de adjuntos de un paso de recolección NO distinguen tipo. Un PDF cuenta igual que una imagen para verificar si el paso tiene "al menos 1 adjunto".
4. **Validación por tipo, no genérica**: imágenes con `validate_image_full()` de `shared/image_security.py`; PDFs con `pikepdf` con límite de 30 páginas. No existe una validación genérica que aplique a ambos por igual.
5. **SSRF obligatorio antes de descarga**: toda URL de adjunto proveniente de Chatwoot pasa por `validate_url()` antes de descargarse. Sin excepción.
6. **No existe flag de bypass por tipo**: cualquier flag tipo `base_docs_pdf_bypass` que pretenda "hacer pasar" un PDF por el camino de imagen debe desaparecer. El ramo polimórfico reemplaza el bypass; es el camino normal, no la excepción.
7. **Visor en panel ramifica por MIME**: el componente de visualización de adjuntos en el admin panel selecciona el visor según el MIME real del asset. Queda prohibido forzar todos los adjuntos a `<img>` o a un lightbox de imagen genérico.

## Mapeo al código

- `shared/attachment_utils.py` — utilidades de adjuntos polimórficos: detección de MIME real, naming canónico, conteo unificado (verificar path exacto).
- `shared/image_security.py` — `validate_image_full()` (imágenes), `validate_url()` (SSRF); validación PDF con `pikepdf` puede vivir aquí o en módulo adyacente (verificar).
- `api/routes/chatwoot.py:70-446` — parsing del webhook, extracción de adjuntos, preservación de MIME real en `ChatwootAttachmentEvent`.
- `api/models/chatwoot_webhook.py` — schema `ChatwootAttachmentEvent` con campo `mime_type` real (no derivado de `file_type` de Chatwoot).
- `shared/chatwoot_image_service.py` — descarga y validación de adjuntos; debe ramificar por MIME: imagen → `validate_image_full()`; PDF → `pikepdf`. Flag `base_docs_pdf_bypass` debe desaparecer si existe (verificar).
- Capa de storage (S3/filesystem/tabla de attachments) — guardar `mime_type` real y extensión real con el naming canónico.
- `admin-panel/components/attachment-viewer.tsx` — componente de visualización; ramifica por MIME real: `image/*` → lightbox/preview; `application/pdf` → iframe/embed (verificar path exacto).

## Fuera de alcance

- Canal de entrada WhatsApp y gestión del webhook (→ `../../infra/canal-whatsapp/webhook.md` — no existe aún, Ola 3).
- Seguridad general de adjuntos más allá de MIME y SSRF (→ `../../infra/seguridad-adjuntos/validacion.md` — no existe aún).
- Flujo de recolección de adjuntos en EXPEDIENTE (→ `../../agente/flujos/expediente/flujo.md` — no existe aún, Ola 2).
- Validación de foto como prueba técnica suficiente (ej. ángulos correctos, nitidez) — eso es lógica del agente, no del sistema de adjuntos.
