"use client"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export default function SettingsPage() {
  const [rolesChannel, setRolesChannel] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState("")

  useEffect(() => {
    fetch("/api/settings")
      .then((r) => {
        if (!r.ok) throw new Error("fetch failed")
        return r.json()
      })
      .then((data) => {
        setRolesChannel(data.roles_channel_name ?? "")
        setLoading(false)
      })
      .catch(() => {
        setMsg("加载失败，请刷新页面")
        setLoading(false)
      })
  }, [])

  async function handleSave() {
    setSaving(true)
    setMsg("")
    try {
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: "roles_channel_name", value: rolesChannel }),
      })
      setMsg(res.ok ? "已保存" : "保存失败")
      setTimeout(() => setMsg(""), 2000)
    } catch {
      setMsg("网络错误，请重试")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6 max-w-md">
      <h1 className="text-xl font-semibold">全局设置</h1>

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

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={saving || loading}>
          {saving ? "保存中…" : "保存"}
        </Button>
        {msg && <span className="text-sm">{msg}</span>}
      </div>
    </div>
  )
}
