import * as React from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface ChatThreadSkeletonProps {
  /** Number of skeleton messages. Default: 6. Alternates L/R. */
  messages?: number;
  className?: string;
}

/**
 * ChatThreadSkeleton — renders alternating L/R skeleton chat bubbles.
 *
 * Accessibility: role="status" + aria-busy="true" on the root.
 *
 * @example
 * <ChatThreadSkeleton messages={6} />
 */
export function ChatThreadSkeleton({
  messages = 6,
  className,
}: ChatThreadSkeletonProps) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando conversación..."
      aria-live="polite"
      className={cn("flex flex-col gap-4 p-4", className)}
    >
      {Array.from({ length: messages }).map((_, idx) => {
        const isRight = idx % 2 === 1;
        return (
          <div
            key={idx}
            className={cn(
              "flex items-end gap-2",
              isRight ? "flex-row-reverse" : "flex-row"
            )}
          >
            {/* Avatar */}
            <Skeleton className="h-8 w-8 rounded-full flex-shrink-0" />

            {/* Bubble */}
            <div
              className={cn(
                "flex flex-col gap-1",
                isRight ? "items-end" : "items-start"
              )}
            >
              {/* Optional sender name */}
              <Skeleton className="h-3 w-16" />
              {/* Message bubble body */}
              <Skeleton
                className="h-10 rounded-2xl"
                style={{
                  width: `${160 + (idx % 3) * 40}px`,
                  maxWidth: "70%",
                }}
              />
              {/* Timestamp */}
              <Skeleton className="h-2 w-10" />
            </div>
          </div>
        );
      })}
      <span className="sr-only">Cargando conversación...</span>
    </div>
  );
}
