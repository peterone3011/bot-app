"use client"
import { useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { signOut } from "next-auth/react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { PanelLeftClose, PanelLeftOpen } from "lucide-react"

const navItems = [
  { href: "/dashboard/embeds",   label: "Embed 消息" },
  { href: "/dashboard/sites",    label: "站点管理" },
  { href: "/dashboard/settings", label: "全局设置" },
]

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const pathname = usePathname()

  if (collapsed) {
    return (
      <aside className="flex h-screen w-14 shrink-0 flex-col border-r border-border bg-card items-center py-4 gap-1">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setCollapsed(false)}
          className="text-muted-foreground"
          title="展开侧边栏"
        >
          <PanelLeftOpen className="h-4 w-4" />
        </Button>
        <Separator className="my-2 w-8" />
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            title={item.label}
            className={cn(
              "flex h-9 w-9 items-center justify-center rounded-md text-xs font-medium transition-colors",
              pathname?.startsWith(item.href)
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
            )}
          >
            {item.label.slice(0, 1)}
          </Link>
        ))}
      </aside>
    )
  }

  return (
    <aside className="flex h-screen w-52 shrink-0 flex-col border-r border-border bg-card px-3 py-4">
      <div className="mb-4 px-2 flex items-center justify-between">
        <div>
          <h1 className="text-sm font-semibold text-foreground">Fortune Purple</h1>
          <p className="text-xs text-muted-foreground">管理后台</p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setCollapsed(true)}
          className="h-7 w-7 text-muted-foreground"
          title="收起侧边栏"
        >
          <PanelLeftClose className="h-4 w-4" />
        </Button>
      </div>
      <Separator className="mb-3" />
      <nav className="flex-1 space-y-1">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "block rounded-md px-3 py-2 text-sm transition-colors",
              pathname?.startsWith(item.href)
                ? "bg-accent text-accent-foreground font-medium"
                : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
            )}
          >
            {item.label}
          </Link>
        ))}
      </nav>
      <Separator className="mb-3" />
      <Button
        variant="ghost"
        size="sm"
        className="w-full justify-start text-muted-foreground"
        onClick={() => signOut({ callbackUrl: "/login" })}
      >
        退出登录
      </Button>
    </aside>
  )
}
