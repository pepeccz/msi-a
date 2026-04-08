import * as React from "react";

import { cn } from "@/lib/utils";

interface PageContainerProps {
  children: React.ReactNode;
  className?: string;
  /**
   * When true, removes max-width constraint for full-bleed pages
   * (e.g. monitoring/system pages that need edge-to-edge layout).
   */
  fullWidth?: boolean;
}

/**
 * PageContainer wraps page content with consistent max-width and responsive padding.
 *
 * Default: max-w-[1440px] centered, with responsive padding.
 * fullWidth: removes max-width for pages needing edge-to-edge content (system monitor, etc.)
 *
 * @example
 * <PageContainer>
 *   <PageHeader title="Usuarios" />
 *   <UserTable />
 * </PageContainer>
 *
 * @example
 * <PageContainer fullWidth>
 *   <SystemMonitor />
 * </PageContainer>
 */
export function PageContainer({
  children,
  className,
  fullWidth = false,
}: PageContainerProps) {
  return (
    <div
      className={cn(
        "px-4 py-5 md:px-6 md:py-6",
        !fullWidth && "mx-auto max-w-[1440px]",
        className
      )}
    >
      {children}
    </div>
  );
}
