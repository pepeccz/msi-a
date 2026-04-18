---
titulo: Validación de adjuntos — SSRF, MIME, PDF
ambito: infra
ultima_verificacion_commit:
ultima_verificacion_fecha: 2026-04-17
---

# Validación de adjuntos — SSRF, MIME, PDF

## Resumen

Antes de que cualquier adjunto enviado por un cliente (imagen o PDF) sea procesado o almacenado, el sistema aplica validaciones en múltiples capas. El objetivo es triple: prevenir ataques SSRF (Server-Side Request Forgery) al descargar archivos desde URLs externas, detectar archivos maliciosos o corruptos independientemente de su extensión declarada, y limitar el tamaño y complejidad de PDFs para evitar bombas de procesamiento.

Este archivo documenta la ejecución técnica. Las reglas de negocio sobre qué adjuntos acepta cada paso de recolección se encuentran en `../../core/adjuntos/polimorfismo.md`.

## Escenarios

### 1. URL de adjunto — validación SSRF antes de descarga
- CUANDO el webhook de Chatwoot incluye un `data_url` para descargar un adjunto
- ENTONCES `image_security.validate_url()` verifica que la URL no apunte a rangos privados (127.x, 10.x, 192.168.x, 169.254.x, ::1, etc.), no use esquemas prohibidos (file://, ftp://, etc.), y el hostname resuelva a una IP pública. Si la validación falla, el adjunto se rechaza con error controlado (no se intenta la descarga).

### 2. Imagen recibida — validación multi-capa
- CUANDO la URL pasa la validación SSRF y se descarga el binario
- ENTONCES `validate_image_full()` aplica en secuencia: (a) MIME sniffing a partir de los primeros bytes del binario (no confía en la extensión ni en el `Content-Type` HTTP), (b) verificación de que el MIME detectado esté en la lista de permitidos (`image/jpeg`, `image/png`, `image/webp`), (c) detección de image bomb (dimensiones desproporcionadas que causarían OOM al decodificar), (d) comprobación de integridad básica del archivo. Si cualquier capa falla, el adjunto se rechaza.

### 3. PDF recibido — validación con pikepdf
- CUANDO el MIME sniffing detecta `application/pdf`
- ENTONCES `pikepdf` abre el archivo para verificar que es un PDF válido y no está corrupto, y cuenta las páginas. Si el PDF tiene más de 30 páginas, se rechaza. Si `pikepdf` no puede abrirlo (archivo truncado, cifrado sin contraseña, estructura inválida), se rechaza con error controlado.

### 4. Adjunto rechazado — comportamiento del sistema
- CUANDO una validación falla en cualquiera de las capas
- ENTONCES: el adjunto NO se almacena ni se propaga aguas abajo; el error se loguea a nivel WARNING/ERROR con structlog incluyendo el `message_id` y el motivo; el agente recibe un evento de adjunto rechazado (no un adjunto válido); el cliente puede recibir un mensaje informándole que el archivo no pudo procesarse (según la lógica del modo activo).

### 5. MIME contradice extensión declarada — el MIME gana
- CUANDO un archivo llega con extensión `.jpg` pero los primeros bytes revelan que es un PDF (magic bytes `%PDF`)
- ENTONCES el MIME sniffing detecta `application/pdf` y el archivo se procesa como PDF (incluyendo validación pikepdf), ignorando la extensión declarada. El `file_type` de Chatwoot es solo un hint; el MIME real es la fuente de verdad.

### 6. Mezcla libre en un paso de recolección
- CUANDO un cliente envía JPG + PDF en el mismo paso (ej. fotos de elemento + permiso de circulación)
- ENTONCES cada adjunto pasa por su validación específica: los JPG por `validate_image_full()`, los PDF por pikepdf + límite de páginas. No existe un flag de bypass que omita validación para algún tipo. Ver `../../core/adjuntos/polimorfismo.md` para la regla de que ambos tipos son aceptados en ciertos pasos.

## Reglas duras

1. **SSRF prevention es primera barrera**: `validate_url()` se ejecuta antes de cualquier intento de descarga. Sin este check, una URL maliciosa podría usarse para escanear la red interna.
2. **MIME sniffing desde el binario, no desde la extensión ni `Content-Type`**: la fuente de verdad del tipo de archivo son los primeros bytes del contenido descargado. `file_type` de Chatwoot y la extensión del nombre de archivo son hints no confiables.
3. **Límite de 30 páginas en PDFs es hard**: PDFs de más de 30 páginas se rechazan antes de cualquier procesamiento adicional. No hay excepción por tipo de paso de recolección.
4. **No existe flag de bypass ad-hoc**: ningún parámetro tipo `base_docs_pdf_bypass` puede omitir la validación de adjuntos. El manejo polimórfico por MIME es el único camino normal.
5. **Errores de validación nunca deben romper la conversación**: excepciones en la capa de validación se capturan y se tratan como adjunto rechazado, no como error fatal del webhook.

## Mapeo al código

- `shared/image_security.py` — `validate_url()` (SSRF check), `validate_image_full()` (multi-layer image validation). Contiene lista de rangos de IP privados bloqueados y magic bytes permitidos.
- `shared/chatwoot_image_service.py` (o equivalente de descarga/validación de adjuntos) — rama por MIME: imagen → `validate_image_full()`; PDF → pikepdf + conteo de páginas. La salida es un asset con MIME preservado.
- `api/routes/chatwoot.py` — punto de entrada donde se llama la validación tras detectar adjuntos en el webhook.

## Fuera de alcance

- Reglas de negocio sobre qué adjuntos acepta cada paso: `../../core/adjuntos/polimorfismo.md`
- Naming y storage de adjuntos validados: `../../core/adjuntos/polimorfismo.md`
- Webhook entrante completo: `../canal-whatsapp/webhook.md`
- `agent/modes/**` — decisiones de qué hacer con el adjunto una vez validado
- Almacenamiento externo (S3 o filesystem): configuración en `shared/config.py`
