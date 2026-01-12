"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2, Copy, Check } from "lucide-react";
import api from "@/lib/api";
import type { PromptPreview } from "@/lib/types";

interface PromptPreviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categoryId: string;
  categoryName: string;
}

export function PromptPreviewDialog({
  open,
  onOpenChange,
  categoryId,
  categoryName,
}: PromptPreviewDialogProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (open && categoryId) {
      loadPreview();
    }
  }, [open, categoryId]);

  const loadPreview = async () => {
    setIsLoading(true);
    try {
      const data = await api.previewCategoryPrompt(categoryId);
      setPreview(data);
    } catch (error) {
      console.error("Error loading preview:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = async () => {
    if (preview?.full_prompt) {
      await navigator.clipboard.writeText(preview.full_prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh]">
        <DialogHeader>
          <DialogTitle>Preview del Prompt - {categoryName}</DialogTitle>
          <DialogDescription>
            Vista previa del prompt completo que usara el agente para esta categoria
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : preview ? (
          <div className="space-y-4">
            {/* Stats */}
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline" className="gap-1">
                {preview.tiers_count} tarifas
              </Badge>
              <Badge variant="outline" className="gap-1">
                {preview.warnings_count} advertencias
              </Badge>
              <Badge variant="outline" className="gap-1">
                {preview.prompt_length.toLocaleString()} caracteres
              </Badge>
              <Badge variant="outline" className="gap-1">
                ~{Math.ceil(preview.prompt_length / 4).toLocaleString()} tokens
              </Badge>
            </div>

            {/* Sections Info */}
            {preview.sections && Object.keys(preview.sections).length > 0 && (
              <div className="flex flex-wrap gap-2">
                <span className="text-sm text-muted-foreground">Secciones:</span>
                {Object.keys(preview.sections).map((section) => (
                  <Badge key={section} variant="secondary" className="text-xs">
                    {section}
                  </Badge>
                ))}
              </div>
            )}

            {/* Prompt Content */}
            <div className="border rounded-lg overflow-hidden">
              <div className="flex items-center justify-between bg-muted px-4 py-2 border-b">
                <span className="text-sm font-medium">Prompt Completo</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleCopy}
                  className="h-8 gap-1"
                >
                  {copied ? (
                    <>
                      <Check className="h-4 w-4" />
                      Copiado
                    </>
                  ) : (
                    <>
                      <Copy className="h-4 w-4" />
                      Copiar
                    </>
                  )}
                </Button>
              </div>
              <pre className="p-4 text-sm overflow-auto max-h-[500px] whitespace-pre-wrap font-mono bg-background">
                {preview.full_prompt}
              </pre>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center py-12 text-muted-foreground">
            No se pudo cargar el preview
          </div>
        )}

        <div className="flex justify-end pt-4">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cerrar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
