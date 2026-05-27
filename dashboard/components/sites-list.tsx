"use client"
import { useState } from "react"
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core"
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import type { Site } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { GripVertical, Pencil, Trash2, Check, X, Globe, Plus } from "lucide-react"

function SortableItem({
  site,
  onDelete,
  onRename,
}: {
  site: Site
  onDelete: (id: string) => void
  onRename: (id: string, name: string) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: site.id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 50 : "auto" as const,
  }
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(site.name)

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`group flex items-center gap-2 rounded-md border bg-card px-2 py-2 transition-colors ${
        isDragging
          ? "border-primary/40 shadow-[0_12px_30px_-10px_hsl(var(--primary)/0.5)]"
          : "border-border hover:border-border/80"
      }`}
    >
      <button
        type="button"
        {...attributes}
        {...listeners}
        className="cursor-grab active:cursor-grabbing rounded p-1 text-muted-foreground/60 hover:text-foreground hover:bg-accent/40 touch-none"
        title="拖动排序"
        aria-label="拖动排序"
      >
        <GripVertical className="h-4 w-4" />
      </button>

      <div className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-primary/12 text-brand-300">
        <Globe className="h-3.5 w-3.5" />
      </div>

      {editing ? (
        <>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-8 text-sm flex-1"
            onKeyDown={(e) => {
              if (e.key === "Enter") { onRename(site.id, name); setEditing(false) }
              if (e.key === "Escape") { setName(site.name); setEditing(false) }
            }}
            autoFocus
          />
          <Button size="sm" variant="ghost" onClick={() => { onRename(site.id, name); setEditing(false) }} title="保存">
            <Check className="h-3.5 w-3.5" />
          </Button>
          <Button size="sm" variant="ghost" onClick={() => { setName(site.name); setEditing(false) }} title="取消">
            <X className="h-3.5 w-3.5" />
          </Button>
        </>
      ) : (
        <>
          <span className="flex-1 text-sm font-medium truncate">{site.name}</span>
          <Button
            size="sm"
            variant="ghost"
            className="opacity-60 group-hover:opacity-100 transition-opacity"
            onClick={() => setEditing(true)}
            title="改名"
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="opacity-60 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive hover:bg-destructive/10"
            onClick={() => onDelete(site.id)}
            title="删除"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </>
      )}
    </div>
  )
}

export function SitesList({ initialSites }: { initialSites: Site[] }) {
  const [sites, setSites] = useState(initialSites)
  const [newName, setNewName] = useState("")
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState("")
  const [msgKind, setMsgKind] = useState<"info" | "error">("info")

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  )

  function flash(text: string, kind: "info" | "error" = "info", ms = 2500) {
    setMsg(text); setMsgKind(kind)
    setTimeout(() => setMsg(""), ms)
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = sites.findIndex((s) => s.id === active.id)
    const newIndex = sites.findIndex((s) => s.id === over.id)
    const prevSites = sites
    const reordered = arrayMove(sites, oldIndex, newIndex)
    setSites(reordered)
    fetch("/api/sites", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reordered.map((site, index) => ({ id: site.id, display_order: index }))),
    }).then((res) => {
      if (!res.ok) throw new Error("reorder failed")
    }).catch(() => {
      setSites(prevSites)
      flash("排序保存失败,已还原", "error", 3000)
    })
  }

  async function handleAdd() {
    if (!newName.trim()) return
    setSaving(true)
    try {
      const res = await fetch("/api/sites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName.trim() }),
      })
      if (res.ok) {
        const site = await res.json()
        setSites((prev) => [...prev, site])
        setNewName("")
        flash("已添加", "info", 2000)
      } else {
        const data = await res.json()
        flash(`错误:${data.error ?? "添加失败"}`, "error")
      }
    } catch {
      flash("网络错误,请重试", "error")
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("确定删除这个站点?Bot 身份组不会被删除,仅从列表中移除。")) return
    try {
      const res = await fetch(`/api/sites/${id}`, { method: "DELETE" })
      if (res.ok) {
        setSites((prev) => prev.filter((s) => s.id !== id))
      } else {
        flash("删除失败,请重试", "error")
      }
    } catch {
      flash("网络错误,请重试", "error")
    }
  }

  async function handleRename(id: string, name: string) {
    try {
      const res = await fetch(`/api/sites/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      })
      if (res.ok) {
        setSites((prev) => prev.map((s) => s.id === id ? { ...s, name } : s))
      } else {
        flash("重命名失败,请重试", "error")
      }
    } catch {
      flash("网络错误,请重试", "error")
    }
  }

  return (
    <div className="space-y-4">
      {sites.length === 0 ? (
        <div className="rounded-md border border-dashed border-border bg-card/40 px-6 py-10 text-center">
          <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-xl border border-border bg-secondary text-brand-300">
            <Globe className="h-4 w-4" />
          </div>
          <p className="text-sm font-medium text-foreground">还没有站点</p>
          <p className="mt-1 text-[12.5px] text-muted-foreground">在下方添加你的第一个站点。</p>
        </div>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={sites.map((s) => s.id)} strategy={verticalListSortingStrategy}>
            <div className="space-y-2">
              {sites.map((site) => (
                <SortableItem key={site.id} site={site} onDelete={handleDelete} onRename={handleRename} />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      {/* Add row */}
      <div className="rounded-md border border-border bg-secondary/40 p-3">
        <p className="mb-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">
          添加站点
        </p>
        <div className="flex gap-2">
          <Input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="站点名称(对应 Discord 身份组名)"
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            className="flex-1"
          />
          <Button onClick={handleAdd} disabled={saving || !newName.trim()}>
            <Plus className="h-3.5 w-3.5" />
            {saving ? "添加中…" : "添加"}
          </Button>
        </div>
      </div>

      {msg && (
        <p className={`text-[12.5px] ${msgKind === "error" ? "text-destructive" : "text-muted-foreground"}`}>
          {msg}
        </p>
      )}
    </div>
  )
}
