# Estándares Frontend React (Next.js 16 + Radix UI)

Patrones para el admin panel MSI-a.

---

## 1. Client Component Pattern

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

export default function MyPage() {
  const [data, setData] = useState<Item[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  
  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true);
      const result = await api.getItems();
      setData(result.items);
    } catch (error) {
      console.error("Error:", error);
      toast.error("Error al cargar los datos");
    } finally {
      setIsLoading(false);
    }
  }, []);
  
  useEffect(() => {
    fetchData();
  }, [fetchData]);
  
  if (isLoading) return <div className="animate-pulse">Cargando...</div>;
  
  return (
    <div className="container">
      {/* UI with Radix components */}
    </div>
  );
}
```

---

## 2. Dialog-Based CRUD

```typescript
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export function CreateDialog({ onSuccess }: { onSuccess?: () => void }) {
  const [open, setOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  
  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setIsSaving(true);
    try {
      const formData = new FormData(e.currentTarget);
      await api.create({ name: formData.get("name") as string });
      toast.success("Creado correctamente");
      setOpen(false);
      onSuccess?.();
    } catch (error) {
      toast.error("Error al crear");
    } finally {
      setIsSaving(false);
    }
  }
  
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Crear Nuevo</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Crear Nuevo</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          {/* form fields */}
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

---

## 3. AlertDialog para Destructive

```typescript
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";

<AlertDialog>
  <AlertDialogTrigger asChild>
    <Button variant="destructive">Eliminar</Button>
  </AlertDialogTrigger>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>¿Eliminar {item.name}?</AlertDialogTitle>
      <AlertDialogDescription>
        Esta acción no se puede deshacer.
      </AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>Cancelar</AlertDialogCancel>
      <AlertDialogAction onClick={handleDelete} className="bg-destructive">
        Eliminar
      </AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

---

## 4. Debounced Search

```typescript
const [searchQuery, setSearchQuery] = useState("");
const [debouncedQuery, setDebouncedQuery] = useState("");

useEffect(() => {
  const timer = setTimeout(() => setDebouncedQuery(searchQuery), 300);
  return () => clearTimeout(timer);
}, [searchQuery]);

useEffect(() => {
  if (debouncedQuery) {
    fetchData({ search: debouncedQuery });
  }
}, [debouncedQuery]);
```

---

## 5. Auto-Refresh Polling

```typescript
useEffect(() => {
  fetchData();
  const interval = setInterval(fetchData, 30000); // 30s
  return () => clearInterval(interval); // ✅ CLEANUP
}, [fetchData]);
```

---

## 6. Reglas Críticas

1. ✅ **SIEMPRE** "use client" para páginas con state
2. ✅ **SIEMPRE** Radix UI → NUNCA <button>, <input>, <table>
3. ✅ **SIEMPRE** toast() → NUNCA alert()/confirm()
4. ✅ **SIEMPRE** AlertDialog para destructive
5. ✅ **SIEMPRE** debounced search (300ms)
6. ✅ **SIEMPRE** cleanup timers en useEffect return
7. ✅ **SIEMPRE** useCallback para fetch dependencies
8. ✅ **SIEMPRE** español para labels de UI
9. ❌ **NUNCA** Server Components para data fetching (Client + useEffect)
10. ❌ **NUNCA** Server Actions para mutations (api client)
11. ❌ **NUNCA** mutar state directamente (setter con prev)

---

## 7. URL State para Páginas de Listado

**Usa siempre `useListUrlState<T>` para filtros, búsqueda y paginación en páginas de listado.** Nunca uses `useState` aislado para estos datos: el estado en la URL permite compartir enlaces y restaurar el estado al navegar hacia atrás.

```typescript
import { useListUrlState } from "@/hooks/use-list-url-state";

const [params, setParams] = useListUrlState({
  defaults: { q: "", status: "all", page: 0 },
  resetPageOn: ["q", "status"], // Resetea la página cuando cambia el filtro
});

// El input refleja params.q (derivado de la URL)
<Input value={params.q} onChange={(e) => setParams({ q: e.target.value })} />
```

**Cuándo usarlo:** en toda página con tabla + filtros. El hook usa `router.replace()` (sin añadir entradas al historial por cada tecla), y lee desde `useSearchParams()`.

**Con debounce para campos de búsqueda libre:**

En páginas donde el campo `q` dispara llamadas a la API (como `/cases` con auto-refresh activo), usa `useDebouncedListUrlState` para evitar llamadas por cada tecla:

```typescript
import { useDebouncedListUrlState } from "@/hooks/use-debounced-list-url-state";

const [params, setParams] = useDebouncedListUrlState({
  defaults: { q: "", status: "all", offset: 0 },
  resetPageOn: ["q", "status"],
  pageKey: "offset",
  debounceFields: ["q"],   // Solo estos campos se debouncea; el resto va a la URL inmediatamente
  delayMs: 300,
});
```

El input se mantiene responsive (actualiza estado local inmediatamente). La URL solo se escribe después de 300ms de inactividad.

**Referencia:** `src/hooks/use-list-url-state.ts`, `src/hooks/use-debounced-list-url-state.ts`

---

## 8. Dirty-State Guard (`useDirtyGuard`)

Protege formularios inline de discards accidentales cuando el usuario navega o hace clic en el sidebar.

```typescript
import { useDirtyGuard } from "@/hooks/use-dirty-guard";
import { DirtyFormBanner } from "@/components/shared/dirty-form-banner";

const { isDirty, markDirty, clearDirty } = useDirtyGuard({
  isDirty: hasUnsavedChanges,
  formId: "users:main:${userId}",  // Único por instancia de formulario
});

// Banner aparece cuando isDirty === true
<DirtyFormBanner formId="users:main:${userId}" onDiscard={handleDiscard} />
```

**Reglas de scoping:**
- Aplica solo al formulario "principal" de la página (campos inline editables).
- **No aplica** a sub-secciones con CRUD en Dialog (guardan inmediatamente al confirmar — ADR D7).
- `formId` sigue el patrón `"entity:section:id"` — ej. `"elementos:main:${elementId}"`.
- Llama `clearDirty()` en el `onSuccess` del save para desactivar el banner.

**El guard intercepta navegación vía sidebar** (a través de `DirtyFormContext` + `guardNavigation` en el sidebar). Muestra un `AlertDialog` de confirmación antes de abandonar la página.

**Referencia:** `src/hooks/use-dirty-guard.ts`, `src/components/shared/dirty-form-banner.tsx`, `src/contexts/dirty-form-context.tsx`

---

## 9. Density Toggle y TableDensityContext

Permite al usuario alternar entre vista compacta y cómoda en tablas. El contexto persiste la preferencia durante la sesión.

```typescript
// Tabla density-aware: añade data-density al contenedor
import { useTableDensity } from "@/contexts/table-density-context";

const { density } = useTableDensity();

<div data-density={density}>
  <Table>...</Table>
</div>
```

**DensityToggle:** botón estándar para incluir en `PageHeader.actions` o dentro de `FilterBar`:

```typescript
import { DensityToggle } from "@/components/shared/density-toggle";

// Dentro de FilterBar (showDensityToggle={true} por defecto):
<FilterBar searchValue={q} onSearchChange={...}>
  {/* DensityToggle se renderiza automáticamente */}
</FilterBar>

// En páginas sin FilterBar (ej. /escalations), en PageHeader.actions:
<PageHeader
  title="Escalaciones"
  actions={
    <>
      <DensityToggle />
      <Button>Actualizar</Button>
    </>
  }
/>
```

**Regla:** toda página con tabla de datos debe tener `DensityToggle` accesible.

**Referencia:** `src/contexts/table-density-context.tsx`, `src/components/shared/density-toggle.tsx`, `src/components/ui/table.tsx` (variantes `data-density`)

---

## 10. Skeleton Archetypes (Loading States)

**Nunca uses** `<div className="animate-pulse">Cargando...</div>` en páginas migradas. Usa el archetype correcto:

| Contexto | Archetype | Importación |
|----------|-----------|-------------|
| Tabla de listado | `<TableSkeleton rows cols />` | `@/components/ui/skeleton-archetypes` |
| Página de detalle (formulario) | `<DetailSkeleton sections />` | `@/components/ui/skeleton-archetypes` |
| Grid de tarjetas | `<CardGridSkeleton cards />` | `@/components/ui/skeleton-archetypes` |
| Hilo de conversación | `<ChatThreadSkeleton messages />` | `@/components/ui/skeleton-archetypes` |

```typescript
import {
  TableSkeleton,
  DetailSkeleton,
  CardGridSkeleton,
  ChatThreadSkeleton,
} from "@/components/ui/skeleton-archetypes";

// Página de listado (mientras isLoading):
{isLoading ? (
  <TableSkeleton rows={8} cols={[{ width: "20%" }, { width: "30%" }, { width: "50%" }]} />
) : fetchError ? (
  <ErrorCard error={fetchError} onRetry={fetchData} message="No se pudieron cargar los datos." />
) : (
  <Table>...</Table>
)}
```

**Referencia:** `src/components/ui/skeleton-archetypes/`

---

## 11. ErrorCard vs error.tsx

| Situación | Mecanismo | Ubicación |
|-----------|-----------|-----------|
| Error de fetch en la UI de la página | `<ErrorCard>` inline | Dentro del componente, sustituyendo la tabla/contenido |
| Error de render (excepción no capturada en React tree) | `error.tsx` de Next.js | `app/(authenticated)/[ruta]/error.tsx` |

**`<ErrorCard>` — para errores de fetch:**

```typescript
import { ErrorCard } from "@/components/shared/error-card";

{fetchError ? (
  <ErrorCard
    error={fetchError}
    onRetry={fetchData}
    message="No se pudieron cargar los expedientes."
    variant="inline"   // "inline" (default) | "page"
  />
) : (
  <Table>...</Table>
)}
```

**`error.tsx` — para errores de render:**

```typescript
// src/app/(authenticated)/cases/[id]/error.tsx
"use client";

import { useEffect } from "react";
import { ErrorCard } from "@/components/shared/error-card";

export default function CaseDetailError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <ErrorCard
      variant="page"
      error={error}
      onRetry={reset}
      message="No se pudo cargar el expediente."
    />
  );
}
```

**Regla:** las páginas de detalle (`/[id]`) deben tener `error.tsx`. Las páginas de listado usan `<ErrorCard>` inline.

**Referencia:** `src/components/shared/error-card.tsx`, `src/app/(authenticated)/cases/[id]/error.tsx`

---

---

## 12. Shell + Table Density Patterns (Fase 1)

Patrones establecidos en el cambio `frontend-shell-and-table-redesign`. Deben mantenerse en todos los cambios futuros del admin panel.

### 12.1 Sidebar — medidas y tokens

| Propiedad | Valor |
|-----------|-------|
| Ancho expandido | `w-[232px]` |
| Ancho colapsado | `w-16` (64px) |
| Token de fondo | `--sidebar-background: 196 60% 12%` (dark teal) |
| Token oscuro | `--sidebar-background: 196 40% 8%` (`.dark`) |
| Item activo | barra izquierda de 3px (`bg-sidebar-primary`) + `bg-sidebar-accent/40` |
| Textos secundarios | `text-sidebar-foreground/70` (roles, botones) / `text-sidebar-foreground/50` (labels de sección) |
| ARIA de toggle | `"Expandir menú"` / `"Colapsar menú"` (dinámico) |

Los tokens `--sidebar-*` están definidos en `globals.css` (`:root` y `.dark`). No uses `text-muted-foreground` ni `bg-muted-*` dentro del sidebar — siempre usa los tokens `sidebar-*` para mantener contraste sobre el fondo teal oscuro.

**Referencia:** `admin-panel/src/app/globals.css`, `admin-panel/src/components/layout/sidebar.tsx`

### 12.2 Header — medidas y responsabilidad

| Propiedad | Valor |
|-----------|-------|
| Altura | `h-11` (44px) |
| Título de página | **Ausente** — lo provee `PageHeader` en cada ruta |

El header (`header.tsx`) NO renderiza un `<h1>` ni calcula `pageTitles`. Su única responsabilidad es el hamburger (slot izquierdo) y los controles globales: `GlobalSearch`, `ThemeToggle`, `NotificationCenter` (slot derecho).

**Referencia:** `admin-panel/src/components/layout/header.tsx`

### 12.3 PageHeader — obligatorio en cada ruta

`<PageHeader>` es **obligatorio** en todas las páginas de listado y detalle. Nunca delegues el título de la ruta al header de la shell.

```typescript
import { PageHeader } from "@/components/shared/page-header";

<PageHeader
  title="Expedientes"
  description="Gestión de solicitudes de homologación"
  actions={<Button>Nuevo</Button>}
/>
```

Páginas que no son de listado ni detalle (p.ej. sub-paneles embebidos) pueden omitir `PageHeader` solo si su contexto visual ya provee el título.

**Referencia:** `admin-panel/src/components/shared/page-header.tsx`

### 12.4 Ancho de columnas en tablas

Declara el ancho de cada columna en el `<TableHead>` correspondiente mediante `className="w-[Npx]"`. Nunca uses `<colgroup>` ni ancho en `<TableCell>`.

```tsx
<TableHead className="w-[130px]">Estado</TableHead>
<TableHead>Cliente</TableHead>          {/* flex: sin className de ancho */}
<TableHead className="w-[100px]">Tarifa</TableHead>
<TableHead className="w-[80px] text-right">Acciones</TableHead>
```

**Regla:** al menos una columna debe ser flexible (sin `w-[Npx]`) para absorber el ancho sobrante. Las columnas de acciones van siempre al final con `text-right`.

**Referencia:** `admin-panel/src/components/ui/table.tsx`, cualquier `page.tsx` de listado

### 12.5 Patrón unified card (filtro + tabla)

Toda página de listado que combine un área de filtros con una tabla usa un único contenedor card:

```tsx
<div className="rounded-lg border bg-card overflow-hidden">
  {/* Cabecera de filtros */}
  <div className="border-b px-4 py-3 flex items-center gap-3">
    <FilterBar ... />
    {/* o FilterChips si la página tiene endpoint de conteos por estado */}
  </div>
  {/* Tabla sin padding adicional */}
  <div className="p-0">
    <Table>...</Table>
  </div>
</div>
```

No uses `<Card>` + `<CardContent>` para este patrón — importa componentes Radix solo cuando necesites su semántica (p.ej. Card con `CardHeader` de título propio).

**Referencia:** `admin-panel/src/app/(authenticated)/cases/page.tsx`, `escalations/page.tsx`, `users/page.tsx`, `conversations/page.tsx`, `advertencias/page.tsx`, `settings/admin-users/page.tsx`

### 12.6 KPI strip — gap en páginas densas

En páginas con tira de estadísticas (KPI strip) sobre la tabla, usa `gap-3` en el grid de tarjetas, no `gap-4`. El valor `gap-3` es el que usa `StatsStrip` internamente; mantenerlo alineado evita inconsistencia visual.

```tsx
<div className="grid grid-cols-2 md:grid-cols-4 gap-3">
  {/* StatCard items */}
</div>
```

**Referencia:** `admin-panel/src/app/(authenticated)/cases/page.tsx`, `escalations/page.tsx`

### 12.7 Componente FilterChips

Usa `<FilterChips>` en páginas que disponen de un endpoint de conteos por estado (p.ej. `GET /api/admin/cases/stats` devuelve `by_status`, `GET /api/admin/escalations/stats` devuelve `by_status`). Sustituye al `<Select>` de filtro de estado.

**API del componente:**

```typescript
interface FilterChipsProps<T extends string> {
  options: FilterChipOption<T>[];  // { value: T | null; label: string; count?: number }
  value: T | null;                 // null = "todos"
  onChange: (value: T | null) => void;
  "aria-label"?: string;           // default: "Filtrar por estado"
}
```

**Patrón de integración con `useListUrlState` / `useDebouncedListUrlState` y `useMemo`:**

```typescript
import { useMemo } from "react";
import { FilterChips } from "@/components/shared/filter-chips";
import { useDebouncedListUrlState } from "@/hooks/use-debounced-list-url-state";

const [params, setParams] = useDebouncedListUrlState({
  defaults: { q: "", status: "all", offset: 0 },
  resetPageOn: ["q", "status"],
  pageKey: "offset",
  debounceFields: ["q"],
  delayMs: 300,
});

const statusFilter = params.status === "all" ? null : params.status;

// Construye las opciones solo cuando cambia stats
const chipOptions = useMemo(() => {
  const byStatus = stats?.by_status ?? {};
  const total = Object.values(byStatus).reduce((a, b) => a + b, 0);
  return [
    { value: null, label: "Todos", count: total },
    { value: "pending",     label: "Pendientes",  count: byStatus.pending ?? 0 },
    { value: "in_progress", label: "En Progreso",  count: byStatus.in_progress ?? 0 },
    // … resto de estados
  ] as FilterChipOption<string>[];
}, [stats?.by_status]);

// En el JSX, dentro del unified card:
<FilterChips
  options={chipOptions}
  value={statusFilter}
  onChange={(v) => setParams({ status: v ?? "all" })}
  aria-label="Filtrar expedientes por estado"
/>
```

**Cuándo usarlo:** solo cuando el backend devuelve `by_status` en el endpoint de stats de la página. No añadas `FilterChips` a páginas sin ese endpoint; usa `<Select>` estándar en su lugar.

**Referencia:** `admin-panel/src/components/shared/filter-chips.tsx`, `admin-panel/src/app/(authenticated)/cases/page.tsx`, `admin-panel/src/app/(authenticated)/escalations/page.tsx`

---

**Referencias:**
- `admin-panel/CLAUDE.md`
- `skills/nextjs-16/SKILL.md`
- `skills/radix-tailwind/SKILL.md`

**Última actualización:** Mayo 2026 (Fase 1 Shell + Table Redesign — frontend-shell-and-table-redesign)
