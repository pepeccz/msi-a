import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground",
        outline: "text-foreground",
        // Status token variants (AD-6) — theme-aware, dark mode safe
        success:
          "border-transparent bg-[hsl(var(--status-success))] text-[hsl(var(--status-success-foreground))]",
        warning:
          "border-transparent bg-[hsl(var(--status-warning))] text-[hsl(var(--status-warning-foreground))]",
        error:
          "border-transparent bg-[hsl(var(--status-error))] text-[hsl(var(--status-error-foreground))]",
        info:
          "border-transparent bg-[hsl(var(--status-info))] text-[hsl(var(--status-info-foreground))]",
        pending:
          "border-transparent bg-[hsl(var(--status-pending))] text-[hsl(var(--status-pending-foreground))]",
        neutral:
          "border-transparent bg-[hsl(var(--status-neutral))] text-[hsl(var(--status-neutral-foreground))]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
