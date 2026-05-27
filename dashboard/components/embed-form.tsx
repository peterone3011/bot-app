"use client"
import { useState } from "react"
import { useRouter } from "next/navigation"
import type { Message } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { EmbedPreview } from "@/components/embed-preview"
import {
  ChevronLeft, Send, Trash2, Save, Clock, Image as ImageIcon,
  Link2, Type, AlignLeft,
} from "lucide-react"

function hexToInt(hex: string): number | null {
  const clean = hex.replace("#", "")
  if (!/^[0-9a-fA-F]{6}$/.test(clean)) return null
  return parseInt(clean, 16)
}

function intToHex(color: number | null): string {
  if (color === null) return ""
  return `#${color.toString(16).padStart(6, "0")}`
}

/** 将 UTC ISO 字符串转换为 UTC+8 的 "YYYY-MM-DD HH:MM" 显示格式 */
function utcToCST(isoStr: string): string {
  const dt = new Date(isoStr)
  if (isNaN(dt.getTime())) return isoStr.slice(0, 16).replace("T", " ")
  const cst = new Date(dt.getTime() + 8 * 60 * 60 * 1000)
  return cst.toISOString().slice(0, 16).replace("T", " ")
}

// Curated color swatches matching Discord role palette feel
const PRESET_COLORS = [
  { name: "紫", hex: "#9B59B6" },
  { name: "蓝", hex: "#5865F2" },
  { name: "青", hex: "#1ABC9C" },
  { name: "绿", hex: "#57F287" },
  { name: "黄", hex: "#FEE75C" },
  { name: "橙", hex: "#E67E22" },
  { name: "红", hex: "#ED4245" },
]

export function EmbedForm({ initial }: { initial: Message }) {
  const router = useRouter()
  const [msg, setMsg] = useState<Message>(initial)
  const [colorHex, setColorHex] = useState(intToHex(initial.color))
  const [saving, setSaving] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [saveMsg, setSaveMsg] = useState("")
  // 初始化时把 UTC 转为 UTC+8 显示给用户
  const [scheduleAt, setScheduleAt] = useState(
    initial.send_at ? utcToCST(initial.send_at) : ""
  )

  function update(field: keyof Message, value: unknown) {
    setMsg((prev) => ({ ...prev, [field]: value }))
  }

  function validate(): string | null {
    if (colorHex && !/^#[0-9a-fA-F]{6}$/.test(colorHex)) {
      return "颜色格式无效，请填写 #RRGGBB 格式（如 #9B59B6）"
    }
    const hasLabel = !!msg.button_label?.trim()
    const hasUrl = !!msg.button_url?.trim()
    if (hasLabel && !hasUrl) return "填写了按钮文字，请同时填写按钮链接"
    if (hasUrl && !hasLabel) return "填写了按钮链接，请同时填写按钮文字"
    if (msg.button_url && !/^https?:\/\/.+/.test(msg.button_url)) {
      return "按钮链接必须以 http:// 或 https:// 开头"
    }
    if (msg.image_url && !/^https?:\/\/.+/.test(msg.image_url)) {
      return "图片链接必须以 http:// 或 https:// 开头"
    }
    return null
  }

  // opts.redirect = false → 留在当前页刷新状态（用于设置/取消定时）
  // opts.redirect 不传或 true → 保存后跳回列表（保存草稿）
  async function save(extraFields?: Partial<Message>, opts?: { redirect?: boolean }) {
    const validationError = validate()
    if (validationError) {
      setSaveMsg(validationError)
      return
    }
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
        if (opts?.redirect === false) {
          const updated = await res.json() as Message
          setMsg(updated)
          if (!updated.send_at) setScheduleAt("")
          setSaveMsg("")
        } else {
          router.push("/dashboard/embeds")
          router.refresh()
        }
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

  async function handlePublish() {
    const validationError = validate()
    if (validationError) { setSaveMsg(validationError); return }
    if (!confirm("确定立即发布到 Discord？")) return
    setPublishing(true)
    setSaveMsg("")
    try {
      // 先保存当前内容，保存失败则中止，避免发出旧内容
      const saveRes = await fetch(`/api/embeds/${msg.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(msg),
      })
      if (!saveRes.ok) {
        const d = await saveRes.json()
        setSaveMsg(`保存失败：${d.error || "请重试"}`)
        return
      }
      const res = await fetch(`/api/embeds/${msg.id}/publish`, { method: "POST" })
      if (res.ok) {
        router.push("/dashboard/embeds")
        router.refresh()
      } else {
        const d = await res.json()
        // 409 = 原帖已被删，提示用户再点一次重新发帖
        const hint = res.status === 409
          ? "（原帖已删，请再次点击发布）"
          : (d.detail ? `（${d.detail}）` : "")
        setSaveMsg(`发布失败：${d.error}${hint}`)
      }
    } catch {
      setSaveMsg("网络错误，请重试")
    } finally {
      setPublishing(false)
    }
  }

  async function handleDelete() {
    if (!confirm("确定删除这条消息？此操作不可恢复。")) return
    try {
      const res = await fetch(`/api/embeds/${msg.id}`, { method: "DELETE" })
      if (!res.ok) {
        setSaveMsg("删除失败，请重试")
        return
      }
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
    // redirect: false → 设置定时后停留在页面继续编辑
    await save({ status: "scheduled", send_at: dt.toISOString() }, { redirect: false })
  }

  const statusBadge =
    msg.status === "published" ? { v: "default" as const, label: "已发出" } :
    msg.status === "scheduled" ? { v: "secondary" as const, label: "定时中" } :
                                 { v: "outline" as const, label: "草稿" }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start gap-4">
        <div className="min-w-0 flex-1">
          <button
            onClick={() => router.push("/dashboard/embeds")}
            className="inline-flex items-center gap-1 text-[12.5px] text-muted-foreground hover:text-foreground transition-colors mb-2"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            返回 Embed 消息列表
          </button>
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="text-[22px] font-semibold tracking-tight">编辑 Embed</h1>
            <Badge variant={statusBadge.v} dot>{statusBadge.label}</Badge>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {saveMsg && (
            <span className="text-[12px] text-destructive max-w-[280px] truncate" title={saveMsg}>{saveMsg}</span>
          )}
          <Button variant="outline" size="sm" onClick={() => save()} disabled={saving}>
            <Save className="h-3.5 w-3.5" />
            {saving ? "保存中…" : "保存草稿"}
          </Button>
          <Button size="sm" onClick={handlePublish} disabled={saving || publishing}>
            <Send className="h-3.5 w-3.5" />
            {publishing ? "发布中…" : "立即发布"}
          </Button>
          <Button size="sm" variant="destructive" onClick={handleDelete}>
            <Trash2 className="h-3.5 w-3.5" />
            删除
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr,340px] gap-6 items-start">
        {/* Left: form */}
        <div className="space-y-5 min-w-0">

          {/* General */}
          <Card>
            <CardHeader>
              <CardTitle>基本信息</CardTitle>
              <CardDescription>标签仅用于后台识别，不会发送到 Discord。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label>标签（可选）</Label>
                <Input
                  value={msg.label ?? ""}
                  onChange={(e) => update("label", e.target.value || null)}
                  placeholder="用于在列表中识别这条消息"
                />
              </div>
            </CardContent>
          </Card>

          {/* Content */}
          <Card>
            <CardHeader>
              <CardTitle>Embed 内容</CardTitle>
              <CardDescription>支持 Markdown · 正文最多 4000 字</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">

              {/* Color */}
              <div className="space-y-2">
                <Label>色条</Label>
                <div className="flex items-center gap-2 flex-wrap">
                  {PRESET_COLORS.map((c) => {
                    const isActive = colorHex.toLowerCase() === c.hex.toLowerCase()
                    return (
                      <button
                        key={c.hex}
                        type="button"
                        title={c.name}
                        onClick={() => {
                          setColorHex(c.hex)
                          const parsed = hexToInt(c.hex)
                          if (parsed !== null) update("color", parsed)
                        }}
                        className={`relative h-7 w-7 rounded-md transition-all ${
                          isActive
                            ? "ring-2 ring-offset-2 ring-offset-card ring-foreground/80 scale-105"
                            : "ring-1 ring-border hover:ring-foreground/30"
                        }`}
                        style={{ backgroundColor: c.hex }}
                      />
                    )
                  })}
                  <div className="ml-1 flex items-center gap-2 rounded-md border border-input bg-background/40 pl-2.5 pr-1 h-9 focus-within:border-primary/60 focus-within:ring-2 focus-within:ring-primary/25">
                    <span className="text-muted-foreground select-none text-sm">#</span>
                    <input
                      value={colorHex.replace("#", "")}
                      onChange={(e) => {
                        const raw = e.target.value.replace(/[^0-9a-fA-F]/g, "").slice(0, 6)
                        const full = "#" + raw
                        setColorHex(full)
                        const parsed = hexToInt(full)
                        if (parsed !== null) update("color", parsed)
                      }}
                      placeholder="9B59B6"
                      maxLength={6}
                      className="w-20 bg-transparent py-1.5 outline-none font-mono text-sm"
                    />
                    <input
                      type="color"
                      value={/^#[0-9a-fA-F]{6}$/.test(colorHex) ? colorHex : "#9B59B6"}
                      onChange={(e) => {
                        setColorHex(e.target.value)
                        const parsed = hexToInt(e.target.value)
                        if (parsed !== null) update("color", parsed)
                      }}
                      className="h-6 w-6 cursor-pointer rounded border-0 bg-transparent p-0"
                      title="调色板"
                    />
                  </div>
                </div>
                {colorHex.replace("#", "").length > 0 && !/^#[0-9a-fA-F]{6}$/.test(colorHex) && (
                  <p className="text-[11.5px] text-destructive">请填写完整的 6 位十六进制颜色</p>
                )}
              </div>

              <div className="space-y-1.5">
                <Label className="flex items-center gap-1.5"><Type className="h-3 w-3" /> 标题</Label>
                <Input
                  value={msg.title ?? ""}
                  onChange={(e) => update("title", e.target.value || null)}
                  maxLength={256}
                  placeholder="Embed 标题"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="flex items-center gap-1.5"><AlignLeft className="h-3 w-3" /> 正文</Label>
                <Textarea
                  value={msg.description ?? ""}
                  onChange={(e) => update("description", e.target.value || null)}
                  maxLength={4000}
                  rows={6}
                  placeholder="Embed 正文内容，支持 Markdown"
                />
                <div className="flex justify-between text-[11.5px] text-muted-foreground">
                  <span>支持 **粗体** · *斜体* · [链接](url)</span>
                  <span className="font-mono tabular-nums">{(msg.description ?? "").length} / 4000</span>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label>底部文字（Footer）</Label>
                <Input
                  value={msg.footer ?? ""}
                  onChange={(e) => update("footer", e.target.value || null)}
                  maxLength={2048}
                  placeholder="底部小字"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="flex items-center gap-1.5"><ImageIcon className="h-3 w-3" /> 图片链接</Label>
                <Input
                  value={msg.image_url ?? ""}
                  onChange={(e) => update("image_url", e.target.value || null)}
                  placeholder="https://..."
                />
              </div>
            </CardContent>
          </Card>

          {/* Button */}
          <Card>
            <CardHeader>
              <CardTitle>互动按钮</CardTitle>
              <CardDescription>可选 · 文字与链接需同时填写。</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>按钮文字</Label>
                  <Input
                    value={msg.button_label ?? ""}
                    onChange={(e) => update("button_label", e.target.value || null)}
                    maxLength={80}
                    placeholder="例如：查看详情"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="flex items-center gap-1.5"><Link2 className="h-3 w-3" /> 按钮链接</Label>
                  <Input
                    value={msg.button_url ?? ""}
                    onChange={(e) => update("button_url", e.target.value || null)}
                    placeholder="https://..."
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Schedule */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-brand-300" />
                定时发送
              </CardTitle>
              <CardDescription>
                设置一个未来时间，Bot 会在到点时自动发送（时区：UTC+8）。
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2 items-center">
                <Input
                  value={scheduleAt}
                  onChange={(e) => setScheduleAt(e.target.value)}
                  placeholder="YYYY-MM-DD HH:MM"
                  className="w-56 font-mono"
                />
                <Button size="sm" variant="secondary" onClick={handleSchedule} disabled={saving}>
                  设置定时
                </Button>
                {msg.status === "scheduled" && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => save({ status: "draft", send_at: null }, { redirect: false })}
                    disabled={saving}
                  >
                    取消定时
                  </Button>
                )}
              </div>
              {msg.status === "scheduled" && msg.send_at && (
                <p className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-warning/30 bg-warning/10 px-2.5 py-1.5 text-[12px] text-warning">
                  <Clock className="h-3 w-3" />
                  将于 <span className="font-mono">{utcToCST(msg.send_at)}</span> (UTC+8) 发送
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right: preview */}
        <aside className="lg:sticky lg:top-6 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">
              Discord 预览
            </span>
            <span className="text-[10.5px] text-muted-foreground inline-flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
              实时同步
            </span>
          </div>
          <div className="rounded-lg border border-border bg-card/60 p-3">
            <EmbedPreview msg={msg} />
          </div>
        </aside>
      </div>
    </div>
  )
}
