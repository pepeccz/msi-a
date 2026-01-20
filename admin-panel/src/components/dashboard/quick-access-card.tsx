"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import { LucideIcon, ExternalLink } from "lucide-react";

interface QuickAccessCardProps {
  title: string;
  description: string;
  href: string;
  icon: LucideIcon;
  external?: boolean;
  variant?: "default" | "primary" | "warning";
}

export function QuickAccessCard({
  title,
  description,
  href,
  icon: Icon,
  external = false,
  variant = "default",
}: QuickAccessCardProps) {
  const content = (
    <div
      className={cn(
        "flex items-center gap-4 rounded-lg border p-4 transition-all hover:shadow-md cursor-pointer",
        variant === "default" && "bg-card hover:bg-accent",
        variant === "primary" && "bg-primary/5 border-primary/20 hover:bg-primary/10",
        variant === "warning" && "bg-orange-50 border-orange-200 hover:bg-orange-100 dark:bg-orange-950/20 dark:border-orange-800 dark:hover:bg-orange-950/40"
      )}
    >
      <div
        className={cn(
          "flex h-10 w-10 items-center justify-center rounded-lg",
          variant === "default" && "bg-muted",
          variant === "primary" && "bg-primary/10",
          variant === "warning" && "bg-orange-100 dark:bg-orange-900/50"
        )}
      >
        <Icon
          className={cn(
            "h-5 w-5",
            variant === "default" && "text-muted-foreground",
            variant === "primary" && "text-primary",
            variant === "warning" && "text-orange-600 dark:text-orange-400"
          )}
        />
      </div>
      <div className="flex-1 min-w-0">
        <h3 className="font-medium text-sm">{title}</h3>
        <p className="text-xs text-muted-foreground truncate">{description}</p>
      </div>
      {external && (
        <ExternalLink className="h-4 w-4 text-muted-foreground flex-shrink-0" />
      )}
    </div>
  );

  if (external) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {content}
      </a>
    );
  }

  return <Link href={href}>{content}</Link>;
}
