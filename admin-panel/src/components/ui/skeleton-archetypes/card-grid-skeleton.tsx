import * as React from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface CardGridSkeletonProps {
  /** Number of skeleton cards. Default: 8 */
  items?: number;
  /** Grid columns. Default: 3 */
  cols?: 2 | 3 | 4;
  className?: string;
}

const colsClassMap: Record<2 | 3 | 4, string> = {
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
  4: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4",
};

/**
 * CardGridSkeleton — renders N skeleton cards in a CSS grid.
 *
 * Accessibility: role="status" + aria-busy="true" on the root.
 *
 * @example
 * <CardGridSkeleton items={9} cols={3} />
 */
export function CardGridSkeleton({
  items = 8,
  cols = 3,
  className,
}: CardGridSkeletonProps) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando elementos..."
      aria-live="polite"
      className={cn("grid gap-4", colsClassMap[cols], className)}
    >
      {Array.from({ length: items }).map((_, idx) => (
        <div
          key={idx}
          className="rounded-xl border bg-card p-4 space-y-3 shadow-sm"
        >
          {/* Card image/thumbnail placeholder */}
          <Skeleton className="h-32 w-full rounded-md" />
          {/* Card title */}
          <Skeleton className="h-4 w-3/4" />
          {/* Card subtitle/meta */}
          <Skeleton className="h-3 w-1/2" />
          {/* Card footer badge/action area */}
          <div className="flex items-center justify-between pt-1">
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-7 w-7 rounded-md" />
          </div>
        </div>
      ))}
      <span className="sr-only">Cargando elementos...</span>
    </div>
  );
}
