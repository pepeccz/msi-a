"use client";

import * as React from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { DensityToggle } from "@/components/shared/density-toggle";
import { cn } from "@/lib/utils";

interface FilterBarProps {
  searchValue: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  children?: React.ReactNode;
  /**
   * When true (default), renders a <DensityToggle /> in the right-aligned
   * actions slot. Set to false on pages without a density-aware table.
   */
  showDensityToggle?: boolean;
  className?: string;
}

/**
 * FilterBar — Standardized search + filter controls across list pages.
 *
 * Renders a search input (with magnifying glass icon) and an optional
 * children slot for additional filter controls (Select, date pickers, etc.).
 * Optionally renders <DensityToggle /> in the right-aligned actions slot
 * (enabled by default for pages with density-aware tables).
 *
 * Stacks vertically on mobile, flexes horizontally from sm breakpoint up.
 *
 * NOTE: No built-in debounce — the parent manages debounce timing.
 * This component simply fires onSearchChange on every keystroke.
 *
 * @example
 * <FilterBar
 *   searchValue={searchQuery}
 *   onSearchChange={setSearchQuery}
 *   searchPlaceholder="Buscar por nombre o teléfono..."
 *   showDensityToggle={true}
 * >
 *   <Select value={statusFilter} onValueChange={setStatusFilter}>
 *     <SelectTrigger className="w-[160px]"><SelectValue /></SelectTrigger>
 *     <SelectContent>
 *       <SelectItem value="all">Todos los estados</SelectItem>
 *       <SelectItem value="active">Activo</SelectItem>
 *     </SelectContent>
 *   </Select>
 * </FilterBar>
 */
export function FilterBar({
  searchValue,
  onSearchChange,
  searchPlaceholder = "Buscar...",
  children,
  showDensityToggle = true,
  className,
}: FilterBarProps) {
  return (
    <div className={cn("flex flex-col gap-3 sm:flex-row sm:items-center", className)}>
      {/* Search input with icon */}
      <div className="relative flex-1 sm:min-w-[250px] sm:flex-none">
        <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground pointer-events-none" />
        <Input
          type="search"
          placeholder={searchPlaceholder}
          value={searchValue}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-9 w-full"
        />
      </div>

      {/* Additional filter controls */}
      {children && (
        <div className="flex flex-wrap items-center gap-3">{children}</div>
      )}

      {/* Right-aligned density toggle */}
      {showDensityToggle && (
        <div className="sm:ml-auto flex-shrink-0">
          <DensityToggle />
        </div>
      )}
    </div>
  );
}
