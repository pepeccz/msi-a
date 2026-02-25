# Plan: UX Improvements Admin Panel — Fases 2 y 3

> **Status**: 🟡 Proposed  
> **Created**: 2026-02-24  
> **Updated**: 2026-02-24  
> **Priority**: 🟡 Medium

---

## Resumen Ejecutivo

Mejoras de usabilidad del admin panel de MSI-a en dos fases: la Fase 2 corrige inconsistencias visuales y de UX sin cambios arquitectónicos (KPI colors, CTA en errores, display names en Tool Logs, sección de accesos rápidos), y la Fase 3 introduce refactors estructurales (componente KPI reutilizable con href, ocultación inteligente de columnas vacías en Usuarios, breadcrumbs, y badges de urgencia en sidebar con estado global de errores del sistema). La Fase 1 (quick wins) ya está completada.

---

## Problema

### Contexto

Tras aplicar los quick wins de Fase 1, quedan 8 problemas UX de esfuerzo medio/mayor que requieren un plan de implementación estructurado. Afectan exclusivamente al Admin Panel (sin cambios en API, Agent ni Database).

### Pain Points Verificados en Código

- **KPI "En Recolección"** (`dashboard/page.tsx:151`): valor tiene `text-blue-600` hardcoded — parece link aunque sea 0
- **KPI "Resueltos Hoy"** (`dashboard/page.tsx:175`): `text-green-600` hardcoded aunque el valor sea 0 (verde vacío no tiene significado)
- **Errores abiertos** (`system-health.tsx:196-202`): badge sin CTA, no navega a ningún lado
- **RAG status** (`system-health.tsx:158-169`): solo dos estados en tipo (`"healthy" | "degraded"`), los tres componentes (embedding, qdrant, reranker) permiten definir "Degradado" cuando alguno falla
- **Tool Logs** (`tool-logs/page.tsx:183`): `log.tool_name` directo, usa `<table>` HTML nativo (deuda técnica conocida)
- **Accesos Rápidos** (`dashboard/page.tsx:191-233`): duplica exactamente el sidebar; el componente `RecentActivity` ya existe y está en la misma página — la sección de quick access es redundante
- **KPI cards de Expedientes** (`cases/page.tsx:203-263`): son `<Card>` planas sin `cursor-pointer` ni `href`
- **KPI cards de Escalaciones** (`escalations/page.tsx:246-299`): ídem
- **Columnas vacías en Usuarios** (`users/page.tsx:279-287`): Email, Empresa, NIF/CIF siempre visibles aunque muestren "–"
- **Sin breadcrumbs** (`layout.tsx`): el layout compartido no tiene breadcrumb component
- **Sidebar badges de errores del sistema**: existe polling para escalaciones/casos, pero NO para errores del contenedor

---

## Servicios Afectados

- [ ] Agent (`agent/`) — No afectado
- [ ] API (`api/`) — No afectado (endpoints existentes son suficientes)
- [x] Admin Panel (`admin-panel/`) — Todo el trabajo está aquí
- [ ] Database (`database/`) — No afectado
- [ ] Shared (`shared/`) — No afectado

---

## Contratos Verificados

Interfaces existentes que este plan usa (sin modificar):

| Interfaz | Archivo leído | Campo usado |
|---|---|---|
| `RAGHealthStatus.status` | `types.ts:1075-1088` | `"healthy" \| "degraded"` |
| `RAGHealthStatus.components` | `types.ts:1077-1087` | `embedding_service`, `qdrant`, `reranker` (boolean) |
| `ContainerErrorStats.total_open` | `types.ts:943-948` | Para CTA en errores |
| `ContainerErrorStats.by_service` | `types.ts:943-948` | Para filtro en URL de destino |
| `api.getContainerErrors(params)` | `api.ts:840-853` | Endpoint `/api/admin/system/errors` |
| `CaseStats` | `types.ts:1263-1271` | `pending_review`, `in_progress`, `collecting`, `resolved_today` |
| `EscalationStats` | `types.ts:1116-1121` | `pending`, `in_progress`, `resolved_today`, `total_today` |
| `ToolCallLog.tool_name` | `types.ts` (via `tool-logs/page.tsx:183`) | String snake_case a mapear |
| `DashboardKPIs` | `types.ts:196-208` | `cases_collecting`, `cases_resolved_today`, `escalations_resolved_today` |
| `sidebar.tsx:269-303` | Leído | `pendingEscalations`, `pendingCases` ya disponibles |

---

## Tareas por Servicio

### Admin Panel — Fase 2 → **frontend-dev**

**Responsable**: frontend-dev  
**Prioridad**: 1 (sin dependencias externas)  
**Estimado**: 4-6 horas

---

#### P1: CTA en errores + Estados RAG claros

**Archivos a modificar**: `admin-panel/src/components/dashboard/system-health.tsx`

**1a. Añadir CTA (enlace) a la badge de errores abiertos**

En la sección de errores abiertos, la badge con `openErrorsCount > 0` no es clickable. Convertir a `<Link>`:

```tsx
// ANTES:
{openErrorsCount > 0 ? (
  <Badge variant="destructive">{openErrorsCount}</Badge>
) : (
  <Badge variant="outline" className="bg-green-50 ...">0</Badge>
)}

// DESPUÉS:
{openErrorsCount > 0 ? (
  <Link href="/settings/system?tab=errors">
    <Badge
      variant="destructive"
      className="cursor-pointer hover:opacity-80 transition-opacity"
    >
      {openErrorsCount}
    </Badge>
  </Link>
) : (
  <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
    0
  </Badge>
)}
```

Añadir `import Link from "next/link"` si no está.

**1b. Definir estado "Degradado" para RAG**

```tsx
// Helper RAG-específico (nuevo):
const getRagStatusBadge = (rag: RAGHealthStatus) => {
  if (rag.status === "healthy") {
    return (
      <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
        OK
      </Badge>
    );
  }
  const failingCount = [
    rag.components.embedding_service,
    rag.components.qdrant,
    rag.components.reranker,
  ].filter((c) => c === false).length;

  if (failingCount >= 2) {
    return <Badge variant="destructive">Error</Badge>;
  }
  return (
    <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-200">
      Degradado
    </Badge>
  );
};
```

Reemplazar el uso actual de `getStatusBadge(health.rag.status === "healthy")` por `getRagStatusBadge(health.rag)`.

**Criterio de aceptación**:
- [ ] Badge de errores > 0 es clickable y navega a `/settings/system`
- [ ] Badge de errores = 0 sigue siendo verde, no clickable
- [ ] RAG muestra "OK" / "Degradado" / "Error" según estado real de sus 3 componentes
- [ ] Ningún componente existente se rompe

---

#### P2: Eliminar "Accesos Rápidos" redundantes

**Archivos a modificar**: `admin-panel/src/app/(dashboard)/dashboard/page.tsx`

Eliminar el bloque completo de "Accesos Rápidos" (sección con las 6 tarjetas que duplican el sidebar).

Actualizar el grid inferior para dar más espacio a RecentActivity:
```tsx
<div className="grid gap-6 lg:grid-cols-3">
  <div className="lg:col-span-2">
    <RecentActivity />
  </div>
  <div>
    <SystemHealth />
  </div>
</div>
```

Limpiar imports sin usar (`QuickAccessCard` si no se usa en otro sitio).

**Criterio de aceptación**:
- [ ] Dashboard no muestra sección "Accesos Rápidos" con las 6 tarjetas
- [ ] `RecentActivity` ocupa `lg:col-span-2`
- [ ] No hay imports sin usar
- [ ] La navegación del sidebar sigue siendo idéntica

---

#### P3: Colores KPI condicionales en Dashboard

**Archivos a modificar**: `admin-panel/src/app/(dashboard)/dashboard/page.tsx`

- "En Recolección": eliminar `text-blue-600` hardcoded → usar color neutro (el dato es informativo, no urgente)
- "Resueltos Hoy": `text-green-600` solo si el valor > 0; si = 0, usar `text-muted-foreground`

```tsx
{/* En Recolección — ANTES: text-blue-600 hardcoded */}
{/* DESPUÉS: sin clase de color */}
<div className="text-2xl font-bold">
  {kpis?.cases_collecting ?? 0}
</div>

{/* Resueltos Hoy — ANTES: text-green-600 hardcoded */}
{/* DESPUÉS: condicional */}
<div className={`text-2xl font-bold ${
  ((kpis?.cases_resolved_today ?? 0) + (kpis?.escalations_resolved_today ?? 0)) > 0
    ? "text-green-600"
    : "text-muted-foreground"
}`}>
  {(kpis?.cases_resolved_today ?? 0) + (kpis?.escalations_resolved_today ?? 0)}
</div>
```

**Criterio de aceptación**:
- [ ] "En Recolección" con valor 0 → color neutro (no azul)
- [ ] "Resueltos Hoy" con valor 0 → `text-muted-foreground` (gris)
- [ ] "Resueltos Hoy" con valor > 0 → `text-green-600` (verde)
- [ ] "Expedientes Pendientes" y "Escalaciones Pendientes" no se tocan

---

#### P4: Display names en Tool Logs

**Archivos a modificar**: `admin-panel/src/app/(dashboard)/tool-logs/page.tsx`

Añadir constante `TOOL_DISPLAY_NAMES` y helper `getToolDisplayName` antes del componente:

```tsx
const TOOL_DISPLAY_NAMES: Record<string, string> = {
  // Element tools
  identificar_y_resolver_elementos: "Identificar Elementos",
  obtener_elementos_disponibles: "Listar Elementos Disponibles",
  seleccionar_variante_por_respuesta: "Seleccionar Variante",
  confirmar_elementos_seleccionados: "Confirmar Elementos",
  obtener_campos_elemento: "Obtener Campos de Elemento",
  verificar_elementos_identificados: "Verificar Elementos",
  listar_variantes_elemento: "Listar Variantes",
  resolver_ambiguedad_elemento: "Resolver Ambigüedad",
  // Tariff tools
  calcular_tarifa_con_elementos: "Calcular Tarifa",
  obtener_advertencias_tarifa: "Obtener Advertencias",
  obtener_resumen_tarifa: "Resumen de Tarifa",
  verificar_tarifa_calculada: "Verificar Tarifa",
  // Case tools
  crear_expediente: "Crear Expediente",
  actualizar_expediente: "Actualizar Expediente",
  finalizar_expediente: "Finalizar Expediente",
  obtener_expediente_activo: "Obtener Expediente Activo",
  verificar_expediente_completo: "Verificar Expediente",
  cancelar_expediente: "Cancelar Expediente",
  registrar_documentacion: "Registrar Documentación",
  verificar_documentacion: "Verificar Documentación",
  // Element data tools
  iniciar_recoleccion_datos: "Iniciar Recolección de Datos",
  completar_elemento_actual: "Completar Elemento Actual",
  obtener_siguiente_elemento: "Siguiente Elemento",
  guardar_dato_elemento: "Guardar Dato de Elemento",
  verificar_datos_elemento: "Verificar Datos de Elemento",
  listar_elementos_pendientes: "Listar Elementos Pendientes",
  resumen_datos_recolectados: "Resumen de Datos",
  // Image tools
  enviar_imagenes_ejemplo: "Enviar Imágenes de Ejemplo",
  // Vehicle tools
  clasificar_vehiculo: "Clasificar Vehículo",
  // Shared tools
  escalar_a_humano: "Escalar a Humano",
};

const getToolDisplayName = (toolName: string): string => {
  return TOOL_DISPLAY_NAMES[toolName] ?? toolName.replace(/_/g, " ");
};
```

Cambios en la tabla:
```tsx
{/* Columna Tool — ANTES: */}
<td className="p-2 font-mono text-xs">{log.tool_name}</td>

{/* DESPUÉS: display name + tooltip nativo con nombre técnico */}
<td className="p-2 text-xs">
  <span title={log.tool_name} className="cursor-help">
    {getToolDisplayName(log.tool_name)}
  </span>
</td>
```

Cambios en el select de filtro:
```tsx
{toolNames.map((name) => (
  <option key={name} value={name}>
    {getToolDisplayName(name)}
  </option>
))}
```

Cambios en stat cards del top (donde usa `replace(/_/g, " ")`):
```tsx
{/* ANTES: */}
{stat.tool_name.replace(/_/g, " ")}

{/* DESPUÉS: */}
{getToolDisplayName(stat.tool_name)}
```

**Criterio de aceptación**:
- [ ] Columna "Tool" muestra "Calcular Tarifa" en lugar de "calcular_tarifa_con_elementos"
- [ ] Hovering muestra el nombre técnico original en tooltip nativo (`title`)
- [ ] Dropdown de filtros muestra nombres legibles
- [ ] Stat cards del top muestran nombres legibles
- [ ] El valor del filtro sigue siendo el snake_case original (la API lo requiere)
- [ ] Tools sin mapeo muestran snake_case con espacios (fallback)

---

### Admin Panel — Fase 3 → **frontend-dev**

**Responsable**: frontend-dev  
**Prioridad**: 2 (después de Fase 2)  
**Estimado**: 8-12 horas

---

#### P5: KPI cards clickables — Componente `StatCard` reutilizable

**Archivos a crear**:
- `admin-panel/src/components/dashboard/stat-card.tsx`

**Archivos a modificar**:
- `admin-panel/src/app/(dashboard)/cases/page.tsx`
- `admin-panel/src/app/(dashboard)/escalations/page.tsx`
- `admin-panel/src/app/(dashboard)/dashboard/page.tsx`
- `admin-panel/src/components/dashboard/index.ts`

**Interfaz del componente**:
```tsx
interface StatCardProps {
  title: string;
  value: number | string;
  subtitle?: string;
  icon: LucideIcon;
  /** Color semántico del valor numérico */
  valueColor?: "red" | "yellow" | "green" | "blue" | "neutral";
  /** Si se provee, la card entera es clickable */
  href?: string;
  /** Si true, aplicar color solo si value > 0 */
  conditionalColor?: boolean;
  isLoading?: boolean;
}
```

**Regla de colores**:
```tsx
const getValueClass = (
  color: StatCardProps["valueColor"],
  value: number | string,
  conditional: boolean
) => {
  if (conditional && Number(value) === 0) return "text-muted-foreground";
  switch (color) {
    case "red":    return "text-red-600";
    case "yellow": return "text-yellow-600";
    case "green":  return "text-green-600";
    case "blue":   return "text-blue-600";
    default:       return "";
  }
};
```

El componente wrappea su contenido en `<Link href={href}>` si `href` existe, o en `<div>` si no. Cards con `href` tienen `cursor-pointer hover:shadow-md transition-shadow`.

**Uso en `cases/page.tsx`**:
```tsx
<StatCard title="Pendientes" value={stats.pending_review}
  subtitle="Esperando revisión" icon={Inbox}
  valueColor="red" conditionalColor={false}
  href="/cases?status=pending_review" />
<StatCard title="En Progreso" value={stats.in_progress}
  subtitle="Siendo atendidos" icon={Play}
  valueColor="yellow" conditionalColor={true}
  href="/cases?status=in_progress" />
<StatCard title="Resueltos Hoy" value={stats.resolved_today}
  subtitle="Completados hoy" icon={CheckCircle2}
  valueColor="green" conditionalColor={true} />
<StatCard title="Recolectando" value={stats.collecting}
  subtitle="Recopilando datos" icon={Clock}
  valueColor="neutral"
  href="/cases?status=collecting" />
```

**Uso en `escalations/page.tsx`**:
```tsx
<StatCard title="Pendientes" value={stats.pending}
  subtitle="Requieren atención" icon={AlertTriangle}
  valueColor="red" conditionalColor={false}
  href="/escalations?status=pending" />
<StatCard title="En Progreso" value={stats.in_progress}
  subtitle="Siendo atendidas" icon={RefreshCw}
  valueColor="yellow" conditionalColor={true}
  href="/escalations?status=in_progress" />
<StatCard title="Resueltas Hoy" value={stats.resolved_today}
  subtitle="Completadas hoy" icon={CheckCircle2}
  valueColor="green" conditionalColor={true} />
<StatCard title="Total Hoy" value={stats.total_today}
  subtitle="Generadas hoy" icon={Clock}
  valueColor="neutral" />
```

**Nota sobre filtros por URL**: Las páginas `/cases` y `/escalations` leen `statusFilter` de `useState`, no de `useSearchParams`. Para que el link funcione, añadir:
```tsx
import { useSearchParams } from "next/navigation";

const searchParams = useSearchParams();
const [statusFilter, setStatusFilter] = useState<string>(
  searchParams.get("status") || "all"
);
```

**Criterio de aceptación**:
- [ ] `StatCard` creado y exportado desde `components/dashboard/index.ts`
- [ ] En Casos: KPIs "Pendientes" e "En Progreso" son clickables con filtro preseleccionado
- [ ] En Escalaciones: KPIs "Pendientes" e "En Progreso" son clickables con filtro
- [ ] En Dashboard: KPIs usan `StatCard` con comportamiento existente preservado
- [ ] Navegación a `/cases?status=pending_review` activa el filtro automáticamente
- [ ] Cards sin `href` no tienen cursor-pointer ni son clickables

---

#### P6: Tabla Usuarios — columnas vacías

**Archivos a modificar**: `admin-panel/src/app/(dashboard)/users/page.tsx`

Ocultar columnas dinámicamente según si algún usuario del listado actual tiene dato:

```tsx
// Calcular visibilidad de columnas (después de filteredUsers):
const hasEmail       = filteredUsers.some((u) => u.email);
const hasCompanyName = filteredUsers.some((u) => u.company_name);
const hasNifCif      = filteredUsers.some((u) => u.nif_cif);

// En TableHead:
{hasEmail       && <TableHead>Email</TableHead>}
{hasCompanyName && <TableHead>Empresa</TableHead>}
{hasNifCif      && <TableHead>NIF/CIF</TableHead>}

// En TableCell (por fila):
{hasEmail       && <TableCell>{user.email || "–"}</TableCell>}
{hasCompanyName && <TableCell>{user.company_name || "–"}</TableCell>}
{hasNifCif      && <TableCell>{user.nif_cif || "–"}</TableCell>}
```

**Criterio de aceptación**:
- [ ] Columnas se ocultan si ningún usuario visible las tiene
- [ ] Columnas aparecen cuando al menos un usuario tiene el dato
- [ ] Dialog de edición mantiene todos los campos independientemente
- [ ] Columnas se actualizan al cambiar filtro/búsqueda
- [ ] No se rompe la navegación a `users/[id]`

---

#### P7: Breadcrumbs

**Archivos a crear**:
- `admin-panel/src/components/layout/breadcrumb.tsx`

**Archivos a modificar**:
- `admin-panel/src/app/(dashboard)/layout.tsx`

**Componente automático basado en pathname**:

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, Home } from "lucide-react";

const PATH_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  cases: "Expedientes",
  escalations: "Escalaciones",
  users: "Usuarios",
  conversations: "Conversaciones",
  reformas: "Reformas",
  elementos: "Elementos",
  advertencias: "Advertencias",
  imagenes: "Imágenes",
  normativas: "Normativas",
  consulta: "Consulta RAG",
  documentos: "Documentos",
  constraints: "Constraints",
  "tool-logs": "Tool Logs",
  settings: "Configuración",
  config: "General",
  system: "Sistema",
  "admin-users": "Administradores",
  usage: "Uso de Tokens",
  "llm-metrics": "Métricas LLM",
  inclusions: "Inclusiones",
};

export function AppBreadcrumb() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean).filter(s => !s.startsWith("("));

  // No mostrar en dashboard (único segmento de profundidad 1)
  if (segments.length <= 1) return null;

  const crumbs = segments.map((segment, idx) => {
    const href = "/" + segments.slice(0, idx + 1).join("/");
    const label = PATH_LABELS[segment] ?? (
      segment.length === 36 ? "Detalle" : segment
    );
    const isLast = idx === segments.length - 1;
    return { href, label, isLast };
  });

  return (
    <nav className="flex items-center gap-1 px-6 py-2 text-sm border-b bg-background">
      <Link href="/dashboard" className="text-muted-foreground hover:text-foreground flex items-center gap-1">
        <Home className="h-3.5 w-3.5" />
      </Link>
      {crumbs.map((crumb) => (
        <span key={crumb.href} className="flex items-center gap-1">
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          {crumb.isLast ? (
            <span className="text-foreground font-medium">{crumb.label}</span>
          ) : (
            <Link href={crumb.href} className="text-muted-foreground hover:text-foreground">
              {crumb.label}
            </Link>
          )}
        </span>
      ))}
    </nav>
  );
}
```

**Integración en layout**:
```tsx
// app/(dashboard)/layout.tsx — añadir después del Header:
import { AppBreadcrumb } from "@/components/layout/breadcrumb";

// En el JSX:
<Header />
<AppBreadcrumb />
<main className="flex-1 overflow-y-auto">
  {children}
</main>
```

**Criterio de aceptación**:
- [ ] Visible en `/cases/[id]` → "🏠 > Expedientes > Detalle"
- [ ] Visible en `/settings/system` → "🏠 > Configuración > Sistema"
- [ ] NO visible en `/dashboard`
- [ ] Todos los segmentos excepto el último son enlaces
- [ ] UUIDs se muestran como "Detalle" (no el UUID raw)
- [ ] Sin fetch adicional de datos

---

#### P8: Badges de urgencia en sidebar

**Archivos a modificar**: `admin-panel/src/components/layout/sidebar.tsx`

Añadir fetch de errores al polling existente:

```tsx
// Estado adicional:
const [openErrors, setOpenErrors] = useState(0);

// En fetchPendingCounts (ya existente), añadir a Promise.all:
const [escalationStats, caseStats, errorStats] = await Promise.all([
  api.getEscalationStats(),
  api.getCaseStats(),
  api.getContainerErrorStats(),  // ← nuevo
]);
setPendingEscalations(escalationStats.pending);
setPendingCases(caseStats.pending_review);
setOpenErrors(errorStats.total_open);  // ← nuevo
```

Añadir badge al ítem de Configuración en `systemNav`:
```tsx
// Después de mainNavWithBadge, añadir:
const systemNavWithBadge: NavItem[] = systemNav.map((item) => {
  if (item.href === "/settings") {
    return { ...item, badge: openErrors > 0 ? openErrors : undefined };
  }
  return item;
});

// En JSX, cambiar systemNav por systemNavWithBadge:
<NavSection title="Sistema" items={systemNavWithBadge} isCollapsed={isCollapsed} />
```

**Criterio de aceptación**:
- [ ] Badge numérica roja en "Configuración" cuando `openErrors > 0`
- [ ] Se actualiza con el polling de 30s existente (sin interval adicional)
- [ ] En sidebar colapsado la badge es visible
- [ ] Si no hay errores, no hay badge
- [ ] Fetch falla silenciosamente (try/catch existente)

---

## Dependencias entre Tareas

### Fase 2 (todas independientes)

```
P1: CTA errores + RAG states   → solo system-health.tsx
P2: Eliminar Accesos Rápidos   → solo dashboard/page.tsx
P3: Colores KPI                → solo dashboard/page.tsx (coordinar con P2, mismo archivo)
P4: Display names Tool Logs    → solo tool-logs/page.tsx
```

⚠️ **P2 y P3 modifican el mismo archivo** — hacer en la misma sesión de trabajo.

### Fase 3 (dependencia interna)

```
P5: StatCard component (crear primero)
    ↓
P5a: cases/page.tsx        → depende de StatCard
P5b: escalations/page.tsx  → depende de StatCard
P5c: dashboard/page.tsx    → depende de StatCard + Fase 2 P2/P3 completos
    
P6: Columnas vacías Usuarios  → independiente
P7: Breadcrumbs               → independiente
P8: Badges sidebar             → independiente
```

**Orden recomendado Fase 3**:
1. Crear `StatCard` component
2. `cases/page.tsx` + `escalations/page.tsx` (en paralelo)
3. `dashboard/page.tsx` con StatCard
4. P6, P7, P8 en paralelo

---

## Tests Requeridos

### Fase 2

| Problema | Test requerido |
|---|---|
| P1 - CTA errores | Badge con `openErrorsCount > 0` es `<Link>` con href correcto |
| P1 - RAG states | Badge "Degradado" cuando 1 componente falla, "Error" cuando ≥2 fallan |
| P2 - Eliminar Accesos Rápidos | `QuickAccessCard` no se renderiza en Dashboard |
| P3 - Colores KPI | `text-green-600` ausente cuando `resolved_today = 0` |
| P4 - Tool display names | `getToolDisplayName("calcular_tarifa_con_elementos")` → "Calcular Tarifa" |

### Fase 3

| Problema | Test requerido |
|---|---|
| P5 - StatCard | Con `href` renderiza `<Link>`, sin `href` renderiza `<div>` |
| P5 - Filtros URL | `/cases?status=pending_review` activa el filtro al montar |
| P6 - Columnas vacías | `hasEmail=false` oculta `<TableHead>` de Email |
| P7 - Breadcrumbs | Pathname `/cases/123` → "Inicio > Expedientes > Detalle" |
| P8 - Sidebar badges | `openErrors=3` añade `badge: 3` al ítem de Settings |

---

## Criterios de Aceptación Globales

### Fase 2 completa cuando:
- [ ] Badge "Errores abiertos" es clickable → `/settings/system`
- [ ] RAG muestra OK / Degradado / Error según estado real
- [ ] Dashboard sin sección "Accesos Rápidos"
- [ ] "En Recolección" sin color azul
- [ ] "Resueltos Hoy" gris cuando = 0, verde cuando > 0
- [ ] Tool Logs muestra "Calcular Tarifa" en lugar de "calcular_tarifa_con_elementos"
- [ ] Sin TypeScript errors nuevos

### Fase 3 completa cuando:
- [ ] `StatCard` existe, exportado, con `href` opcional y colores condicionales
- [ ] KPI cards de Casos y Escalaciones clickables con filtro preseleccionado
- [ ] Dashboard KPIs usan `StatCard` sin ruptura de funcionalidad
- [ ] Columnas Email/Empresa/NIF-CIF se ocultan dinámicamente si vacías
- [ ] Breadcrumb visible en páginas anidadas
- [ ] Badge numérica en "Configuración" cuando hay errores del sistema

---

## Checklist Pre-Deploy

- [ ] Sin nuevas dependencias npm
- [ ] `tsc --noEmit` sin errores nuevos
- [ ] No hay `console.error` sin `toast.error` pareja
- [ ] Ningún componente Radix UI reemplazado por HTML nativo
- [ ] Verificar en dark mode
- [ ] Sidebar colapsado: badges de P8 no rompen layout

---

**Plan creado por**: architect  
**Fecha**: 2026-02-24  
**Revisado por**: Pendiente aprobación usuario
