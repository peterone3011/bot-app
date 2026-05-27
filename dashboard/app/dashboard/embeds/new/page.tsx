"use client"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { ChannelSelect } from "@/components/channel-select"
import { ChevronLeft } from "lucide-react"

export default function NewEmbedPage() {
  const router = useRouter()
  const [channelId, setChannelId] = useState("")
  const [label, setLabel] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function handleCreate() {
    if (!channelId) {
      setError("请选择目标频道")
      return
    }
    setLoading(true)
    setError("")
    try {
      const res = await fetch("/api/embeds", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel_id: channelId, label: label || null }),
      })
      if (!res.ok) {
        const data = await res.json()
        setError(data.error ?? "创建失败")
        setLoading(false)
        return
      }
      const msg = await res.json()
      router.push(`/dashboard/embeds/${msg.id}`)
    } catch {
      setError("网络错误,请重试")
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <button
          onClick={() => router.back()}
          className="inline-flex items-center gap-1 text-[12.5px] text-muted-foreground hover:text-foreground transition-colors mb-3"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          返回列表
        </button>
        <h1 className="text-[22px] font-semibold tracking-tight">新建 Embed 消息</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          选择投递频道,创建一条空白 Embed,稍后可继续编辑内容。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>基本信息</CardTitle>
          <CardDescription>必填项:频道。标签用于在列表中识别这条消息。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <Label>目标频道 <span className="normal-case text-destructive">*</span></Label>
            <ChannelSelect value={channelId} onChange={setChannelId} disabled={loading} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="label">标签(可选)</Label>
            <Input
              id="label"
              placeholder="例如:五月公告"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              disabled={loading}
            />
            <p className="text-[11.5px] text-muted-foreground">仅用于后台识别,不会发送到 Discord。</p>
          </div>

          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[12.5px] text-destructive">
              {error}
            </div>
          )}

          <div className="flex gap-2 pt-1">
            <Button onClick={handleCreate} disabled={loading || !channelId}>
              {loading ? "创建中…" : "创建并编辑"}
            </Button>
            <Button variant="outline" onClick={() => router.back()} disabled={loading}>
              取消
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
