import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-none tracking-wide transition-colors focus:outline-none",
  {
    variants: {
      variant: {
        // Maps to "published" — violet/brand
        default:
          "border-primary/30 bg-primary/12 text-brand-300 [&>.dot]:bg-primary",
        // Maps to "scheduled" — warm/amber
        secondary:
          "border-warning/30 bg-warning/10 text-warning [&>.dot]:bg-warning",
        destructive:
          "border-destructive/30 bg-destructive/10 text-destructive [&>.dot]:bg-destructive",
        // Maps to "draft" — neutral
        outline:
          "border-border bg-secondary text-muted-foreground [&>.dot]:bg-muted-foreground",
        success:
          "border-success/30 bg-success/10 text-success [&>.dot]:bg-success",
      },
    },
    defaultVariants: { variant: "default" },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {
  /** Show a leading status dot (handy for pill-style status badges). */
  dot?: boolean
}

function Badge({ className, variant, dot, children, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props}>
      {dot && <span className="dot h-1.5 w-1.5 rounded-full" aria-hidden="true" />}
      {children}
    </div>
  )
}

export { Badge, badgeVariants }
