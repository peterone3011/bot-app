import { NextRequest, NextResponse } from "next/server"
import { Redis } from "@upstash/redis"

const COOLDOWN_KEY = "bigwin:cooldown"
const COOLDOWN_SECONDS = 14400 // 4 hours

export async function POST(req: NextRequest) {
  // 1. Auth
  const apiKey = process.env.BROADCAST_API_KEY
  const authHeader = req.headers.get("authorization")
  if (!apiKey || !authHeader || authHeader !== `Bearer ${apiKey}`) {
    console.warn("[bigwin] Unauthorized request")
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  // 2. Parse and validate body
  let amount: string, game: string
  try {
    const body = await req.json()
    amount = body.amount
    game = body.game
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 })
  }
  if (!amount || !game) {
    return NextResponse.json({ error: "Missing required fields: amount, game" }, { status: 400 })
  }

  // 3. Cooldown check (fail-open if Redis unavailable)
  const redis = Redis.fromEnv()
  try {
    const inCooldown = await redis.get(COOLDOWN_KEY)
    if (inCooldown) {
      console.info("[bigwin] Skipped: cooldown active")
      return NextResponse.json({ skipped: true, reason: "cooldown" })
    }
  } catch (err) {
    console.error("[bigwin] Redis error during cooldown check:", err)
  }

  // 4. Check required env vars
  const botToken = process.env.DISCORD_BOT_TOKEN
  const channelId = process.env.BIGWIN_CHANNEL_ID
  const buttonUrl = process.env.BIGWIN_BUTTON_URL
  if (!botToken || !channelId || !buttonUrl) {
    console.error("[bigwin] Missing env vars")
    return NextResponse.json({ error: "Server misconfigured" }, { status: 503 })
  }

  // 5. Send to Discord
  const discordBody = {
    embeds: [{
      description: `🏆 **BIG WIN ALERT!!**\n\nA Fortune Chasers just won **${amount} SC** on **${game}**!\nThink you're next? Jump in and spin! 🎰💜`,
      color: 0xff9933,
    }],
    components: [{
      type: 1,
      components: [{
        type: 2,
        style: 5,
        label: "Play Now",
        url: buttonUrl,
      }],
    }],
  }

  let discordRes: Response
  try {
    discordRes = await fetch(
      `https://discord.com/api/v10/channels/${channelId}/messages`,
      {
        method: "POST",
        headers: {
          Authorization: `Bot ${botToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(discordBody),
      }
    )
  } catch {
    console.error("[bigwin] Discord API unreachable")
    return NextResponse.json({ error: "Discord API unreachable" }, { status: 502 })
  }

  if (!discordRes.ok) {
    const detail = await discordRes.text()
    console.error("[bigwin] Discord API error:", discordRes.status, detail)
    return NextResponse.json({ error: "Discord API error", detail }, { status: 502 })
  }

  // 6. Write cooldown AFTER successful send only
  try {
    await redis.set(COOLDOWN_KEY, "1", { ex: COOLDOWN_SECONDS })
  } catch (err) {
    console.error("[bigwin] Redis error when setting cooldown:", err)
    // Don't fail — message was already sent
  }

  console.info(`[bigwin] Broadcast sent: ${amount} SC on ${game}`)
  return NextResponse.json({ ok: true })
}
