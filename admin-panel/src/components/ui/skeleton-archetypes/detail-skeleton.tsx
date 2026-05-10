import * as React from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface SectionConfig {
  /** Whether to render a title bar for this section. Default: true */
  title?: boolean;
  /** Number of label/value field rows. Default: 4 */
  fields?: number;
  /** Whether to render a full-width single skeleton (textarea style). Default: false */
  fullWidth?: boolean;
}

interface DetailSkeletonProps {
  /**
   * Array of section descriptors. Each section renders a heading block
   * plus N field rows in a two-column label/value layout.
   * If not provided, renders a single default section.
   */
  sections?: SectionConfig[];
  className?: string;
}

/**
 * DetailSkeleton — renders a heading + label/value field pairs approximating
 * the shape of a detail form page.
 *
 * Composition over variant enum: pages declare their own section shape.
 *
 * Accessibility: role="status" + aria-busy="true" on the root.
 *
 * @example
 * <DetailSkeleton sections={[{ title: true, fields: 3 }, { title: true, fields: 5 }]} />
 */
export function DetailSkeleton({ sections, className }: DetailSkeletonProps) {
  const resolvedSections: SectionConfig[] =
    sections && sections.length > 0 ? sections : [{ title: true, fields: 4 }];

  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando detalle..."
      aria-live="polite"
      className={cn("space-y-8", className)}
    >
      {/* Page-level heading block */}
      <div className="space-y-2">
        <Skeleton className="h-8 w-2/5" />
        <Skeleton className="h-4 w-1/3" />
      </div>

      {resolvedSections.map((section, sectionIdx) => (
        <div key={sectionIdx} className="space-y-4">
          {/* Section title bar */}
          {section.title !== false && (
            <Skeleton className="h-5 w-1/4" />
          )}

          {section.fullWidth ? (
            /* Full-width textarea-style skeleton */
            <Skeleton className="h-24 w-full" />
          ) : (
            /* Two-column label / value pairs */
            <div className="grid grid-cols-2 gap-x-8 gap-y-4">
              {Array.from({ length: section.fields ?? 4 }).map((_, fieldIdx) => (
                <React.Fragment key={fieldIdx}>
                  {/* Label column */}
                  <div className="space-y-1">
                    <Skeleton className="h-3 w-1/3" />
                    <Skeleton
                      className="h-5"
                      style={{
                        width: fieldIdx % 2 === 0 ? "80%" : "60%",
                      }}
                    />
                  </div>
                  {/* Value column */}
                  <div className="space-y-1">
                    <Skeleton className="h-3 w-1/4" />
                    <Skeleton
                      className="h-5"
                      style={{
                        width: fieldIdx % 3 === 0 ? "70%" : "90%",
                      }}
                    />
                  </div>
                </React.Fragment>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
