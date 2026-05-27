import Link from "next/link"
import { supabase } from "@/lib/supabase"
import { type Message } from "@/lib/types"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Plus, FileText, Clock, Send, Hash, ChevronRight, Inbox } from "lucide-react"

export const dynamic = "force-dynamic"

type BadgeVariant = "default" | "secondary" | "outline"
function statusVariant(status: string): BadgeVariant {
  if (status === "published") return "default"
  if (status === "scheduled") return "secondary"
  return "outline"
}
function statusLabel(status: string) {
  if (status === "published") return "已发出"
  if (status === "scheduled") return "定时中"
  return "草稿"
}

function MessageRow({ msg }: { msg: Message }) {
  return (
    <Link
      href={`/dashboard/embeds/${msg.id}`}
      className="group flex items-center gap-4 rounded-lg border border-border bg-card px-4 py-3.5 transition-all hover:border-border/80 hover:bg-card/80 hover:shadow-[0_8px_24px_-16px_rgba(0,0,0,0.4)]"
    >
      {/* Color stripe (uses embed color when present) */}
      <div
        className="h-10 w-1 rounded-full shrink-0"
        style={{
          background:
            msg.color !== null && msg.color !== undefined
              ? `#${msg.color.toString(16).padStart(6, "0")}`
              : "hsl(var(--primary))",
        }}
        aria-hidden="true"
      />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 min-w-0">
          <p className="truncate text-sm font-medium text-foreground">
            {msg.label ?? msg.title ?? "(无标题)"}
          </p>
        </div>
        <div className="mt-1 flex items-center gap-x-3 gap-y-1 text-[11.5px] text-muted-foreground flex-wrap">
          <span className="inline-flex items-center gap-1">
            <Hash className="h-3 w-3" />
            <span className="font-mono">{msg.channel_id}</span>
          </span>
          {msg.send_at && (
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3 w-3" />
              <span>{msg.send_at.slice(0, 16).replace("T", " ")}</span>
            </span>
          )}
        </div>
      </div>

      <Badge variant={statusVariant(msg.status)} dot>
        {statusLabel(msg.status)}
      </Badge>
      <ChevronRight className="h-4 w-4 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-muted-foreground" />
    </Link>
  )
}

type EmptyKind = "draft" | "scheduled" | "published"
function EmptyState({ kind }: { kind: EmptyKind }) {
  const config = {
    draft:     { Icon: FileText, title: "暂无草稿",       copy: "开始撰写一条 Embed 消息,保存为草稿后可随时编辑或定时发送。" },
    scheduled: { Icon: Clock,    title: "暂无定时任务",   copy: "安排一条 Embed 在未来的某个时间自动发送 — 适合公告、活动开始与定期提醒。" },
    published: { Icon: Send,     title: "尚未发送过消息", copy: "首次发送 Embed 后,这里会显示历史记录与发送结果。" },
  }[kind]
  const Icon = config.Icon

  return (
    <div
      className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-card/40 px-6 py-14 text-center"
      style={{
        backgroundImage:
          "radial-gradient(500px 180px at 50% -20%, hsl(var(--primary)/0.06), transparent 70%)",
      }}
    >
      <div
        className="mb-4 grid h-14 w-14 place-items-center rounded-2xl border border-border bg-secondary text-brand-300"
        style={{ boxShadow: "0 0 0 1px hsl(var(--primary)/0.10), 0 8px 30px -10px hsl(var(--primary)/0.25)" }}
        aria-hidden="true"
      >
        <Icon className="h-5 w-5" />
      </div>
      <h3 className="mb-1.5 text-[15px] font-semibold tracking-tight">{config.title}</h3>
      <p className="max-w-[420px] text-[13px] leading-relaxed text-muted-foreground">
        {config.copy}
      </p>
      <Button asChild size="sm" className="mt-5">
        <Link href="/dashboard/embeds/new">
          <Plus className="h-3.5 w-3.5" />
          新建消息
        </Link>
      </Button>
    </div>
  )
}

export default async function EmbedsPage() {
  const { data: messages } = await supabase
    .from("messages")
    .select("*")
    .order("created_at", { ascending: false })

  const all = (messages ?? []) as Message[]
  const drafts    = all.filter((m) => m.status === "draft")
  const scheduled = all.filter((m) => m.status === "scheduled")
  const published = all.filter((m) => m.status === "published")

  return (
    <div className="space-y-7">
      {/* Page head */}
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
            <span>工作区</span>
            <span className="text-muted-foreground/40">/</span>
            <span className="text-foreground">Embed 消息</span>
          </div>
          <h1 className="mt-1.5 text-[22px] font-semibold tracking-tight">Embed 消息</h1>
          <p className="mt-1 text-[13px] text-muted-foreground">
            在 Discord 频道中创建、定时与发送 Embed 富文本消息。
          </p>
        </div>
        <Button asChild>
          <Link href="/dashboard/embeds/new">
            <Plus className="h-3.5 w-3.5" />
            新建消息
          </Link>
        </Button>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="draft">
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="draft">
              <Inbox className="h-3.5 w-3.5" />
              <span>草稿</span>
              <span className="count">{drafts.length}</span>
            </TabsTrigger>
            <TabsTrigger value="scheduled">
              <Clock className="h-3.5 w-3.5" />
              <span>定时中</span>
              <span className="count">{scheduled.length}</span>
            </TabsTrigger>
            <TabsTrigger value="published">
              <Send className="h-3.5 w-3.5" />
              <span>已发出</span>
              <span className="count">{published.length}</span>
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="draft">
          {drafts.length === 0 ? (
            <EmptyState kind="draft" />
          ) : (
            <div className="space-y-2">{drafts.map((m) => <MessageRow key={m.id} msg={m} />)}</div>
          )}
        </TabsContent>
        <TabsContent value="scheduled">
          {scheduled.length === 0 ? (
            <EmptyState kind="scheduled" />
          ) : (
            <div className="space-y-2">{scheduled.map((m) => <MessageRow key={m.id} msg={m} />)}</div>
          )}
        </TabsContent>
        <TabsContent value="published">
          {published.length === 0 ? (
            <EmptyState kind="published" />
          ) : (
            <div className="space-y-2">{published.map((m) => <MessageRow key={m.id} msg={m} />)}</div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
