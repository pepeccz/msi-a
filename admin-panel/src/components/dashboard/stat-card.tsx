"use client";

import Link from "next/link";
import { LucideIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface StatCardProps {
  title: string;
  value: number | string;
  subtitle?: string;
  icon: LucideIcon;
  iconClassName?: string;
  /** Color semántico del valor numérico */
  valueColor?: "red" | "yellow" | "green" | "blue" | "neutral";
  /** Si true, aplicar el color solo cuando value > 0. Con value = 0 → text-muted-foreground */
  conditionalColor?: boolean;
  /** Si se provee, la card entera es clickable y navega a este href */
  href?: string;
  isLoading?: boolean;
}

const VALUE_COLOR_MAP: Record<NonNullable<StatCardProps["valueColor"]>, string> = {
  red:     "text-red-600",
  yellow:  "text-yellow-600",
  green:   "text-green-600",
  blue:    "text-blue-600",
  neutral: "",
};

function getValueClassName(
  color: StatCardProps["valueColor"],
  value: number | string,
  conditional: boolean
): string {
  if (!color || color === "neutral") return "";
  if (conditional && Number(value) === 0) return "text-muted-foreground";
  return VALUE_COLOR_MAP[color];
}

export function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  iconClassName,
  valueColor = "neutral",
  conditionalColor = false,
  href,
  isLoading = false,
}: StatCardProps) {
  const cardContent = (
    <Card className={cn(href && "cursor-pointer hover:shadow-md transition-shadow")}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className={cn("h-4 w-4 text-muted-foreground", iconClassName)} />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <>
            <Skeleton className="h-8 w-16 mb-1" />
            {subtitle && <Skeleton className="h-3 w-24" />}
          </>
        ) : (
          <>
            <div
              className={cn(
                "text-2xl font-bold",
                getValueClassName(valueColor, value, conditionalColor)
              )}
            >
              {value}
            </div>
            {subtitle && (
              <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );

  if (href) {
    return <Link href={href}>{cardContent}</Link>;
  }
  return cardContent;
}
