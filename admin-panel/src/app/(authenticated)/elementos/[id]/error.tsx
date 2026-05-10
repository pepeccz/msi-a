"use client";

import { useEffect } from "react";
import { ErrorCard } from "@/components/shared/error-card";

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * Route-level error boundary for /elementos/[id].
 * Catches render-time crashes (not fetch errors — those are handled inline).
 * Fetch errors are caught in try/catch inside the page component.
 */
export default function ElementDetailError({ error, reset }: ErrorProps) {
  useEffect(() => {
    // Log for dev visibility — never expose to user UI
    console.error("[elementos/[id]/error.tsx]", error);
  }, [error]);

  return (
    <ErrorCard
      variant="page"
      error={error}
      onRetry={reset}
      message="No se pudo cargar el elemento. Puedes intentarlo de nuevo o volver al catálogo."
    />
  );
}
