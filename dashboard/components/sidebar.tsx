"use client"
import { useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { signOut, useSession } from "next-auth/react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  PanelLeftClose,
  PanelLeftOpen,
  MessageSquare,
  Users,
  LogOut,
  Trophy,
  ClipboardList,
} from "lucide-react"

const navItems = [
  { href: "/dashboard/embeds", label: "Embed 消息",   icon: MessageSquare, short: "E" },
  { href: "/dashboard/roles",  label: "身份组管理",    icon: Users,         short: "R" },
  { href: "/dashboard/bigwin", label: "Big Win 记录", icon: Trophy,        short: "B" },
  { href: "/dashboard/activities", label: "活动管理", icon: ClipboardList, short: "活" },
]

function BrandMark({ size = 32 }: { size?: number }) {
  return (
    <div
      className="fp-brand-mark shrink-0"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <svg width={size * 0.5} height={size * 0.5} viewBox="0 0 16 16" fill="none">
        <path d="M8 1.5 L14.5 8 L8 14.5 L1.5 8 Z"
              stroke="rgba(255,255,255,0.9)" strokeWidth="1.2" strokeLinejoin="round"/>
        <path d="M8 5 L11 8 L8 11 L5 8 Z" fill="rgba(255,255,255,0.9)"/>
      </svg>
    </div>
  )
}

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const pathname = usePathname()
  const { data: session } = useSession()
  const displayName = session?.user?.name ?? "管理员"
  const avatarText  = (session?.user?.name ?? "FP").slice(0, 2).toUpperCase()

  // ───────────── Collapsed rail ─────────────
  if (collapsed) {
    return (
      <aside className="flex h-screen w-14 shrink-0 flex-col items-center border-r border-border bg-card/80 backdrop-blur-sm py-4 gap-2">
        <BrandMark size={28} />
        <div className="h-px w-8 bg-border my-1" />
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setCollapsed(false)}
          className="h-8 w-8 text-muted-foreground"
          title="展开侧边栏"
        >
          <PanelLeftOpen className="h-4 w-4" />
        </Button>
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = pathname?.startsWith(item.href)
          return (
            <Link
              key={item.href}
              href={item.href}
              title={item.label}
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-md transition-colors",
                isActive
                  ? "bg-primary/15 text-brand-300 ring-1 ring-primary/30"
                  : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
            </Link>
          )
        })}
        <div className="flex-1" />
        <Button
          variant="ghost"
          size="icon"
          onClick={() => signOut({ callbackUrl: "/login" })}
          title="退出登录"
          className="h-8 w-8 text-muted-foreground hover:text-foreground"
        >
          <LogOut className="h-4 w-4" />
        </Button>
      </aside>
    )
  }

  // ───────────── Expanded sidebar ─────────────
  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-border bg-card/80 backdrop-blur-sm">

      {/* Brand */}
      <div className="flex items-center gap-2.5 px-4 pt-4 pb-3.5 border-b border-border">
        <BrandMark size={30} />
        <div className="flex min-w-0 flex-1 flex-col leading-tight">
          <span className="truncate text-[13.5px] font-semibold tracking-tight text-foreground">Fortune Purple</span>
          <span className="truncate text-[11.5px] text-muted-foreground">管理后台</span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setCollapsed(true)}
          className="h-7 w-7 text-muted-foreground hover:text-foreground"
          title="收起侧边栏"
        >
          <PanelLeftClose className="h-4 w-4" />
        </Button>
      </div>

      {/* Section label */}
      <div className="px-4 pt-4 pb-1.5">
        <span className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/70">
          工作区
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 pb-3 space-y-0.5">
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = pathname?.startsWith(item.href)
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group relative flex items-center gap-2.5 rounded-md pl-3 pr-2 py-2 text-[13.5px] font-medium transition-colors",
                isActive
                  ? "bg-gradient-to-b from-primary/10 to-primary/[0.06] text-foreground border border-primary/15"
                  : "text-muted-foreground border border-transparent hover:bg-accent/40 hover:text-foreground"
              )}
            >
              {/* Active left rail */}
              <span
                aria-hidden="true"
                className={cn(
                  "absolute -left-3 top-2 bottom-2 w-[2px] rounded-full transition-colors",
                  isActive ? "bg-primary shadow-[0_0_8px_hsl(var(--primary)/0.6)]" : "bg-transparent"
                )}
              />
              <Icon className={cn(
                "h-4 w-4 transition-colors",
                isActive ? "text-brand-300" : "text-muted-foreground group-hover:text-foreground"
              )} />
              <span className="truncate flex-1">{item.label}</span>
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-border p-3 space-y-1.5">
        <div className="flex items-center gap-2.5 rounded-md border border-border bg-secondary/40 px-2.5 py-2">
          <div
            className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-[11px] font-semibold text-white"
            style={{
              background: "linear-gradient(135deg, hsl(270 45% 50%), hsl(270 45% 32%))",
              boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.08)",
            }}
            aria-hidden="true"
          >
            {avatarText}
          </div>
          <div className="flex min-w-0 flex-1 flex-col leading-tight">
            <span className="truncate text-[12.5px] font-semibold text-foreground">{displayName}</span>
            <span className="truncate text-[11px] text-muted-foreground">已登录</span>
          </div>
          <span className="h-1.5 w-1.5 rounded-full bg-success shadow-[0_0_6px_hsl(var(--success)/0.6)]" aria-hidden="true" />
        </div>

        <button
          onClick={() => signOut({ callbackUrl: "/login" })}
          className="group flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-[13px] font-medium text-muted-foreground transition-colors hover:bg-accent/40 hover:text-foreground"
        >
          <LogOut className="h-4 w-4" />
          <span>退出登录</span>
        </button>
      </div>
    </aside>
  )
}
