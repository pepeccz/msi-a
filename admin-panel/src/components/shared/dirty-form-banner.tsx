"use client";

import * as React from "react";
import { Save, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDirtyFormSafe } from "@/contexts/dirty-form-context";
import { cn } from "@/lib/utils";

interface DirtyFormBannerProps {
  /** Must match the formId passed to useDirtyGuard */
  formId: string;
  /** Called when the user clicks "Guardar" */
  onSave: () => void;
  /** Called when the user clicks "Descartar cambios" */
  onDiscard: () => void;
  className?: string;
}

/**
 * DirtyFormBanner — sticky banner visible only when the specified form is dirty.
 *
 * Renders "Guardar" (primary) and "Descartar cambios" (ghost) buttons.
 * Visibility is driven by DirtyFormContext — no internal state.
 *
 * Place above the form section it corresponds to.
 *
 * @example
 * <DirtyFormBanner
 *   formId={`users:main:${id}`}
 *   onSave={handleSave}
 *   onDiscard={handleDiscard}
 * />
 */
export function DirtyFormBanner({
  formId,
  onSave,
  onDiscard,
  className,
}: DirtyFormBannerProps) {
  const { dirtyForms } = useDirtyFormSafe();
  const isVisible = dirtyForms.has(formId);

  if (!isVisible) return null;

  return (
    <div
      role="alert"
      aria-live="polite"
      className={cn(
        "sticky top-0 z-40 flex items-center justify-between gap-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 shadow-sm dark:border-amber-800 dark:bg-amber-950",
        className
      )}
    >
      <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
        Tienes cambios sin guardar
      </p>

      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={onDiscard}
          className="gap-1.5 text-amber-800 hover:bg-amber-100 hover:text-amber-900 dark:text-amber-200 dark:hover:bg-amber-900"
        >
          <Undo2 className="h-3.5 w-3.5" aria-hidden="true" />
          Descartar cambios
        </Button>

        <Button
          size="sm"
          onClick={onSave}
          className="gap-1.5"
        >
          <Save className="h-3.5 w-3.5" aria-hidden="true" />
          Guardar
        </Button>
      </div>
    </div>
  );
}
