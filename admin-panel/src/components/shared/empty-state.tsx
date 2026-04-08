"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

interface EmptyStateProps {
  /** Optional icon element (from lucide-react). Rendered at h-12 w-12 in muted color. */
  icon?: React.ReactNode;
  /** Primary message, e.g. "No se encontraron resultados" */
  title: string;
  /** Optional longer explanation below the title */
  description?: string;
  /** Optional call-to-action (Button, Link, etc.) */
  action?: React.ReactNode;
  className?: string;
}

/**
 * EmptyState renders a consistent empty/no-data state across pages.
 *
 * Use this component instead of ad-hoc "No data" messages.
 *
 * @example
 * <EmptyState
 *   icon={<Search className="h-12 w-12" />}
 *   title="No se encontraron resultados"
 *   description="Intenta con otros términos de búsqueda."
 *   action={<Button onClick={onReset}>Limpiar filtros</Button>}
 * />
 *
 * @example
 * <EmptyState
 *   icon={<FileText className="h-12 w-12" />}
 *   title="No hay documentos"
 *   action={<Button>Subir documento</Button>}
 * />
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center py-12 text-center",
        className
      )}
    >
      {icon && (
        <div className="mb-4 text-muted-foreground [&>svg]:h-12 [&>svg]:w-12">
          {icon}
        </div>
      )}

      <p className="text-lg font-medium">{title}</p>

      {description && (
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          {description}
        </p>
      )}

      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
