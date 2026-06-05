"use client"
import { useState, useRef, useEffect } from "react"
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
import type { Role } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { GripVertical, Pencil, Trash2, Check, X, Users, Plus } from "lucide-react"

const MAX_LABEL = 100

function SortableItem({
  role,
  isOnly,
  onDelete,
  onEdit,
}: {
  role: Role
  isOnly: boolean
  onDelete: (id: string) => void
  onEdit: (id: string, label: string, description: string) => Promise<boolean>
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: role.id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 50 : ("auto" as const),
  }
  const [editing, setEditing] = useState(false)
  const [label, setLabel] = useState(role.label)
  const [description, setDescription] = useState(role.description)
  const [labelError, setLabelError] = useState("")

  async function handleSave() {
    if (!label.trim()) return
    if (label.trim().length > MAX_LABEL) {
      setLabelError(`最多 ${MAX_LABEL} 个字符`)
      return
    }
    setLabelError("")
    const ok = await onEdit(role.id, label.trim(), description.trim())
    if (ok) setEditing(false)
  }

  function handleCancel() {
    setLabel(role.label)
    setDescription(role.description)
    setLabelError("")
    setEditing(false)
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`group flex items-start gap-2 rounded-md border bg-card px-2 py-2 transition-colors ${
        isDragging
          ? "border-primary/40 shadow-[0_12px_30px_-10px_hsl(var(--primary)/0.5)]"
          : "border-border hover:border-border/80"
      }`}
    >
      <button
        type="button"
        {...attributes}
        {...listeners}
        className="mt-1 cursor-grab active:cursor-grabbing rounded p-1 text-muted-foreground/60 hover:text-foreground hover:bg-accent/40 touch-none"
        title="拖动排序"
        aria-label="拖动排序"
      >
        <GripVertical className="h-4 w-4" />
      </button>

      <div className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-md bg-primary/12 text-brand-300">
        <Users className="h-3.5 w-3.5" />
      </div>

      {editing ? (
        <>
          <div className="flex flex-col gap-1 flex-1 min-w-0">
            <div>
              <Input
                value={label}
                onChange={(e) => {
                  setLabel(e.target.value)
                  setLabelError("")
                }}
                className="h-8 text-sm"
                maxLength={MAX_LABEL + 1}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSave()
                  if (e.key === "Escape") handleCancel()
                }}
                autoFocus
              />
              {labelError && (
                <p className="text-[11px] text-destructive mt-0.5">{labelError}</p>
              )}
            </div>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="h-7 text-xs"
              placeholder="描述（可选）"
              onKeyDown={(e) => {
                if (e.key === "Escape") handleCancel()
              }}
            />
          </div>
          <div className="flex gap-1 mt-0.5">
            <Button size="sm" variant="ghost" onClick={handleSave} title="保存" aria-label="保存">
              <Check className="h-3.5 w-3.5" />
            </Button>
            <Button size="sm" variant="ghost" onClick={handleCancel} title="取消" aria-label="取消">
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </>
      ) : (
        <>
          <div className="flex flex-col min-w-0 flex-1">
            <span className="text-sm font-medium truncate">{role.label}</span>
            {role.description && (
              <span className="text-xs text-muted-foreground truncate">
                {role.description}
              </span>
            )}
          </div>
          <div className="flex gap-1 mt-0.5">
            <Button
              size="sm"
              variant="ghost"
              className="opacity-60 group-hover:opacity-100 transition-opacity"
              onClick={() => setEditing(true)}
              title="编辑"
              aria-label="编辑"
            >
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="opacity-60 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive hover:bg-destructive/10"
              onClick={() => onDelete(role.id)}
              title="删除"
              aria-label="删除"
              disabled={isOnly}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </>
      )}
    </div>
  )
}

export function RolesList({ initialRoles }: { initialRoles: Role[] }) {
  const [roles, setRoles] = useState(initialRoles)
  const [newLabel, setNewLabel] = useState("")
  const [newLabelError, setNewLabelError] = useState("")
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState("")
  const [msgKind, setMsgKind] = useState<"info" | "error">("info")
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  )

  function flash(text: string, kind: "info" | "error" = "info", ms = 2500) {
    if (flashTimer.current) clearTimeout(flashTimer.current)
    setMsg(text)
    setMsgKind(kind)
    flashTimer.current = setTimeout(() => setMsg(""), ms)
  }

  useEffect(() => () => { if (flashTimer.current) clearTimeout(flashTimer.current) }, [])

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = roles.findIndex((r) => r.id === active.id)
    const newIndex = roles.findIndex((r) => r.id === over.id)
    const prevRoles = roles
    const reordered = arrayMove(roles, oldIndex, newIndex)
    setRoles(reordered)
    fetch("/api/roles", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        reordered.map((role, index) => ({ id: role.id, display_order: index }))
      ),
    })
      .then((res) => {
        if (!res.ok) throw new Error("reorder failed")
      })
      .catch(() => {
        setRoles(prevRoles)
        flash("排序保存失败，已还原", "error", 3000)
      })
  }

  async function handleAdd() {
    if (saving) return
    if (!newLabel.trim()) return
    if (newLabel.trim().length > MAX_LABEL) {
      setNewLabelError(`最多 ${MAX_LABEL} 个字符`)
      return
    }
    setNewLabelError("")
    setSaving(true)
    try {
      const res = await fetch("/api/roles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: newLabel.trim() }),
      })
      if (res.ok) {
        const role = await res.json()
        setRoles((prev) => [...prev, role])
        setNewLabel("")
        flash("已添加", "info", 2000)
      } else {
        const data = await res.json()
        flash(`错误：${data.error ?? "添加失败"}`, "error")
      }
    } catch {
      flash("网络错误，请重试", "error")
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id: string) {
    if (
      !confirm(
        "确定删除这个身份组？Discord 中的身份组不会被删除，仅从列表中移除。"
      )
    )
      return
    try {
      const res = await fetch(`/api/roles/${id}`, { method: "DELETE" })
      if (res.ok) {
        setRoles((prev) => prev.filter((r) => r.id !== id))
      } else {
        flash("删除失败，请重试", "error")
      }
    } catch {
      flash("网络错误，请重试", "error")
    }
  }

  async function handleEdit(id: string, label: string, description: string): Promise<boolean> {
    try {
      const res = await fetch(`/api/roles/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label, description }),
      })
      if (res.ok) {
        setRoles((prev) =>
          prev.map((r) => (r.id === id ? { ...r, label, description } : r))
        )
        return true
      } else {
        flash("保存失败，请重试", "error")
        return false
      }
    } catch {
      flash("网络错误，请重试", "error")
      return false
    }
  }

  return (
    <div className="space-y-4">
      {roles.length === 0 ? (
        <div className="rounded-md border border-dashed border-border bg-card/40 px-6 py-10 text-center">
          <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-xl border border-border bg-secondary text-brand-300">
            <Users className="h-4 w-4" />
          </div>
          <p className="text-sm font-medium text-foreground">还没有身份组</p>
          <p className="mt-1 text-[12.5px] text-muted-foreground">
            在下方添加第一个身份组。
          </p>
        </div>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={roles.map((r) => r.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="space-y-2">
              {roles.map((role) => (
                <SortableItem
                  key={role.id}
                  role={role}
                  isOnly={roles.length === 1}
                  onDelete={handleDelete}
                  onEdit={handleEdit}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      <div className="rounded-md border border-border bg-secondary/40 p-3">
        <p className="mb-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">
          添加身份组
        </p>
        <div className="flex gap-2">
          <div className="flex-1">
            <Input
              value={newLabel}
              onChange={(e) => {
                setNewLabel(e.target.value)
                setNewLabelError("")
              }}
              placeholder="身份组名称（对应 Discord 身份组名，最多 100 字符）"
              onKeyDown={(e) => e.key === "Enter" && handleAdd()}
              maxLength={MAX_LABEL + 1}
            />
            {newLabelError && (
              <p className="text-[11px] text-destructive mt-0.5">{newLabelError}</p>
            )}
          </div>
          <Button onClick={handleAdd} disabled={saving || !newLabel.trim()}>
            <Plus className="h-3.5 w-3.5" />
            {saving ? "添加中…" : "添加"}
          </Button>
        </div>
      </div>

      {msg && (
        <p
          className={`text-[12.5px] ${
            msgKind === "error" ? "text-destructive" : "text-muted-foreground"
          }`}
        >
          {msg}
        </p>
      )}
    </div>
  )
}
