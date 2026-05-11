"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface FilterChipOption<T extends string = string> {
  value: T;
  label: string;
  count?: number;
  icon?: React.ReactNode;
}

export interface FilterChipsProps<T extends string = string> {
  options: FilterChipOption<T>[];
  value: T | null;
  onChange: (value: T | null) => void;
  "aria-label"?: string;
  className?: string;
}

/**
 * FilterChips — Horizontal pill-chip strip for single-select status filtering.
 *
 * - Active chip: `bg-primary text-primary-foreground`
 * - Inactive chip: `bg-muted/40 text-muted-foreground hover:bg-muted/60`
 * - Zero-count chips: rendered with `opacity-60` but still clickable
 * - Clicking the active chip toggles it off (calls onChange with null)
 * - Count badge is nested inside each chip as a small <span>
 *
 * ARIA: wrapping div has role="group" + aria-label. Each button has aria-pressed.
 * Keyboard: browser-native focus order (Tab); arrow-key nav not added because
 * chips are not a single composite widget but independent toggle-buttons.
 *
 * @example
 * <FilterChips
 *   options={[
 *     { value: "all",     label: "Todos",     count: 42 },
 *     { value: "pending", label: "Pendientes", count: 7  },
 *   ]}
 *   value={currentStatus}
 *   onChange={(v) => setParams({ status: v ?? "all" })}
 *   aria-label="Filtrar por estado"
 * />
 */
export function FilterChips<T extends string = string>({
  options,
  value,
  onChange,
  "aria-label": ariaLabel = "Filtrar por estado",
  className,
}: FilterChipsProps<T>) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cn(
        "flex flex-wrap gap-2 px-4 py-3",
        className,
      )}
    >
      {options.map((option) => {
        const isActive = option.value === value;
        const isZeroCount = option.count !== undefined && option.count === 0;

        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={isActive}
            onClick={() => onChange(isActive ? null : option.value)}
            className={cn(
              // Base pill styles
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium",
              "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
              // Active vs inactive
              isActive
                ? "bg-primary text-primary-foreground"
                : "bg-muted/40 text-muted-foreground hover:bg-muted/60",
              // Zero count: de-emphasize
              isZeroCount && !isActive && "opacity-60",
            )}
          >
            {/* Optional icon */}
            {option.icon && (
              <span className="h-3 w-3 flex-shrink-0">{option.icon}</span>
            )}

            {/* Label */}
            <span>{option.label}</span>

            {/* Count badge */}
            {option.count !== undefined && (
              <span
                className={cn(
                  "inline-flex items-center justify-center rounded-full px-1.5 py-0.5 text-xs leading-none min-w-[18px]",
                  isActive
                    ? "bg-background/20 text-primary-foreground"
                    : "bg-background text-muted-foreground",
                )}
              >
                {option.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
