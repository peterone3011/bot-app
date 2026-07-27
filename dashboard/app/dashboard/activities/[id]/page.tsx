import { notFound } from "next/navigation"
import { ClipboardList, KeyRound, Settings } from "lucide-react"

import { ActivityCodePool } from "@/components/activity-code-pool"
import { ActivityEditor } from "@/components/activity-editor"
import { ActivitySubmissions } from "@/components/activity-submissions"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { supabase } from "@/lib/supabase"
import type { ActivityCampaign, ActivityQuestion } from "@/lib/types"


export const dynamic = "force-dynamic"

export default async function ActivityPage({ params }: { params: { id: string } }) {
  const { data, error } = await supabase
    .from("activity_campaigns")
    .select("*, activity_questions(*)")
    .eq("id", params.id)
    .single()
  if (error || !data) notFound()

  const row = data as Record<string, unknown>
  const campaign = {
    ...row,
    questions: ((row.activity_questions ?? []) as ActivityQuestion[]).sort((a, b) => a.position - b.position),
  } as unknown as ActivityCampaign

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
          <span>活动管理</span><span className="text-muted-foreground/40">/</span><span className="truncate text-foreground">{campaign.name}</span>
        </div>
        <h1 className="mt-1.5 text-[22px] font-semibold">{campaign.name}</h1>
      </div>
      <Tabs defaultValue="settings">
        <TabsList>
          <TabsTrigger value="settings"><Settings className="h-3.5 w-3.5" /> 活动设置</TabsTrigger>
          <TabsTrigger value="codes"><KeyRound className="h-3.5 w-3.5" /> 福利码</TabsTrigger>
          <TabsTrigger value="submissions"><ClipboardList className="h-3.5 w-3.5" /> 提交记录</TabsTrigger>
        </TabsList>
        <TabsContent value="settings"><ActivityEditor initial={campaign} /></TabsContent>
        <TabsContent value="codes"><ActivityCodePool campaign={campaign} /></TabsContent>
        <TabsContent value="submissions"><ActivitySubmissions campaignId={campaign.id} questions={campaign.questions} /></TabsContent>
      </Tabs>
    </div>
  )
}
