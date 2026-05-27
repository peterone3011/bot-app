import { supabase } from "@/lib/supabase"
import type { Site } from "@/lib/types"
import { SitesList } from "@/components/sites-list"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { GripVertical } from "lucide-react"

export const dynamic = "force-dynamic"

export default async function SitesPage() {
  const { data } = await supabase
    .from("sites")
    .select("*")
    .order("display_order", { ascending: true })

  const sites = (data ?? []) as Site[]

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <div className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
          <span>工作区</span>
          <span className="text-muted-foreground/40">/</span>
          <span className="text-foreground">站点管理</span>
        </div>
        <h1 className="mt-1.5 text-[22px] font-semibold tracking-tight">站点管理</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          维护 Bot 身份组选择器中展示的站点列表与排序。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>站点列表</CardTitle>
          <CardDescription className="flex items-center gap-1.5">
            <GripVertical className="h-3.5 w-3.5" />
            拖动左侧手柄可排序 · Bot 身份组选择器会按此顺序展示
          </CardDescription>
        </CardHeader>
        <CardContent>
          <SitesList initialSites={sites} />
        </CardContent>
      </Card>
    </div>
  )
}
