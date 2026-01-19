---
name: msia-admin
description: >
  MSI-a Admin Panel patterns using Next.js and Radix UI.
  Trigger: When working on admin panel components, pages, contexts, or hooks.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root, admin-panel]
  auto_invoke: "Working on admin panel components"
---

## Admin Panel Structure

```
admin-panel/
├── src/
│   ├── app/
│   │   ├── layout.tsx              # Root layout
│   │   ├── page.tsx                # Redirect to login/dashboard
│   │   ├── login/page.tsx          # Login page
│   │   └── (authenticated)/        # Protected routes
│   │       ├── layout.tsx          # Auth check + sidebar
│   │       ├── dashboard/page.tsx
│   │       ├── conversations/
│   │       ├── escalations/
│   │       ├── users/
│   │       ├── cases/
│   │       ├── reformas/           # Tariff management
│   │       ├── elementos/          # Element management
│   │       ├── advertencias/       # Warnings
│   │       ├── normativas/         # RAG documents
│   │       ├── imagenes/           # Image management
│   │       └── settings/
│   ├── components/
│   │   ├── ui/                     # Radix UI primitives
│   │   ├── layout/                 # Header, Sidebar
│   │   ├── tariffs/                # Tariff-specific
│   │   ├── elements/               # Element-specific
│   │   └── categories/             # Category components
│   ├── contexts/
│   │   ├── auth-context.tsx        # Authentication
│   │   └── sidebar-context.tsx     # Sidebar state
│   ├── hooks/
│   │   ├── use-category-data.ts    # Category fetching
│   │   ├── use-category-elements.ts
│   │   └── use-tier-elements.ts
│   └── lib/
│       ├── api.ts                  # API client
│       ├── auth.ts                 # Auth utilities
│       ├── types.ts                # TypeScript types
│       ├── utils.ts                # cn() and helpers
│       └── validators.ts           # Form validation
└── package.json
```

## Page Pattern (Server Component)

```typescript
// app/(authenticated)/elementos/page.tsx
import { Suspense } from "react";
import { ElementsList } from "@/components/elements/elements-list";
import { ElementsListSkeleton } from "@/components/elements/elements-list-skeleton";

export const metadata = {
  title: "Elementos | MSI-a Admin",
};

export default function ElementsPage() {
  return (
    <div className="container mx-auto py-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Elementos</h1>
      </div>
      <Suspense fallback={<ElementsListSkeleton />}>
        <ElementsList />
      </Suspense>
    </div>
  );
}
```

## Dialog Pattern (Client Component)

```typescript
// components/tariffs/tier-form-dialog.tsx
"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

interface TierFormDialogProps {
  categoryId: string;
  onSuccess?: () => void;
  trigger?: React.ReactNode;
}

export function TierFormDialog({ categoryId, onSuccess, trigger }: TierFormDialogProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);

    const formData = new FormData(e.currentTarget);
    const data = {
      category_id: categoryId,
      code: formData.get("code") as string,
      name: formData.get("name") as string,
      price: parseFloat(formData.get("price") as string),
    };

    try {
      await api.post("/tariffs/tiers", data);
      setOpen(false);
      onSuccess?.();
    } catch (error) {
      console.error("Failed to create tier:", error);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? <Button>Nuevo Tier</Button>}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Crear Tier</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="code">Codigo</Label>
            <Input id="code" name="code" required />
          </div>
          <div className="space-y-2">
            <Label htmlFor="name">Nombre</Label>
            <Input id="name" name="name" required />
          </div>
          <div className="space-y-2">
            <Label htmlFor="price">Precio (EUR)</Label>
            <Input
              id="price"
              name="price"
              type="number"
              step="0.01"
              min="0"
              required
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? "Guardando..." : "Guardar"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

## API Client Pattern

```typescript
// lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiClient {
  private getHeaders(): HeadersInit {
    const token = localStorage.getItem("token");
    return {
      "Content-Type": "application/json",
      ...(token && { Authorization: `Bearer ${token}` }),
    };
  }

  async get<T>(path: string): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: this.getHeaders(),
    });
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    return response.json();
  }

  async post<T>(path: string, data: unknown): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    return response.json();
  }

  // ... put, delete, etc.
}

export const api = new ApiClient();
```

## Hook Pattern

```typescript
// hooks/use-category-data.ts
"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import type { VehicleCategory, TariffTier } from "@/lib/types";

interface CategoryData {
  category: VehicleCategory | null;
  tiers: TariffTier[];
  loading: boolean;
  error: Error | null;
  refresh: () => void;
}

export function useCategoryData(categoryId: string): CategoryData {
  const [category, setCategory] = useState<VehicleCategory | null>(null);
  const [tiers, setTiers] = useState<TariffTier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  async function fetchData() {
    setLoading(true);
    try {
      const [cat, tierList] = await Promise.all([
        api.get<VehicleCategory>(`/api/tariffs/categories/${categoryId}`),
        api.get<TariffTier[]>(`/api/tariffs/categories/${categoryId}/tiers`),
      ]);
      setCategory(cat);
      setTiers(tierList);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchData();
  }, [categoryId]);

  return { category, tiers, loading, error, refresh: fetchData };
}
```

## Auth Context Pattern

```typescript
// contexts/auth-context.tsx
"use client";

import { createContext, useContext, useState, useEffect } from "react";
import { useRouter } from "next/navigation";

interface User {
  id: string;
  username: string;
  role: "admin" | "user";
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  // Check auth on mount
  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) {
      // Validate token...
    }
    setLoading(false);
  }, []);

  async function login(username: string, password: string) {
    // API call...
  }

  function logout() {
    localStorage.removeItem("token");
    setUser(null);
    router.push("/login");
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
```

## Toast Notifications (Sonner)

The admin panel uses **Sonner** for toast notifications. The `<Toaster>` is already configured in the root layout.

```typescript
// Import toast from sonner
import { toast } from "sonner";

// Success messages
toast.success("Elemento actualizado correctamente");

// Error messages
toast.error("Error al guardar: " + error.message);

// Info messages
toast.info("Procesando...");

// NEVER use native alert() - always use toast
```

## Image Gallery Pattern

Use `ImageGalleryDialog` from `@/components/image-upload` to allow users to select existing images from the gallery.

```typescript
import { ImageGalleryDialog } from "@/components/image-upload";

// State
const [showGallery, setShowGallery] = useState(false);

// Handler
const handleSelectFromGallery = (url: string) => {
  setShowGallery(false);
  // Use the selected image URL
  setImageUrl(url);
};

// Component usage
<ImageGalleryDialog
  open={showGallery}
  onOpenChange={setShowGallery}
  onSelect={handleSelectFromGallery}
  category="element" // optional: filter by category
/>
```

For full image upload with gallery support, use the `ImageUpload` component:

```typescript
import { ImageUpload } from "@/components/image-upload";

<ImageUpload
  value={imageUrl}
  onChange={(url) => setImageUrl(url)}
  category="element"
/>
```

## Critical Rules

- Server Components are DEFAULT - only use "use client" when needed
- ALWAYS use Spanish for UI labels (user-facing content)
- ALWAYS use Radix UI primitives from `@/components/ui/`
- ALWAYS use `cn()` from `@/lib/utils` for conditional classes
- NEVER use `useState` in Server Components
- ALWAYS handle loading/error states in hooks
- ALWAYS close dialogs on successful form submission
- NEVER use `alert()` - use `toast` from Sonner instead
- ALWAYS provide feedback via toast after user actions (save, delete, etc.)

## Resources

- [nextjs-16 skill](../nextjs-16/SKILL.md) - Next.js patterns
- [radix-tailwind skill](../radix-tailwind/SKILL.md) - UI patterns
