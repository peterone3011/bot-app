"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { signOut } from "next-auth/react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"

const navItems = [
  { href: "/dashboard/embeds",   label: "Embed 消息" },
  { href: "/dashboard/sites",    label: "站点管理" },
  { href: "/dashboard/settings", label: "全局设置" },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="flex h-screen w-52 flex-col border-r border-border bg-card px-3 py-4">
      <div className="mb-4 px-2">
        <h1 className="text-sm font-semibold text-foreground">Fortune Purple</h1>
        <p className="text-xs text-muted-foreground">管理后台</p>
      </div>
      <Separator className="mb-3" />
      <nav className="flex-1 space-y-1">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "block rounded-md px-3 py-2 text-sm transition-colors",
              pathname.startsWith(item.href)
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
