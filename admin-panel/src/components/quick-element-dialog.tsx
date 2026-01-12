"use client";

import { useState } from "react";
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
import { Badge } from "@/components/ui/badge";
import { X } from "lucide-react";
import api from "@/lib/api";

interface QuickElementDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categoryId: string;
  tierId: string;
  onSuccess: () => void;
}

export function QuickElementDialog({
  open,
  onOpenChange,
  categoryId,
  tierId,
  onSuccess,
}: QuickElementDialogProps) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [keywordInput, setKeywordInput] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAddKeyword = () => {
    const keyword = keywordInput.trim().toLowerCase();
    if (keyword && !keywords.includes(keyword)) {
      setKeywords([...keywords, keyword]);
      setKeywordInput("");
    }
  };

  const handleRemoveKeyword = (keyword: string) => {
    setKeywords(keywords.filter((k) => k !== keyword));
  };

  const resetForm = () => {
    setCode("");
    setName("");
    setKeywords([]);
    setKeywordInput("");
    setError(null);
  };

  const handleSubmit = async () => {
    setError(null);

    if (!code.trim()) {
      setError("El codigo es requerido");
      return;
    }
    if (!name.trim()) {
      setError("El nombre es requerido");
      return;
    }
    if (keywords.length === 0) {
      setError("Debes agregar al menos 1 keyword");
      return;
    }

    try {
      setIsSaving(true);

      // Create element
      const element = await api.createElement({
        category_id: categoryId,
        code: code.toUpperCase(),
        name: name.trim(),
        keywords,
        is_active: true,
      });

      // Add to tier with unlimited quantity by default
      await api.createTierInclusion(tierId, {
        element_id: element.id,
        max_quantity: null,
      });

      resetForm();
      onSuccess();
    } catch (err) {
      console.error("Error creating element:", err);
      setError(
        err instanceof Error ? err.message : "Error desconocido al crear elemento"
      );
    } finally {
      setIsSaving(false);
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!open && !isSaving) {
      resetForm();
    }
    onOpenChange(open);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Crear Elemento Rapido</DialogTitle>
          <DialogDescription>
            El elemento se creara y se anadira automaticamente a esta tarifa con
            cantidad ilimitada
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {error && (
            <div className="bg-destructive/10 text-destructive text-sm p-3 rounded-md">
              {error}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="quick-code">Codigo *</Label>
            <Input
              id="quick-code"
              placeholder="ej: ESC_MEC"
              value={code}
              onChange={(e) =>
                setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ""))
              }
              disabled={isSaving}
              className="font-mono"
              maxLength={50}
            />
            <p className="text-xs text-muted-foreground">
              Solo mayusculas, numeros y guiones bajos
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="quick-name">Nombre *</Label>
            <Input
              id="quick-name"
              placeholder="ej: Escalera mecanica"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isSaving}
              maxLength={200}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="quick-keywords">Keywords * (minimo 1)</Label>
            <div className="flex gap-2">
              <Input
                id="quick-keywords"
                placeholder="escalera, peldanos..."
                value={keywordInput}
                onChange={(e) => setKeywordInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAddKeyword();
                  }
                }}
                disabled={isSaving}
              />
              <Button
                type="button"
                variant="outline"
                onClick={handleAddKeyword}
                disabled={isSaving || !keywordInput.trim()}
              >
                Anadir
              </Button>
            </div>

            {keywords.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {keywords.map((keyword) => (
                  <Badge key={keyword} variant="secondary" className="gap-1">
                    {keyword}
                    <button
                      type="button"
                      onClick={() => handleRemoveKeyword(keyword)}
                      disabled={isSaving}
                      className="hover:text-destructive"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={isSaving}
          >
            Cancelar
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={
              isSaving || !code.trim() || !name.trim() || keywords.length === 0
            }
          >
            {isSaving ? "Creando..." : "Crear y Anadir"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
