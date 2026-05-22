"use client"
import { useState } from "react"
import { useRouter } from "next/navigation"
import type { Message } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { EmbedPreview } from "@/components/embed-preview"

function hexToInt(hex: string): number | null {
  const clean = hex.replace("#", "")
  if (!/^[0-9a-fA-F]{6}$/.test(clean)) return null
  return parseInt(clean, 16)
}

function intToHex(color: number | null): string {
  if (color === null) return ""
  return `#${color.toString(16).padStart(6, "0")}`
}

export function EmbedForm({ initial }: { initial: Message }) {
  const router = useRouter()
  const [msg, setMsg] = useState<Message>(initial)
  const [colorHex, setColorHex] = useState(intToHex(initial.color))
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState("")
  const [scheduleAt, setScheduleAt] = useState(
    initial.send_at ? initial.send_at.slice(0, 16).replace("T", " ") : ""
  )

  function update(field: keyof Message, value: unknown) {
    setMsg((prev) => ({ ...prev, [field]: value }))
  }

  async function save(extraFields?: Partial<Message>) {
    setSaving(true)
    setSaveMsg("")
    const payload = { ...msg, ...extraFields }
    try {
      const res = await fetch(`/api/embeds/${msg.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      if (res.ok) {
        setSaveMsg("已保存")
        setTimeout(() => setSaveMsg(""), 2000)
      } else {
        const d = await res.json()
        setSaveMsg(`错误：${d.error}`)
      }
    } catch {
      setSaveMsg("网络错误，请重试")
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!confirm("确定删除这条消息？此操作不可恢复。")) return
    try {
      await fetch(`/api/embeds/${msg.id}`, { method: "DELETE" })
      router.push("/dashboard/embeds")
      router.refresh()
    } catch {
      setSaveMsg("删除失败，请重试")
    }
  }

  async function handleSchedule() {
    if (!scheduleAt.trim()) {
      setSaveMsg("请填写发送时间")
      return
    }
    const dt = new Date(scheduleAt.trim().replace(" ", "T") + "+08:00")
    if (isNaN(dt.getTime()) || dt <= new Date()) {
      setSaveMsg("时间无效或已过期，格式：YYYY-MM-DD HH:MM")
      return
    }
    await save({ status: "scheduled", send_at: dt.toISOString() })
  }

  return (
    <div className="flex gap-8">
      {/* Left: form */}
      <div className="flex-1 space-y-4 max-w-lg">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">编辑 Embed</h1>
          <div className="flex gap-2 items-center">
            {saveMsg && <span className="text-sm">{saveMsg}</span>}
            <Button size="sm" onClick={() => save()} disabled={saving}>
              {saving ? "保存中…" : "保存"}
            </Button>
            <Button size="sm" variant="destructive" onClick={handleDelete}>
              删除
            </Button>
          </div>
        </div>

        <div className="space-y-2">
          <Label>标签（可选）</Label>
          <Input value={msg.label ?? ""} onChange={(e) => update("label", e.target.value || null)} placeholder="用于在列表中识别这条消息" />
        </div>

        <div className="space-y-2">
          <Label>标题</Label>
          <Input value={msg.title ?? ""} onChange={(e) => update("title", e.target.value || null)} maxLength={256} placeholder="Embed 标题" />
        </div>

        <div className="space-y-2">
          <Label>正文</Label>
          <Textarea value={msg.description ?? ""} onChange={(e) => update("description", e.target.value || null)} maxLength={4000} rows={5} placeholder="Embed 正文内容" />
        </div>

        <div className="space-y-2">
          <Label>底部文字（Footer）</Label>
          <Input value={msg.footer ?? ""} onChange={(e) => update("footer", e.target.value || null)} maxLength={2048} placeholder="底部小字" />
        </div>

        <div className="space-y-2">
          <Label>图片链接</Label>
          <Input value={msg.image_url ?? ""} onChange={(e) => update("image_url", e.target.value || null)} placeholder="https://..." />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label>按钮文字</Label>
            <Input value={msg.button_label ?? ""} onChange={(e) => update("button_label", e.target.value || null)} maxLength={80} />
          </div>
          <div className="space-y-2">
            <Label>按钮链接</Label>
            <Input value={msg.button_url ?? ""} onChange={(e) => update("button_url", e.target.value || null)} placeholder="https://..." />
          </div>
        </div>

        <div className="space-y-2">
          <Label>颜色（Hex）</Label>
          <div className="flex gap-2 items-center">
            <Input
              value={colorHex}
              onChange={(e) => {
                setColorHex(e.target.value)
                const parsed = hexToInt(e.target.value)
                if (parsed !== null) update("color", parsed)
              }}
              placeholder="#9B59B6"
              maxLength={7}
              className="w-36"
            />
            {colorHex && /^#[0-9a-fA-F]{6}$/.test(colorHex) && (
              <div className="h-6 w-6 rounded border" style={{ backgroundColor: colorHex }} />
            )}
          </div>
        </div>

        {/* Schedule section */}
        <div className="rounded-md border border-border p-4 space-y-3">
          <p className="text-sm font-medium">定时发送</p>
          <div className="flex gap-2 items-center">
            <Input
              value={scheduleAt}
              onChange={(e) => setScheduleAt(e.target.value)}
              placeholder="YYYY-MM-DD HH:MM (UTC+8)"
              className="w-52"
            />
            <Button size="sm" variant="secondary" onClick={handleSchedule} disabled={saving}>
              设置定时
            </Button>
            {msg.status === "scheduled" && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => save({ status: "draft", send_at: null })}
                disabled={saving}
              >
                取消定时
              </Button>
            )}
          </div>
          {msg.status === "scheduled" && msg.send_at && (
            <p className="text-xs text-muted-foreground">
              将于 {msg.send_at.slice(0, 16).replace("T", " ")} (UTC) 发送
            </p>
          )}
        </div>

        <p className="text-xs text-muted-foreground">
          状态：{msg.status === "draft" ? "草稿" : msg.status === "scheduled" ? "定时中" : "已发出"} · 频道 {msg.channel_id}
        </p>
      </div>

      {/* Right: preview */}
      <div className="w-80 shrink-0">
        <p className="mb-3 text-sm font-medium text-muted-foreground">预览</p>
        <EmbedPreview msg={msg} />
      </div>
    </div>
  )
}
