"use client";

import { useState, useEffect } from "react";
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
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { X } from "lucide-react";
import type { Element, VehicleCategory, ElementCreate, ElementUpdate } from "@/lib/types";

interface ElementFormProps {
  categories: VehicleCategory[];
  initialData?: Element;
  onSubmit: (data: ElementCreate | ElementUpdate) => Promise<void>;
  isSubmitting?: boolean;
  onCancel: () => void;
}

export default function ElementForm({
  categories,
  initialData,
  onSubmit,
  isSubmitting = false,
  onCancel,
}: ElementFormProps) {
  const [formData, setFormData] = useState({
    category_id: initialData?.category_id || "",
    code: initialData?.code || "",
    name: initialData?.name || "",
    description: initialData?.description || "",
    keywords: initialData?.keywords || [],
    aliases: initialData?.aliases || [],
    is_active: initialData?.is_active !== false,
  });

  const [newKeyword, setNewKeyword] = useState("");
  const [newAlias, setNewAlias] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.category_id.trim()) {
      newErrors.category_id = "La categoría es requerida";
    }

    if (!formData.code.trim()) {
      newErrors.code = "El código es requerido";
    } else if (!/^[A-Z0-9_]+$/.test(formData.code)) {
      newErrors.code = "El código debe contener solo letras mayúsculas, números y guiones";
    }

    if (!formData.name.trim()) {
      newErrors.name = "El nombre es requerido";
    }

    if (formData.keywords.length === 0) {
      newErrors.keywords = "Se requiere al menos una keyword";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleAddKeyword = () => {
    if (newKeyword.trim() && !formData.keywords.includes(newKeyword.toLowerCase())) {
      setFormData((prev) => ({
        ...prev,
        keywords: [...prev.keywords, newKeyword.toLowerCase()],
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

  const handleAddAlias = () => {
    if (newAlias.trim() && !formData.aliases?.includes(newAlias.toLowerCase())) {
      setFormData((prev) => ({
        ...prev,
        aliases: [...(prev.aliases || []), newAlias.toLowerCase()],
      }));
      setNewAlias("");
    }
  };

  const handleRemoveAlias = (alias: string) => {
    setFormData((prev) => ({
      ...prev,
      aliases: prev.aliases?.filter((a) => a !== alias) || [],
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) return;

    try {
      const submitData = initialData
        ? {
            code: formData.code,
            name: formData.name,
            description: formData.description || undefined,
            keywords: formData.keywords,
            aliases: formData.aliases,
            is_active: formData.is_active,
          }
        : {
            category_id: formData.category_id,
            code: formData.code,
            name: formData.name,
            description: formData.description || undefined,
            keywords: formData.keywords,
            aliases: formData.aliases,
            is_active: formData.is_active,
          };

      await onSubmit(submitData);
    } catch (error) {
      console.error("Form submission error:", error);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Category */}
      <div className="space-y-2">
        <Label htmlFor="category">
          Categoría de Vehículo <span className="text-destructive">*</span>
        </Label>
        <Select
          value={formData.category_id}
          onValueChange={(value) =>
            setFormData((prev) => ({ ...prev, category_id: value }))
          }
          disabled={!!initialData}
        >
          <SelectTrigger id="category">
            <SelectValue placeholder="Selecciona una categoría" />
          </SelectTrigger>
          <SelectContent>
            {categories.map((category) => (
              <SelectItem key={category.id} value={category.id}>
                {category.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {errors.category_id && (
          <p className="text-sm text-destructive">{errors.category_id}</p>
        )}
      </div>

      {/* Code */}
      <div className="space-y-2">
        <Label htmlFor="code">
          Código <span className="text-destructive">*</span>
        </Label>
        <Input
          id="code"
          placeholder="ej: ESC_MEC, TOLDO_LAT"
          value={formData.code}
          onChange={(e) =>
            setFormData((prev) => ({ ...prev, code: e.target.value.toUpperCase() }))
          }
          disabled={isSubmitting || !!initialData}
          className="font-mono"
        />
        <p className="text-xs text-muted-foreground">
          Identificador único, letras mayúsculas, números y guiones
        </p>
        {errors.code && <p className="text-sm text-destructive">{errors.code}</p>}
      </div>

      {/* Name */}
      <div className="space-y-2">
        <Label htmlFor="name">
          Nombre <span className="text-destructive">*</span>
        </Label>
        <Input
          id="name"
          placeholder="ej: Escalera mecánica trasera"
          value={formData.name}
          onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
          disabled={isSubmitting}
        />
        {errors.name && <p className="text-sm text-destructive">{errors.name}</p>}
      </div>

      {/* Description */}
      <div className="space-y-2">
        <Label htmlFor="description">Descripción</Label>
        <Textarea
          id="description"
          placeholder="Descripción detallada del elemento..."
          value={formData.description}
          onChange={(e) =>
            setFormData((prev) => ({ ...prev, description: e.target.value }))
          }
          disabled={isSubmitting}
          rows={3}
        />
        <p className="text-xs text-muted-foreground">Opcional</p>
      </div>

      {/* Keywords */}
      <div className="space-y-2">
        <Label htmlFor="keywords">
          Keywords para Matching <span className="text-destructive">*</span>
        </Label>
        <div className="flex gap-2">
          <Input
            id="keywords"
            placeholder="Escribe un keyword y presiona Enter..."
            value={newKeyword}
            onChange={(e) => setNewKeyword(e.target.value)}
            onKeyPress={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleAddKeyword();
              }
            }}
            disabled={isSubmitting}
          />
          <Button
            type="button"
            variant="outline"
            onClick={handleAddKeyword}
            disabled={isSubmitting || !newKeyword.trim()}
          >
            Añadir
          </Button>
        </div>

        {formData.keywords.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {formData.keywords.map((keyword) => (
              <Badge key={keyword} variant="secondary" className="gap-1">
                {keyword}
                <button
                  type="button"
                  onClick={() => handleRemoveKeyword(keyword)}
                  disabled={isSubmitting}
                  className="ml-1 hover:text-destructive"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
        )}

        {errors.keywords && (
          <p className="text-sm text-destructive">{errors.keywords}</p>
        )}
      </div>

      {/* Aliases */}
      <div className="space-y-2">
        <Label htmlFor="aliases">Aliases (Nombres Alternativos)</Label>
        <div className="flex gap-2">
          <Input
            id="aliases"
            placeholder="ej: escalerilla, peldaños..."
            value={newAlias}
            onChange={(e) => setNewAlias(e.target.value)}
            onKeyPress={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleAddAlias();
              }
            }}
            disabled={isSubmitting}
          />
          <Button
            type="button"
            variant="outline"
            onClick={handleAddAlias}
            disabled={isSubmitting || !newAlias.trim()}
          >
            Añadir
          </Button>
        </div>

        {formData.aliases && formData.aliases.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {formData.aliases.map((alias) => (
              <Badge key={alias} variant="outline" className="gap-1">
                {alias}
                <button
                  type="button"
                  onClick={() => handleRemoveAlias(alias)}
                  disabled={isSubmitting}
                  className="ml-1 hover:text-destructive"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
        )}

        <p className="text-xs text-muted-foreground">Opcional</p>
      </div>

      {/* Status */}
      <div className="flex items-center justify-between p-3 border rounded-lg bg-muted/50">
        <Label htmlFor="is_active" className="cursor-pointer">
          <span className="font-medium">Elemento Activo</span>
          <p className="text-xs text-muted-foreground">Los elementos inactivos no aparecen en las búsquedas</p>
        </Label>
        <Switch
          id="is_active"
          checked={formData.is_active}
          onCheckedChange={(checked) =>
            setFormData((prev) => ({ ...prev, is_active: checked }))
          }
          disabled={isSubmitting}
        />
      </div>

      {/* Actions */}
      <div className="flex gap-3 justify-end pt-4 border-t">
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Cancelar
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting
            ? "Guardando..."
            : initialData
              ? "Guardar Cambios"
              : "Crear Elemento"}
        </Button>
      </div>
    </form>
  );
}
