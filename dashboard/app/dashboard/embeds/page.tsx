import Link from "next/link"
import { supabase } from "@/lib/supabase"
import { type Message } from "@/lib/types"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

export const dynamic = "force-dynamic"

function statusColor(status: string): "default" | "secondary" | "outline" {
  if (status === "published") return "default"
  if (status === "scheduled") return "secondary"
  return "outline"
}

function statusLabel(status: string) {
  if (status === "published") return "已发出"
  if (status === "scheduled") return "定时中"
  return "草稿"
}

function MessageCard({ msg }: { msg: Message }) {
  return (
    <Link href={`/dashboard/embeds/${msg.id}`}>
      <Card className="mb-2 cursor-pointer transition-colors hover:bg-accent/50">
        <CardContent className="flex items-center justify-between py-3 px-4">
          <div className="space-y-0.5">
            <p className="text-sm font-medium">
              {msg.label ?? msg.title ?? "(无标题)"}
            </p>
            <p className="text-xs text-muted-foreground">
              频道 {msg.channel_id}
              {msg.send_at && ` · ${msg.send_at.slice(0, 16).replace("T", " ")}`}
            </p>
          </div>
          <Badge variant={statusColor(msg.status)}>{statusLabel(msg.status)}</Badge>
        </CardContent>
      </Card>
    </Link>
  )
}

export default async function EmbedsPage() {
  const { data: messages } = await supabase
    .from("messages")
    .select("*")
    .order("created_at", { ascending: false })

  const all = (messages ?? []) as Message[]
  const drafts = all.filter((m) => m.status === "draft")
  const scheduled = all.filter((m) => m.status === "scheduled")
  const published = all.filter((m) => m.status === "published")

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Embed 消息</h1>
        <Button asChild>
          <Link href="/dashboard/embeds/new">+ 新建消息</Link>
        </Button>
      </div>

      <Tabs defaultValue="draft">
        <TabsList>
          <TabsTrigger value="draft">草稿 ({drafts.length})</TabsTrigger>
          <TabsTrigger value="scheduled">定时中 ({scheduled.length})</TabsTrigger>
          <TabsTrigger value="published">已发出 ({published.length})</TabsTrigger>
        </TabsList>
        <TabsContent value="draft" className="mt-3">
          {drafts.length === 0 ? <p className="text-sm text-muted-foreground">暂无草稿</p> : drafts.map((m) => <MessageCard key={m.id} msg={m} />)}
        </TabsContent>
        <TabsContent value="scheduled" className="mt-3">
          {scheduled.length === 0 ? <p className="text-sm text-muted-foreground">暂无定时消息</p> : scheduled.map((m) => <MessageCard key={m.id} msg={m} />)}
        </TabsContent>
        <TabsContent value="published" className="mt-3">
          {published.length === 0 ? <p className="text-sm text-muted-foreground">暂无已发出消息</p> : published.map((m) => <MessageCard key={m.id} msg={m} />)}
        </TabsContent>
      </Tabs>
    </div>
  )
}
