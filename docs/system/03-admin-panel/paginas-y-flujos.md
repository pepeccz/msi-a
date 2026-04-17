---
titulo: Panel admin — páginas y flujos
ambito: admin-panel
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Panel admin — páginas y flujos

## Resumen

El **Admin Panel** es la interfaz de gestión operativa de MSI-a, donde el owner y el equipo de operaciones manejan el negocio en tiempo real. Es un dashboard web (**Next.js 16 + React 19 + Radix UI**) con **28 rutas y 46 componentes**, usado para 4 funciones centrales:

1. **Ver y resolver conversaciones activas** con clientes — acceder al historial, leer mensajes, saber cuáles están escaladas
2. **Gestionar el catálogo** — crear/editar categorías, tiers de precio, elementos homologables, documentación requerida
3. **Administrar usuarios** — crear operadores, asignar roles, bloquear acceso, ver actividad
4. **Supervisar la salud del sistema** — métricas de tokens, logs de API, estado de servicios, uso de IA

En resumen: es el "cerebro" de operaciones donde todo el negocio se controla manualmente.

## Escenarios

### 1. Operador entra y ve conversaciones activas
- CUANDO el operador abre sesión y navega a **Conversaciones** (`/conversations`)
- ENTONCES ve una tabla de todas las conversaciones con cliente: fecha, último mensaje, estado. Puede ordenar por fecha. Click en una fila = abre el historial completo.

### 2. Operador abre una conversación escalada
- CUANDO el operador hace click en una conversación desde la tabla, navegando a `/conversations/[id]`
- ENTONCES ve el hilo completo de mensajes en orden cronológico. Si está escalada (badge rojo), ve botón "Resolver Escalado". Puede abrirla en Chatwoot (WhatsApp) directamente con botón "Abrir en Chatwoot".

### 3. Operador navega a escalaciones pendientes
- CUANDO abre **Escalaciones** (`/escalations`)
- ENTONCES ve listado de conversaciones pendientes de resolución humana, con resumen del problema y flag de urgencia. Auto-refresca cada 30s. Click para ver detalles, botón "Marcar Resuelto".

### 4. Admin crea una nueva categoría de tarifas
- CUANDO hace click en **Reformas** → botón "Crear Categoría" (abre un Dialog)
- ENTONCES form con campos: nombre, tipo de vehículo (auto/moto/otro), descripción. Click "Guardar" → toast verde "Creado correctamente" → dialog cierra → tabla se refresca.

### 5. Admin edita una tarifa existente
- CUANDO hace click en categoría en la tabla de Reformas → abre `/reformas/[categoryId]`
- ENTONCES ve secciones desplegables: Tiers de precio (básico/premium), Elementos incluidos en cada tier, Documentación requerida, Servicios adicionales. Click "Editar" en cada sección abre un Dialog. Guardar → toast → refresco.

### 6. Admin gestiona elementos del catálogo
- CUANDO hace click en **Elementos** → ver catálogo plano O jerárquico (toggle)
- ENTONCES tabla con elemento, categoría, precio. Click "Nuevo Elemento" abre Dialog con form. Click fila → `/elementos/[id]` con editor completo (imágenes, variantes, campos requeridos, warnings asociados). Save → toast.

### 7. Admin asigna o revoca warnings / requisitos
- CUANDO abre `/advertencias` o desde `/elementos/[id]` botón "Gestionar Warnings"
- ENTONCES Dialog o página donde ve warnings (ej. *"Faro debe tener fotos desde 3 ángulos"*). Click "Crear Warning" form → CRUD estándar Dialog-based. Asocialos a elementos con checkboxes.

### 8. Admin crea usuario nuevo o edita permisos
- CUANDO abre **Usuarios** (`/users`) → botón "Crear Usuario" o click fila → `/users/[id]`
- ENTONCES Dialog de crear con fields: nombre, email, teléfono, rol (operator/admin), estado (activo/bloqueado). Editar en inline form con botón "Guardar Cambios" solo si hay cambios. Delete → AlertDialog rojo "¿Eliminar?".

### 9. Admin ve historial de acceso y actividad
- CUANDO abre **Settings → Admin-Only Sections** (solo admins) → Usuarios Admin (`/settings/admin-users`)
- ENTONCES tabla: usuario, último login, IP, acciones recientes. Log de auditoría. Los cambios de roles/permisos quedan registrados aquí.

### 10. Admin consulta métricas de uso y tokens
- CUANDO abre **Settings → Uso de Tokens** (`/settings/usage`) o **Métricas LLM** (`/settings/llm-metrics`)
- ENTONCES gráficos de: tokens consumidos hoy/mes, costo estimado, promedio por conversación. LLM Metrics muestra qué % del tráfico usa qué modelo (local/cloud, fallbacks).

### 11. Admin monitorea salud del sistema
- CUANDO abre **Settings → Sistema** (`/settings/system`)
- ENTONCES dashboard en vivo: estado de servicios (FastAPI, Redis, PostgreSQL — verde/naranja/rojo), últimos errores de API, logs de Docker en tiempo real (SSE stream), botón "Panic" para apagar agent.

### 12. Operador busca rápido con Cmd+K
- CUANDO presiona **Cmd+K** (o Ctrl+K) desde cualquier página
- ENTONCES abre el command palette de búsqueda global: busca conversaciones, elementos, categorías, usuarios. Enter = navega directo a la página.

### 13. Admin gestiona facturación mensual
- CUANDO abre **Billing** (ruta bajo `/billing` o sección Settings)
- ENTONCES ve historial de facturas con estado (draft→issued→paid/overdue/void), puede descargar PDF, ver monto y período. Ver contrato completo en [`docs/system/04-reglas-negocio/facturacion.md`](../04-reglas-negocio/facturacion.md). API backend: `api/routes/billing.py` (10 endpoints bajo `/api/billing`).

### 14. Operador lee mensajes de una conversación específica
- CUANDO navega a `/conversations/[id]` y necesita ver el hilo completo message a message
- ENTONCES el panel llama `GET /api/admin/conversations/{conversation_id}/messages` (paginado: `limit=100`, `offset=0`, orden cronológico)
- Cada mensaje incluye: `role` (user/assistant), `content`, `chatwoot_message_id`, `has_images`, `image_count`, `created_at`
- También disponible: `GET /api/admin/conversations/{conversation_id}/messages/stats` — totales, conteo por rol, conteo con imágenes, primer y último mensaje
- API backend: `api/routes/conversation_messages.py` (2 endpoints)

### 15. Admin consulta métricas de validación del agente
- CUANDO abre **Settings → Validación** o sección de monitoring
- ENTONCES ve `GET /api/validation-metrics` — estadísticas agregadas del sistema de validación: intentos totales, fallos por tool, tasa de escalación, tasa de éxito en reintento
- Admin puede resetear el contador con `POST /api/validation-metrics/reset` para iniciar nueva ventana de medición
- Acceso: solo admin (requiere JWT + rol admin)
- API backend: `api/routes/validation_metrics.py` — importa `agent.utils.validation_metrics.get_validation_metrics()`

### 16. Admin resetea una conversación (coordinado)
- CUANDO necesita borrar el estado completo de una conversación (testing, error grave, solicitud del usuario)
- ENTONCES puede disparar un reset coordinado que limpia 4 dominios en orden: **database** (primero, gatekeeper) → **redis** → **files** → **chatwoot** (opcional)
- Si el dominio `database` falla → el reset se aborta sin tocar Redis ni files (contrato DB-first)
- Si Redis o files fallan → se marca `partial_failure=true` pero se considera success si DB limpió correctamente
- Chatwoot solo se limpia si `include_chatwoot=true` en la request
- API backend: `api/services/conversation_reset_coordinator.py` + 4 executors (`_db`, `_redis`, `_files`, `_chatwoot`)

## Reglas duras

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

## Mapeo al código

### Rutas principales (~10 relevantes de 28, + rutas de API backend)

| Ruta | Archivo | Líneas | Qué hace |
|------|---------|--------|----------|
| `/dashboard` | `dashboard/page.tsx` | 287 | KPIs, widgets, auto-refresca 30s |
| `/conversations` | `conversations/page.tsx` | 284 | Tabla conversaciones, sort, delete dialog |
| `/conversations/[id]` | `conversations/[id]/page.tsx` | 512 | Historial + botón Chatwoot |
| `/escalations` | `escalations/page.tsx` | 473 | Tabla escalaciones, resolve, 30s refresh |
| `/users` | `users/page.tsx` | 608 | CRUD usuarios, search, filter rol |
| `/users/[id]` | `users/[id]/page.tsx` | 642 | Edit inline, change tracking |
| `/reformas` | `reformas/page.tsx` | 312 | Categorías agrupadas por vehículo |
| `/reformas/[categoryId]` | `reformas/[categoryId]/page.tsx` | 910 | Editor tiers, elementos, docs |
| `/elementos` | `elementos/page.tsx` | 726 | Catálogo elementos, create/delete |
| `/elementos/[id]` | `elementos/[id]/page.tsx` | 1400+ | Editor grande: imágenes, variantes, warnings |
| `/settings/system` | `settings/system/page.tsx` | 1030 | Monitor salud, SSE logs, panic button |
| `/settings/admin-users` | `settings/admin-users/page.tsx` | 866 | Admin CRUD + audit logs (admin-only) |

**Endpoints API adicionales** (no mapeados a rutas propias del panel pero usados por él):

| Endpoint | Backend | Qué hace |
|----------|---------|----------|
| `GET /api/billing/*` | `api/routes/billing.py` | Historial facturas, PDF, Stripe. Ver `facturacion.md` |
| `GET /api/admin/conversations/{id}/messages` | `api/routes/conversation_messages.py` | Historial de mensajes paginado (100/pag, orden cronológico) |
| `GET /api/admin/conversations/{id}/messages/stats` | `api/routes/conversation_messages.py` | Conteos por rol, fechas, imágenes |
| `GET /api/validation-metrics` | `api/routes/validation_metrics.py` | Métricas de validación del agente (admin only) |
| `POST /api/validation-metrics/reset` | `api/routes/validation_metrics.py` | Reset contadores de validación (admin only) |
| `POST /api/admin/conversations/{id}/reset` | `api/services/conversation_reset_coordinator.py` | Reset coordinado DB→Redis→Files→Chatwoot(opt) |

### Componentes UI (21 Radix wrappers, todos activos)

- **Heavy use** (10+ importers): `button` (45), `badge` (37), `card` (29), `dialog` (26), `input` (26), `label` (22), `select` (20), `table` (16), `textarea` (15), `alert-dialog` (12)
- **Moderate** (3-9): `switch` (8), `separator` (6), `tooltip` (4)
- **Light** (1-2): `accordion`, `scroll-area`, `skeleton`, `tabs`, `command`, `error-boundary`, `popover`, `progress`

### Contextos y hooks

- `AuthProvider` (`src/contexts/auth-context.tsx`) — JWT + `useAuth()` = `{ user, isAdmin, hasRole(), logout() }`
- `SidebarProvider` — estado collapsed/expanded persistido en localStorage
- `GlobalSearchProvider` — Cmd+K search state
- `use-category-data.ts` — fetch categoría con tiers/elementos/docs
- `use-global-search.ts` — busca en 5 dominios: páginas, elementos, categorías, tiers, usuarios

### API client (`src/lib/api.ts`)

Singleton `api` con 30+ métodos: `api.getConversations()`, `api.deleteConversation()`, `api.getUsers()`, `api.createUser()`, `api.getVehicleCategories()`, `api.createElement()`, `api.updateElement()`, `api.getWarnings()`, `api.getEscalations()`, etc.

### Tipos TypeScript (`src/lib/types.ts`)

100+ interfaces: `User`, `ConversationHistory`, `VehicleCategory`, `TariffTier`, `Element`, `Warning`, `CaseDetail`, `Escalation`, etc.

### Constants (`src/lib/constants.ts`)

`SEARCH_DEBOUNCE_MS = 300`, `AUTO_REFRESH_INTERVAL_MS = 30000`, `PAGINATION_LIMIT = 25`, límites de archivo, TTLs.

## Fuera de alcance

- `agent/**` — motor LLM, modos (PRE_EXPEDIENTE / EXPEDIENTE), herramientas, prompts
- `api/**` — backend FastAPI, endpoints, lógica de negocio (scope: API)
- `database/**` — modelos ORM, migrations, acceso a datos
- `shared/**` — clientes compartidos (Chatwoot SDK, LLM router)
- Componentes internos que no cambian comportamiento visible: `PageContainer`, `PageHeader`, `FilterBar`, `PaginationControls`, layout helpers
