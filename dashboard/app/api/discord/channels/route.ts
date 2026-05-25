import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"

const DISCORD_API = "https://discord.com/api/v10"

// Text channel types: 0 = GUILD_TEXT, 5 = GUILD_ANNOUNCEMENT
const TEXT_TYPES = new Set([0, 5])

export async function GET() {
  const session = await auth()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  const guildId = process.env.DISCORD_GUILD_ID
  const botToken = process.env.DISCORD_BOT_TOKEN

  if (!guildId || !botToken || guildId === "placeholder" || botToken === "placeholder") {
    return NextResponse.json({ error: "Discord not configured" }, { status: 503 })
  }

  let res: Response
  try {
    res = await fetch(`${DISCORD_API}/guilds/${guildId}/channels`, {
      headers: { Authorization: `Bot ${botToken}` },
    })
  } catch {
    return NextResponse.json({ error: "Discord API unreachable" }, { status: 502 })
  }

  if (!res.ok) {
    const body = await res.text()
    console.error("Discord API error", res.status, body)
    return NextResponse.json({ error: "Discord API error", detail: body }, { status: 502 })
  }

  const all = await res.json()

  // Build category name map for grouping labels
  const categoryNames: Record<string, string> = {}
  for (const c of all) {
    if (c.type === 4) categoryNames[c.id] = c.name
  }

  const channels = all
    .filter((c: { type: number }) => TEXT_TYPES.has(c.type))
    .sort((a: { position: number }, b: { position: number }) => a.position - b.position)
    .map((c: { id: string; name: string; parent_id: string | null }) => ({
      id: c.id,
      name: c.name,
      category: c.parent_id ? (categoryNames[c.parent_id] ?? null) : null,
    }))

  return NextResponse.json(channels)
}
