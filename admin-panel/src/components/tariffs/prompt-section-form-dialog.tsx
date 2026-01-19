"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import api from "@/lib/api";
import type {
  TariffPromptSection,
  TariffPromptSectionCreate,
  TariffPromptSectionUpdate,
  PromptSectionType,
} from "@/lib/types";

const SECTION_TYPES: { value: PromptSectionType; label: string; description: string }[] = [
  {
    value: "algorithm",
    label: "Algoritmo de Decisión",
    description: "Reglas para seleccionar qué tarifa aplica",
  },
  {
    value: "recognition_table",
    label: "Tabla de Reconocimiento",
    description: "Mapeo de elementos a tarifas típicas",
  },
  {
    value: "special_cases",
    label: "Casos Especiales",
    description: "Excepciones y situaciones particulares",
  },
  {
    value: "footer",
    label: "Contexto Adicional",
    description: "Información extra para el agente",
  },
];

interface PromptSectionFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  section: TariffPromptSection | null;
  categoryId: string;
  existingSectionTypes: PromptSectionType[];
  onSuccess: () => void;
}

export function PromptSectionFormDialog({
  open,
  onOpenChange,
  section,
  categoryId,
  existingSectionTypes,
  onSuccess,
}: PromptSectionFormDialogProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [formData, setFormData] = useState({
    section_type: "algorithm" as PromptSectionType,
    content: "",
    is_active: true,
  });

  // Get available section types (exclude already used ones, unless editing that type)
  const availableSectionTypes = SECTION_TYPES.filter(
    (type) =>
      !existingSectionTypes.includes(type.value) ||
      section?.section_type === type.value
  );

  useEffect(() => {
    if (section) {
      setFormData({
        section_type: section.section_type,
        content: section.content,
        is_active: section.is_active,
      });
    } else {
      // Set default to first available type
      const defaultType = availableSectionTypes[0]?.value || "algorithm";
      setFormData({
        section_type: defaultType,
        content: "",
        is_active: true,
      });
    }
  }, [section, open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      if (section) {
        const updateData: TariffPromptSectionUpdate = {
          content: formData.content,
          is_active: formData.is_active,
        };
        await api.updatePromptSection(section.id, updateData);
      } else {
        const createData: TariffPromptSectionCreate = {
          category_id: categoryId,
          section_type: formData.section_type,
          content: formData.content,
          is_active: formData.is_active,
        };
        await api.createPromptSection(createData);
      }

      onSuccess();
      onOpenChange(false);
    } catch (error) {
      console.error("Error saving prompt section:", error);
      alert("Error al guardar la seccion de prompt");
    } finally {
      setIsLoading(false);
    }
  };

  const getSectionLabel = (type: PromptSectionType) => {
    return SECTION_TYPES.find((s) => s.value === type)?.label || type;
  };

  const getSectionDescription = (type: PromptSectionType) => {
    return SECTION_TYPES.find((s) => s.value === type)?.description || "";
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {section ? "Editar Seccion de Prompt" : "Nueva Seccion de Prompt"}
          </DialogTitle>
          <DialogDescription>
            {section
              ? `Modificando seccion: ${getSectionLabel(section.section_type)}`
              : "Crea una nueva seccion de contexto para el agente"}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="section_type">Tipo de Seccion</Label>
            <Select
              value={formData.section_type}
              onValueChange={(value: PromptSectionType) =>
                setFormData({ ...formData, section_type: value })
              }
              disabled={!!section}
            >
              <SelectTrigger>
                <SelectValue placeholder="Selecciona un tipo" />
              </SelectTrigger>
              <SelectContent>
                {(section ? SECTION_TYPES : availableSectionTypes).map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    <div className="flex flex-col">
                      <span>{type.label}</span>
                      <span className="text-xs text-muted-foreground">
                        {type.description}
                      </span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!section && (
              <p className="text-xs text-muted-foreground">
                {getSectionDescription(formData.section_type)}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="content">Contenido</Label>
              <span className="text-xs text-muted-foreground">
                {formData.content.length} caracteres
              </span>
            </div>
            <Textarea
              id="content"
              value={formData.content}
              onChange={(e) => setFormData({ ...formData, content: e.target.value })}
              placeholder="Escribe el contenido de la seccion en formato Markdown..."
              className="min-h-[300px] font-mono text-sm"
              required
            />
            <p className="text-xs text-muted-foreground">
              Soporta formato Markdown. Este contenido se inyectara en el prompt del agente.
            </p>
          </div>

          <div className="flex items-center justify-between py-2 px-3 bg-muted/50 rounded-lg">
            <div>
              <Label htmlFor="is_active" className="text-sm font-medium cursor-pointer">
                Seccion Activa
              </Label>
              <p className="text-xs text-muted-foreground">
                Las secciones inactivas no se incluyen en el prompt
              </p>
            </div>
            <Switch
              id="is_active"
              checked={formData.is_active}
              onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
            />
          </div>

          {section && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Badge variant="outline">v{section.version}</Badge>
              <span>
                Ultima actualizacion:{" "}
                {new Date(section.updated_at).toLocaleString("es-ES", {
                  day: "2-digit",
                  month: "2-digit",
                  year: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isLoading || !formData.content.trim()}>
              {isLoading ? "Guardando..." : section ? "Guardar" : "Crear"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
