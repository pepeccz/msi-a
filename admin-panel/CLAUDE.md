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
│   │   ├── api/                    # Next.js API routes
│   │   │   └── admin/system/[service]/logs/  # System service logs
│   │   └── (authenticated)/        # Protected routes
│   │       ├── layout.tsx          # Auth + sidebar
│   │       ├── dashboard/
│   │       ├── conversations/
│   │       │   └── [id]/           # Conversation detail
│   │       ├── escalations/
│   │       ├── users/
│   │       │   └── [id]/           # User detail
│   │       ├── cases/
│   │       │   └── [id]/           # Case detail
│   │       ├── reformas/           # Tariffs
│   │       │   └── [categoryId]/
│   │       │       └── [tierId]/
│   │       │           └── inclusions/
│   │       ├── elementos/          # Elements
│   │       │   └── [id]/           # Element detail
│   │       ├── advertencias/       # Warnings
│   │       ├── normativas/         # RAG docs
│   │       │   ├── documentos/     # Document management
│   │       │   └── consulta/       # RAG query
│   │       ├── imagenes/           # Images
│   │       └── settings/
│   │           ├── admin-users/    # Admin user management
│   │           ├── config/         # System configuration
│   │           ├── system/         # System status
│   │           └── usage/          # Token usage
│   ├── components/
│   │   ├── ui/                     # Radix primitives
│   │   ├── layout/                 # Header, Sidebar
│   │   ├── tariffs/                # Tariff components
│   │   ├── elements/               # Element components
│   │   ├── categories/             # Category components
│   │   ├── dashboard/              # Dashboard widgets
│   │   │   ├── quick-access-card.tsx
│   │   │   ├── system-health.tsx
│   │   │   └── recent-activity.tsx
│   │   ├── global-search.tsx       # Global search component
│   │   ├── notification-center.tsx # Notifications
│   │   ├── image-upload.tsx        # Image upload component
│   │   ├── tier-inclusion-editor.tsx # Tier inclusion editor
│   │   └── quick-element-dialog.tsx  # Quick element creation
│   ├── contexts/
│   │   ├── auth-context.tsx
│   │   ├── sidebar-context.tsx
│   │   └── global-search-context.tsx
│   ├── hooks/
│   │   ├── use-category-data.ts
│   │   ├── use-tier-elements.ts
│   │   ├── use-category-elements.ts
│   │   └── use-global-search.ts
│   └── lib/
│       ├── api.ts                  # API client
│       ├── auth.ts                 # Auth utilities
│       ├── types.ts                # TypeScript types
│       ├── utils.ts                # cn() helper
│       └── validators.ts           # Form validators
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

### Auto-invoke Skills

When performing these actions, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Working on admin panel components | `msia-admin` |
| Working with Next.js App Router | `nextjs-16` |
| Working with Radix UI + Tailwind | `radix-tailwind` |
