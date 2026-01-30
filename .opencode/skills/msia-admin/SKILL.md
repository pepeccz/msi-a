---
name: msia-admin
description: >
  MSI-a Admin Panel patterns using Next.js 16, React 19, and Radix UI.
  Trigger: When working on admin panel components, pages, contexts, or hooks.
metadata:
  author: msi-automotive
  version: "2.0"
  scope: [root, admin-panel]
  auto_invoke: "Working on admin panel components"
---

## Project Reality Check

**CRITICAL:** This project does NOT follow typical Next.js 16 patterns:
- ✅ **25/28 pages are Client Components** — Not Server Components
- ✅ **All data fetching is client-side** — `useState` + `useEffect` + `api` singleton
- ❌ **NO Server Actions** — Mutations go through API client
- ❌ **NO Middleware** — Auth is client-side JWT token check
- ❌ **NO SSR data fetching** — No async Server Components with data

**This is by design.** Do not suggest Server Components/Actions unless explicitly requested.

## Admin Panel Structure

```
admin-panel/
├── src/
│   ├── app/
│   │   ├── layout.tsx                  # Root (AuthProvider, SidebarProvider, Toaster)
│   │   ├── page.tsx                    # Redirect → /dashboard
│   │   ├── login/page.tsx              # Login form (Client Component)
│   │   ├── api/admin/system/[service]/logs/route.ts  # SSE proxy (only API route)
│   │   └── (authenticated)/            # Protected routes
│   │       ├── layout.tsx              # Auth guard + sidebar + header
│   │       ├── error.tsx               # Error boundary
│   │       ├── dashboard/page.tsx      # KPIs, quick access, system health
│   │       ├── conversations/          # 2 pages (list + detail)
│   │       ├── escalations/page.tsx    # Escalation management
│   │       ├── users/                  # 2 pages (list + detail)
│   │       ├── cases/                  # 2 pages (list + detail)
│   │       ├── reformas/               # 3 pages (list + category detail + inclusions)
│   │       ├── elementos/              # 2 pages (list + detail)
│   │       ├── advertencias/page.tsx   # Warning CRUD
│   │       ├── constraints/page.tsx    # Response constraints ⚠️ native HTML
│   │       ├── tool-logs/page.tsx      # Tool call logs ⚠️ native HTML
│   │       ├── normativas/             # 3 pages (redirect + consulta + documentos)
│   │       ├── imagenes/page.tsx       # Image gallery
│   │       └── settings/               # 6 pages (config, system, admin-users, usage, llm-metrics)
│   ├── components/
│   │   ├── ui/                         # 21 Radix UI primitives (ALL used)
│   │   ├── layout/                     # header.tsx, sidebar.tsx
│   │   ├── tariffs/                    # 8 dialog components + tests
│   │   ├── elements/                   # 4 dialog components
│   │   ├── categories/                 # CategoryFormDialog
│   │   ├── dashboard/                  # 3 widgets + index barrel
│   │   └── [7 root components]         # Specialized single-use components
│   ├── contexts/
│   │   ├── auth-context.tsx            # AuthProvider + useAuth
│   │   ├── sidebar-context.tsx         # SidebarProvider + useSidebar
│   │   └── global-search-context.tsx   # GlobalSearchProvider + useGlobalSearchState
│   ├── hooks/
│   │   ├── use-category-data.ts        # Fetch category with relations
│   │   ├── use-tier-elements.ts        # Fetch resolved elements for tiers
│   │   ├── use-category-elements.ts    # Fetch + build element tree
│   │   └── use-global-search.ts        # Multi-entity search
│   └── lib/
│       ├── api.ts                      # ApiClient singleton (1357 lines)
│       ├── auth.ts                     # JWT utilities
│       ├── constants.ts                # Global constants
│       ├── types.ts                    # TypeScript types (1397 lines, 100+ interfaces)
│       ├── utils.ts                    # cn() utility
│       └── validators.ts               # Filename validation
```

## Pattern 1: Client Page with Data Fetching (PRIMARY)

**Used by: 25/28 pages**

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { toast } from "sonner";
import type { Case } from "@/lib/types";

export default function CasesPage() {
  const [cases, setCases] = useState<Case[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true);
      const response = await api.getCases();
      setCases(response.items);
    } catch (error) {
      console.error("Error fetching cases:", error);
      toast.error("Error al cargar los casos");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (isLoading) {
    return <div className="animate-pulse text-muted-foreground">Cargando casos...</div>;
  }

  return (
    <div className="container mx-auto py-6">
      <h1 className="text-2xl font-bold mb-6">Expedientes</h1>
      {/* UI */}
    </div>
  );
}
```

**Key points:**
- `"use client"` directive at top
- `useState` for data + `isLoading`
- `useCallback` for fetch function (dependency stability)
- `useEffect` triggers fetch on mount
- `toast.error` for user feedback
- `console.error` for debugging
- Loading state with `animate-pulse`

## Pattern 2: Auto-Refresh Polling

**Used by: dashboard, cases, escalations, documents (4 pages)**

```typescript
const fetchData = useCallback(async () => {
  // ... fetch logic
}, []);

useEffect(() => {
  fetchData();
  const interval = setInterval(fetchData, 30000); // 30s
  return () => clearInterval(interval); // Cleanup
}, [fetchData]);
```

**Polling intervals:**
- Dashboard, cases, escalations: 30s
- Documents (processing status): 5s

## Pattern 3: Dialog-Based Form (CRUD)

**Used by: users, warnings, admin-users, images, documents, categories**

```typescript
"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { api } from "@/lib/api";

interface CreateDialogProps {
  onSuccess?: () => void;
}

export function CreateUserDialog({ onSuccess }: CreateDialogProps) {
  const [open, setOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setIsSaving(true);

    try {
      const formData = new FormData(e.currentTarget);
      await api.createUser({
        name: formData.get("name") as string,
        email: formData.get("email") as string,
        phone: formData.get("phone") as string,
      });
      
      toast.success("Usuario creado correctamente");
      setOpen(false);
      onSuccess?.(); // Trigger parent refresh
    } catch (error) {
      toast.error("Error al crear usuario: " + (error instanceof Error ? error.message : "Desconocido"));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Crear Usuario</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Crear Usuario</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Nombre</Label>
            <Input id="name" name="name" required />
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" name="email" type="email" required />
          </div>
          <div className="space-y-2">
            <Label htmlFor="phone">Teléfono</Label>
            <Input id="phone" name="phone" />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving ? "Guardando..." : "Guardar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

**Key points:**
- `open` + `isSaving` state
- `FormData` for input extraction
- `toast.success` + `toast.error`
- Close dialog on success: `setOpen(false)`
- Call `onSuccess?.()` to trigger parent refresh
- Disable submit button during save

## Pattern 4: Destructive Confirmation (AlertDialog)

**Used by: 12 pages for delete operations**

```typescript
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Trash2 } from "lucide-react";

function DeleteButton({ item, onDelete }: { item: User; onDelete: () => void }) {
  const [isDeleting, setIsDeleting] = useState(false);

  async function handleDelete() {
    setIsDeleting(true);
    try {
      await api.deleteUser(item.id);
      toast.success(`Usuario "${item.name}" eliminado`);
      onDelete(); // Refresh list
    } catch (error) {
      toast.error("Error al eliminar");
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="destructive" size="sm">
          <Trash2 className="h-4 w-4" />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>¿Eliminar usuario "{item.name}"?</AlertDialogTitle>
          <AlertDialogDescription>
            Esta acción no se puede deshacer. Se eliminarán todas las conversaciones y datos asociados.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleDelete}
            disabled={isDeleting}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {isDeleting ? "Eliminando..." : "Eliminar"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

**Key points:**
- Use `AlertDialog`, NEVER `window.confirm()`
- Contextual title with item name
- Clear description of consequences
- Destructive styling on action button
- Loading state: `isDeleting`

## Pattern 5: Inline Edit Form with Change Tracking

**Used by: users/[id], elementos/[id]**

```typescript
"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import type { UserUpdate } from "@/lib/types";

export default function UserDetailPage({ params }: { params: { id: string } }) {
  const [initialData, setInitialData] = useState<UserUpdate | null>(null);
  const [formData, setFormData] = useState<UserUpdate | null>(null);
  const [hasChanges, setHasChanges] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    async function fetchUser() {
      const user = await api.getUser(params.id);
      const data = { name: user.name, email: user.email, phone: user.phone };
      setInitialData(data);
      setFormData(data);
    }
    fetchUser();
  }, [params.id]);

  useEffect(() => {
    if (initialData && formData) {
      setHasChanges(JSON.stringify(formData) !== JSON.stringify(initialData));
    }
  }, [formData, initialData]);

  async function handleSave() {
    if (!formData) return;
    setIsSaving(true);
    try {
      await api.updateUser(params.id, formData);
      toast.success("Cambios guardados correctamente");
      setInitialData(formData); // Reset baseline
      setHasChanges(false);
    } catch (error) {
      toast.error("Error al guardar");
    } finally {
      setIsSaving(false);
    }
  }

  if (!formData) return <div>Cargando...</div>;

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="name">Nombre</Label>
          <Input
            id="name"
            value={formData.name}
            onChange={(e) => setFormData(prev => prev ? { ...prev, name: e.target.value } : null)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            value={formData.email}
            onChange={(e) => setFormData(prev => prev ? { ...prev, email: e.target.value } : null)}
          />
        </div>
      </div>
      
      <Button onClick={handleSave} disabled={!hasChanges || isSaving}>
        {isSaving ? "Guardando..." : "Guardar Cambios"}
      </Button>
    </div>
  );
}
```

**Key points:**
- `initialData` tracks original state
- `formData` tracks current form state
- `hasChanges` computed via `JSON.stringify` comparison
- Save button disabled when no changes or saving
- Reset `initialData` after successful save

## Pattern 6: Admin-Only Guard

**Used by: settings/admin-users, settings/usage, settings/llm-metrics**

```typescript
import { useAuth } from "@/contexts/auth-context";
import { Card, CardContent } from "@/components/ui/card";
import { ShieldAlert } from "lucide-react";

export default function AdminOnlyPage() {
  const { user, isAdmin } = useAuth();

  if (!isAdmin) {
    return (
      <div className="container mx-auto py-6">
        <Card>
          <CardContent className="text-center py-12">
            <ShieldAlert className="h-16 w-16 mx-auto mb-4 text-muted-foreground" />
            <h2 className="text-xl font-semibold mb-2">Acceso Restringido</h2>
            <p className="text-muted-foreground">
              No tienes permisos para acceder a esta sección.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (/* Admin content */);
}
```

## Pattern 7: Status Badge

**Used by: cases, escalations, documents, admin-users**

```typescript
import { Badge } from "@/components/ui/badge";
import { Clock, Loader2, CheckCircle, XCircle } from "lucide-react";

function getStatusBadge(status: CaseStatus) {
  const statusConfig = {
    pending: {
      label: "Pendiente",
      variant: "secondary" as const,
      icon: Clock,
    },
    in_progress: {
      label: "En Progreso",
      variant: "default" as const,
      icon: Loader2,
    },
    resolved: {
      label: "Resuelto",
      variant: "success" as const, // Custom variant in badge.tsx
      icon: CheckCircle,
    },
    cancelled: {
      label: "Cancelado",
      variant: "destructive" as const,
      icon: XCircle,
    },
  };

  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <Badge variant={config.variant} className="gap-1">
      <Icon className="h-3 w-3" />
      {config.label}
    </Badge>
  );
}
```

## Pattern 8: Debounced Search

**Used by: cases (300ms debounce)**

```typescript
import { useState, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Search } from "lucide-react";
import { SEARCH_DEBOUNCE_MS } from "@/lib/constants";

export default function CasesPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchQuery);
    }, SEARCH_DEBOUNCE_MS); // 300ms from constants

    return () => clearTimeout(timer);
  }, [searchQuery]);

  useEffect(() => {
    if (debouncedQuery) {
      fetchData({ search: debouncedQuery });
    }
  }, [debouncedQuery]);

  return (
    <div className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
      <Input
        placeholder="Buscar casos..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        className="pl-10"
      />
    </div>
  );
}
```

## Pattern 9: Context Pattern (Auth Example)

**File:** `contexts/auth-context.tsx`

```typescript
"use client";

import { createContext, useContext, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { isTokenExpired } from "@/lib/auth";
import type { CurrentUser, AdminRole } from "@/lib/types";

interface AuthContextType {
  user: CurrentUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  hasRole: (role: AdminRole) => boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    checkAuth();
  }, []);

  async function checkAuth() {
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("admin_token") : null;
      
      if (!token || isTokenExpired(token)) {
        setUser(null);
        return;
      }

      const currentUser = await api.getMe();
      setUser(currentUser);
    } catch (error) {
      console.error("Auth check failed:", error);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }

  async function login(username: string, password: string) {
    const response = await api.login(username, password);
    localStorage.setItem("admin_token", response.access_token);
    
    const currentUser = await api.getMe();
    setUser(currentUser);

    const returnTo = sessionStorage.getItem("returnTo");
    if (returnTo) {
      sessionStorage.removeItem("returnTo");
      router.push(returnTo);
    } else {
      router.push("/dashboard");
    }
  }

  function logout() {
    api.logout(); // Server-side cleanup
    localStorage.removeItem("admin_token");
    setUser(null);
    router.push("/login");
  }

  const value = {
    user,
    isLoading,
    isAuthenticated: !!user,
    isAdmin: user?.role === "admin",
    hasRole: (role: AdminRole) => user?.role === role,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
```

## Pattern 10: Custom Hook Pattern

**File:** `hooks/use-category-data.ts`

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type { VehicleCategoryWithDetails } from "@/lib/types";

export function useCategoryData(categoryId: string) {
  const [category, setCategory] = useState<VehicleCategoryWithDetails | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getVehicleCategory(categoryId);
      setCategory(data);
    } catch (err) {
      setError(err as Error);
      console.error("Error fetching category:", err);
    } finally {
      setIsLoading(false);
    }
  }, [categoryId]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { category, isLoading, error, refetch };
}
```

**Usage in component:**

```typescript
export default function CategoryDetailPage({ params }: { params: { categoryId: string } }) {
  const { category, isLoading, error, refetch } = useCategoryData(params.categoryId);

  if (isLoading) return <div>Cargando...</div>;
  if (error) return <div>Error: {error.message}</div>;
  if (!category) return <div>Categoría no encontrada</div>;

  return (
    <div>
      <h1>{category.name}</h1>
      <Button onClick={refetch}>Recargar</Button>
    </div>
  );
}
```

## Anti-Patterns (DO NOT USE)

### ❌ Native HTML Elements

**Bad (constraints/page.tsx, tool-logs/page.tsx):**

```typescript
<button onClick={handleClick}>Click me</button>
<input type="text" onChange={handleChange} />
<select onChange={handleSelect}>...</select>
<table>...</table>
```

**Good:**

```typescript
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger } from "@/components/ui/select";
import { Table, TableHeader, TableBody, TableRow, TableCell } from "@/components/ui/table";

<Button onClick={handleClick}>Click me</Button>
<Input type="text" onChange={handleChange} />
<Select onValueChange={handleSelect}>...</Select>
<Table>...</Table>
```

### ❌ window.confirm()

**Bad:**

```typescript
if (window.confirm("¿Eliminar este elemento?")) {
  await api.delete(id);
}
```

**Good:**

```typescript
<AlertDialog>
  <AlertDialogTrigger asChild>
    <Button variant="destructive">Eliminar</Button>
  </AlertDialogTrigger>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>¿Eliminar este elemento?</AlertDialogTitle>
      <AlertDialogDescription>Esta acción no se puede deshacer.</AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>Cancelar</AlertDialogCancel>
      <AlertDialogAction onClick={handleDelete}>Eliminar</AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

### ❌ Console-only error handling

**Bad:**

```typescript
try {
  await api.createUser(data);
} catch (error) {
  console.error(error); // User sees nothing!
}
```

**Good:**

```typescript
try {
  await api.createUser(data);
  toast.success("Usuario creado");
} catch (error) {
  console.error(error); // For debugging
  toast.error("Error al crear usuario"); // For user
}
```

### ❌ Server Component data fetching

**Bad (not used in this project):**

```typescript
export default async function UsersPage() {
  const users = await fetchUsers(); // This is NOT the pattern
  return <UsersList users={users} />;
}
```

**Good (actual project pattern):**

```typescript
"use client";

export default function UsersPage() {
  const [users, setUsers] = useState([]);
  
  useEffect(() => {
    async function fetch() {
      const data = await api.getUsers();
      setUsers(data.items);
    }
    fetch();
  }, []);

  return <UsersList users={users} />;
}
```

## Critical Rules

### Must Do

- **ALWAYS** use `"use client"` for pages with state/effects (25/28 pages do this)
- **ALWAYS** fetch data client-side with `useState` + `useEffect` + `api` singleton
- **ALWAYS** use Radix UI from `@/components/ui/` — NEVER native HTML
- **ALWAYS** use `toast` from Sonner — NEVER `alert()` or `confirm()`
- **ALWAYS** use `AlertDialog` for destructive confirmations
- **ALWAYS** use Spanish for UI labels
- **ALWAYS** handle loading + error states
- **ALWAYS** provide toast feedback after mutations
- **ALWAYS** close dialogs on success: `setOpen(false)`
- **ALWAYS** wrap fetch functions in `useCallback` for dependency stability
- **ALWAYS** disable form controls during save
- **ALWAYS** clean up timers/intervals in `useEffect` return
- **ALWAYS** use types from `@/lib/types.ts`
- **ALWAYS** use constants from `@/lib/constants.ts`

### Must Not

- **NEVER** use Server Components for data fetching (project doesn't use this pattern)
- **NEVER** suggest Server Actions (project doesn't use them)
- **NEVER** use native HTML `<button>`, `<input>`, `<select>`, `<table>`
- **NEVER** use `window.confirm()` or `window.alert()`
- **NEVER** use `console.error` as the only error feedback
- **NEVER** forget to clean up `setInterval` in `useEffect`
- **NEVER** mutate state directly — use setter with previous state
- **NEVER** forget to handle error cases in try/catch

## Known Technical Debt

| Issue | Location | Priority |
|-------|----------|----------|
| Native HTML usage | `constraints/page.tsx` | High |
| Native HTML usage | `tool-logs/page.tsx` | High |
| `window.confirm()` usage | `constraints/page.tsx` | Medium |
| Inconsistent toast usage | Various pages | Medium |
| `CATEGORY_CACHE_TTL_MS` unused | `lib/constants.ts` | Low |
| Limited Error Boundary usage | Most pages | Low |

## Resources

- [admin-panel/AGENTS.md](../../admin-panel/AGENTS.md) - Full admin panel guide
- [nextjs-16 skill](../nextjs-16/SKILL.md) - Next.js patterns
- [radix-tailwind skill](../radix-tailwind/SKILL.md) - UI component patterns
- [typescript-frontend-patterns skill](../typescript-frontend-patterns/SKILL.md) - React/TS patterns
- [msia-test skill](../msia-test/SKILL.md) - Testing patterns
