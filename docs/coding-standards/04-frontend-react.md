# Estándares Frontend React (Next.js 16 + Radix UI)

Patrones para el admin panel MSI-a.

---

## 1. Client Component Pattern

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

export default function MyPage() {
  const [data, setData] = useState<Item[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  
  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true);
      const result = await api.getItems();
      setData(result.items);
    } catch (error) {
      console.error("Error:", error);
      toast.error("Error al cargar los datos");
    } finally {
      setIsLoading(false);
    }
  }, []);
  
  useEffect(() => {
    fetchData();
  }, [fetchData]);
  
  if (isLoading) return <div className="animate-pulse">Cargando...</div>;
  
  return (
    <div className="container">
      {/* UI with Radix components */}
    </div>
  );
}
```

---

## 2. Dialog-Based CRUD

```typescript
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export function CreateDialog({ onSuccess }: { onSuccess?: () => void }) {
  const [open, setOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  
  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setIsSaving(true);
    try {
      const formData = new FormData(e.currentTarget);
      await api.create({ name: formData.get("name") as string });
      toast.success("Creado correctamente");
      setOpen(false);
      onSuccess?.();
    } catch (error) {
      toast.error("Error al crear");
    } finally {
      setIsSaving(false);
    }
  }
  
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Crear Nuevo</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Crear Nuevo</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          {/* form fields */}
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

---

## 3. AlertDialog para Destructive

```typescript
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";

<AlertDialog>
  <AlertDialogTrigger asChild>
    <Button variant="destructive">Eliminar</Button>
  </AlertDialogTrigger>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>¿Eliminar {item.name}?</AlertDialogTitle>
      <AlertDialogDescription>
        Esta acción no se puede deshacer.
      </AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>Cancelar</AlertDialogCancel>
      <AlertDialogAction onClick={handleDelete} className="bg-destructive">
        Eliminar
      </AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

---

## 4. Debounced Search

```typescript
const [searchQuery, setSearchQuery] = useState("");
const [debouncedQuery, setDebouncedQuery] = useState("");

useEffect(() => {
  const timer = setTimeout(() => setDebouncedQuery(searchQuery), 300);
  return () => clearTimeout(timer);
}, [searchQuery]);

useEffect(() => {
  if (debouncedQuery) {
    fetchData({ search: debouncedQuery });
  }
}, [debouncedQuery]);
```

---

## 5. Auto-Refresh Polling

```typescript
useEffect(() => {
  fetchData();
  const interval = setInterval(fetchData, 30000); // 30s
  return () => clearInterval(interval); // ✅ CLEANUP
}, [fetchData]);
```

---

## 6. Reglas Críticas

1. ✅ **SIEMPRE** "use client" para páginas con state
2. ✅ **SIEMPRE** Radix UI → NUNCA <button>, <input>, <table>
3. ✅ **SIEMPRE** toast() → NUNCA alert()/confirm()
4. ✅ **SIEMPRE** AlertDialog para destructive
5. ✅ **SIEMPRE** debounced search (300ms)
6. ✅ **SIEMPRE** cleanup timers en useEffect return
7. ✅ **SIEMPRE** useCallback para fetch dependencies
8. ✅ **SIEMPRE** español para labels de UI
9. ❌ **NUNCA** Server Components para data fetching (Client + useEffect)
10. ❌ **NUNCA** Server Actions para mutations (api client)
11. ❌ **NUNCA** mutar state directamente (setter con prev)

---

**Referencias:**
- `admin-panel/AGENTS.md`
- `skills/nextjs-16/SKILL.md`
- `skills/radix-tailwind/SKILL.md`

**Última actualización:** Febrero 2026
