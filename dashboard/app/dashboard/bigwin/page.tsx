"use client"
import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { Trophy } from "lucide-react"

interface HistoryRecord {
  id: string
  ts: number
  amount: string
  game: string
  source: "cron" | "api"
  discordMessageId: string
}

function formatTs(ts: number): string {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

export default function BigwinHistoryPage() {
  const [source, setSource] = useState<string>("all")
  const [records, setRecords] = useState<HistoryRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(false)
    const url =
      source === "all"
        ? "/api/broadcast/bigwin/history"
        : `/api/broadcast/bigwin/history?source=${source}`
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error("fetch failed")
        return r.json()
      })
      .then((data) => {
        setRecords(data.records ?? [])
        setLoading(false)
      })
      .catch(() => {
        setError(true)
        setLoading(false)
      })
  }, [source])

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
          <span>工作区</span>
          <span className="text-muted-foreground/40">/</span>
          <span className="text-foreground">Big Win 记录</span>
        </div>
        <h1 className="mt-1.5 text-[22px] font-semibold tracking-tight">Big Win 记录</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          最近 30 天播报历史，保留最新 200 条。
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Trophy className="h-4 w-4 text-brand-300" />
              播报历史
            </CardTitle>
            <Select value={source} onValueChange={setSource}>
              <SelectTrigger className="w-36 h-8 text-[13px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部</SelectItem>
                <SelectItem value="cron">我们的Bot</SelectItem>
                <SelectItem value="api">技术接口</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <CardDescription>时间为本地时间。</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="py-12 flex justify-center text-[13px] text-muted-foreground">
              加载中…
            </div>
          ) : error ? (
            <div className="py-12 flex justify-center text-[13px] text-destructive">
              加载失败，请刷新页面重试
            </div>
          ) : records.length === 0 ? (
            <div className="py-12 flex justify-center text-[13px] text-muted-foreground">
              暂无记录
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]" aria-label="Big Win 播报历史">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="text-left py-2 pr-4 font-medium">时间</th>
                    <th className="text-left py-2 pr-4 font-medium">金额</th>
                    <th className="text-left py-2 pr-4 font-medium">游戏</th>
                    <th className="text-left py-2 font-medium">来源</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((r) => (
                    <tr key={r.id || String(r.ts)} className="border-b border-border/50 hover:bg-accent/20">
                      <td className="py-2.5 pr-4 tabular-nums text-muted-foreground">
                        {formatTs(r.ts)}
                      </td>
                      <td className="py-2.5 pr-4 font-medium">{r.amount} SC</td>
                      <td className="py-2.5 pr-4 text-muted-foreground">{r.game}</td>
                      <td className="py-2.5">
                        {r.source === "cron" ? (
                          <Badge
                            variant="outline"
                            className="border-success/40 text-success text-[11px]"
                          >
                            Bot
                          </Badge>
                        ) : (
                          <Badge
                            variant="outline"
                            className="border-primary/40 text-primary text-[11px]"
                          >
                            技术接口
                          </Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
