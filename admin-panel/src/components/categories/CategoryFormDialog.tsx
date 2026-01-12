"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import api from "@/lib/api";
import type {
  VehicleCategory,
  VehicleCategoryCreate,
  VehicleCategoryUpdate,
  ClientType,
} from "@/lib/types";

interface CategoryFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  category?: VehicleCategory;
  onSuccess: () => void;
}

interface CategoryFormState {
  name: string;
  slug: string;
  client_type: ClientType;
  description: string;
  icon: string;
  is_active: boolean;
  sort_order: string;
}

const defaultFormState: CategoryFormState = {
  name: "",
  slug: "",
  client_type: "particular",
  description: "",
  icon: "",
  is_active: true,
  sort_order: "0",
};

export function CategoryFormDialog({
  open,
  onOpenChange,
  category,
  onSuccess,
}: CategoryFormDialogProps) {
  const [form, setForm] = useState<CategoryFormState>(defaultFormState);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoGenerateSlug, setAutoGenerateSlug] = useState(!category);

  useEffect(() => {
    if (category) {
      setForm({
        name: category.name,
        slug: category.slug,
        client_type: category.client_type,
        description: category.description || "",
        icon: category.icon || "",
        is_active: category.is_active,
        sort_order: category.sort_order?.toString() || "0",
      });
      setAutoGenerateSlug(false);
    } else {
      setForm(defaultFormState);
      setAutoGenerateSlug(true);
    }
    setError(null);
  }, [category, open]);

  // Auto-generate slug from name and client_type
  useEffect(() => {
    if (autoGenerateSlug && form.name) {
      const slugBase = form.name
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");

      const suffix = form.client_type === "particular" ? "-part" : "-prof";
      setForm((prev) => ({
        ...prev,
        slug: slugBase + suffix,
      }));
    }
  }, [form.name, form.client_type, autoGenerateSlug]);

  const validate = (): boolean => {
    if (!form.name.trim()) {
      setError("El nombre es requerido");
      return false;
    }

    if (form.name.trim().length > 100) {
      setError("El nombre no puede exceder 100 caracteres");
      return false;
    }

    if (!form.slug.trim()) {
      setError("El slug es requerido");
      return false;
    }

    if (!/^[a-z0-9-]+$/.test(form.slug)) {
      setError(
        "El slug solo puede contener letras minúsculas, números y guiones"
      );
      return false;
    }

    if (form.slug.length > 50) {
      setError("El slug no puede exceder 50 caracteres");
      return false;
    }

    if (form.description && form.description.length > 500) {
      setError("La descripción no puede exceder 500 caracteres");
      return false;
    }

    return true;
  };

  const handleSave = async () => {
    if (!validate()) return;

    setIsSaving(true);
    setError(null);

    try {
      const data = {
        name: form.name.trim(),
        slug: form.slug.trim(),
        client_type: form.client_type,
        description: form.description || null,
        icon: form.icon || null,
        is_active: form.is_active,
        sort_order: parseInt(form.sort_order) || 0,
      };

      if (category) {
        await api.updateVehicleCategory(
          category.id,
          data as VehicleCategoryUpdate
        );
      } else {
        await api.createVehicleCategory(data as VehicleCategoryCreate);
      }

      onOpenChange(false);
      onSuccess();
    } catch (err: any) {
      const errorMessage =
        err.response?.data?.detail ||
        err.message ||
        "Error al guardar la categoría";
      setError(errorMessage);
      console.error("Error saving category:", err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {category ? "Editar Categoría" : "Nueva Categoría"}
          </DialogTitle>
          <DialogDescription>
            {category
              ? "Modifica los datos de la categoría de vehículos"
              : "Crea una nueva categoría de vehículos"}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {error && (
            <div className="p-3 rounded-md bg-destructive/10 text-destructive text-sm">
              {error}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="name">Nombre *</Label>
            <Input
              id="name"
              value={form.name}
              onChange={(e) => {
                setForm((prev) => ({ ...prev, name: e.target.value }));
              }}
              placeholder="ej: Motocicletas, Autocaravanas"
              disabled={isSaving}
            />
            <p className="text-xs text-muted-foreground">
              {form.name.length}/100 caracteres
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="client_type">Tipo de Cliente *</Label>
            <Select
              value={form.client_type}
              onValueChange={(value) => {
                setForm((prev) => ({
                  ...prev,
                  client_type: value as ClientType,
                }));
              }}
              disabled={isSaving}
            >
              <SelectTrigger id="client_type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="particular">Particulares</SelectItem>
                <SelectItem value="professional">Profesionales</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="slug">
              Slug (generado automáticamente) *
              {!category && (
                <button
                  type="button"
                  className="ml-2 text-xs text-primary hover:underline"
                  onClick={() => setAutoGenerateSlug(!autoGenerateSlug)}
                >
                  {autoGenerateSlug ? "Editar manualmente" : "Auto-generar"}
                </button>
              )}
            </Label>
            <Input
              id="slug"
              value={form.slug}
              onChange={(e) => {
                setForm((prev) => ({ ...prev, slug: e.target.value }));
                if (!category) {
                  setAutoGenerateSlug(false);
                }
              }}
              placeholder="ej: motos-part, autocaravanas-prof"
              disabled={isSaving || (autoGenerateSlug && !category)}
            />
            <p className="text-xs text-muted-foreground">
              Sufijo: {form.client_type === "particular" ? "-part" : "-prof"}
            </p>
            <p className="text-xs text-muted-foreground">
              {form.slug.length}/50 caracteres
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Descripción (opcional)</Label>
            <Textarea
              id="description"
              value={form.description}
              onChange={(e) => {
                setForm((prev) => ({ ...prev, description: e.target.value }));
              }}
              placeholder="Descripción de la categoría..."
              disabled={isSaving}
              rows={3}
            />
            <p className="text-xs text-muted-foreground">
              {form.description.length}/500 caracteres
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="icon">Icono (opcional)</Label>
            <Input
              id="icon"
              value={form.icon}
              onChange={(e) => {
                setForm((prev) => ({ ...prev, icon: e.target.value }));
              }}
              placeholder="ej: bike, car, truck, caravan"
              disabled={isSaving}
            />
            <p className="text-xs text-muted-foreground">
              Nombre de icono Lucide (sin espacios)
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="sort_order">Orden de visualización</Label>
              <Input
                id="sort_order"
                type="number"
                value={form.sort_order}
                onChange={(e) => {
                  setForm((prev) => ({ ...prev, sort_order: e.target.value }));
                }}
                placeholder="0"
                disabled={isSaving}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="is_active">Estado</Label>
              <Select
                value={form.is_active ? "active" : "inactive"}
                onValueChange={(value) => {
                  setForm((prev) => ({
                    ...prev,
                    is_active: value === "active",
                  }));
                }}
                disabled={isSaving}
              >
                <SelectTrigger id="is_active">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Activo</SelectItem>
                  <SelectItem value="inactive">Inactivo</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isSaving}
          >
            Cancelar
          </Button>
          <Button
            onClick={handleSave}
            disabled={isSaving || !form.name.trim() || !form.slug.trim()}
          >
            {isSaving ? "Guardando..." : "Guardar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
