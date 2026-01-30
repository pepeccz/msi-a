---
name: nextjs-16
description: >
  Next.js 16 App Router patterns.
  Trigger: When working with App Router, Server Components, Server Actions, or route handlers.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root, admin-panel]
  auto_invoke: "Working with Next.js App Router"
---

## App Router File Conventions

```
app/
├── layout.tsx          # Root layout (required)
├── page.tsx            # Home page (/)
├── loading.tsx         # Loading UI (Suspense boundary)
├── error.tsx           # Error boundary
├── not-found.tsx       # 404 page
├── (auth)/             # Route group (no URL impact)
│   ├── login/page.tsx  # /login
│   └── signup/page.tsx # /signup
├── users/
│   ├── page.tsx        # /users
│   └── [id]/
│       └── page.tsx    # /users/:id
├── api/
│   └── route.ts        # API route handler
└── _components/        # Private folder (not routed)
```

## Server Components (Default)

```typescript
// No directive needed - async by default
export default async function UsersPage() {
  const users = await fetchUsers();
  
  return (
    <div>
      <h1>Users</h1>
      <ul>
        {users.map(user => (
          <li key={user.id}>{user.name}</li>
        ))}
      </ul>
    </div>
  );
}
```

## Client Components

```typescript
"use client";

import { useState } from "react";

export function Counter() {
  const [count, setCount] = useState(0);
  
  return (
    <button onClick={() => setCount(c => c + 1)}>
      Count: {count}
    </button>
  );
}
```

## Server Actions

```typescript
// app/actions.ts
"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

export async function createUser(formData: FormData) {
  const name = formData.get("name") as string;
  const email = formData.get("email") as string;
  
  await db.users.create({ data: { name, email } });
  
  revalidatePath("/users");
  redirect("/users");
}

// Usage in component
<form action={createUser}>
  <input name="name" required />
  <input name="email" type="email" required />
  <button type="submit">Create User</button>
</form>
```

## Server Actions with useActionState

```typescript
"use client";

import { useActionState } from "react";
import { createUser } from "./actions";

export function CreateUserForm() {
  const [state, formAction, isPending] = useActionState(createUser, null);
  
  return (
    <form action={formAction}>
      <input name="name" required disabled={isPending} />
      <input name="email" type="email" required disabled={isPending} />
      <button type="submit" disabled={isPending}>
        {isPending ? "Creating..." : "Create User"}
      </button>
      {state?.error && <p className="text-red-500">{state.error}</p>}
    </form>
  );
}
```

## Data Fetching

```typescript
// Parallel fetching
async function Dashboard() {
  const [users, posts] = await Promise.all([
    fetchUsers(),
    fetchPosts(),
  ]);
  
  return <DashboardContent users={users} posts={posts} />;
}

// With Suspense streaming
import { Suspense } from "react";

export default function Page() {
  return (
    <div>
      <h1>Dashboard</h1>
      <Suspense fallback={<UsersSkeleton />}>
        <UsersSection />
      </Suspense>
      <Suspense fallback={<PostsSkeleton />}>
        <PostsSection />
      </Suspense>
    </div>
  );
}
```

## Route Handlers (API Routes)

```typescript
// app/api/users/route.ts
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const limit = searchParams.get("limit") ?? "10";
  
  const users = await fetchUsers(parseInt(limit));
  return NextResponse.json(users);
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const user = await createUser(body);
  return NextResponse.json(user, { status: 201 });
}

// Dynamic route: app/api/users/[id]/route.ts
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const user = await fetchUser(id);
  
  if (!user) {
    return NextResponse.json(
      { error: "User not found" },
      { status: 404 }
    );
  }
  
  return NextResponse.json(user);
}
```

## Layouts and Templates

```typescript
// app/(authenticated)/layout.tsx
export default async function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await getUser();
  
  if (!user) {
    redirect("/login");
  }
  
  return (
    <div className="flex">
      <Sidebar user={user} />
      <main className="flex-1">{children}</main>
    </div>
  );
}
```

## Metadata

```typescript
// Static metadata
export const metadata = {
  title: "My App",
  description: "App description",
};

// Dynamic metadata
export async function generateMetadata({ params }: Props) {
  const { id } = await params;
  const user = await fetchUser(id);
  
  return {
    title: user?.name ?? "User",
    description: `Profile of ${user?.name}`,
  };
}
```

## Loading and Error States

```typescript
// loading.tsx - Auto Suspense boundary
export default function Loading() {
  return <div className="animate-pulse">Loading...</div>;
}

// error.tsx - Error boundary
"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <div>
      <h2>Something went wrong!</h2>
      <button onClick={reset}>Try again</button>
    </div>
  );
}
```

## Critical Rules

- Server Components are the DEFAULT - only use "use client" when needed
- NEVER use useState/useEffect in Server Components
- ALWAYS use Server Actions for mutations (not API routes)
- ALWAYS use `await params` in dynamic routes (Next.js 15+)
- ALWAYS put "use server" at top of action files
- ALWAYS use revalidatePath/revalidateTag after mutations
- PREFER parallel data fetching with Promise.all
- USE Suspense boundaries for streaming
