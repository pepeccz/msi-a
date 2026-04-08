"use client";

import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface StatItem {
  label: string;
  value: string | number;
  /** Optional icon element (from lucide-react). Rendered at h-4 w-4 in muted color. */
  icon?: React.ReactNode;
  /** Optional trend indicator */
  trend?: {
    value: number;
    isPositive: boolean;
  };
  className?: string;
}

interface StatsStripProps {
  stats: StatItem[];
  /** Shows skeleton placeholders while true */
  isLoading?: boolean;
  className?: string;
}

/**
 * StatsStrip renders a responsive grid of KPI/stat cards.
 *
 * Replaces the ad-hoc `grid gap-4 md:grid-cols-2 lg:grid-cols-4` stat card
 * patterns spread across dashboard, cases, and escalations pages.
 *
 * @example
 * <StatsStrip
 *   stats={[
 *     { label: "Expedientes Pendientes", value: 12, icon: <Clock className="h-4 w-4" /> },
 *     { label: "Resueltos Hoy", value: 5, icon: <CheckCircle2 className="h-4 w-4" />, trend: { value: 20, isPositive: true } },
 *   ]}
 *   isLoading={isLoading}
 * />
 */
export function StatsStrip({ stats, isLoading = false, className }: StatsStripProps) {
  if (isLoading) {
    return (
      <div
        className={cn(
          "grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4",
          className
        )}
      >
        {/* Render one skeleton per expected stat slot (min 4, or actual count) */}
        {Array.from({ length: Math.max(stats.length, 4) }).map((_, i) => (
          <div
            key={i}
            className="rounded-lg border bg-card p-3"
          >
            <div className="flex items-center justify-between mb-2">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-4 w-4 rounded" />
            </div>
            <Skeleton className="h-7 w-16" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4",
        className
      )}
    >
      {stats.map((stat, index) => (
        <StatCard key={index} stat={stat} />
      ))}
    </div>
  );
}

/** Individual stat card — not exported, internal to StatsStrip */
function StatCard({ stat }: { stat: StatItem }) {
  return (
    <div className={cn("rounded-lg border bg-card p-3", stat.className)}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {stat.label}
        </p>
        {stat.icon && (
          <span className="shrink-0 text-muted-foreground [&>svg]:h-4 [&>svg]:w-4">
            {stat.icon}
          </span>
        )}
      </div>

      <div className="mt-1 flex items-end gap-2">
        <p className="text-2xl font-bold leading-none">{stat.value}</p>

        {stat.trend !== undefined && (
          <TrendIndicator trend={stat.trend} />
        )}
      </div>
    </div>
  );
}

/** Renders a small coloured trend string: +12% ↑ or -5% ↓ */
function TrendIndicator({
  trend,
}: {
  trend: NonNullable<StatItem["trend"]>;
}) {
  const { value, isPositive } = trend;
  const sign = isPositive ? "+" : "-";
  const arrow = isPositive ? "↑" : "↓";
  const colorClass = isPositive
    ? "text-[hsl(var(--status-success))]"
    : "text-[hsl(var(--status-error))]";

  return (
    <span className={cn("mb-0.5 text-xs font-medium", colorClass)}>
      {sign}
      {Math.abs(value)}% {arrow}
    </span>
  );
}
