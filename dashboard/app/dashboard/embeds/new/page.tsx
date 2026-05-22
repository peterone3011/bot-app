"use client"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ChannelSelect } from "@/components/channel-select"

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
      setError("网络错误，请重试")
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md space-y-6">
      <h1 className="text-xl font-semibold">新建 Embed 消息</h1>

      <div className="space-y-2">
        <Label>目标频道</Label>
        <ChannelSelect value={channelId} onChange={setChannelId} disabled={loading} />
      </div>

      <div className="space-y-2">
        <Label htmlFor="label">标签（可选）</Label>
        <Input
          id="label"
          placeholder="例如：五月公告"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          disabled={loading}
        />
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex gap-2">
        <Button onClick={handleCreate} disabled={loading || !channelId}>
          {loading ? "创建中…" : "创建并编辑"}
        </Button>
        <Button variant="outline" onClick={() => router.back()} disabled={loading}>
          取消
        </Button>
      </div>
    </div>
  )
}
