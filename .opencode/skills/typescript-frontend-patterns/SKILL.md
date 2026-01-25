---
name: typescript-frontend-patterns
description: >
  Next.js 16, React 19, Radix UI, and Tailwind patterns for MSI-a.
  Trigger: Working on admin-panel/ TypeScript code.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [admin-panel]
  auto_invoke: "Working on admin-panel/ TypeScript code"
---

## Overview

Frontend patterns for MSI-a admin panel using Next.js 16, React 19, Radix UI, and Tailwind CSS.

## Next.js App Router

### Server Components (Default)

```typescript
// app/tariffs/page.tsx
// No 'use client' - this is a Server Component

import { getTariffs } from '@/lib/api';
import { TariffTable } from '@/components/tariffs/tariff-table';

export default async function TariffsPage() {
  const tariffs = await getTariffs();

  return (
    <div className="container py-8">
      <h1 className="text-2xl font-bold mb-6">Tarifas</h1>
      <TariffTable tariffs={tariffs} />
    </div>
  );
}
```

### Client Components (When Needed)

```typescript
// components/tariffs/tariff-filter.tsx
'use client';

import { useState } from 'react';
import { Input } from '@/components/ui/input';

interface TariffFilterProps {
  onFilter: (query: string) => void;
}

export function TariffFilter({ onFilter }: TariffFilterProps) {
  const [query, setQuery] = useState('');

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value);
    onFilter(e.target.value);
  };

  return <Input value={query} onChange={handleChange} placeholder="Buscar..." />;
}
```

### Server Actions

```typescript
// app/tariffs/actions.ts
'use server';

import { revalidatePath } from 'next/cache';

export async function createTariff(formData: FormData) {
  const name = formData.get('name') as string;
  const price = parseFloat(formData.get('price') as string);

  await fetch(`${API_URL}/tariffs`, {
    method: 'POST',
    body: JSON.stringify({ name, price }),
  });

  revalidatePath('/tariffs');
}
```

### Loading and Error States

```typescript
// app/tariffs/loading.tsx
import { Skeleton } from '@/components/ui/skeleton';

export default function Loading() {
  return (
    <div className="container py-8">
      <Skeleton className="h-8 w-48 mb-6" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

// app/tariffs/error.tsx
'use client';

export default function Error({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <div className="container py-8">
      <h2>Algo salió mal</h2>
      <button onClick={reset}>Intentar de nuevo</button>
    </div>
  );
}
```

## Radix UI + Tailwind

### Using Radix Primitives

```typescript
// components/ui/button.tsx
import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
        destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 px-3',
        lg: 'h-11 px-8',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : 'button';
  return <Comp className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}
```

### The cn() Utility

```typescript
// lib/utils.ts
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Usage
<div className={cn(
  'base-classes',
  condition && 'conditional-class',
  className
)} />
```

## Hooks Patterns

### Custom Data Hook

```typescript
// hooks/use-tariffs.ts
'use client';

import useSWR from 'swr';

const fetcher = (url: string) => fetch(url).then(r => r.json());

export function useTariffs() {
  const { data, error, isLoading, mutate } = useSWR('/api/tariffs', fetcher);

  return {
    tariffs: data ?? [],
    isLoading,
    isError: !!error,
    refresh: mutate,
  };
}
```

### Debounced Input

```typescript
// hooks/use-debounce.ts
import { useState, useEffect } from 'react';

export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}
```

## State Management

### React Context

```typescript
// contexts/auth-context.tsx
'use client';

import { createContext, useContext, useState, ReactNode } from 'react';

interface AuthContextType {
  user: User | null;
  login: (credentials: Credentials) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);

  const login = async (credentials: Credentials) => {
    const user = await authenticate(credentials);
    setUser(user);
  };

  const logout = () => setUser(null);

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
```

## Tailwind Patterns

### Responsive Design

```typescript
// Mobile first
<div className="
  flex flex-col gap-4
  md:flex-row md:gap-6
  lg:gap-8
">
```

### Dark Mode

```typescript
// Using CSS variables
<div className="bg-background text-foreground" />

// Direct dark mode
<div className="bg-white dark:bg-gray-900" />
```

## Related Skills

- `coding-standards` - General coding rules
- `msia-admin` - MSI-a specific admin patterns
