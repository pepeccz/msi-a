"use client";

import * as React from "react";
import { Rows3, Rows4 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useTableDensity } from "@/contexts/table-density-context";

/**
 * DensityToggle — icon button that toggles table density between
 * "compact" and "comfortable" via TableDensityContext.
 *
 * No internal state. Place inside a FilterBar or toolbar.
 *
 * @example
 * <FilterBar ...>
 *   <DensityToggle />
 * </FilterBar>
 */
export function DensityToggle() {
  const { density, toggleDensity } = useTableDensity();

  const isCompact = density === "compact";
  // Dynamic aria-label reflects current state (what will happen on click)
  const ariaLabel = isCompact
    ? "Cambiar a vista cómoda"
    : "Cambiar a vista compacta";

  return (
    <TooltipProvider delayDuration={0}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="icon"
            onClick={toggleDensity}
            aria-label={ariaLabel}
            aria-pressed={isCompact}
            className="h-9 w-9 flex-shrink-0"
          >
            {isCompact ? (
              <Rows4 className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Rows3 className="h-4 w-4" aria-hidden="true" />
            )}
          </Button>
        </TooltipTrigger>
        {/* Tooltip always shows a stable label — screen readers use aria-label above */}
        <TooltipContent side="bottom">Cambiar densidad de tabla</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
