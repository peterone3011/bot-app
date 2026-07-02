# Roles Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded bot roles and unused dashboard pages (站点管理, 全局设置) with a DB-driven roles table managed via a new 身份组管理 dashboard page.

**Architecture:** A new `roles` Supabase table drives both the dashboard CRUD UI and the bot's Discord role-selector embed. The dashboard exposes REST endpoints (`/api/roles`, `/api/roles/[id]`) consumed by a drag-drop `RolesList` client component. The bot's `RolesCog` queries the DB fresh on every `_post_role_embeds()` call (fires on `on_ready` and `cog_load`).

**Tech Stack:** Next.js 14 App Router, TypeScript, @upstash/redis (unchanged), @supabase/supabase-js v2, @dnd-kit/core, discord.py, Supabase Management API (for DB migration), vitest + @testing-library/react

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `app/api/roles/route.ts` | GET list, POST add, PUT reorder |
| Create | `app/api/roles/[id]/route.ts` | PUT edit (label+description), DELETE (with last-role guard) |
| Create | `app/dashboard/roles/page.tsx` | 身份组管理 server page |
| Create | `components/roles-list.tsx` | Drag-drop role list, inline label+description editing |
| Create | `__tests__/roles-list.test.tsx` | Component tests |
| Modify | `lib/types.ts` | Add `Role`, remove `Site` and `Config` |
| Modify | `components/sidebar.tsx` | `/dashboard/roles` replaces `/dashboard/sites`; remove settings |
| Modify | `cogs/db.py` | Add `load_roles()` / `aload_roles()`, remove `load_sites()` |
| Modify | `cogs/roles.py` | Dynamic options from DB, hardcode channel name |
| Delete | `app/api/sites/route.ts` | — |
| Delete | `app/api/sites/[id]/route.ts` | — |
| Delete | `app/api/settings/route.ts` | — |
| Delete | `app/dashboard/sites/page.tsx` | — |
| Delete | `app/dashboard/settings/page.tsx` | — |
| Delete | `components/sites-list.tsx` | — |
| Delete | `__tests__/settings-page.test.tsx` | — |
| Delete | `__tests__/sites-list-rename.test.tsx` | — |

---

## Task 1: Phase 1 DB Migration

**Files:**
- Create (then delete): `dashboard/migrate-phase1.mjs` (temporary migration script)

Shell escaping for emoji and quotes in curl is error-prone — use a Node.js script instead.

- [ ] **Step 1: Write the migration script**

Create `dashboard/migrate-phase1.mjs`:

```javascript
const API = "https://api.supabase.com/v1/projects/aojqdfhevisgcvfuurvl/database/query"
const TOKEN = process.env.SUPABASE_MANAGEMENT_TOKEN

async function run(sql) {
  const res = await fetch(API, {
    method: "POST",
    headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ query: sql }),
  })
  const json = await res.json()
  if (json.error || (Array.isArray(json) && json[0]?.error)) {
    console.error("FAILED:", JSON.stringify(json, null, 2))
    process.exit(1)
  }
  console.log("OK:", JSON.stringify(json))
}

await run(`
  CREATE TABLE roles (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    label         varchar(100) NOT NULL,
    description   text NOT NULL DEFAULT '',
    display_order integer NOT NULL DEFAULT 0,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
  )
`)

await run(`
  CREATE OR REPLACE FUNCTION set_updated_at()
  RETURNS TRIGGER LANGUAGE plpgsql AS $$
  BEGIN NEW.updated_at = now(); RETURN NEW; END;
  $$
`)

await run(`
  CREATE TRIGGER roles_set_updated_at
    BEFORE UPDATE ON roles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at()
`)

await run(`
  INSERT INTO roles (label, description, display_order) VALUES
    ('📢 Exclusive Updates', 'Access our exclusive updates channel', 0),
    ('🎰Gaming Alerts',      'Get notified for jackpots and big wins',  1)
`)

await run(`ALTER TABLE roles ENABLE ROW LEVEL SECURITY`)

await run(`CREATE POLICY "deny anon" ON roles FOR ALL TO anon USING (false)`)

console.log("Migration complete.")
```

- [ ] **Step 2: Run the migration**

```bash
cd E:/company-ai/fpbot/dashboard && node migrate-phase1.mjs
```

Expected: six `OK:` lines, then `Migration complete.` — no `FAILED:` output.

- [ ] **Step 3: Verify seed data**

```bash
node -e "
const r = await fetch('https://api.supabase.com/v1/projects/aojqdfhevisgcvfuurvl/database/query', {
  method:'POST',
  headers:{'Authorization':'Bearer ' + process.env.SUPABASE_MANAGEMENT_TOKEN,'Content-Type':'application/json'},
  body: JSON.stringify({query:'SELECT label, display_order FROM roles ORDER BY display_order'})
})
console.log(JSON.stringify(await r.json(), null, 2))
"
```

Expected: two rows — `📢 Exclusive Updates` (order 0) and `🎰Gaming Alerts` (order 1).

- [ ] **Step 4: Delete the migration script**

```bash
rm migrate-phase1.mjs
```

- [ ] **Step 5: Commit milestone**

```bash
git commit --allow-empty -m "chore: phase 1 DB migration complete — roles table created"
```

---

## Task 2: Update TypeScript Types

**Files:**
- Modify: `dashboard/lib/types.ts`

- [ ] **Step 1: Replace Site and Config interfaces with Role**

Open `lib/types.ts`. Replace the `Site` and `Config` interfaces:

```typescript
// Remove these:
// export interface Site { ... }
// export interface Config { ... }

// Add this:
export interface Role {
  id: string
  label: string
  description: string
  display_order: number
  created_at: string
  updated_at: string
}
```

The full file after edit:

```typescript
export interface Message {
  id: string
  status: "draft" | "scheduled" | "published"
  label: string | null
  created_at: string
  channel_id: string
  send_at: string | null
  message_id: number | null
  title: string | null
  description: string | null
  footer: string | null
  image_url: string | null
  button_label: string | null
  button_url: string | null
  color: number | null
}

export interface Role {
  id: string
  label: string
  description: string
  display_order: number
  created_at: string
  updated_at: string
}
```

- [ ] **Step 2: Commit**

```bash
cd dashboard && git add lib/types.ts
git commit -m "refactor: replace Site/Config types with Role"
```

---

## Task 3: Create /api/roles Route

**Files:**
- Create: `dashboard/app/api/roles/route.ts`

- [ ] **Step 1: Create the file**

```typescript
import { NextRequest, NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { supabase } from "@/lib/supabase"
import { rateLimitCheck } from "@/lib/rate-limit"

export const dynamic = "force-dynamic"

const MAX_LABEL_LENGTH = 100

export async function GET(req: NextRequest) {
  const limited = await rateLimitCheck(req)
  if (limited) return limited

  const session = await auth()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  const { data, error } = await supabase
    .from("roles")
    .select("*")
    .order("display_order", { ascending: true })

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json(data)
}

export async function PUT(req: NextRequest) {
  const limited = await rateLimitCheck(req)
  if (limited) return limited

  const session = await auth()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 })
  }

  if (!Array.isArray(body) || body.length === 0) {
    return NextResponse.json(
      { error: "Body must be a non-empty array of {id, display_order}" },
      { status: 400 }
    )
  }

  for (const item of body as unknown[]) {
    if (
      typeof (item as Record<string, unknown>).id !== "string" ||
      typeof (item as Record<string, unknown>).display_order !== "number" ||
      !Number.isInteger((item as Record<string, unknown>).display_order)
    ) {
      return NextResponse.json(
        { error: "Each item must have id (string) and display_order (integer)" },
        { status: 400 }
      )
    }
  }

  const updates = (body as Array<{ id: string; display_order: number }>).map(
    ({ id, display_order }) => ({ id, display_order })
  )

  const { error } = await supabase.from("roles").upsert(updates, { onConflict: "id" })
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json({ ok: true })
}

export async function POST(req: NextRequest) {
  const limited = await rateLimitCheck(req)
  if (limited) return limited

  const session = await auth()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  let body: Record<string, unknown>
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 })
  }

  const { label, description } = body
  if (!label || typeof label !== "string" || label.trim().length === 0) {
    return NextResponse.json({ error: "label is required" }, { status: 400 })
  }
  if (label.trim().length > MAX_LABEL_LENGTH) {
    return NextResponse.json(
      { error: `label must be ${MAX_LABEL_LENGTH} characters or fewer` },
      { status: 400 }
    )
  }

  const { data: existing } = await supabase
    .from("roles")
    .select("display_order")
    .order("display_order", { ascending: false })
    .limit(1)

  const nextOrder = existing && existing.length > 0 ? existing[0].display_order + 1 : 0

  const role = {
    id: crypto.randomUUID(),
    label: label.trim(),
    description: typeof description === "string" ? description.trim() : "",
    display_order: nextOrder,
  }

  const { data, error } = await supabase.from("roles").insert(role).select().single()
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json(data, { status: 201 })
}
```

- [ ] **Step 2: Commit**

```bash
git add app/api/roles/route.ts
git commit -m "feat: add /api/roles GET, POST, PUT reorder"
```

---

## Task 4: Create /api/roles/[id] Route

**Files:**
- Create: `dashboard/app/api/roles/[id]/route.ts`

- [ ] **Step 1: Create the directory and file**

```typescript
import { NextRequest, NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { supabase } from "@/lib/supabase"
import { rateLimitCheck } from "@/lib/rate-limit"

const MAX_LABEL_LENGTH = 100

export async function PUT(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const limited = await rateLimitCheck(req)
  if (limited) return limited

  const session = await auth()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  let body: Record<string, unknown>
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 })
  }

  const updates: Record<string, unknown> = {}
  if (typeof body.label === "string") {
    const trimmed = body.label.trim()
    if (trimmed.length === 0)
      return NextResponse.json({ error: "label cannot be empty" }, { status: 400 })
    if (trimmed.length > MAX_LABEL_LENGTH)
      return NextResponse.json(
        { error: `label must be ${MAX_LABEL_LENGTH} characters or fewer` },
        { status: 400 }
      )
    updates.label = trimmed
  }
  if (typeof body.description === "string") updates.description = body.description.trim()
  if (
    typeof body.display_order === "number" &&
    Number.isInteger(body.display_order)
  ) {
    updates.display_order = body.display_order
  }

  if (Object.keys(updates).length === 0)
    return NextResponse.json({ error: "No valid fields to update" }, { status: 400 })

  const { data, error } = await supabase
    .from("roles")
    .update(updates)
    .eq("id", params.id)
    .select()
    .single()

  if (error) {
    if (error.code === "PGRST116")
      return NextResponse.json({ error: "Not found" }, { status: 404 })
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
  return NextResponse.json(data)
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const limited = await rateLimitCheck(req)
  if (limited) return limited

  const session = await auth()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  const { count, error: countError } = await supabase
    .from("roles")
    .select("*", { count: "exact", head: true })

  if (countError) return NextResponse.json({ error: countError.message }, { status: 500 })
  if (count !== null && count <= 1)
    return NextResponse.json({ error: "Cannot delete the last role" }, { status: 400 })

  const { error } = await supabase.from("roles").delete().eq("id", params.id)
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return new NextResponse(null, { status: 204 })
}
```

- [ ] **Step 2: Commit**

```bash
git add "app/api/roles/[id]/route.ts"
git commit -m "feat: add /api/roles/[id] PUT edit and DELETE with last-role guard"
```

---

## Task 5: Write Failing Tests for RolesList

**Files:**
- Create: `dashboard/__tests__/roles-list.test.tsx`

- [ ] **Step 1: Create the test file**

```typescript
// @vitest-environment jsdom

import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { describe, it, expect, vi, afterEach } from "vitest"
import { RolesList } from "@/components/roles-list"

const SAMPLE_ROLES = [
  {
    id: "r1",
    label: "📢 Exclusive Updates",
    description: "Access our updates",
    display_order: 0,
    created_at: "",
    updated_at: "",
  },
  {
    id: "r2",
    label: "🎰Gaming Alerts",
    description: "Gaming notifications",
    display_order: 1,
    created_at: "",
    updated_at: "",
  },
]
const SINGLE_ROLE = [SAMPLE_ROLES[0]]

describe("RolesList", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it("does not call the API when saving an empty label", async () => {
    const mockFetch = vi.fn()
    vi.stubGlobal("fetch", mockFetch)

    render(<RolesList initialRoles={SAMPLE_ROLES} />)
    fireEvent.click(screen.getAllByTitle("编辑")[0])

    const labelInput = screen.getByDisplayValue("📢 Exclusive Updates")
    fireEvent.change(labelInput, { target: { value: "" } })
    fireEvent.click(screen.getByTitle("保存"))

    await waitFor(() => expect(mockFetch).not.toHaveBeenCalled())
  })

  it("does not call the API when label exceeds 100 characters", async () => {
    const mockFetch = vi.fn()
    vi.stubGlobal("fetch", mockFetch)

    render(<RolesList initialRoles={SAMPLE_ROLES} />)
    fireEvent.click(screen.getAllByTitle("编辑")[0])

    const labelInput = screen.getByDisplayValue("📢 Exclusive Updates")
    fireEvent.change(labelInput, { target: { value: "a".repeat(101) } })
    fireEvent.click(screen.getByTitle("保存"))

    await waitFor(() => expect(mockFetch).not.toHaveBeenCalled())
  })

  it("shows an error message when label exceeds 100 characters", async () => {
    vi.stubGlobal("fetch", vi.fn())

    render(<RolesList initialRoles={SAMPLE_ROLES} />)
    fireEvent.click(screen.getAllByTitle("编辑")[0])

    const labelInput = screen.getByDisplayValue("📢 Exclusive Updates")
    fireEvent.change(labelInput, { target: { value: "a".repeat(101) } })
    fireEvent.click(screen.getByTitle("保存"))

    await waitFor(() => expect(screen.getByText(/最多 100 个字符/)).toBeInTheDocument())
  })

  it("calls PUT with both label and description on save", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal("fetch", mockFetch)

    render(<RolesList initialRoles={SAMPLE_ROLES} />)
    fireEvent.click(screen.getAllByTitle("编辑")[0])

    const descInput = screen.getByDisplayValue("Access our updates")
    fireEvent.change(descInput, { target: { value: "New description" } })
    fireEvent.click(screen.getByTitle("保存"))

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/roles/r1",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({
            label: "📢 Exclusive Updates",
            description: "New description",
          }),
        })
      )
    )
  })

  it("disables the delete button when only one role remains", () => {
    vi.stubGlobal("fetch", vi.fn())
    render(<RolesList initialRoles={SINGLE_ROLE} />)
    expect(screen.getByTitle("删除")).toBeDisabled()
  })

  it("enables the delete button when more than one role exists", () => {
    vi.stubGlobal("fetch", vi.fn())
    render(<RolesList initialRoles={SAMPLE_ROLES} />)
    screen.getAllByTitle("删除").forEach((btn) => expect(btn).not.toBeDisabled())
  })

  it("does not add a role when label exceeds 100 characters", async () => {
    const mockFetch = vi.fn()
    vi.stubGlobal("fetch", mockFetch)

    render(<RolesList initialRoles={SAMPLE_ROLES} />)
    const addInput = screen.getByPlaceholderText(/身份组名称/)
    fireEvent.change(addInput, { target: { value: "a".repeat(101) } })
    fireEvent.click(screen.getByRole("button", { name: /添加/ }))

    await waitFor(() => expect(mockFetch).not.toHaveBeenCalled())
    expect(screen.getByText(/最多 100 个字符/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests — expect all to FAIL (component not yet created)**

```bash
cd E:/company-ai/fpbot/dashboard && npx vitest run __tests__/roles-list.test.tsx
```

Expected: all 7 tests fail with "Cannot find module '@/components/roles-list'".

---

## Task 6: Create RolesList Component

**Files:**
- Create: `dashboard/components/roles-list.tsx`

- [ ] **Step 1: Create the component**

```typescript
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
  onEdit: (id: string, label: string, description: string) => void
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

  function handleSave() {
    if (!label.trim()) return
    if (label.trim().length > MAX_LABEL) {
      setLabelError(`最多 ${MAX_LABEL} 个字符`)
      return
    }
    setLabelError("")
    onEdit(role.id, label.trim(), description.trim())
    setEditing(false)
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
            <Button size="sm" variant="ghost" onClick={handleSave} title="保存">
              <Check className="h-3.5 w-3.5" />
            </Button>
            <Button size="sm" variant="ghost" onClick={handleCancel} title="取消">
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
            >
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="opacity-60 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive hover:bg-destructive/10"
              onClick={() => onDelete(role.id)}
              title="删除"
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

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  )

  function flash(text: string, kind: "info" | "error" = "info", ms = 2500) {
    setMsg(text)
    setMsgKind(kind)
    setTimeout(() => setMsg(""), ms)
  }

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

  async function handleEdit(id: string, label: string, description: string) {
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
      } else {
        flash("保存失败，请重试", "error")
      }
    } catch {
      flash("网络错误，请重试", "error")
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
```

- [ ] **Step 2: Run tests — all must pass**

```bash
npx vitest run __tests__/roles-list.test.tsx
```

Expected: `7 passed`.

- [ ] **Step 3: Commit**

```bash
git add components/roles-list.tsx __tests__/roles-list.test.tsx
git commit -m "feat: add RolesList component with label/description editing and last-role guard"
```

---

## Task 7: Create Roles Dashboard Page

**Files:**
- Create: `dashboard/app/dashboard/roles/page.tsx`

- [ ] **Step 1: Create the page**

```typescript
import { supabase } from "@/lib/supabase"
import type { Role } from "@/lib/types"
import { RolesList } from "@/components/roles-list"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card"
import { GripVertical } from "lucide-react"

export const dynamic = "force-dynamic"

export default async function RolesPage() {
  const { data } = await supabase
    .from("roles")
    .select("*")
    .order("display_order", { ascending: true })

  const roles = (data ?? []) as Role[]

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <div className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
          <span>工作区</span>
          <span className="text-muted-foreground/40">/</span>
          <span className="text-foreground">身份组管理</span>
        </div>
        <h1 className="mt-1.5 text-[22px] font-semibold tracking-tight">
          身份组管理
        </h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          维护 Bot 身份组选择器中展示的角色列表与排序。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>身份组列表</CardTitle>
          <CardDescription className="flex items-center gap-1.5">
            <GripVertical className="h-3.5 w-3.5" />
            拖动左侧手柄可排序 · Bot 选择器会按此顺序展示
          </CardDescription>
        </CardHeader>
        <CardContent>
          <RolesList initialRoles={roles} />
        </CardContent>
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add app/dashboard/roles/page.tsx
git commit -m "feat: add /dashboard/roles page"
```

---

## Task 8: Update Sidebar

**Files:**
- Modify: `dashboard/components/sidebar.tsx`

- [ ] **Step 1: Replace nav items**

In `components/sidebar.tsx`, change the `navItems` array and imports:

Replace the import line:
```typescript
// OLD:
import {
  PanelLeftClose, PanelLeftOpen, MessageSquare,
  Globe, Settings, LogOut, Trophy,
} from "lucide-react"

// NEW:
import {
  PanelLeftClose, PanelLeftOpen, MessageSquare,
  Users, LogOut, Trophy,
} from "lucide-react"
```

Replace the `navItems` array:
```typescript
// OLD:
const navItems = [
  { href: "/dashboard/embeds",   label: "Embed 消息",   icon: MessageSquare, short: "E" },
  { href: "/dashboard/sites",    label: "站点管理",      icon: Globe,         short: "S" },
  { href: "/dashboard/settings", label: "全局设置",      icon: Settings,      short: "C" },
  { href: "/dashboard/bigwin",   label: "Big Win 记录", icon: Trophy,        short: "B" },
]

// NEW:
const navItems = [
  { href: "/dashboard/embeds", label: "Embed 消息",   icon: MessageSquare, short: "E" },
  { href: "/dashboard/roles",  label: "身份组管理",    icon: Users,         short: "R" },
  { href: "/dashboard/bigwin", label: "Big Win 记录", icon: Trophy,        short: "B" },
]
```

- [ ] **Step 2: Run full test suite to confirm no regressions**

```bash
npx vitest run
```

Expected: all existing tests pass (settings-page and sites-list tests will be deleted in Task 9, so ignore any failures from those two files for now).

- [ ] **Step 3: Commit**

```bash
git add components/sidebar.tsx
git commit -m "feat: update sidebar — add roles nav, remove sites and settings"
```

---

## Task 9: Delete Old Files

**Files:** all deletions

- [ ] **Step 1: Delete old dashboard files**

```bash
cd E:/company-ai/fpbot/dashboard
rm app/api/sites/route.ts
rm "app/api/sites/[id]/route.ts"
rmdir app/api/sites
rm app/api/settings/route.ts
rmdir app/api/settings
rm app/dashboard/sites/page.tsx
rmdir app/dashboard/sites
rm app/dashboard/settings/page.tsx
rmdir app/dashboard/settings
rm components/sites-list.tsx
rm __tests__/settings-page.test.tsx
rm __tests__/sites-list-rename.test.tsx
```

- [ ] **Step 2: Run full test suite — confirm clean**

```bash
npx vitest run
```

Expected: all tests pass, deleted test files are gone, no import errors.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove sites and settings pages, routes, and tests"
```

---

## Task 10: Update Bot — db.py

**Files:**
- Modify: `cogs/db.py`

- [ ] **Step 1: Replace load_sites with load_roles**

In `cogs/db.py`, replace the entire `# Sites` section:

```python
# Remove this block:
# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------

# def load_sites() -> list[str]:
#     rows = get_client().table("sites").select("name").order("display_order").execute().data
#     return [row["name"] for row in rows]
```

Add a new `# Roles` section after the `# Async wrappers` section:

```python
# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

def load_roles() -> list[dict]:
    rows = (
        get_client()
        .table("roles")
        .select("id, label, description, display_order")
        .order("display_order")
        .execute()
        .data
    )
    return rows


async def aload_roles() -> list[dict]:
    return await asyncio.to_thread(load_roles)
```

- [ ] **Step 2: Verify no remaining references to load_sites**

```bash
cd E:/company-ai/fpbot && grep -r "load_sites" --include="*.py"
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add cogs/db.py
git commit -m "feat: add load_roles/aload_roles to db.py, remove load_sites"
```

---

## Task 11: Update Bot — roles.py

**Files:**
- Modify: `cogs/roles.py`

- [ ] **Step 1: Rewrite roles.py**

Replace the entire file content:

```python
import discord
from discord.ext import commands

from cogs.db import aload_roles

EMBED_TITLE = "Select Your Notifications"
EMBED_DESCRIPTION = (
    "Subscribe to the channels you want to follow.\n"
    "Click once to **subscribe** — click again to **unsubscribe**."
)

CHANNEL_NAME = "🔔roles"


async def _build_options() -> list[discord.SelectOption]:
    roles = await aload_roles()
    return [
        discord.SelectOption(
            label=r["label"],
            value=r["label"],
            description=r.get("description", ""),
        )
        for r in roles
    ]


async def handle_role(interaction: discord.Interaction, selected: str) -> None:
    member = interaction.user
    guild = interaction.guild

    role = discord.utils.get(guild.roles, name=selected)
    if not role:
        await interaction.followup.send(
            content=f"⚠️ Role **{selected}** not found. Please contact an admin.",
            ephemeral=True,
        )
        return

    if role in member.roles:
        await member.remove_roles(role)
        await interaction.followup.send(
            content=f"✅ Unsubscribed from **{selected}**.", ephemeral=True
        )
    else:
        await member.add_roles(role)
        await interaction.followup.send(
            content=f"✅ Subscribed to **{selected}**!", ephemeral=True
        )


class SubscriptionSelect(discord.ui.Select):
    def __init__(self, options: list[discord.SelectOption]) -> None:
        super().__init__(
            placeholder="Subscribe / unsubscribe to notifications...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="subscription_role_select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await handle_role(interaction, self.values[0])
        try:
            opts = await _build_options()
            if opts:
                await interaction.message.edit(view=RoleView(opts))
        except Exception as e:
            print(f"[roles] Failed to refresh view after interaction: {e}", flush=True)


class RoleView(discord.ui.View):
    def __init__(self, options: list[discord.SelectOption]) -> None:
        super().__init__(timeout=None)
        self.add_item(SubscriptionSelect(options))


class RolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Register persistent view handler for interactions on existing Discord messages.
        # A single placeholder option is enough to register the custom_id;
        # real options are loaded from DB in _post_role_embeds().
        bot.add_view(RoleView([discord.SelectOption(label="loading", value="loading")]))

    def cog_unload(self) -> None:
        pass

    async def _post_role_embeds(self) -> None:
        try:
            opts = await _build_options()
        except Exception as e:
            print(f"[roles] Failed to load roles from DB: {e}", flush=True)
            return
        if not opts:
            print("[roles] No roles found in DB, skipping embed update", flush=True)
            return

        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)
            if not channel:
                continue
            existing: discord.Message | None = None
            async for msg in channel.history(limit=50):
                if msg.author == self.bot.user and msg.embeds:
                    existing = msg
                    break
            embed = discord.Embed(
                title=EMBED_TITLE,
                description=EMBED_DESCRIPTION,
                color=0x9B59B6,
            )
            try:
                if existing:
                    await existing.edit(embed=embed, view=RoleView(opts))
                else:
                    await channel.send(embed=embed, view=RoleView(opts))
            except Exception as e:
                print(f"[roles] Failed to post/update role embed: {e}", flush=True)

    async def cog_load(self) -> None:
        if self.bot.is_ready():
            await self._post_role_embeds()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self._post_role_embeds()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RolesCog(bot))
```

- [ ] **Step 2: Verify no remaining references to get_config or SUBSCRIPTION_ROLES**

```bash
grep -n "get_config\|SUBSCRIPTION_ROLES\|load_sites" cogs/roles.py
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add cogs/roles.py
git commit -m "feat: load roles dynamically from DB in RolesCog, hardcode channel name"
```

---

## Task 12: Push, Deploy, and Verify

- [ ] **Step 1: Push to GitHub**

```bash
git -c http.proxy=socks5://127.0.0.1:10808 push
```

- [ ] **Step 2: Deploy dashboard to Vercel production**

```bash
cd dashboard && npx vercel --prod
```

Expected: `▲ Aliased https://fortunepurplebot.vercel.app`, status READY.

- [ ] **Step 3: Smoke-check the dashboard**

Open `https://fortunepurplebot.vercel.app/dashboard/roles` in a browser.
Verify:
- Two roles are listed: `📢 Exclusive Updates` and `🎰Gaming Alerts`
- Sidebar shows 身份组管理, no 站点管理 or 全局设置
- Edit, description edit, add, and drag-drop work without errors

- [ ] **Step 4: Run code review**

```
/code-review
```

Fix any findings before proceeding to Phase 2.

---

## Task 13: Phase 2 DB Migration (after verification)

Only run this after Task 12 is confirmed working.

- [ ] **Step 1: Drop the sites table**

```bash
node -e "
const r = await fetch('https://api.supabase.com/v1/projects/aojqdfhevisgcvfuurvl/database/query', {
  method:'POST',
  headers:{'Authorization':'Bearer ' + process.env.SUPABASE_MANAGEMENT_TOKEN,'Content-Type':'application/json'},
  body: JSON.stringify({query:'DROP TABLE sites'})
})
console.log(JSON.stringify(await r.json()))
"
```

Expected: success response, no `error` key.

- [ ] **Step 2: Verify sites table is gone**

```bash
node -e "
const r = await fetch('https://api.supabase.com/v1/projects/aojqdfhevisgcvfuurvl/database/query', {
  method:'POST',
  headers:{'Authorization':'Bearer ' + process.env.SUPABASE_MANAGEMENT_TOKEN,'Content-Type':'application/json'},
  body: JSON.stringify({query:\"SELECT to_regclass('public.sites')\"})
})
console.log(JSON.stringify(await r.json()))
"
```

Expected: `[{"to_regclass":null}]`.

- [ ] **Step 3: Final commit**

```bash
git commit --allow-empty -m "chore: phase 2 DB migration complete — sites table dropped"
```
