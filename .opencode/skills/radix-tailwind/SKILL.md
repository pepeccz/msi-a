---
name: radix-tailwind
description: >
  Radix UI + Tailwind CSS patterns for MSI-a admin panel.
  Trigger: When working with UI components, Radix primitives, or Tailwind styling.
metadata:
  author: msi-automotive
  version: "2.0"
  scope: [root, admin-panel]
  auto_invoke: "Working with Radix UI + Tailwind"
---

## shadcn/ui Configuration

**MSI-a Admin Panel uses shadcn/ui with:**
- **Style**: `new-york` (refined, modern aesthetic)
- **Base color**: `zinc` (neutral gray palette)
- **Dark mode**: `class` (toggle via className)
- **Icon library**: `lucide-react`
- **Tailwind**: HSL CSS variables theme

## Available UI Components (21 total — all actively used)

### Heavy Use (10+ importers)

| Component | Importers | Usage |
|-----------|:---------:|-------|
| `button` | 45 | Primary UI actions, forms, navigation |
| `badge` | 37 | Status indicators, labels, counts |
| `card` | 29 | Content containers, sections |
| `dialog` | 26 | Form modals, detail views |
| `input` | 26 | Text fields, search, forms |
| `label` | 22 | Form field labels |
| `select` | 20 | Dropdown selectors, filters |
| `table` | 16 | Data tables, lists |
| `textarea` | 15 | Multi-line text input |
| `alert-dialog` | 12 | Destructive confirmations |

### Moderate Use (3-9 importers)

| Component | Importers | Usage |
|-----------|:---------:|-------|
| `switch` | 8 | Boolean toggles (is_active, is_hidden) |
| `separator` | 6 | Visual dividers |
| `tooltip` | 4 | Hover hints |

### Light Use (1-2 importers)

| Component | Importers | Usage |
|-----------|:---------:|-------|
| `accordion` | 2 | Collapsible sections (case images, element hierarchy) |
| `scroll-area` | 2 | Scrollable containers |
| `skeleton` | 2 | Loading placeholders |
| `tabs` | 2 | Tabbed navigation (settings, admin users, llm metrics) |
| `command` | 1 | Global search (Cmd+K) |
| `error-boundary` | 1 | React error boundary (elements-tree-section) |
| `popover` | 1 | Notification center |
| `progress` | 1 | LLM metrics progress bars |

## cn() Utility

```typescript
// lib/utils.ts
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Usage
<div className={cn(
  "base-styles",
  isActive && "active-styles",
  variant === "primary" && "primary-styles",
  className
)} />
```

## Button Component

```typescript
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline: "border border-input bg-background hover:bg-accent",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
```

## Dialog Component

```typescript
"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

const Dialog = DialogPrimitive.Root;
const DialogTrigger = DialogPrimitive.Trigger;
const DialogPortal = DialogPrimitive.Portal;
const DialogClose = DialogPrimitive.Close;

const DialogOverlay = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out",
      className
    )}
    {...props}
  />
));

const DialogContent = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        "fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg duration-200 sm:rounded-lg",
        className
      )}
      {...props}
    >
      {children}
      <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm opacity-70 hover:opacity-100">
        <X className="h-4 w-4" />
        <span className="sr-only">Close</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPortal>
));

const DialogHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("flex flex-col space-y-1.5 text-center sm:text-left", className)} {...props} />
);

const DialogTitle = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn("text-lg font-semibold leading-none tracking-tight", className)}
    {...props}
  />
));
```

## AlertDialog Pattern (Destructive Confirmations)

**Used by 12 pages for delete operations.**

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

<AlertDialog>
  <AlertDialogTrigger asChild>
    <Button variant="destructive" size="sm">Eliminar</Button>
  </AlertDialogTrigger>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>¿Eliminar elemento "{item.name}"?</AlertDialogTitle>
      <AlertDialogDescription>
        Esta acción no se puede deshacer.
      </AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>Cancelar</AlertDialogCancel>
      <AlertDialogAction
        onClick={handleDelete}
        className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
      >
        Eliminar
      </AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

## Form Pattern with Dialog

```typescript
"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function CreateUserDialog() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    
    const formData = new FormData(e.currentTarget);
    await createUser(formData);
    
    setLoading(false);
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Create User</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create New User</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input id="name" name="name" required />
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" name="email" type="email" required />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? "Creating..." : "Create"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

## Select Component

```typescript
"use client";

import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const Select = SelectPrimitive.Root;
const SelectValue = SelectPrimitive.Value;

const SelectTrigger = React.forwardRef<
  React.ComponentRef<typeof SelectPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    className={cn(
      "flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 disabled:cursor-not-allowed disabled:opacity-50",
      className
    )}
    {...props}
  >
    {children}
    <SelectPrimitive.Icon asChild>
      <ChevronDown className="h-4 w-4 opacity-50" />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
));

// Usage
<Select value={value} onValueChange={setValue}>
  <SelectTrigger>
    <SelectValue placeholder="Select option" />
  </SelectTrigger>
  <SelectContent>
    <SelectItem value="option1">Option 1</SelectItem>
    <SelectItem value="option2">Option 2</SelectItem>
  </SelectContent>
</Select>
```

## Tabs Pattern

**Used by: settings layout, admin-users, llm-metrics**

```typescript
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

<Tabs defaultValue="usuarios" className="w-full">
  <TabsList className="grid w-full grid-cols-2">
    <TabsTrigger value="usuarios">Usuarios</TabsTrigger>
    <TabsTrigger value="logs">Logs de Acceso</TabsTrigger>
  </TabsList>
  <TabsContent value="usuarios">
    {/* Content */}
  </TabsContent>
  <TabsContent value="logs">
    {/* Content */}
  </TabsContent>
</Tabs>
```

## Accordion Pattern

**Used by: case detail, elements list**

```typescript
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";

<Accordion type="single" collapsible className="w-full">
  <AccordionItem value="item-1">
    <AccordionTrigger>Section 1</AccordionTrigger>
    <AccordionContent>
      {/* Content */}
    </AccordionContent>
  </AccordionItem>
  <AccordionItem value="item-2">
    <AccordionTrigger>Section 2</AccordionTrigger>
    <AccordionContent>
      {/* Content */}
    </AccordionContent>
  </AccordionItem>
</Accordion>
```

## Tailwind Responsive Patterns

```typescript
// Mobile-first responsive
<div className="
  grid grid-cols-1    // Mobile: 1 column
  sm:grid-cols-2      // Small: 2 columns
  md:grid-cols-3      // Medium: 3 columns
  lg:grid-cols-4      // Large: 4 columns
  gap-4
">

// Container pattern
<div className="container mx-auto px-4 sm:px-6 lg:px-8">

// Flex responsive
<div className="flex flex-col md:flex-row gap-4">
```

## Critical Rules

- **ALWAYS** use `cn()` for conditional classes
- **ALWAYS** use `forwardRef` for component wrappers
- **ALWAYS** add `displayName` for debugging
- **NEVER** use inline styles - use Tailwind
- **ALWAYS** use `data-[state=*]` for Radix animations
- **ALWAYS** handle loading/disabled states
- **USE** "use client" only when needed (interactivity)
- **PREFER** composition over props for variants
- **NEVER** use native HTML elements - use Radix wrappers
- **NEVER** use `window.confirm()` - use `AlertDialog`
