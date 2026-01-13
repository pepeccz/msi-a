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
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Plus, X } from "lucide-react";
import api from "@/lib/api";
import type {
  TariffTier,
  TariffTierCreate,
  TariffTierUpdate,
  ClassificationRules,
} from "@/lib/types";

interface TierFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tier: TariffTier | null;
  categoryId: string;
  onSuccess: () => void;
  inheritedKeywords?: string[];
}

interface TierFormState {
  code: string;
  name: string;
  description: string;
  price: string;
  conditions: string;
  classification_rules: ClassificationRules;
  min_elements: string;
  max_elements: string;
  is_active: boolean;
}

const defaultFormState: TierFormState = {
  code: "",
  name: "",
  description: "",
  price: "",
  conditions: "",
  classification_rules: {
    applies_if_any: [],
    priority: 0,
    requires_project: false,
  },
  min_elements: "",
  max_elements: "",
  is_active: true,
};

export function TierFormDialog({
  open,
  onOpenChange,
  tier,
  categoryId,
  onSuccess,
  inheritedKeywords,
}: TierFormDialogProps) {
  const [form, setForm] = useState<TierFormState>(defaultFormState);
  const [keywordInput, setKeywordInput] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (tier) {
      setForm({
        code: tier.code,
        name: tier.name,
        description: tier.description || "",
        price: tier.price.toString(),
        conditions: tier.conditions || "",
        classification_rules: tier.classification_rules || {
          applies_if_any: [],
          priority: 0,
          requires_project: false,
        },
        min_elements: tier.min_elements?.toString() || "",
        max_elements: tier.max_elements?.toString() || "",
        is_active: tier.is_active,
      });
    } else {
      setForm(defaultFormState);
    }
    setKeywordInput("");
  }, [tier, open]);

  const addKeyword = () => {
    const keyword = keywordInput.trim().toLowerCase();
    if (keyword && !form.classification_rules.applies_if_any.includes(keyword)) {
      setForm((prev) => ({
        ...prev,
        classification_rules: {
          ...prev.classification_rules,
          applies_if_any: [...prev.classification_rules.applies_if_any, keyword],
        },
      }));
      setKeywordInput("");
    }
  };

  const removeKeyword = (keyword: string) => {
    setForm((prev) => ({
      ...prev,
      classification_rules: {
        ...prev.classification_rules,
        applies_if_any: prev.classification_rules.applies_if_any.filter(
          (k) => k !== keyword
        ),
      },
    }));
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const price = parseFloat(form.price);
      if (isNaN(price)) return;

      const data = {
        code: form.code,
        name: form.name,
        description: form.description || null,
        price,
        conditions: form.conditions || null,
        classification_rules: form.classification_rules,
        min_elements: form.min_elements ? parseInt(form.min_elements) : null,
        max_elements: form.max_elements ? parseInt(form.max_elements) : null,
        is_active: form.is_active,
      };

      if (tier) {
        await api.updateTariffTier(tier.id, data as TariffTierUpdate);
      } else {
        await api.createTariffTier({
          ...data,
          category_id: categoryId,
        } as TariffTierCreate);
      }

      onOpenChange(false);
      onSuccess();
    } catch (error) {
      console.error("Error saving tier:", error);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{tier ? "Editar Tarifa" : "Nueva Tarifa"}</DialogTitle>
          <DialogDescription>
            {tier
              ? "Modifica los datos de la tarifa"
              : "Crea una nueva tarifa para esta categoria"}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="code">Codigo</Label>
              <Input
                id="code"
                value={form.code}
                onChange={(e) =>
                  setForm((prev) => ({
                    ...prev,
                    code: e.target.value.toUpperCase(),
                  }))
                }
                placeholder="T1"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="price">Precio (EUR)</Label>
              <Input
                id="price"
                type="number"
                step="0.01"
                value={form.price}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, price: e.target.value }))
                }
                placeholder="450"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="name">Nombre</Label>
            <Input
              id="name"
              value={form.name}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, name: e.target.value }))
              }
              placeholder="Tarifa Basica"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Descripcion</Label>
            <Textarea
              id="description"
              value={form.description}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, description: e.target.value }))
              }
              placeholder="Descripcion de la tarifa..."
            />
          </div>

          <div className="space-y-2">
            <Label>Estado</Label>
            <Select
              value={form.is_active ? "active" : "inactive"}
              onValueChange={(value) =>
                setForm((prev) => ({ ...prev, is_active: value === "active" }))
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="active">Activo</SelectItem>
                <SelectItem value="inactive">Inactivo</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="conditions">Condiciones</Label>
            <Textarea
              id="conditions"
              value={form.conditions}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, conditions: e.target.value }))
              }
              placeholder="Condiciones de aplicacion de la tarifa..."
            />
          </div>

          <div className="space-y-2">
            <Label>Keywords de clasificacion (para la IA)</Label>
            <div className="flex gap-2">
              <Input
                value={keywordInput}
                onChange={(e) => setKeywordInput(e.target.value)}
                placeholder="escape, silenciador..."
                onKeyDown={(e) =>
                  e.key === "Enter" && (e.preventDefault(), addKeyword())
                }
              />
              <Button type="button" variant="outline" onClick={addKeyword}>
                <Plus className="h-4 w-4" />
              </Button>
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              {form.classification_rules.applies_if_any.map((keyword) => (
                <Badge key={keyword} variant="secondary" className="gap-1">
                  {keyword}
                  <button type="button" onClick={() => removeKeyword(keyword)}>
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              La IA aplicara esta tarifa si el usuario menciona alguna de estas
              palabras
            </p>
          </div>

          {/* Keywords heredados de elementos (solo lectura) */}
          {tier && inheritedKeywords && inheritedKeywords.length > 0 && (
            <div className="space-y-2">
              <Label className="text-muted-foreground">
                Keywords heredados de elementos incluidos
              </Label>
              <div className="flex flex-wrap gap-2">
                {inheritedKeywords.slice(0, 20).map((keyword, index) => (
                  <Badge key={index} variant="outline" className="text-muted-foreground">
                    {keyword}
                  </Badge>
                ))}
                {inheritedKeywords.length > 20 && (
                  <Badge variant="outline" className="text-muted-foreground">
                    +{inheritedKeywords.length - 20} mas
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                Estos keywords provienen de los elementos configurados en esta tarifa
              </p>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="priority">Prioridad de clasificacion</Label>
            <Input
              id="priority"
              type="number"
              min="0"
              value={form.classification_rules.priority}
              onChange={(e) =>
                setForm((prev) => ({
                  ...prev,
                  classification_rules: {
                    ...prev.classification_rules,
                    priority: parseInt(e.target.value) || 0,
                  },
                }))
              }
              placeholder="0"
            />
            <p className="text-xs text-muted-foreground">
              Menor numero = mayor prioridad. Usado cuando multiples tarifas coinciden.
            </p>
          </div>

          <div className="flex items-center justify-between py-2 px-3 bg-muted/50 rounded-lg">
            <div>
              <Label htmlFor="requires_project" className="text-sm font-medium cursor-pointer">
                Requiere Proyecto Tecnico
              </Label>
              <p className="text-xs text-muted-foreground">
                Marcar si esta tarifa requiere elaboracion de proyecto tecnico
              </p>
            </div>
            <Switch
              id="requires_project"
              checked={form.classification_rules.requires_project}
              onCheckedChange={(checked) =>
                setForm((prev) => ({
                  ...prev,
                  classification_rules: {
                    ...prev.classification_rules,
                    requires_project: checked,
                  },
                }))
              }
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="min_elements">Min. Elementos</Label>
              <Input
                id="min_elements"
                type="number"
                value={form.min_elements}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, min_elements: e.target.value }))
                }
                placeholder="Opcional"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="max_elements">Max. Elementos</Label>
              <Input
                id="max_elements"
                type="number"
                value={form.max_elements}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, max_elements: e.target.value }))
                }
                placeholder="Opcional"
              />
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
            disabled={
              isSaving || !form.code.trim() || !form.name.trim() || !form.price
            }
          >
            {isSaving ? "Guardando..." : "Guardar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
