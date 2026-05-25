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

  // channel_id may lose bigint precision via JSON — re-fetch as text to get exact value
  const chanRes = await fetch(
    `${process.env.SUPABASE_URL}/rest/v1/messages?id=eq.${params.id}&select=channel_id::text`,
    {
      headers: {
        Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
        apikey: process.env.SUPABASE_SERVICE_KEY!,
      },
    }
  )
  if (chanRes.ok) {
    const rows = await chanRes.json() as Array<{ channel_id: string }>
    if (rows[0]?.channel_id) msg.channel_id = rows[0].channel_id
  }

  if (!msg.title && !msg.description) {
    return NextResponse.json({ error: "Embed 至少需要填写标题或正文才能发布" }, { status: 400 })
  }

  const embed: Record<string, unknown> = {}
  if (msg.title) embed.title = msg.title
  if (msg.description) embed.description = msg.description
  if (msg.footer) embed.footer = { text: msg.footer }
  if (msg.image_url) embed.image = { url: msg.image_url }
  if (msg.color !== null) embed.color = msg.color

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
    discordRes = await fetch(
      `https://discord.com/api/v10/channels/${msg.channel_id}/messages`,
      {
        method: "POST",
        headers: {
          Authorization: `Bot ${botToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      }
    )
  } catch {
    return NextResponse.json({ error: "Discord API unreachable" }, { status: 502 })
  }

  if (!discordRes.ok) {
    const detail = await discordRes.text()
    return NextResponse.json({ error: "Discord API error", detail }, { status: 502 })
  }

  const discordMsg = await discordRes.json()

  const { error: updateError } = await supabase
    .from("messages")
    .update({ status: "published", message_id: discordMsg.id, send_at: null })
    .eq("id", params.id)

  if (updateError) return NextResponse.json({ error: updateError.message }, { status: 500 })

  return NextResponse.json({ ok: true })
}
