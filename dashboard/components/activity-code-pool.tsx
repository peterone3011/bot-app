"use client"

import { useEffect, useMemo, useState } from "react"
import { KeyRound, Save } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { parseRewardCodes } from "@/lib/activities"
import type { ActivityCampaign } from "@/lib/types"


type CodeRow = { position: number; code: string; claimed_at?: string | null }

export function ActivityCodePool({ campaign }: { campaign: ActivityCampaign }) {
  const [raw, setRaw] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState("")
  const locked = campaign.status !== "draft"
  const count = useMemo(() => raw.split(/\r?\n/).filter((line) => line.trim()).length, [raw])

  useEffect(() => {
    fetch(`/api/activities/${campaign.id}/codes`)
      .then(async (response) => {
        if (!response.ok) throw new Error("load failed")
        return response.json() as Promise<CodeRow[]>
      })
      .then((rows) => setRaw(rows.map((row) => row.code).join("\n")))
      .catch(() => setMessage("福利码加载失败"))
      .finally(() => setLoading(false))
  }, [campaign.id])

  async function save() {
    let codes: string[]
    try {
      codes = parseRewardCodes(raw)
    } catch (error) {
      setMessage((error as Error).message)
      return
    }
    setSaving(true)
    setMessage("")
    try {
      const response = await fetch(`/api/activities/${campaign.id}/codes`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ codes }),
      })
      const data = await response.json()
      setMessage(response.ok ? `已导入 ${data.count} 个福利码` : data.error)
    } catch {
      setMessage("网络错误")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between border-b border-border pb-4">
        <div className="flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-brand-300" />
          <span className="font-mono text-sm">{count} / {campaign.winner_limit}</span>
        </div>
        {!locked && (
          <Button size="sm" onClick={save} disabled={saving || loading}>
            <Save className="h-3.5 w-3.5" /> 导入福利码
          </Button>
        )}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="reward-codes">福利码（每行一个，按顺序发放）</Label>
        <Textarea id="reward-codes" aria-label="福利码" rows={18} className="font-mono" value={raw} disabled={locked || loading} onChange={(event) => setRaw(event.target.value)} />
      </div>
      {message && <p className="text-[12.5px] text-muted-foreground">{message}</p>}
    </div>
  )
}
