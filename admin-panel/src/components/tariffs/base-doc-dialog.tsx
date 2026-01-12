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
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ImageUpload } from "@/components/image-upload";
import api from "@/lib/api";
import type { BaseDocumentation } from "@/lib/types";

interface BaseDocDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  doc: BaseDocumentation | null;
  categoryId: string;
  defaultSortOrder: number;
  onSuccess: () => void;
}

interface BaseDocFormState {
  description: string;
  image_url: string | null;
  sort_order: number;
}

export function BaseDocDialog({
  open,
  onOpenChange,
  doc,
  categoryId,
  defaultSortOrder,
  onSuccess,
}: BaseDocDialogProps) {
  const [form, setForm] = useState<BaseDocFormState>({
    description: "",
    image_url: null,
    sort_order: 0,
  });
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (doc) {
      setForm({
        description: doc.description,
        image_url: doc.image_url,
        sort_order: doc.sort_order,
      });
    } else {
      setForm({
        description: "",
        image_url: null,
        sort_order: defaultSortOrder,
      });
    }
  }, [doc, open, defaultSortOrder]);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const data = {
        description: form.description,
        image_url: form.image_url,
        sort_order: form.sort_order,
      };

      if (doc) {
        await api.updateBaseDocumentation(doc.id, data);
      } else {
        await api.createBaseDocumentation({
          ...data,
          category_id: categoryId,
        });
      }

      onOpenChange(false);
      onSuccess();
    } catch (error) {
      console.error("Error saving base documentation:", error);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>
            {doc ? "Editar Documentacion" : "Nueva Documentacion Base"}
          </DialogTitle>
          <DialogDescription>
            Define un requisito de documentacion que aplica a todas las
            homologaciones
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="baseDocDescription">Descripcion del requisito</Label>
            <Textarea
              id="baseDocDescription"
              value={form.description}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, description: e.target.value }))
              }
              placeholder="Ej: Ficha tecnica del vehiculo (ambas caras)"
              rows={3}
            />
          </div>

          <div className="space-y-2">
            <Label>Imagen de ejemplo (opcional)</Label>
            <ImageUpload
              value={form.image_url}
              onChange={(url) =>
                setForm((prev) => ({ ...prev, image_url: url }))
              }
              category="documentation"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="baseSortOrder">Orden</Label>
            <Input
              id="baseSortOrder"
              type="number"
              value={form.sort_order}
              onChange={(e) =>
                setForm((prev) => ({
                  ...prev,
                  sort_order: parseInt(e.target.value) || 0,
                }))
              }
            />
            <p className="text-xs text-muted-foreground">
              Orden en que aparecera en la lista (menor = primero)
            </p>
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
            disabled={isSaving || !form.description.trim()}
          >
            {isSaving ? "Guardando..." : "Guardar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
