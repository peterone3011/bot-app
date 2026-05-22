import { supabase } from "@/lib/supabase"
import type { Site } from "@/lib/types"
import { SitesList } from "@/components/sites-list"

export const dynamic = "force-dynamic"

export default async function SitesPage() {
  const { data } = await supabase
    .from("sites")
    .select("*")
    .order("display_order", { ascending: true })

  const sites = (data ?? []) as Site[]

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">站点管理</h1>
      <p className="text-sm text-muted-foreground">
        拖动可排序。Bot 身份组选择器会按此顺序展示站点。
      </p>
      <SitesList initialSites={sites} />
    </div>
  )
}
