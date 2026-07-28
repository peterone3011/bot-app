"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { ChevronRight, ClipboardList, Plus } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useActivityDisplayStatus } from "@/hooks/use-activity-display-status"
import type { ActivityCampaign, ActivityDisplayStatus } from "@/lib/types"


const statusLabels: Record<ActivityDisplayStatus, string> = {
  draft: "草稿",
  active: "进行中",
  expired: "已结束",
  closed: "已关闭",
}

function ActivityListItem({
  campaign,
  renderedAtMs,
}: {
  campaign: ActivityCampaign
  renderedAtMs: number
}) {
  const displayStatus = useActivityDisplayStatus(campaign, renderedAtMs)

  return (
    <a href={`/dashboard/activities/${campaign.id}`} className="group flex items-center gap-4 rounded-md border border-border bg-card px-4 py-3.5 hover:bg-card/80">
      <span className="h-9 w-1 shrink-0 rounded-full" style={{ backgroundColor: `#${(campaign.color ?? 0xff9933).toString(16).padStart(6, "0")}` }} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{campaign.name}</p>
        <p className="mt-1 font-mono text-[11px] text-muted-foreground">{campaign.code_count ?? 0} 个福利码 · {campaign.submission_count ?? 0} 条提交</p>
      </div>
      <span className="fp-pill fp-pill-muted">{statusLabels[displayStatus]}</span>
      <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
    </a>
  )
}

export function ActivityList({
  campaigns,
  renderedAtMs,
}: {
  campaigns: ActivityCampaign[]
  renderedAtMs: number
}) {
  const router = useRouter()
  const [name, setName] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  async function create() {
    if (!name.trim()) {
      setError("请输入活动名称")
      return
    }
    setBusy(true)
    setError("")
    const body = {
      name: name.trim(),
      winner_limit: 20,
      ends_at: null,
      discord_guild_id: null,
      discord_channel_id: null,
      embed_title: "",
      embed_description: "",
      image_url: null,
      color: 0xff9933,
      button_label: "Join Activity",
      modal_title: "Activity Entry",
      winner_message: "Congratulations! You’re one of our first participants.\nYour reward code: **{code}**",
      sold_out_message: "Sorry, all reward codes have been claimed. Please keep following our server—more events are coming soon!",
      closed_message: "This activity has ended. Please stay tuned for more events.",
      questions: [{
        id: "",
        campaign_id: "",
        field_key: "discord_username",
        position: 1,
        label: "Discord Username",
        input_style: "short",
        required: true,
        placeholder: "Your Discord username",
        min_length: 1,
        max_length: 100,
        prefill_discord_username: true,
        is_participant_key: false,
      }],
    }
    try {
      const response = await fetch("/api/activities", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      const data = await response.json()
      if (!response.ok) {
        setError(data.error ?? "创建失败")
        return
      }
      router.push(`/dashboard/activities/${data.id}`)
      router.refresh()
    } catch {
      setError("网络错误")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2 border-b border-border pb-5">
        <Input className="max-w-sm" value={name} onChange={(event) => setName(event.target.value)} placeholder="输入活动名称" />
        <Button onClick={create} disabled={busy}><Plus className="h-3.5 w-3.5" /> 创建草稿</Button>
        {error && <span className="self-center text-[12px] text-destructive">{error}</span>}
      </div>
      {campaigns.length === 0 ? (
        <div className="rounded-md border border-dashed border-border py-16 text-center text-muted-foreground">
          <ClipboardList className="mx-auto mb-3 h-5 w-5" />
          <p className="text-sm">暂无活动</p>
        </div>
      ) : (
        <div className="space-y-2">
          {campaigns.map((campaign) => (
            <ActivityListItem
              key={campaign.id}
              campaign={campaign}
              renderedAtMs={renderedAtMs}
            />
          ))}
        </div>
      )}
    </div>
  )
}
