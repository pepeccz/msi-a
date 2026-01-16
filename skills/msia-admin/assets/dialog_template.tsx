/**
 * Template for MSI-a Admin Panel dialog component.
 *
 * Usage:
 * 1. Copy this file to admin-panel/src/components/your-section/
 * 2. Rename to your-dialog.tsx
 * 3. Update the component name, form fields, and API call
 */

"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { Plus } from "lucide-react";

interface CreateResourceDialogProps {
  categoryId: string;
  onSuccess?: () => void;
  trigger?: React.ReactNode;
}

export function CreateResourceDialog({
  categoryId,
  onSuccess,
  trigger,
}: CreateResourceDialogProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const formData = new FormData(e.currentTarget);

    const data = {
      category_id: categoryId,
      name: formData.get("name") as string,
      code: formData.get("code") as string,
      description: formData.get("description") as string || null,
      type: formData.get("type") as string,
    };

    try {
      await api.post("/api/my-resource", data);
      setOpen(false);
      onSuccess?.();
    } catch (err) {
      console.error("Failed to create resource:", err);
      setError("Error al crear el recurso. Por favor, inténtalo de nuevo.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            Nuevo Recurso
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Crear Nuevo Recurso</DialogTitle>
          <DialogDescription>
            Completa los campos para crear un nuevo recurso.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Name field */}
          <div className="space-y-2">
            <Label htmlFor="name">Nombre *</Label>
            <Input
              id="name"
              name="name"
              placeholder="Nombre del recurso"
              required
              disabled={loading}
            />
          </div>

          {/* Code field */}
          <div className="space-y-2">
            <Label htmlFor="code">Código *</Label>
            <Input
              id="code"
              name="code"
              placeholder="CODIGO_UNICO"
              pattern="[A-Z0-9_]+"
              title="Solo mayúsculas, números y guiones bajos"
              required
              disabled={loading}
            />
            <p className="text-xs text-muted-foreground">
              Solo mayúsculas, números y guiones bajos
            </p>
          </div>

          {/* Select field */}
          <div className="space-y-2">
            <Label htmlFor="type">Tipo *</Label>
            <Select name="type" required disabled={loading}>
              <SelectTrigger>
                <SelectValue placeholder="Selecciona un tipo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="type1">Tipo 1</SelectItem>
                <SelectItem value="type2">Tipo 2</SelectItem>
                <SelectItem value="type3">Tipo 3</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Description field */}
          <div className="space-y-2">
            <Label htmlFor="description">Descripción</Label>
            <Textarea
              id="description"
              name="description"
              placeholder="Descripción opcional del recurso..."
              rows={3}
              disabled={loading}
            />
          </div>

          {/* Error message */}
          {error && (
            <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={loading}
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

// =============================================================================
// Alternative: Edit dialog with initial data
// =============================================================================

/*
interface Resource {
  id: string;
  name: string;
  code: string;
  description: string | null;
}

interface EditResourceDialogProps {
  resource: Resource;
  onSuccess?: () => void;
}

export function EditResourceDialog({ resource, onSuccess }: EditResourceDialogProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);

    const formData = new FormData(e.currentTarget);
    const data = {
      name: formData.get("name") as string,
      description: formData.get("description") as string || null,
    };

    try {
      await api.put(`/api/my-resource/${resource.id}`, data);
      setOpen(false);
      onSuccess?.();
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm">Editar</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Editar {resource.name}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Nombre</Label>
            <Input
              id="name"
              name="name"
              defaultValue={resource.name}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="description">Descripción</Label>
            <Textarea
              id="description"
              name="description"
              defaultValue={resource.description ?? ""}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
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
*/
