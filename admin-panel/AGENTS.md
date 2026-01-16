# Admin Panel Component Guidelines

This directory contains the MSI-a Admin Panel built with Next.js 16 and Radix UI.

## Auto-invoke Skills

When working in this directory, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Creating/modifying pages | `msia-admin` |
| Creating/modifying components | `msia-admin` |
| Working with contexts/hooks | `msia-admin` |
| Working with App Router | `nextjs-16` |
| Working with Radix UI | `radix-tailwind` |
| Working with tariffs UI | `msia-tariffs` |

## Directory Structure

```
admin-panel/
├── src/
│   ├── app/
│   │   ├── layout.tsx              # Root layout
│   │   ├── page.tsx                # Redirect
│   │   ├── login/page.tsx          # Login
│   │   └── (authenticated)/        # Protected routes
│   │       ├── layout.tsx          # Auth + sidebar
│   │       ├── dashboard/
│   │       ├── conversations/
│   │       ├── escalations/
│   │       ├── users/
│   │       ├── cases/
│   │       ├── reformas/           # Tariffs
│   │       ├── elementos/          # Elements
│   │       ├── advertencias/       # Warnings
│   │       ├── normativas/         # RAG docs
│   │       ├── imagenes/           # Images
│   │       └── settings/
│   ├── components/
│   │   ├── ui/                     # Radix primitives
│   │   ├── layout/                 # Header, Sidebar
│   │   ├── tariffs/                # Tariff components
│   │   ├── elements/               # Element components
│   │   └── categories/             # Category components
│   ├── contexts/
│   │   ├── auth-context.tsx
│   │   └── sidebar-context.tsx
│   ├── hooks/
│   │   ├── use-category-data.ts
│   │   └── use-tier-elements.ts
│   └── lib/
│       ├── api.ts                  # API client
│       ├── auth.ts                 # Auth utilities
│       ├── types.ts                # TypeScript types
│       └── utils.ts                # cn() helper
└── package.json
```

## Key Patterns

### Server Component (Default)

```typescript
export default async function Page() {
  const data = await fetchData();
  return <Component data={data} />;
}
```

### Client Component with Dialog

```typescript
"use client";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";

export function MyDialog() {
  const [open, setOpen] = useState(false);
  // ...
}
```

## Critical Rules

- Server Components are DEFAULT
- ALWAYS use Spanish for UI labels
- ALWAYS use Radix UI from `@/components/ui/`
- ALWAYS use `cn()` for conditional classes
- NEVER use `useState` in Server Components
