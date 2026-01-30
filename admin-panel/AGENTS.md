# Admin Panel Component Guidelines

This directory contains the MSI-a Admin Panel built with **Next.js 16**, **React 19**, **Radix UI** (shadcn/ui), and **Tailwind CSS**.

## Auto-invoke Skills

When working in this directory, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Creating/modifying pages | `msia-admin` |
| Creating/modifying components | `msia-admin` |
| Working with contexts/hooks | `msia-admin` |
| Working with App Router | `nextjs-16` |
| Working with Radix UI + Tailwind | `radix-tailwind` |
| Working with tariffs UI | `msia-tariffs` |
| TypeScript/React patterns | `typescript-frontend-patterns` |

## Tech Stack

| Technology | Version | Purpose |
|-----------|---------|---------|
| Next.js | 16.x | Framework (App Router, standalone output) |
| React | 19.x | UI library |
| Radix UI | Various | Accessible UI primitives (shadcn/ui `new-york` style) |
| Tailwind CSS | 3.x | Utility-first styling (`zinc` base, `class` dark mode) |
| Sonner | 1.x | Toast notifications |
| Lucide React | 0.460+ | Icon library |
| jose | 5.x | JWT token handling |
| date-fns | 3.x | Date formatting |
| zod | 3.x | Schema validation |
| react-hook-form | 7.x | Form management (available, used sparingly) |
| Jest + RTL | 29.x | Testing |

## Architecture Overview

```
Browser → Next.js (standalone) → API Rewrites → FastAPI Backend
                                    ↓
                              SSE Proxy Route → Docker Log Streaming
```

- **All data fetching is client-side** via `useEffect` + `api` singleton
- **No Server Actions** — mutations go through the API client
- **No Middleware** — auth is checked client-side via JWT token expiration
- **API proxy** — Next.js rewrites proxy `/api/*`, `/health`, `/images/*`, `/case-images/*`, `/llm-metrics/*` to backend

## Directory Structure

```
admin-panel/
├── src/
│   ├── app/
│   │   ├── layout.tsx                  # Root layout (Inter font, AuthProvider, SidebarProvider, Toaster)
│   │   ├── page.tsx                    # Redirect → /dashboard
│   │   ├── globals.css                 # Tailwind + CSS variables
│   │   ├── login/page.tsx              # Login form
│   │   ├── api/                        # Next.js API routes
│   │   │   └── admin/system/[service]/logs/route.ts  # SSE proxy for Docker logs
│   │   └── (authenticated)/            # Protected routes (auth guard layout)
│   │       ├── layout.tsx              # Auth check + sidebar + header + GlobalSearchProvider
│   │       ├── error.tsx               # Error boundary ("Algo salio mal" + retry)
│   │       ├── dashboard/page.tsx      # KPIs + quick access + system health
│   │       ├── conversations/
│   │       │   ├── page.tsx            # Conversation list (sort, delete)
│   │       │   └── [id]/page.tsx       # Conversation detail + messages
│   │       ├── escalations/page.tsx    # Escalation management (resolve, stats)
│   │       ├── users/
│   │       │   ├── page.tsx            # User CRUD (search, filter, create/edit/delete dialogs)
│   │       │   └── [id]/page.tsx       # User detail (inline edit, conversations, cases)
│   │       ├── cases/
│   │       │   ├── page.tsx            # Case list (stats, search, filter)
│   │       │   └── [id]/page.tsx       # Case detail (take, resolve, images, accordion sections)
│   │       ├── reformas/               # Tariff management
│   │       │   ├── page.tsx            # Categories overview (grouped by client_type)
│   │       │   └── [categoryId]/
│   │       │       ├── page.tsx        # Category detail (tiers, elements, docs, services, prompts)
│   │       │       └── [tierId]/
│   │       │           └── inclusions/page.tsx  # Tier inclusion editor
│   │       ├── elementos/              # Element management
│   │       │   ├── page.tsx            # Element catalog (flat/hierarchy views, create, delete)
│   │       │   └── [id]/page.tsx       # Element detail (edit, images, warnings, variants, required fields)
│   │       ├── advertencias/page.tsx   # Warning CRUD (trigger conditions)
│   │       ├── constraints/page.tsx    # Response constraints (anti-hallucination) ⚠️ Uses native HTML
│   │       ├── tool-logs/page.tsx      # Tool call logs (debugging) ⚠️ Uses native HTML
│   │       ├── normativas/             # RAG documents
│   │       │   ├── layout.tsx          # Tab navigation (consulta/documentos)
│   │       │   ├── page.tsx            # Redirect → /normativas/consulta
│   │       │   ├── consulta/page.tsx   # RAG chat interface (query + citations)
│   │       │   └── documentos/page.tsx # Document management (upload, process, activate)
│   │       ├── imagenes/page.tsx       # Image gallery (upload, browse, delete)
│   │       └── settings/
│   │           ├── layout.tsx          # Tab navigation (role-filtered tabs)
│   │           ├── page.tsx            # Redirect → /settings/config
│   │           ├── config/page.tsx     # System config (panic button, agent toggle)
│   │           ├── system/page.tsx     # System monitor (health, services, SSE logs, errors)
│   │           ├── admin-users/page.tsx # Admin user CRUD + access logs (admin-only)
│   │           ├── usage/page.tsx      # Token usage dashboard (admin-only)
│   │           └── llm-metrics/page.tsx # Hybrid LLM metrics (admin-only)
│   ├── components/
│   │   ├── ui/                         # Radix UI primitives (21 components, ALL actively used)
│   │   │   ├── accordion.tsx           # (2 importers)
│   │   │   ├── alert-dialog.tsx        # (12 importers) — destructive confirmations
│   │   │   ├── badge.tsx               # (37 importers) — status/type indicators
│   │   │   ├── button.tsx              # (45 importers) — primary UI action
│   │   │   ├── card.tsx                # (29 importers) — content containers
│   │   │   ├── command.tsx             # (1 importer) — global search command palette
│   │   │   ├── dialog.tsx              # (26 importers) — form dialogs/modals
│   │   │   ├── error-boundary.tsx      # (1 importer) — React error boundary
│   │   │   ├── input.tsx               # (26 importers) — text inputs
│   │   │   ├── label.tsx               # (22 importers) — form labels
│   │   │   ├── popover.tsx             # (1 importer) — notification center
│   │   │   ├── progress.tsx            # (1 importer) — LLM metrics progress bars
│   │   │   ├── scroll-area.tsx         # (2 importers) — scrollable containers
│   │   │   ├── select.tsx              # (20 importers) — dropdown selects
│   │   │   ├── separator.tsx           # (6 importers) — visual dividers
│   │   │   ├── skeleton.tsx            # (2 importers) — loading placeholders
│   │   │   ├── switch.tsx              # (8 importers) — toggle switches
│   │   │   ├── table.tsx               # (16 importers) — data tables
│   │   │   ├── tabs.tsx                # (2 importers) — tabbed navigation
│   │   │   ├── textarea.tsx            # (15 importers) — multi-line text inputs
│   │   │   └── tooltip.tsx             # (4 importers) — hover tooltips
│   │   ├── layout/
│   │   │   ├── header.tsx              # Top header (search, notifications, user menu)
│   │   │   └── sidebar.tsx             # Navigation sidebar (collapsible, persistent state)
│   │   ├── tariffs/                    # Tariff components (all used by reformas/[categoryId])
│   │   │   ├── base-doc-dialog.tsx     # Base documentation CRUD dialog
│   │   │   ├── delete-confirmation-dialog.tsx  # Generic delete confirmation
│   │   │   ├── element-form-dialog.tsx # Element form within tariff context
│   │   │   ├── elements-tree-section.tsx # Hierarchical element tree view
│   │   │   ├── prompt-preview-dialog.tsx # Full prompt preview dialog
│   │   │   ├── prompt-section-form-dialog.tsx # Prompt section CRUD dialog
│   │   │   ├── service-form-dialog.tsx # Additional service CRUD dialog
│   │   │   ├── tier-form-dialog.tsx    # Tariff tier CRUD dialog
│   │   │   └── __tests__/             # Jest tests
│   │   │       └── elements-tree-section.test.tsx
│   │   ├── elements/                   # Element components
│   │   │   ├── create-variant-dialog.tsx   # Create element variant dialog
│   │   │   ├── element-form.tsx            # Element creation form
│   │   │   ├── element-required-fields-dialog.tsx  # Required fields management
│   │   │   └── element-warnings-dialog.tsx # Warning associations dialog
│   │   ├── categories/
│   │   │   └── CategoryFormDialog.tsx  # Category CRUD dialog
│   │   ├── dashboard/
│   │   │   ├── index.ts                # Barrel export
│   │   │   ├── quick-access-card.tsx   # Navigation shortcut card
│   │   │   ├── system-health.tsx       # System health widget
│   │   │   └── recent-activity.tsx     # Recent activity widget
│   │   ├── escalation-details-dialog.tsx   # Escalation detail view
│   │   ├── global-search.tsx           # Cmd+K search command palette
│   │   ├── image-preview-rename-dialog.tsx # Image preview + rename
│   │   ├── image-upload.tsx            # Image upload + gallery (ImageUpload, ImageGalleryDialog)
│   │   ├── notification-center.tsx     # Notification popover
│   │   ├── quick-element-dialog.tsx    # Quick element creation
│   │   └── tier-inclusion-editor.tsx   # Tier inclusion management
│   ├── contexts/
│   │   ├── auth-context.tsx            # AuthProvider + useAuth (login, logout, isAdmin, hasRole)
│   │   ├── sidebar-context.tsx         # SidebarProvider + useSidebar (collapse/expand, persisted)
│   │   └── global-search-context.tsx   # GlobalSearchProvider + useGlobalSearchState (Cmd+K)
│   ├── hooks/
│   │   ├── use-category-data.ts        # Fetch category with all relations
│   │   ├── use-tier-elements.ts        # Fetch resolved elements for all tiers
│   │   ├── use-category-elements.ts    # Fetch + build element tree for category
│   │   └── use-global-search.ts        # Multi-entity search (pages, elements, categories, tiers, users)
│   └── lib/
│       ├── api.ts                      # ApiClient singleton (1357 lines, 30+ resource domains)
│       ├── auth.ts                     # JWT utilities (decode, verify, expiration check)
│       ├── constants.ts                # Global constants (limits, debounce, TTLs)
│       ├── types.ts                    # TypeScript types (1397 lines, 100+ interfaces)
│       ├── utils.ts                    # cn() utility (clsx + tailwind-merge)
│       └── validators.ts               # Filename validation, file size formatting
├── components.json                     # shadcn/ui config (new-york, zinc, lucide)
├── jest.config.js                      # Jest config (jsdom, @/ alias)
├── jest.setup.js                       # @testing-library/jest-dom
├── next.config.ts                      # Standalone output + API rewrites
├── tailwind.config.ts                  # HSL CSS variables theme
├── tsconfig.json                       # Strict, ES2017, bundler resolution
└── package.json
```

## Pages Summary (28 routes)

| Route | Type | Lines | Description |
|-------|------|-------|-------------|
| `/` | Client | 19 | Redirect → /dashboard |
| `/login` | Client | 107 | Login form |
| `/dashboard` | Client | 287 | KPIs, quick access, system health (auto-refresh 30s) |
| `/conversations` | Client | 284 | Conversation list (sort, delete) |
| `/conversations/[id]` | Client | 512 | Conversation detail + message history |
| `/cases` | Client | 432 | Case list + stats (auto-refresh 30s, debounced search) |
| `/cases/[id]` | Client | 909 | Case detail (take, resolve, images, accordion) |
| `/users` | Client | 608 | User CRUD (search, filter, dialogs) |
| `/users/[id]` | Client | 642 | User detail (inline edit, related data) |
| `/escalations` | Client | 473 | Escalation management (auto-refresh 30s) |
| `/reformas` | Client | 312 | Categories overview (grouped by client_type) |
| `/reformas/[categoryId]` | Client | 910 | Category detail (tiers, elements, docs, services, prompts) |
| `/reformas/.../inclusions` | Client | 148 | Tier inclusion editor |
| `/elementos` | Client | 726 | Element catalog (flat/hierarchy views) |
| `/elementos/[id]` | Client | 1400+ | Element detail editor (largest page) |
| `/imagenes` | Client | 601 | Image gallery (upload, browse, delete) |
| `/constraints` | Client | 314 | Response constraints ⚠️ native HTML |
| `/advertencias` | Client | 685 | Warning CRUD |
| `/tool-logs` | Client | 274 | Tool call logs ⚠️ native HTML |
| `/normativas` | Server | 6 | Redirect → /normativas/consulta |
| `/normativas/consulta` | Client | 242 | RAG chat interface |
| `/normativas/documentos` | Client | 531 | Document management (poll 5s) |
| `/settings` | Server | 6 | Redirect → /settings/config |
| `/settings/config` | Client | 347 | System config (panic button) |
| `/settings/system` | Client | 1030 | System monitor (SSE log streaming) |
| `/settings/admin-users` | Client | 866 | Admin user CRUD + access logs (admin-only) |
| `/settings/usage` | Client | 359 | Token usage (admin-only) |
| `/settings/llm-metrics` | Client | 585 | Hybrid LLM metrics (admin-only) |

> **Note:** 25/28 pages are Client Components. Only 3 are Server Components (2 redirects + 1 normativas index).

## Key Patterns

### 1. Client Page with Data Fetching (Primary Pattern)

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function MyPage() {
  const [data, setData] = useState<MyType[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true);
      const result = await api.getMyData();
      setData(result.items);
    } catch (error) {
      console.error("Error fetching data:", error);
      toast.error("Error al cargar los datos");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (isLoading) return <div className="animate-pulse text-muted-foreground">Cargando...</div>;

  return (/* UI */);
}
```

### 2. Dialog-Based Form (CRUD Operations)

```typescript
"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

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
      toast.error("Error al crear: " + (error instanceof Error ? error.message : "Desconocido"));
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
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* form fields */}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving ? "Guardando..." : "Guardar"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

### 3. Destructive Confirmation (AlertDialog)

```typescript
<AlertDialog>
  <AlertDialogTrigger asChild>
    <Button variant="destructive" size="sm">Eliminar</Button>
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
      <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
        Eliminar
      </AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

### 4. Auto-Refresh Polling

```typescript
useEffect(() => {
  fetchData();
  const interval = setInterval(fetchData, 30000); // 30s for dashboard/cases/escalations
  return () => clearInterval(interval);
}, [fetchData]);
```

### 5. Admin-Only Guard

```typescript
const { user, isAdmin } = useAuth();

if (!isAdmin) {
  return (
    <Card>
      <CardContent className="text-center py-8">
        <ShieldAlert className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
        <p className="text-muted-foreground">No tienes permisos para acceder a esta sección</p>
      </CardContent>
    </Card>
  );
}
```

### 6. Status Badge Pattern

```typescript
function getStatusBadge(status: CaseStatus) {
  const config = {
    pending: { label: "Pendiente", variant: "secondary" as const, icon: Clock },
    in_progress: { label: "En Progreso", variant: "default" as const, icon: Loader2 },
    resolved: { label: "Resuelto", variant: "success" as const, icon: CheckCircle },
    cancelled: { label: "Cancelado", variant: "destructive" as const, icon: XCircle },
  };
  const { label, variant, icon: Icon } = config[status];
  return (
    <Badge variant={variant} className="gap-1">
      <Icon className="h-3 w-3" />
      {label}
    </Badge>
  );
}
```

### 7. Debounced Search

```typescript
const [searchQuery, setSearchQuery] = useState("");
const [debouncedQuery, setDebouncedQuery] = useState("");

useEffect(() => {
  const timer = setTimeout(() => {
    setDebouncedQuery(searchQuery);
  }, 300); // SEARCH_DEBOUNCE_MS
  return () => clearTimeout(timer);
}, [searchQuery]);

useEffect(() => {
  if (debouncedQuery) {
    fetchData({ search: debouncedQuery });
  }
}, [debouncedQuery]);
```

### 8. Inline Edit Form with Change Tracking

```typescript
const [formData, setFormData] = useState<UserUpdate>(initialData);
const [hasChanges, setHasChanges] = useState(false);

useEffect(() => {
  setHasChanges(JSON.stringify(formData) !== JSON.stringify(initialData));
}, [formData, initialData]);

async function handleSave() {
  try {
    await api.updateUser(userId, formData);
    toast.success("Cambios guardados");
    setHasChanges(false);
  } catch (error) {
    toast.error("Error al guardar");
  }
}

return (
  <form className="space-y-4">
    <Input value={formData.name} onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))} />
    <Button onClick={handleSave} disabled={!hasChanges || isSaving}>
      Guardar Cambios
    </Button>
  </form>
);
```

## Critical Rules

### Must Do

- **ALWAYS** use Radix UI from `@/components/ui/` — NEVER native HTML elements for UI
- **ALWAYS** use `cn()` from `@/lib/utils` for conditional classes
- **ALWAYS** use `toast` from Sonner for user feedback — NEVER `alert()` or `confirm()`
- **ALWAYS** use `AlertDialog` for destructive confirmations
- **ALWAYS** use Spanish for UI labels (user-facing content)
- **ALWAYS** handle loading + error states in all data-fetching components
- **ALWAYS** provide toast feedback after mutations (create, update, delete)
- **ALWAYS** close dialogs on successful form submission
- **ALWAYS** use types from `@/lib/types.ts` — never inline types for API responses
- **ALWAYS** use constants from `@/lib/constants.ts` instead of magic numbers
- **ALWAYS** wrap fetch functions in `useCallback` when used as dependencies
- **ALWAYS** disable form controls during save/loading states

### Must Not

- **NEVER** use `useState` in Server Components
- **NEVER** fetch data in Server Components (project pattern is client-side fetching)
- **NEVER** use native HTML `<button>`, `<input>`, `<select>`, `<table>` — use Radix UI wrappers
- **NEVER** use `console.error` as the only error feedback — always pair with `toast.error`
- **NEVER** use `window.confirm()` — use `AlertDialog`
- **NEVER** forget to clean up intervals/timers in `useEffect` return
- **NEVER** mutate state directly — always use setter functions with previous state
- **NEVER** forget to handle error states in API calls

### Known Technical Debt

| Issue | Location | Action Needed |
|-------|----------|---------------|
| Native HTML instead of Radix UI | `constraints/page.tsx` | Refactor to use Radix UI components |
| Native HTML instead of Radix UI | `tool-logs/page.tsx` | Refactor to use Radix UI components |
| `window.confirm()` usage | `constraints/page.tsx` | Replace with `AlertDialog` |
| `CATEGORY_CACHE_TTL_MS` unused | `lib/constants.ts` | Implement or remove |
| Inconsistent toast usage | Various pages | Add toast.error to all catch blocks |
| No Error Boundary coverage | Most pages | Only elements-tree-section uses ErrorBoundary |

## Component Inventory (46 components — all actively used)

### Heavy Use (10+ importers)
`button` (45), `badge` (37), `card` (29), `dialog` (26), `input` (26), `label` (22), `select` (20), `table` (16), `textarea` (15), `alert-dialog` (12)

### Moderate Use (3-9 importers)
`switch` (8), `separator` (6), `tooltip` (4)

### Light Use (1-2 importers)
`accordion` (2), `scroll-area` (2), `skeleton` (2), `tabs` (2), `command` (1), `error-boundary` (1), `popover` (1), `progress` (1)

### Single-Purpose Components (1 importer each)
- **Tariffs**: 8 components → `reformas/[categoryId]/page.tsx`
- **Elements**: 3 components → `elementos/[id]/page.tsx`, 1 → `elementos/page.tsx`
- **Categories**: 1 component → `reformas/page.tsx`
- **Dashboard**: 3 components → `dashboard/page.tsx` (via barrel export)
- **Root**: 7 specialized components for specific pages

## Related Skills

| Skill | When to Use |
|-------|-------------|
| `msia-admin` | Working on pages, components, contexts, hooks |
| `nextjs-16` | App Router patterns, route handlers |
| `radix-tailwind` | UI components, Tailwind styling |
| `typescript-frontend-patterns` | React patterns, API client, data fetching |
| `msia-tariffs` | Tariff system UI |
| `msia-test` | Writing Jest tests |
