import { NextRequest, NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { supabase } from "@/lib/supabase"
import { rateLimitCheck } from "@/lib/rate-limit"
import type { Message } from "@/lib/types"

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const limited = await rateLimitCheck(req)
  if (limited) return limited

  const session = await auth()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  const botToken = process.env.DISCORD_BOT_TOKEN
  if (!botToken) return NextResponse.json({ error: "Bot token not configured" }, { status: 503 })

  const { data, error } = await supabase
    .from("messages")
    .select("*")
    .eq("id", params.id)
    .single()

  if (error || !data) return NextResponse.json({ error: "Not found" }, { status: 404 })

  const msg = data as Message

  // channel_id / message_id 是 Discord 64 位 snowflake，JS JSON 解析会丢精度，
  // 通过 Supabase REST API 用 ::text 强制以字符串读取
  let channelId = msg.channel_id
  let messageId: string | null = msg.message_id != null ? String(msg.message_id) : null

  const idsRes = await fetch(
    `${process.env.SUPABASE_URL}/rest/v1/messages?id=eq.${params.id}&select=channel_id::text,message_id::text`,
    {
      headers: {
        Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
        apikey: process.env.SUPABASE_SERVICE_KEY!,
      },
    }
  )
  if (idsRes.ok) {
    const rows = await idsRes.json() as Array<{ channel_id: string; message_id: string | null }>
    // 只在行存在时更新，防止极端情况下空数组把已初始化的 messageId 清掉
    if (rows[0]) {
      if (rows[0].channel_id) channelId = rows[0].channel_id
      messageId = rows[0].message_id ?? null
    }
  }

  if (!msg.title && !msg.description) {
    return NextResponse.json({ error: "Embed 至少需要填写标题或正文才能发布" }, { status: 400 })
  }

  const embed: Record<string, unknown> = {}
  if (msg.title) embed.title = msg.title
  if (msg.description) embed.description = msg.description
  if (msg.footer) embed.footer = { text: msg.footer }
  if (msg.image_url) embed.image = { url: msg.image_url }
  if (msg.color !== null && msg.color !== undefined) embed.color = Number(msg.color)

  const body: Record<string, unknown> = { embeds: [embed] }

  if (msg.button_label && msg.button_url) {
    body.components = [
      {
        type: 1,
        components: [
          { type: 2, style: 5, label: msg.button_label, url: msg.button_url },
        ],
      },
    ]
  }

  let discordRes: Response
  try {
    if (messageId) {
      // 已有原帖 → PATCH 编辑，不新建
      discordRes = await fetch(
        `https://discord.com/api/v10/channels/${channelId}/messages/${messageId}`,
        {
          method: "PATCH",
          headers: {
            Authorization: `Bot ${botToken}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(body),
        }
      )
    } else {
      // 首次发布 → POST 新建
      discordRes = await fetch(
        `https://discord.com/api/v10/channels/${channelId}/messages`,
        {
          method: "POST",
          headers: {
            Authorization: `Bot ${botToken}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(body),
        }
      )
    }
  } catch {
    return NextResponse.json({ error: "Discord API unreachable" }, { status: 502 })
  }

  if (!discordRes.ok) {
    // 原帖已被删除 → 清除 DB 里的 message_id，返回 409 告知前端重试（会走 POST 新建）
    if (messageId && discordRes.status === 404) {
      await supabase.from("messages").update({ message_id: null }).eq("id", params.id)
      return NextResponse.json({ error: "原帖已被删除，请再次点击发布" }, { status: 409 })
    }
    const detail = await discordRes.text()
    return NextResponse.json({ error: "Discord API error", detail }, { status: 502 })
  }

  // 新建时才需要从响应里拿 message_id；编辑时 message_id 不变
  const dbUpdate: Record<string, unknown> = { status: "published", send_at: null }
  if (!messageId) {
    const discordMsg = await discordRes.json()
    dbUpdate.message_id = discordMsg.id
  }

  const { error: updateError } = await supabase
    .from("messages")
    .update(dbUpdate)
    .eq("id", params.id)

  if (updateError) return NextResponse.json({ error: updateError.message }, { status: 500 })

  return NextResponse.json({ ok: true })
}
