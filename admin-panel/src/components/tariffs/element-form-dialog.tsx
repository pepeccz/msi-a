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
import { Badge } from "@/components/ui/badge";
import { X, Plus } from "lucide-react";
import api from "@/lib/api";
import type { Element } from "@/lib/types";

interface ElementFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  element: Element | null;
  categoryId: string;
  onSuccess: () => void;
}

export function ElementFormDialog({
  open,
  onOpenChange,
  element,
  categoryId,
  onSuccess,
}: ElementFormDialogProps) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [keywordInput, setKeywordInput] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (element) {
      setCode(element.code);
      setName(element.name);
      setDescription(element.description || "");
      setKeywords(element.keywords || []);
    } else {
      setCode("");
      setName("");
      setDescription("");
      setKeywords([]);
    }
    setKeywordInput("");
  }, [element, open]);

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

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const data = {
        code: code.toUpperCase(),
        name: name.trim(),
        description: description.trim() || null,
        keywords,
        is_active: true,
      };

      if (element) {
        await api.updateElement(element.id, data);
      } else {
        await api.createElement({
          ...data,
          category_id: categoryId,
        });
      }

      onOpenChange(false);
      onSuccess();
    } catch (error) {
      console.error("Error saving element:", error);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {element ? "Editar Elemento" : "Nuevo Elemento"}
          </DialogTitle>
          <DialogDescription>
            {element
              ? "Modifica los datos del elemento"
              : "Crea un nuevo elemento para esta categoria"}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="elementCode">Codigo *</Label>
              <Input
                id="elementCode"
                value={code}
                onChange={(e) =>
                  setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ""))
                }
                placeholder="ESC_MEC"
                className="font-mono"
                maxLength={50}
              />
              <p className="text-xs text-muted-foreground">
                Solo mayusculas, numeros y guiones bajos
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="elementName">Nombre *</Label>
              <Input
                id="elementName"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Escalera mecanica"
                maxLength={200}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="elementDescription">Descripcion</Label>
            <Textarea
              id="elementDescription"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Descripcion del elemento..."
              rows={3}
            />
          </div>

          <div className="space-y-2">
            <Label>Keywords * (minimo 1)</Label>
            <div className="flex gap-2">
              <Input
                value={keywordInput}
                onChange={(e) => setKeywordInput(e.target.value)}
                placeholder="escalera, peldanos..."
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAddKeyword();
                  }
                }}
              />
              <Button
                type="button"
                variant="outline"
                onClick={handleAddKeyword}
                disabled={!keywordInput.trim()}
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              {keywords.map((keyword) => (
                <Badge key={keyword} variant="secondary" className="gap-1">
                  {keyword}
                  <button type="button" onClick={() => handleRemoveKeyword(keyword)}>
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              La IA usara estas keywords para identificar el elemento
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
            disabled={isSaving || !code.trim() || !name.trim() || keywords.length === 0}
          >
            {isSaving ? "Guardando..." : "Guardar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
