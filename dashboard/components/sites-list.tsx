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

function SortableItem({
  site,
  onDelete,
  onRename,
}: {
  site: Site
  onDelete: (id: string) => void
  onRename: (id: string, name: string) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: site.id })
  const style = { transform: CSS.Transform.toString(transform), transition }
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(site.name)

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 mb-2"
    >
      <span {...attributes} {...listeners} className="cursor-grab text-muted-foreground select-none pr-1">⠿</span>
      {editing ? (
        <>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-7 text-sm flex-1"
            onKeyDown={(e) => {
              if (e.key === "Enter") { onRename(site.id, name); setEditing(false) }
              if (e.key === "Escape") { setName(site.name); setEditing(false) }
            }}
            autoFocus
          />
          <Button size="sm" variant="ghost" onClick={() => { onRename(site.id, name); setEditing(false) }}>保存</Button>
        </>
      ) : (
        <>
          <span className="flex-1 text-sm">{site.name}</span>
          <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>改名</Button>
          <Button size="sm" variant="ghost" className="text-destructive" onClick={() => onDelete(site.id)}>删除</Button>
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

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  )

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
      setMsg("排序保存失败，已还原")
      setTimeout(() => setMsg(""), 3000)
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
        setMsg("已添加")
        setTimeout(() => setMsg(""), 2000)
      } else {
        const data = await res.json()
        setMsg(`错误：${data.error ?? "添加失败"}`)
      }
    } catch {
      setMsg("网络错误，请重试")
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("确定删除这个站点？Bot 身份组不会被删除，仅从列表中移除。")) return
    try {
      const res = await fetch(`/api/sites/${id}`, { method: "DELETE" })
      if (res.ok) {
        setSites((prev) => prev.filter((s) => s.id !== id))
      } else {
        setMsg("删除失败，请重试")
      }
    } catch {
      setMsg("网络错误，请重试")
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
        setMsg("重命名失败，请重试")
      }
    } catch {
      setMsg("网络错误，请重试")
    }
  }

  return (
    <div className="space-y-4 max-w-md">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={sites.map((s) => s.id)} strategy={verticalListSortingStrategy}>
          {sites.map((site) => (
            <SortableItem key={site.id} site={site} onDelete={handleDelete} onRename={handleRename} />
          ))}
        </SortableContext>
      </DndContext>

      {sites.length === 0 && (
        <p className="text-sm text-muted-foreground">暂无站点，请添加。</p>
      )}

      <div className="flex gap-2 items-center pt-2">
        <Input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="站点名称（对应 Discord 身份组名）"
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          className="flex-1"
        />
        <Button onClick={handleAdd} disabled={saving || !newName.trim()}>添加</Button>
      </div>
      {msg && <p className="text-sm">{msg}</p>}
    </div>
  )
}
