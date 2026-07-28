import { ActivityList } from "@/components/activity-list"
import { supabase } from "@/lib/supabase"
import type { ActivityCampaign } from "@/lib/types"


export const dynamic = "force-dynamic"

export default async function ActivitiesPage() {
  const renderedAtMs = Date.now()
  const { data } = await supabase
    .from("activity_campaigns")
    .select("*, activity_questions(*), activity_codes(count), activity_submissions(count)")
    .order("created_at", { ascending: false })

  const campaigns = ((data ?? []) as Array<Record<string, unknown>>).map((row) => ({
    ...row,
    questions: row.activity_questions ?? [],
    code_count: (row.activity_codes as Array<{ count: number }> | undefined)?.[0]?.count ?? 0,
    submission_count: (row.activity_submissions as Array<{ count: number }> | undefined)?.[0]?.count ?? 0,
  })) as unknown as ActivityCampaign[]

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
          <span>工作台</span><span className="text-muted-foreground/40">/</span><span className="text-foreground">活动管理</span>
        </div>
        <h1 className="mt-1.5 text-[22px] font-semibold">活动管理</h1>
      </div>
      <ActivityList campaigns={campaigns} renderedAtMs={renderedAtMs} />
    </div>
  )
}
