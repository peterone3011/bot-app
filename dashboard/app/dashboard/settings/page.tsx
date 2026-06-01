"use client"
import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Hash, Check, AlertCircle } from "lucide-react"

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
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState("")
  const [msgKind, setMsgKind] = useState<"ok" | "err">("ok")
  const msgTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

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
        showMsg("加载失败，请刷新页面重试", "err")
        setLoadError(true)
        setLoading(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function showMsg(text: string, kind: "ok" | "err" = "ok") {
    if (msgTimerRef.current) clearTimeout(msgTimerRef.current)
    setMsg(text); setMsgKind(kind)
    msgTimerRef.current = setTimeout(() => setMsg(""), 2500)
  }

  async function handleSaveRoles() {
    if (saving) return
    setMsg("")
    setSaving(true)
    const ok = await saveSetting("roles_channel_name", rolesChannel).catch(() => false)
    showMsg(ok ? "已保存" : "保存失败", ok ? "ok" : "err")
    setSaving(false)
  }

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Page head */}
      <div>
        <div className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
          <span>工作区</span>
          <span className="text-muted-foreground/40">/</span>
          <span className="text-foreground">全局设置</span>
        </div>
        <h1 className="mt-1.5 text-[22px] font-semibold tracking-tight">全局设置</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Bot 行为的全局开关。
        </p>
      </div>

      {/* Roles channel */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Hash className="h-4 w-4 text-brand-300" />
            身份组
          </CardTitle>
          <CardDescription>Bot 会在指定名称的频道里发布身份组选择消息。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="roles-channel">角色选择频道名称</Label>
            <Input
              id="roles-channel"
              value={rolesChannel}
              onChange={(e) => setRolesChannel(e.target.value)}
              placeholder="🔔roles"
              disabled={loading}
            />
            <p className="text-[11.5px] text-muted-foreground">
              不需要包含 <code className="font-mono">#</code> 号 · 必须与 Discord 频道名完全一致。
            </p>
          </div>
          <div className="flex justify-end pt-1">
            <Button onClick={handleSaveRoles} disabled={saving || loading || loadError} size="sm">
              {saving ? "保存中…" : "保存"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Toast / status line */}
      {msg && (
        <div
          className={`fixed bottom-6 left-1/2 -translate-x-1/2 z-50 inline-flex items-center gap-2 rounded-lg border px-3.5 py-2 text-[12.5px] shadow-lg animate-fade-in ${
            msgKind === "ok"
              ? "border-success/30 bg-success/10 text-success"
              : "border-destructive/30 bg-destructive/10 text-destructive"
          }`}
          role="status"
        >
          {msgKind === "ok" ? <Check className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
          <span>{msg}</span>
        </div>
      )}
    </div>
  )
}
