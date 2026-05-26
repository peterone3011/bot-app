"use client"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

async function saveSetting(key: string, value: string): Promise<boolean> {
  const res = await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  })
  return res.ok
}

export default function SettingsPage() {
  const [rolesChannel, setRolesChannel] = useState("")
  const [bigwinImage1, setBigwinImage1] = useState("")
  const [bigwinImage2, setBigwinImage2] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)
  const [msg, setMsg] = useState("")

  useEffect(() => {
    fetch("/api/settings")
      .then((r) => {
        if (!r.ok) throw new Error("fetch failed")
        return r.json()
      })
      .then((data) => {
        setRolesChannel(data.roles_channel_name ?? "")
        setBigwinImage1(data.bigwin_image_1 ?? "")
        setBigwinImage2(data.bigwin_image_2 ?? "")
        setLoading(false)
      })
      .catch(() => {
        setMsg("加载失败，请刷新页面")
        setLoading(false)
      })
  }, [])

  function showMsg(text: string) {
    setMsg(text)
    setTimeout(() => setMsg(""), 2500)
  }

  async function handleSaveRoles() {
    setSaving("roles")
    const ok = await saveSetting("roles_channel_name", rolesChannel).catch(() => false)
    showMsg(ok ? "✅ 已保存" : "❌ 保存失败")
    setSaving(null)
  }

  async function handleSaveImages() {
    setSaving("images")
    const [ok1, ok2] = await Promise.all([
      saveSetting("bigwin_image_1", bigwinImage1).catch(() => false),
      saveSetting("bigwin_image_2", bigwinImage2).catch(() => false),
    ])
    showMsg(ok1 && ok2 ? "✅ 已保存" : "❌ 部分保存失败，请重试")
    setSaving(null)
  }

  return (
    <div className="space-y-8 max-w-lg">
      <h1 className="text-xl font-semibold">全局设置</h1>

      {/* 角色频道设置 */}
      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">身份组</h2>
        <div className="space-y-2">
          <Label htmlFor="roles-channel">角色选择频道名称</Label>
          <Input
            id="roles-channel"
            value={rolesChannel}
            onChange={(e) => setRolesChannel(e.target.value)}
            placeholder="🔔roles"
            disabled={loading}
          />
          <p className="text-xs text-muted-foreground">
            Bot 会在这个名称的频道里发布身份组选择消息。
          </p>
        </div>
        <Button onClick={handleSaveRoles} disabled={saving === "roles" || loading} size="sm">
          {saving === "roles" ? "保存中…" : "保存"}
        </Button>
      </section>

      <div className="border-t border-border" />

      {/* 大奖播报配图 */}
      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">大奖播报配图</h2>
        <p className="text-xs text-muted-foreground">每次播报随机选一张展示。留空则不显示图片。</p>

        <div className="space-y-2">
          <Label htmlFor="bigwin-img-1">图片 1 URL</Label>
          <Input
            id="bigwin-img-1"
            value={bigwinImage1}
            onChange={(e) => setBigwinImage1(e.target.value)}
            placeholder="https://cdn.discordapp.com/..."
            disabled={loading}
          />
          {bigwinImage1 && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={bigwinImage1} alt="预览图 1" className="mt-1 h-20 rounded object-cover border border-border" />
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="bigwin-img-2">图片 2 URL</Label>
          <Input
            id="bigwin-img-2"
            value={bigwinImage2}
            onChange={(e) => setBigwinImage2(e.target.value)}
            placeholder="https://cdn.discordapp.com/..."
            disabled={loading}
          />
          {bigwinImage2 && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={bigwinImage2} alt="预览图 2" className="mt-1 h-20 rounded object-cover border border-border" />
          )}
        </div>

        <Button onClick={handleSaveImages} disabled={saving === "images" || loading} size="sm">
          {saving === "images" ? "保存中…" : "保存两张图片"}
        </Button>
      </section>

      {msg && <p className="text-sm">{msg}</p>}
    </div>
  )
}
