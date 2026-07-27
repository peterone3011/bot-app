"use client"

import { useEffect, useMemo, useState } from "react"
import { Download, Search } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { filterActivitySubmissions } from "@/lib/activities"
import type { ActivityQuestion, ActivitySubmission, ActivitySubmissionOutcome } from "@/lib/types"


const outcomeLabels: Record<ActivitySubmissionOutcome, string> = {
  winner: "中奖",
  sold_out: "未中奖（已发完）",
}

export function ActivitySubmissions({ campaignId, questions }: { campaignId: string; questions: ActivityQuestion[] }) {
  const [submissions, setSubmissions] = useState<ActivitySubmission[]>([])
  const [search, setSearch] = useState("")
  const [outcome, setOutcome] = useState<ActivitySubmissionOutcome | "all">("all")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    fetch(`/api/activities/${campaignId}/submissions`)
      .then(async (response) => {
        if (!response.ok) throw new Error("load failed")
        return response.json() as Promise<ActivitySubmission[]>
      })
      .then(setSubmissions)
      .catch(() => setError("提交记录加载失败"))
      .finally(() => setLoading(false))
  }, [campaignId])

  const filtered = useMemo(() => filterActivitySubmissions(submissions, search, outcome), [outcome, search, submissions])
  const orderedQuestions = [...questions].sort((a, b) => a.position - b.position)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 border-b border-border pb-4">
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input aria-label="搜索提交记录" className="pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索 Discord 用户或 FP ID" />
        </div>
        <select aria-label="中奖状态筛选" className="h-9 rounded-md border border-input bg-background px-3 text-sm" value={outcome} onChange={(event) => setOutcome(event.target.value as ActivitySubmissionOutcome | "all")}>
          <option value="all">全部</option>
          <option value="winner">中奖</option>
          <option value="sold_out">未中奖（已发完）</option>
        </select>
        <Button asChild variant="outline" size="sm">
          <a href={`/api/activities/${campaignId}/submissions/export`}>
            <Download className="h-3.5 w-3.5" /> 导出 CSV
          </a>
        </Button>
      </div>

      {loading ? (
        <div className="h-32 animate-pulse rounded-md border border-border bg-card/40" />
      ) : error ? (
        <p className="text-sm text-destructive">{error}</p>
      ) : filtered.length === 0 ? (
        <div className="rounded-md border border-dashed border-border py-12 text-center text-sm text-muted-foreground">暂无提交记录</div>
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full min-w-[820px] text-left text-[12.5px]">
            <thead className="border-b border-border bg-secondary/50 text-muted-foreground">
              <tr>
                <th className="px-3 py-2.5 font-medium">提交时间</th>
                <th className="px-3 py-2.5 font-medium">Discord</th>
                {orderedQuestions.map((question) => <th key={question.id} className="px-3 py-2.5 font-medium">{question.label}</th>)}
                <th className="px-3 py-2.5 font-medium">结果</th>
                <th className="px-3 py-2.5 font-medium">福利码</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((submission) => (
                <tr key={submission.id} className="border-b border-border last:border-0">
                  <td className="whitespace-nowrap px-3 py-2.5 text-muted-foreground">{new Date(submission.submitted_at).toLocaleString()}</td>
                  <td className="px-3 py-2.5">
                    <div>{submission.discord_username}</div>
                    <div className="font-mono text-[11px] text-muted-foreground">{submission.discord_user_id}</div>
                  </td>
                  {orderedQuestions.map((question) => <td key={question.id} className="max-w-[240px] truncate px-3 py-2.5">{submission.answers[question.field_key] ?? ""}</td>)}
                  <td className="px-3 py-2.5"><span className={submission.outcome === "winner" ? "fp-pill fp-pill-success" : "fp-pill fp-pill-muted"}>{outcomeLabels[submission.outcome]}</span></td>
                  <td className="px-3 py-2.5 font-mono">{submission.reward_code ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
