---
titulo: Panel admin — conversaciones
ambito: ui
ultima_verificacion_commit:
ultima_verificacion_fecha: 2026-04-17
---

# Panel admin — conversaciones

## Resumen

El área de conversaciones es el corazón operativo del panel: donde los operadores leen el historial de mensajes de cada cliente, gestionan las escalaciones pendientes y acceden a los adjuntos que el cliente envió. Cubre las rutas `/conversations`, `/conversations/[id]` y `/escalations`, y es la sección de mayor uso diario por parte del equipo.

## Escenarios

### 1. Operador entra y ve conversaciones activas
- CUANDO el operador abre sesión y navega a **Conversaciones** (`/conversations`)
- ENTONCES ve una tabla de todas las conversaciones con cliente: fecha, último mensaje, estado. Puede ordenar por fecha. Click en una fila abre el historial completo.

### 2. Operador abre una conversación escalada
- CUANDO el operador hace click en una conversación desde la tabla, navegando a `/conversations/[id]`
- ENTONCES ve el hilo completo de mensajes en orden cronológico. Si está escalada (badge rojo), ve botón "Resolver Escalado". Puede abrirla en Chatwoot (WhatsApp) directamente con botón "Abrir en Chatwoot".

### 3. Operador navega a escalaciones pendientes
- CUANDO abre **Escalaciones** (`/escalations`)
- ENTONCES ve listado de conversaciones pendientes de resolución humana, con resumen del problema y flag de urgencia. Auto-refresca cada 30s. Click para ver detalles, botón "Marcar Resuelto".

### 14. Operador lee mensajes de una conversación específica
- CUANDO navega a `/conversations/[id]` y necesita ver el hilo completo mensaje a mensaje
- ENTONCES el panel llama `GET /api/admin/conversations/{conversation_id}/messages` (paginado: `limit=100`, `offset=0`, orden cronológico)
- Cada mensaje incluye: `role` (user/assistant), `content`, `chatwoot_message_id`, `has_images`, `image_count`, `created_at`
- También disponible: `GET /api/admin/conversations/{conversation_id}/messages/stats` — totales, conteo por rol, conteo con imágenes, primer y último mensaje
- API backend: `api/routes/conversation_messages.py` (2 endpoints)

### 16. Admin resetea una conversación (coordinado)
- CUANDO el admin necesita borrar el estado completo de una conversación (testing, error grave, solicitud del usuario)
- ENTONCES puede disparar un reset coordinado que limpia 4 dominios en orden: **database** (primero, gatekeeper) → **redis** → **files** → **chatwoot** (opcional)
- Si el dominio `database` falla, el reset se aborta sin tocar Redis ni files (contrato DB-first)
- Si Redis o files fallan, se marca `partial_failure=true` pero se considera success si DB limpió correctamente
- Chatwoot solo se limpia si `include_chatwoot=true` en la request
- API backend: `api/services/conversation_reset_coordinator.py` + 4 executors (`_db`, `_redis`, `_files`, `_chatwoot`)

### 16.bis. Operador abre un attachment de un caso
- CUANDO desde una conversación o detalle de caso el operador hace click en un adjunto del cliente (foto de elemento, documentación base, etc.)
- ENTONCES el visor que se abre es polimórfico según el MIME real del asset:
  - Si el MIME es `image/*` (JPG, PNG, WebP) → se abre un visor de imagen (lightbox / preview de imagen estándar del panel)
  - Si el MIME es `application/pdf` → se abre un visor de PDF (iframe/embed/pdf.js dentro del panel o en nueva pestaña del navegador), nunca un visor de imagen
- El nombre del archivo mostrado y el nombre de la descarga reflejan el tipo real y preservan el nombre original que envió el cliente cuando venga presente en el attachment de Chatwoot (p. ej. `permiso_circulacion.pdf` tal cual lo subió el usuario). Si no hay nombre original, se usa el fallback `case_{short}_doc_N.{ext}` con extensión derivada del MIME real (`.pdf`, `.jpg`, `.png`). Nunca `case_{short}_image_N` para un PDF.
- Ver reglas de polimorfismo de adjuntos en [`../../core/adjuntos/polimorfismo.md`](../../core/adjuntos/polimorfismo.md)
- Anti-patrón a eliminar: actualmente al abrir un adjunto que internamente es PDF pero fue clasificado como imagen, el navegador intenta renderizarlo como imagen, falla y bloquea la descarga/visualización. Con el MIME preservado end-to-end (ver regla 13 de `agente/flujos/expediente/flujo.md` y regla 7 de `infra/canal-whatsapp/webhook.md`) el panel puede ramificar correctamente y este anti-patrón deja de reproducirse.

## Reglas duras

### Reglas propias de conversaciones

- Los resets coordinados siempre respetan el contrato DB-first: si la base de datos falla, no se toca ningún otro dominio.
- El visor de attachments no puede forzar todos los adjuntos a un `<img>` o lightbox de imagen genérico — debe ramificar por MIME real.

### Reglas compartidas (aplican a todo el panel)

Las siguientes reglas aplican a TODAS las secciones del panel admin. Los otros 4 archivos de `ui/admin-panel/` las referencian aquí en lugar de duplicarlas.

1. **Client Components obligatorio**: 25/28 rutas son Client (`"use client"`), solo 3 son Server (redirects). Todo fetcheo es client-side con `useEffect` + `api.singleton`.

2. **JWT + RBAC requerido**: login en `/login` con JWT, validado client-side. Contexto `AuthProvider` guarda token + user data. Routes bajo `(authenticated)/` layout check `useAuth()` → redirige a login si falta JWT válido.

3. **Radix UI ONLY, NEVER HTML nativo**: prohibido `<button>`, `<input>`, `<table>`, `<select>` — SIEMPRE desde `@/components/ui/`. Excepciones documentadas: `constraints/page.tsx` y `tool-logs/page.tsx` usan HTML nativo (deuda técnica).

4. **Dialog para CRUD, AlertDialog para destruir**: CREATE/EDIT → Dialog. DELETE → AlertDialog con texto rojo "Esta acción no se puede deshacer". No permitir `window.confirm()`.

5. **Toasts via Sileo, NUNCA `alert()`**: feedback del usuario: `sileo.success({title: "..."})` o `sileo.error({title: "...", description: "..."})`. Toasts top-center, animación gooey SVG.

6. **Español en UI labels**: todos los textos visibles son español — "Guardar", "Cancelar", "Crear", "Eliminar", "¿Estás seguro?", etc.

7. **Validación con Zod**: forms usan schemas Zod; evitar validación ad-hoc en onChange.

8. **Estados loading + error siempre**: todo fetch page: `const [isLoading, setIsLoading] = useState(true)`, `useCallback`, `useEffect`. Render loading spinner, error toast.

9. **Auto-refresh 30s en dashboard / cases / escalations**: `setInterval` cada 30s con cleanup en `useEffect` return.

10. **Debounce search 300ms**: campos de búsqueda no hacen fetch en cada keystroke, esperan 300ms parado.

11. **Admin-only guards**: secciones como `/settings/admin-users`, `/settings/usage`, `/settings/llm-metrics` usan `const { isAdmin } = useAuth()`, renderean "No tenés permisos" si false.

12. **Cierre de Dialog en submit exitoso**: post-mutation → toast success → `setOpen(false)`.

13. **Visor de attachments ramifica por MIME**: los componentes que muestran adjuntos de cliente leen el MIME real del asset (ya preservado end-to-end por backend — ver `infra/canal-whatsapp/webhook.md` regla 7) y seleccionan el visor: imagen → preview de imagen; PDF → visor de PDF (iframe/embed). Queda prohibido forzar todos los adjuntos a un `<img>` o a un lightbox de imagen genérico. El nombre visible y el `download` del link respetan la extensión real del archivo.

## Mapeo al código

| Ruta | Archivo | Líneas | Qué hace |
|------|---------|--------|----------|
| `/conversations` | `admin-panel/src/app/(authenticated)/conversations/page.tsx` | 284 | Tabla conversaciones, sort, delete dialog |
| `/conversations/[id]` | `admin-panel/src/app/(authenticated)/conversations/[id]/page.tsx` | 512 | Historial + botón Chatwoot |
| `/escalations` | `admin-panel/src/app/(authenticated)/escalations/page.tsx` | 473 | Tabla escalaciones, resolve, 30s refresh |
| `GET /api/admin/conversations/{id}/messages` | `api/routes/conversation_messages.py` | — | Historial paginado (limit=100, orden cronológico) |
| `GET /api/admin/conversations/{id}/messages/stats` | `api/routes/conversation_messages.py` | — | Conteos por rol, fechas, imágenes |
| `POST /api/admin/conversations/{id}/reset` | `api/services/conversation_reset_coordinator.py` | — | Reset coordinado DB→Redis→Files→Chatwoot(opt) |

## Fuera de alcance

- `agent/**` — motor LLM, lógica de procesamiento de conversaciones
- `api/**` — backend FastAPI, lógica de negocio de mensajes
- `database/**` — modelos ORM, acceso a datos de conversaciones
- `shared/**` — clientes compartidos (Chatwoot SDK)
