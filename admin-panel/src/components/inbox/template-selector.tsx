"use client";

import { useState, useMemo } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertTriangle, ChevronLeft, Send } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTemplates } from "@/hooks/use-inbox";
import type { TemplateResponse } from "@/lib/types";

interface TemplateSelectorProps {
  open: boolean;
  onClose: () => void;
  onSend: (
    templateName: string,
    params: Record<string, string>,
    language: string,
  ) => Promise<void>;
  isSubmitting?: boolean;
}

/** Extract {{n}} placeholders from template body text. Returns ordered list of placeholder numbers. */
function extractPlaceholders(components: TemplateResponse["components"]): number[] {
  const bodyComponent = components.find((c) => c.type === "BODY");
  if (!bodyComponent?.text) return [];
  const matches = bodyComponent.text.matchAll(/\{\{(\d+)\}\}/g);
  const nums = new Set<number>();
  for (const m of matches) {
    nums.add(parseInt(m[1], 10));
  }
  return Array.from(nums).sort((a, b) => a - b);
}

function TemplateCard({
  template,
  isSelected,
  onClick,
}: {
  template: TemplateResponse;
  isSelected: boolean;
  onClick: () => void;
}) {
  const body = template.components.find((c) => c.type === "BODY");

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full text-left rounded-lg border p-3 space-y-1 transition-colors",
        "hover:border-primary/60 hover:bg-muted/30",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        isSelected && "border-primary bg-primary/5",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium truncate">{template.name}</span>
        <Badge variant="outline" className="text-[10px] flex-shrink-0">
          {template.language}
        </Badge>
      </div>
      {body?.text && (
        <p className="text-xs text-muted-foreground line-clamp-2">
          {body.text}
        </p>
      )}
      <Badge
        variant="secondary"
        className="text-[10px]"
      >
        {template.category}
      </Badge>
    </button>
  );
}

export function TemplateSelector({
  open,
  onClose,
  onSend,
  isSubmitting = false,
}: TemplateSelectorProps) {
  const { templates, isLoading, error } = useTemplates();
  const [selectedTemplate, setSelectedTemplate] =
    useState<TemplateResponse | null>(null);
  const [paramValues, setParamValues] = useState<Record<string, string>>({});
  const [step, setStep] = useState<"list" | "params">("list");

  const placeholders = useMemo(
    () =>
      selectedTemplate
        ? extractPlaceholders(selectedTemplate.components)
        : [],
    [selectedTemplate],
  );

  function handleSelectTemplate(template: TemplateResponse) {
    setSelectedTemplate(template);
    setParamValues({});
    setStep("params");
  }

  function handleBack() {
    setSelectedTemplate(null);
    setParamValues({});
    setStep("list");
  }

  function handleClose() {
    setSelectedTemplate(null);
    setParamValues({});
    setStep("list");
    onClose();
  }

  async function handleSend() {
    if (!selectedTemplate) return;
    // Build params dict: key = "1", "2", ...
    const builtParams: Record<string, string> = {};
    for (const num of placeholders) {
      builtParams[String(num)] = paramValues[String(num)] ?? "";
    }
    await onSend(selectedTemplate.name, builtParams, selectedTemplate.language);
    handleClose();
  }

  const isParamsComplete =
    placeholders.length === 0 ||
    placeholders.every(
      (n) => (paramValues[String(n)] ?? "").trim().length > 0,
    );

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {step === "params" && (
              <button
                type="button"
                onClick={handleBack}
                className="text-muted-foreground hover:text-foreground"
                aria-label="Volver a la lista"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
            )}
            {step === "list" ? "Seleccionar plantilla" : "Completar parámetros"}
          </DialogTitle>
          <DialogDescription>
            {step === "list"
              ? "Enviá una plantilla aprobada de WhatsApp. Disponibles en cualquier momento."
              : `Plantilla: ${selectedTemplate?.name}`}
          </DialogDescription>
        </DialogHeader>

        {/* Step: list */}
        {step === "list" && (
          <div className="max-h-80 overflow-y-auto space-y-2 pr-1">
            {isLoading && (
              <>
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 w-full rounded-lg" />
                ))}
              </>
            )}

            {error && (
              <div className="flex items-center gap-2 text-destructive text-sm py-4">
                <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                <span>Error al cargar plantillas: {error}</span>
              </div>
            )}

            {!isLoading && !error && templates.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-8">
                No hay plantillas disponibles
              </p>
            )}

            {templates.map((t) => (
              <TemplateCard
                key={`${t.name}-${t.language}`}
                template={t}
                isSelected={selectedTemplate?.name === t.name}
                onClick={() => handleSelectTemplate(t)}
              />
            ))}
          </div>
        )}

        {/* Step: fill params */}
        {step === "params" && selectedTemplate && (
          <div className="space-y-4">
            {/* Template body preview */}
            {selectedTemplate.components.find((c) => c.type === "BODY")
              ?.text && (
              <div className="rounded-md bg-muted/50 p-3 text-sm text-muted-foreground">
                {selectedTemplate.components.find((c) => c.type === "BODY")
                  ?.text}
              </div>
            )}

            {placeholders.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Esta plantilla no requiere parámetros.
              </p>
            )}

            {placeholders.map((num) => (
              <div key={num} className="space-y-1.5">
                <Label htmlFor={`param-${num}`}>Parámetro {"{{"}{num}{"}}"}</Label>
                <Input
                  id={`param-${num}`}
                  placeholder={`Valor para {{${num}}}`}
                  value={paramValues[String(num)] ?? ""}
                  onChange={(e) =>
                    setParamValues((prev) => ({
                      ...prev,
                      [String(num)]: e.target.value,
                    }))
                  }
                />
              </div>
            ))}
          </div>
        )}

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            type="button"
            variant="outline"
            onClick={handleClose}
            disabled={isSubmitting}
          >
            Cancelar
          </Button>
          {step === "params" && (
            <Button
              type="button"
              onClick={handleSend}
              disabled={isSubmitting || !isParamsComplete}
              className="gap-1.5"
            >
              <Send className="h-4 w-4" />
              {isSubmitting ? "Enviando..." : "Enviar plantilla"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
