"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}

/**
 * PageHeader — Standardized page title area across all pages.
 *
 * Renders a flex row with title (+ optional description) on the left
 * and an actions slot (buttons, etc.) on the right.
 * Stacks vertically on mobile, side-by-side from sm breakpoint up.
 *
 * @example
 * <PageHeader
 *   title="Usuarios"
 *   description="Gestiona los usuarios del sistema"
 *   actions={<Button><Plus className="h-4 w-4" />Nuevo usuario</Button>}
 * />
 */
export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between",
        className
      )}
    >
      {/* Left: title + description */}
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight truncate">{title}</h1>
        {description && (
          <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
        )}
      </div>

      {/* Right: actions slot */}
      {actions && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      )}
    </div>
  );
}
