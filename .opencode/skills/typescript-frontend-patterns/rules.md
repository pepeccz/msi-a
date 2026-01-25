# TypeScript Frontend Quick Rules

## Components

```typescript
// Server Component (default, no directive)
export default async function Page() {
  const data = await fetch();
  return <div>{data}</div>;
}

// Client Component (only when needed)
'use client';
import { useState } from 'react';
```

## When to use 'use client'

- useState, useEffect, useContext
- Event handlers (onClick, onChange)
- Browser APIs (window, localStorage)
- Third-party client libraries

## Radix + Tailwind

```typescript
// Always use cn() for className merging
import { cn } from '@/lib/utils';

<div className={cn('base', condition && 'added', className)} />
```

## Props

```typescript
// Always define interface
interface Props {
  title: string;
  count?: number;
  children: React.ReactNode;
}
```

## Data Fetching

```typescript
// Server Component: direct fetch
const data = await fetch(url);

// Client Component: SWR
const { data, isLoading } = useSWR(url, fetcher);
```

## Don't

- Don't use `any` type
- Don't skip loading states
- Don't forget key prop on lists
- Don't use inline styles (use Tailwind)
