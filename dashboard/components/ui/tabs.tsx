"use client"

import * as React from "react"
import * as TabsPrimitive from "@radix-ui/react-tabs"

import { cn } from "@/lib/utils"

const Tabs = TabsPrimitive.Root

/**
 * Underline-style tab list (Linear / Vercel feel).
 * Sits on a hairline border-bottom; active tab gets a violet underline + glow.
 */
const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn(
      "inline-flex items-center gap-1 border-b border-border text-muted-foreground",
      className
    )}
    {...props}
  />
))
TabsList.displayName = TabsPrimitive.List.displayName

const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      // base
      "relative inline-flex items-center gap-2 whitespace-nowrap px-3.5 py-2.5 text-sm font-medium",
      "transition-colors focus-visible:outline-none focus-visible:text-foreground",
      "disabled:pointer-events-none disabled:opacity-50",
      // hover
      "hover:text-foreground",
      // active state: text + underline via ::after
      "data-[state=active]:text-foreground",
      "after:pointer-events-none after:absolute after:left-2 after:right-2 after:-bottom-px after:h-[2px] after:rounded-t after:bg-transparent after:transition-all",
      "data-[state=active]:after:bg-primary data-[state=active]:after:shadow-[0_0_12px_0_hsl(var(--primary)/0.5)]",
      // count chip styling for `(N)` inside the label
      "[&_.count]:font-mono [&_.count]:text-[11px] [&_.count]:tabular-nums [&_.count]:px-1.5 [&_.count]:py-0.5 [&_.count]:rounded-full [&_.count]:border [&_.count]:border-border [&_.count]:bg-secondary [&_.count]:text-muted-foreground",
      "data-[state=active]:[&_.count]:bg-primary/10 data-[state=active]:[&_.count]:text-brand-300 data-[state=active]:[&_.count]:border-primary/30",
      className
    )}
    {...props}
  />
))
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName

const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn(
      "mt-4 ring-offset-background focus-visible:outline-none animate-fade-in",
      className
    )}
    {...props}
  />
))
TabsContent.displayName = TabsPrimitive.Content.displayName

export { Tabs, TabsList, TabsTrigger, TabsContent }
