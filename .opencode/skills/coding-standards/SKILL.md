---
name: coding-standards
description: >
  MSI-a coding standards for Python and TypeScript.
  Trigger: Any code writing task.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [agent, api, admin-panel]
  auto_invoke: "Any code writing task"
---

## Overview

Coding standards for MSI-a ensuring consistency across Python (agent, api) and TypeScript (admin-panel).

## Python Standards

### Type Hints (Required)

```python
# All functions must have complete type hints
async def get_user(user_id: int) -> User | None:
    pass

# Use modern union syntax (Python 3.10+)
def process(value: str | int | None = None) -> dict[str, Any]:
    pass
```

### Async Patterns

```python
# All I/O operations must be async
async def fetch_data() -> Data:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()

# Never use blocking calls
# BAD: requests.get(url)
# GOOD: await client.get(url)
```

### Pydantic Models

```python
from pydantic import BaseModel, Field

class TariffCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(gt=0)
    category_id: int

    class Config:
        from_attributes = True
```

### Structured Logging

```python
import structlog

logger = structlog.get_logger()

# GOOD: Structured with context
logger.info("tariff_created", tariff_id=123, price=100.0)

# BAD: String interpolation
logger.info(f"Created tariff {tariff_id}")
```

## TypeScript Standards

### Strict Mode

```typescript
// tsconfig.json must have strict: true
// Never use 'any' - use 'unknown' and type guards
```

### React Components

```typescript
// Props interface always defined
interface ButtonProps {
  label: string;
  onClick: () => void;
  variant?: 'primary' | 'secondary';
}

// Functional components with proper types
export function Button({ label, onClick, variant = 'primary' }: ButtonProps) {
  return <button className={cn(variants[variant])} onClick={onClick}>{label}</button>;
}
```

### Server vs Client Components

```typescript
// Default: Server Component (no directive needed)
export default async function Page() {
  const data = await fetchData();
  return <div>{data}</div>;
}

// Only when needed: Client Component
'use client';

import { useState } from 'react';

export function Counter() {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(c => c + 1)}>{count}</button>;
}
```

## File Organization

### Maximum Sizes

| Metric | Limit |
|--------|-------|
| Lines per file | 500 |
| Lines per function | 50 |
| Parameters per function | 5 |

### Import Order

```python
# Python (enforced by ruff)
# 1. Standard library
import os
from typing import Any

# 2. Third-party
from fastapi import APIRouter
from pydantic import BaseModel

# 3. Local
from database.models import User
from shared.config import settings
```

```typescript
// TypeScript (enforced by prettier)
// 1. React/Next
import { useState } from 'react';
import Link from 'next/link';

// 2. Third-party
import { Button } from '@radix-ui/themes';

// 3. Local
import { cn } from '@/lib/utils';
import { UserCard } from '@/components/user-card';
```

## Language Guidelines

- **User-facing text**: Spanish
- **Code/comments**: English
- **Documentation**: English
- **Error messages to users**: Spanish

```python
# Spanish for users
raise HTTPException(status_code=404, detail="Tarifa no encontrada")

# English for logs
logger.error("tariff_not_found", tariff_id=123)
```

## Related Skills

- `python-backend-patterns` - FastAPI and SQLAlchemy specifics
- `typescript-frontend-patterns` - Next.js and Radix UI specifics
