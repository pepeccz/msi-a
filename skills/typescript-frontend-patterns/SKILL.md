---
name: typescript-frontend-patterns
description: >
  TypeScript and React patterns for MSI-a admin panel.
  Trigger: When working on React components, TypeScript types, API clients, or custom hooks.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root, admin-panel]
  auto_invoke: "TypeScript/React patterns"
---

## Project TypeScript Patterns

This skill documents the **actual patterns used** in the MSI-a admin panel codebase, not theoretical best practices.

## API Client Pattern (Singleton Class)

**File:** `lib/api.ts` (1357 lines)

```typescript
// Singleton pattern with generic CRUD methods
const API_BASE_URL = ""; // Relative - Next.js rewrites proxy to backend

interface ApiError {
  error: string;
  details?: unknown;
}

class ApiClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  setToken(token: string | null) {
    this.token = token;
  }

  getToken(): string | null {
    if (typeof window !== "undefined") {
      return this.token || localStorage.getItem("admin_token");
    }
    return this.token;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const token = this.getToken();

    const headers: HeadersInit = {
      "Content-Type": "application/json",
      ...options.headers,
    };

    if (token) {
      (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: "include",
    });

    if (!response.ok) {
      if (response.status === 401) {
        this.setToken(null);
        if (typeof window !== "undefined") {
          localStorage.removeItem("admin_token");
          const currentPath = window.location.pathname + window.location.search;
          if (currentPath !== "/login") {
            sessionStorage.setItem("returnTo", currentPath);
          }
          window.location.href = "/login";
        }
      }

      const error: ApiError = await response.json().catch(() => ({
        error: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(error.error || "Unknown error");
    }

    if (response.status === 204 || response.headers.get("content-length") === "0") {
      return undefined as T;
    }
    return response.json();
  }

  // Generic CRUD methods
  async list<T>(
    resource: string,
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<PaginatedResponse<T>> {
    const searchParams = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          searchParams.append(key, String(value));
        }
      });
    }
    const query = searchParams.toString();
    return this.request(`/api/admin/${resource}${query ? `?${query}` : ""}`);
  }

  async get<T>(resource: string, id: string): Promise<T> {
    return this.request(`/api/admin/${resource}/${id}`);
  }

  async create<T, D = Partial<T>>(resource: string, data: D): Promise<T> {
    return this.request(`/api/admin/${resource}`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async update<T, D = Partial<T>>(resource: string, id: string, data: D): Promise<T> {
    return this.request(`/api/admin/${resource}/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  async delete(resource: string, id: string): Promise<void> {
    await this.request(`/api/admin/${resource}/${id}`, {
      method: "DELETE",
    });
  }

  // Resource-specific methods build on generic CRUD
  async getUsers(params?: Record<string, string | number | boolean | undefined>): Promise<PaginatedResponse<User>> {
    return this.list<User>("users", params);
  }

  async getUser(id: string): Promise<User> {
    return this.get<User>("users", id);
  }

  async createUser(data: UserCreate): Promise<User> {
    return this.create<User, UserCreate>("users", data);
  }

  async updateUser(id: string, data: UserUpdate): Promise<User> {
    return this.update<User, UserUpdate>("users", id, data);
  }

  async deleteUser(id: string): Promise<void> {
    return this.delete("users", id);
  }

  // Special methods for file uploads
  async uploadImage(file: File, category?: string, description?: string): Promise<UploadedImage> {
    const formData = new FormData();
    formData.append("file", file);

    const params = new URLSearchParams();
    if (category) params.append("category", category);
    if (description) params.append("description", description);

    const url = `/api/admin/images/upload${params.toString() ? `?${params}` : ""}`;
    const token = this.getToken();

    const headers: HeadersInit = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(`${this.baseUrl}${url}`, {
      method: "POST",
      headers,
      body: formData,
      credentials: "include",
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        error: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(error.detail || error.error || "Upload failed");
    }

    return response.json();
  }
}

export const api = new ApiClient(API_BASE_URL);
export default api;
```

**Key patterns:**
- Singleton export: `export const api = new ApiClient(...)`
- Generic CRUD methods: `list()`, `get()`, `create()`, `update()`, `delete()`
- Resource-specific wrappers for type safety
- Auto-redirect to `/login` on 401
- Save `returnTo` path for post-login redirect
- Handle 204 No Content responses
- Separate methods for `FormData` uploads

## Types Pattern (Domain-Organized Interfaces)

**File:** `lib/types.ts` (1397 lines, 100+ interfaces)

```typescript
// Admin user types
export type AdminRole = "admin" | "user";

export interface AdminUser {
  id: string;
  username: string;
  display_name: string;
  role: AdminRole;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AdminUserCreate {
  username: string;
  password: string;
  display_name: string;
  role: AdminRole;
  is_active?: boolean;
}

export interface AdminUserUpdate {
  display_name?: string;
  role?: AdminRole;
  is_active?: boolean;
}

export interface AdminUserPasswordChange {
  new_password: string;
}

// WhatsApp user types
export type ClientType = "particular" | "professional";

export interface User {
  id: string;
  chatwoot_contact_id: number;
  name: string;
  email: string | null;
  phone: string;
  client_type: ClientType;
  created_at: string;
  updated_at: string;
}

export interface UserCreate {
  chatwoot_contact_id: number;
  name: string;
  email?: string | null;
  phone: string;
  client_type: ClientType;
}

export interface UserUpdate {
  name?: string;
  email?: string | null;
  phone?: string;
  client_type?: ClientType;
}

// Paginated response wrapper
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

// Case types with nested data
export type CaseStatus = "pending" | "in_progress" | "resolved" | "cancelled";

export interface Case {
  id: string;
  user_id: string;
  status: CaseStatus;
  category_id: string | null;
  tier_id: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  
  // Relations
  user: User;
  category: VehicleCategory | null;
  tier: TariffTier | null;
  images: CaseImage[];
  element_data: CaseElementData[];
}

export interface CaseListItem {
  id: string;
  user_id: string;
  user_name: string;
  status: CaseStatus;
  category_name: string | null;
  created_at: string;
}
```

**Organization pattern:**
- **Domain grouping**: Admin users, WhatsApp users, cases, elements, etc.
- **CRUD trio**: `Type`, `TypeCreate`, `TypeUpdate` for each entity
- **List vs Detail**: `TypeListItem` (minimal) vs `Type` (with relations)
- **Enums as string literal unions**: `type CaseStatus = "pending" | "in_progress" | ...`
- **Generic wrappers**: `PaginatedResponse<T>`
- **Nested relations**: Full objects, not just IDs

## Custom Hook Pattern (Data Fetching)

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

**Key patterns:**
- Return object with data + meta state
- `useCallback` for `refetch` function (dependency stability)
- `useEffect` triggers fetch on mount + dependency changes
- Error logged to console + stored in state
- `finally` block for loading state cleanup

**Usage:**

```typescript
export default function CategoryPage({ params }: { params: { categoryId: string } }) {
  const { category, isLoading, error, refetch } = useCategoryData(params.categoryId);

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorCard error={error} />;
  if (!category) return <NotFound />;

  return (
    <div>
      <h1>{category.name}</h1>
      <Button onClick={refetch}>Reload</Button>
    </div>
  );
}
```

## Context Pattern (Auth Example)

```typescript
"use client";

import { createContext, useContext, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { CurrentUser, AdminRole } from "@/lib/types";

// 1. Define context interface
interface AuthContextType {
  user: CurrentUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  hasRole: (role: AdminRole) => boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

// 2. Create context with undefined default
const AuthContext = createContext<AuthContextType | undefined>(undefined);

// 3. Provider component
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
    api.logout();
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

// 4. Custom hook with error boundary
export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
```

**Key patterns:**
- Separate interface for context value
- `undefined` as default (not `null`) to catch missing Provider
- Custom hook with error boundary
- Provider mounted in root layout
- Derived values (isAuthenticated, isAdmin) computed from state

## Form State Pattern

```typescript
// Dialog-based form
const [formData, setFormData] = useState<UserCreate>({
  name: "",
  email: "",
  phone: "",
  client_type: "particular",
});

// Update field
function handleFieldChange(field: keyof UserCreate, value: string) {
  setFormData(prev => ({ ...prev, [field]: value }));
}

// Or with event handlers
<Input
  value={formData.name}
  onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
/>

// Inline edit with change tracking
const [initialData, setInitialData] = useState<UserUpdate>(user);
const [formData, setFormData] = useState<UserUpdate>(user);
const [hasChanges, setHasChanges] = useState(false);

useEffect(() => {
  setHasChanges(JSON.stringify(formData) !== JSON.stringify(initialData));
}, [formData, initialData]);

async function handleSave() {
  await api.updateUser(userId, formData);
  setInitialData(formData); // Reset baseline
  setHasChanges(false);
}
```

## Constants Pattern

**File:** `lib/constants.ts`

```typescript
// Configuration constants to avoid magic numbers
export const DEFAULT_ELEMENTS_LIMIT = 500;
export const TOOL_LOGS_PAGE_SIZE = 30;
export const SEARCH_DEBOUNCE_MS = 300;
export const MAX_VISIBLE_KEYWORDS = 3;
export const MAX_VISIBLE_SERVICES = 3;
export const CATEGORY_CACHE_TTL_MS = 300000; // 5 min

// Usage in hooks
import { DEFAULT_ELEMENTS_LIMIT } from "@/lib/constants";

export function useCategoryElements(categoryId: string, options?: { limit?: number }) {
  const limit = options?.limit ?? DEFAULT_ELEMENTS_LIMIT;
  // ...
}

// Usage in components
import { SEARCH_DEBOUNCE_MS } from "@/lib/constants";

useEffect(() => {
  const timer = setTimeout(() => {
    setDebouncedQuery(searchQuery);
  }, SEARCH_DEBOUNCE_MS);
  return () => clearTimeout(timer);
}, [searchQuery]);
```

## Utility Functions Pattern

**File:** `lib/validators.ts`

```typescript
export interface FilenameValidation {
  isValid: boolean;
  error: string | null;
}

export function getFileExtension(filename: string): string {
  const lastDot = filename.lastIndexOf(".");
  return lastDot === -1 ? "" : filename.slice(lastDot);
}

export function getBasename(filename: string): string {
  const ext = getFileExtension(filename);
  return ext ? filename.slice(0, -ext.length) : filename;
}

export function validateFilename(filename: string): FilenameValidation {
  if (!filename || filename.trim() === "") {
    return { isValid: false, error: "El nombre del archivo no puede estar vacío" };
  }

  if (filename.length > 200) {
    return { isValid: false, error: "El nombre del archivo es demasiado largo (máximo 200 caracteres)" };
  }

  const invalidChars = /[\/\\:*?"<>|]/;
  if (invalidChars.test(filename)) {
    return { isValid: false, error: "El nombre contiene caracteres no válidos" };
  }

  if (filename.startsWith(" ") || filename.endsWith(" ")) {
    return { isValid: false, error: "El nombre no puede comenzar ni terminar con espacios" };
  }

  if (/\s{2,}/.test(filename)) {
    return { isValid: false, error: "El nombre no puede contener espacios consecutivos" };
  }

  return { isValid: true, error: null };
}

export function sanitizeFilename(filename: string): string {
  let sanitized = filename
    .replace(/[\/\\:*?"<>|]/g, "-") // Replace invalid chars
    .replace(/\s+/g, " ") // Compress spaces
    .trim(); // Remove leading/trailing spaces

  if (sanitized.length > 200) {
    const ext = getFileExtension(sanitized);
    const base = getBasename(sanitized);
    const maxBaseLength = 200 - ext.length;
    sanitized = base.slice(0, maxBaseLength) + ext;
  }

  return sanitized;
}

export function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
}

export async function getImageDimensions(file: File): Promise<{ width: number; height: number } | null> {
  if (!file.type.startsWith("image/")) return null;

  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve({ width: img.width, height: img.height });
    img.onerror = () => resolve(null);
    img.src = URL.createObjectURL(file);
  });
}
```

**Key patterns:**
- Custom return types for complex results
- Spanish error messages
- Chainable utility functions
- Async utilities return `Promise<T | null>`

## Critical Rules

### Must Do

- **ALWAYS** use the `api` singleton for HTTP requests
- **ALWAYS** define types in `lib/types.ts` (never inline for API responses)
- **ALWAYS** use constants from `lib/constants.ts`
- **ALWAYS** wrap fetch functions in `useCallback` for dependency stability
- **ALWAYS** provide `refetch` function in custom hooks
- **ALWAYS** handle error + loading states in hooks
- **ALWAYS** use spread operator for state updates: `setState(prev => ({ ...prev, field: value }))`
- **ALWAYS** clean up timers/intervals in `useEffect` return
- **ALWAYS** check context !== undefined in custom hooks

### Must Not

- **NEVER** fetch directly with `fetch()` — use `api` singleton
- **NEVER** inline API response types — define in `lib/types.ts`
- **NEVER** hardcode magic numbers — define in `lib/constants.ts`
- **NEVER** mutate state directly: `formData.name = "x"` ❌
- **NEVER** forget cleanup in `useEffect` with timers/intervals
- **NEVER** use context without error boundary check

## Related Skills

- [msia-admin](../msia-admin/SKILL.md) - Admin panel React patterns
- [nextjs-16](../nextjs-16/SKILL.md) - Next.js App Router
- [radix-tailwind](../radix-tailwind/SKILL.md) - UI components
