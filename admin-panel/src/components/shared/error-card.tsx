"use client";

import * as React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ErrorCardProps {
  /** Card title. Default: "No se pudo cargar" */
  title?: string;
  /** User-friendly description message. Default: generic Spanish message */
  message?: string;
  /**
   * The caught error object.
   * In development, renders error.message in a <details> collapsible.
   * NEVER shown in production.
   */
  error?: Error | unknown;
  /** When provided, renders a "Reintentar" button. */
  onRetry?: () => void;
  /**
   * - 'inline': renders as a card inside the page content area
   * - 'page': renders centered, full-area replacement (for route-level error.tsx)
   */
  variant?: "inline" | "page";
  className?: string;
}

/**
 * ErrorCard — shared error display component.
 *
 * Used both for inline fetch errors (list/detail pages) and for
 * route-level error.tsx boundaries. Never exposes stack traces in production.
 *
 * @example
 * // Inline fetch error
 * <ErrorCard message="No se pudieron cargar los usuarios" onRetry={fetchData} />
 *
 * // Route-level (error.tsx)
 * <ErrorCard variant="page" error={error} onRetry={reset} message="No se pudo cargar el expediente." />
 */
export function ErrorCard({
  title = "No se pudo cargar",
  message = "No se pudo cargar la información. Por favor, intente de nuevo.",
  error,
  onRetry,
  variant = "inline",
  className,
}: ErrorCardProps) {
  const isDev = process.env.NODE_ENV !== "production";
  const errorMessage =
    isDev && error instanceof Error ? error.message : undefined;
  const errorStack =
    isDev && error instanceof Error ? error.stack : undefined;

  return (
    <div
      className={cn(
        variant === "page"
          ? "flex min-h-[60vh] items-center justify-center p-6"
          : "w-full",
        className
      )}
    >
      <Card
        className={cn(
          "border-destructive/50 bg-destructive/5",
          variant === "page" ? "w-full max-w-md" : "w-full"
        )}
      >
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-destructive text-base">
            <AlertCircle className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
            {title}
          </CardTitle>
        </CardHeader>

        <CardContent className="pb-3">
          <p className="text-sm text-muted-foreground">{message}</p>

          {/* Dev-only error detail — NEVER in production */}
          {isDev && errorMessage && (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
                Detalles técnicos (solo visible en desarrollo)
              </summary>
              <pre className="mt-2 overflow-auto rounded-md bg-muted p-3 text-xs leading-relaxed">
                {errorStack ?? errorMessage}
              </pre>
            </details>
          )}
        </CardContent>

        {onRetry && (
          <CardFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={onRetry}
              className="gap-2"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              Reintentar
            </Button>
          </CardFooter>
        )}
      </Card>
    </div>
  );
}
