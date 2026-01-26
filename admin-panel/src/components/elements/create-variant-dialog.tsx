"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { X, Plus } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import type { Element, ElementCreate, ElementWithImagesAndChildren } from "@/lib/types";

interface CreateVariantDialogProps {
  /** Parent element to create variant under */
  parentElement: Element | ElementWithImagesAndChildren;
  /** Whether the dialog is open */
  open: boolean;
  /** Callback when dialog open state changes */
  onOpenChange: (open: boolean) => void;
  /** Callback when variant is successfully created */
  onSuccess: () => void;
}

export function CreateVariantDialog({
  parentElement,
  open,
  onOpenChange,
  onSuccess,
}: CreateVariantDialogProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  // Form state
  const [formData, setFormData] = useState({
    name: "",
    variant_code: "",
    variant_type: parentElement.variant_type || "",
    keywords: [] as string[],
    inherit_parent_data: true,
  });
  const [newKeyword, setNewKeyword] = useState("");

  // Reset form when dialog opens/closes or parent changes
  useEffect(() => {
    if (open) {
      setFormData({
        name: "",
        variant_code: "",
        variant_type: parentElement.variant_type || "",
        keywords: [],
        inherit_parent_data: true,
      });
      setNewKeyword("");
    }
  }, [open, parentElement.variant_type]);

  // Auto-generate code from parent code + variant code
  const generatedCode = formData.variant_code
    ? `${parentElement.code}_${formData.variant_code.toUpperCase().replace(/\s+/g, "_")}`
    : "";

  // Keyword handlers
  const handleAddKeyword = () => {
    const keyword = newKeyword.trim().toLowerCase();
    if (keyword && !formData.keywords.includes(keyword)) {
      setFormData((prev) => ({
        ...prev,
        keywords: [...prev.keywords, keyword],
      }));
      setNewKeyword("");
    }
  };

  const handleRemoveKeyword = (keyword: string) => {
    setFormData((prev) => ({
      ...prev,
      keywords: prev.keywords.filter((k) => k !== keyword),
    }));
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAddKeyword();
    }
  };

  // Form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validation
    if (!formData.name.trim()) {
      toast.error("El nombre es requerido");
      return;
    }
    if (!formData.variant_code.trim()) {
      toast.error("El código de variante es requerido");
      return;
    }

    try {
      setIsSubmitting(true);

      const data: ElementCreate = {
        category_id: parentElement.category_id,
        code: generatedCode,
        name: formData.name.trim(),
        keywords: formData.keywords,
        parent_element_id: parentElement.id,
        variant_type: formData.variant_type.trim() || null,
        variant_code: formData.variant_code.toUpperCase().trim(),
        inherit_parent_data: formData.inherit_parent_data,
        is_active: true,
      };

      await api.createElement(data);
      
      toast.success(`Variante "${formData.name}" creada correctamente`);
      onOpenChange(false);
      onSuccess();
    } catch (error) {
      console.error("Error creating variant:", error);
      const message = error instanceof Error ? error.message : "Error desconocido";
      toast.error(`Error al crear variante: ${message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Nueva Variante</DialogTitle>
          <DialogDescription>
            Crear una nueva variante de{" "}
            <span className="font-medium text-foreground">{parentElement.name}</span>
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Name */}
          <div className="space-y-2">
            <Label htmlFor="variant-name">Nombre *</Label>
            <Input
              id="variant-name"
              value={formData.name}
              onChange={(e) =>
                setFormData((prev) => ({ ...prev, name: e.target.value }))
              }
              placeholder="Ej: Suspensión Delantera"
              disabled={isSubmitting}
              autoFocus
            />
          </div>

          {/* Variant Code */}
          <div className="space-y-2">
            <Label htmlFor="variant-code">Código de Variante *</Label>
            <Input
              id="variant-code"
              value={formData.variant_code}
              onChange={(e) =>
                setFormData((prev) => ({
                  ...prev,
                  variant_code: e.target.value.toUpperCase(),
                }))
              }
              placeholder="Ej: DELANTERA"
              disabled={isSubmitting}
              className="font-mono uppercase"
            />
            <p className="text-xs text-muted-foreground">
              Identificador corto de esta variante (se guarda en mayúsculas)
            </p>
          </div>

          {/* Generated Code Preview */}
          {generatedCode && (
            <div className="p-3 bg-muted/50 rounded-lg border">
              <p className="text-xs text-muted-foreground mb-1">Código generado:</p>
              <code className="text-sm font-mono font-medium">{generatedCode}</code>
            </div>
          )}

          {/* Variant Type */}
          <div className="space-y-2">
            <Label htmlFor="variant-type">Tipo de Variante</Label>
            <Input
              id="variant-type"
              value={formData.variant_type}
              onChange={(e) =>
                setFormData((prev) => ({
                  ...prev,
                  variant_type: e.target.value.toLowerCase(),
                }))
              }
              placeholder="Ej: suspension_type, mmr_option"
              disabled={isSubmitting}
            />
            <p className="text-xs text-muted-foreground">
              Categoría de variante (heredado del padre si existe)
            </p>
          </div>

          {/* Keywords */}
          <div className="space-y-2">
            <Label>Keywords para Matching</Label>
            <div className="flex gap-2">
              <Input
                value={newKeyword}
                onChange={(e) => setNewKeyword(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Escribe y presiona Enter..."
                disabled={isSubmitting}
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={handleAddKeyword}
                disabled={isSubmitting || !newKeyword.trim()}
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>
            {formData.keywords.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {formData.keywords.map((keyword) => (
                  <Badge key={keyword} variant="secondary" className="gap-1">
                    {keyword}
                    <button
                      type="button"
                      onClick={() => handleRemoveKeyword(keyword)}
                      disabled={isSubmitting}
                      className="ml-0.5 hover:text-destructive"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
          </div>

          {/* Inherit Parent Data */}
          <div className="flex items-center justify-between p-3 border rounded-lg bg-muted/30">
            <div className="space-y-0.5">
              <Label htmlFor="inherit-data" className="text-sm font-medium cursor-pointer">
                Heredar datos del padre
              </Label>
              <p className="text-xs text-muted-foreground">
                Incluir advertencias e imágenes del elemento padre
              </p>
            </div>
            <Switch
              id="inherit-data"
              checked={formData.inherit_parent_data}
              onCheckedChange={(checked) =>
                setFormData((prev) => ({ ...prev, inherit_parent_data: checked }))
              }
              disabled={isSubmitting}
            />
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Creando..." : "Crear Variante"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
