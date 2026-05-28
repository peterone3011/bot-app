import { NextRequest, NextResponse } from "next/server"
import { Redis } from "@upstash/redis"
import { supabase } from "@/lib/supabase"

export const dynamic = "force-dynamic"

const COOLDOWN_KEY = "bigwin:cooldown"
const COOLDOWN_SECONDS = 14100 // 4h minus 5-min jitter window (bot applies 0–300 s random delay)
const IMAGE_INDEX_KEY = "bigwin:image_index"

const GAME_NAMES = [
  "MONEY COMING",
  "CASH KING",
  "MUMMY MIA",
  "ASCENT CHARGE BISON",
  "EPIC MAYAN DESTINY",
  "DEVIL FIRE 2",
]

/** 随机生成金额：1000–30000 之间的整数 + .0 或 .5 */
function randomAmount(): string {
  const integer = Math.floor(Math.random() * 29001) + 1000
  const decimal = Math.random() < 0.5 ? ".0" : ".5"
  return integer.toLocaleString("en-US") + decimal
}

function randomGame(): string {
  return GAME_NAMES[Math.floor(Math.random() * GAME_NAMES.length)]
}

// ─── 核心播报逻辑（POST 和 GET 共用）─────────────────────────────────────────

async function broadcast(amount: string, game: string, source: "api" | "cron") {
  const redis = Redis.fromEnv()

  // 1. 冷却检查（fail-open：Redis 不可用则放行）
  try {
    const inCooldown = await redis.get(COOLDOWN_KEY)
    if (inCooldown) {
      console.info(`[bigwin][${source}] Skipped: cooldown active`)
      return NextResponse.json({ skipped: true, reason: "cooldown" })
    }
  } catch (err) {
    console.error(`[bigwin][${source}] Redis error during cooldown check:`, err)
  }

  // 2. 读取图片轮换索引（0 → image_1，1 → image_2，严格交替）
  let imageIndex = 0
  try {
    const stored = await redis.get<number>(IMAGE_INDEX_KEY)
    imageIndex = stored ?? 0
  } catch (err) {
    console.error(`[bigwin][${source}] Redis error reading image index:`, err)
  }

  // 3. 读取配图
  let imageUrl: string | null = null
  try {
    const { data: configRows, error: configError } = await supabase
      .from("config")
      .select("key, value")
      .in("key", ["bigwin_image_1", "bigwin_image_2"])
    if (configError) {
      console.error(`[bigwin][${source}] Supabase config read error:`, configError.message)
    }
    const images = (configRows ?? [])
      .sort((a: { key: string }, b: { key: string }) => a.key.localeCompare(b.key)) // image_1 在前，image_2 在后
      .map((r: { key: string; value: string }) => r.value)
      .filter(Boolean)
    if (images.length > 0) {
      imageUrl = images[imageIndex % images.length]
    }
  } catch (err) {
    console.error(`[bigwin][${source}] Failed to read image config:`, err)
  }

  // 4. 环境变量检查
  const botToken = process.env.DISCORD_BOT_TOKEN
  const channelId = process.env.BIGWIN_CHANNEL_ID
  const buttonUrl = process.env.BIGWIN_BUTTON_URL
  if (!botToken || !channelId || !buttonUrl) {
    console.error(`[bigwin][${source}] Missing env vars`)
    return NextResponse.json({ error: "Server misconfigured" }, { status: 503 })
  }

  // 5. 发送到 Discord
  const embed: Record<string, unknown> = {
    description: `🏆 **BIG WIN ALERT!!**\n\nA Fortune Chasers just won **${amount} SC** on **${game}**!\nThink you're next? Jump in and spin! 🎰💜`,
    color: 0xff9933,
  }
  if (imageUrl) embed.image = { url: imageUrl }

  const discordBody = {
    embeds: [embed],
    components: [{
      type: 1,
      components: [{ type: 2, style: 5, label: "Play Now", url: buttonUrl }],
    }],
  }

  let discordRes: Response
  try {
    discordRes = await fetch(
      `https://discord.com/api/v10/channels/${channelId}/messages`,
      {
        method: "POST",
        headers: { Authorization: `Bot ${botToken}`, "Content-Type": "application/json" },
        body: JSON.stringify(discordBody),
      }
    )
  } catch {
    console.error(`[bigwin][${source}] Discord API unreachable`)
    return NextResponse.json({ error: "Discord API unreachable" }, { status: 502 })
  }

  if (!discordRes.ok) {
    const detail = await discordRes.text()
    console.error(`[bigwin][${source}] Discord API error:`, discordRes.status, detail)
    return NextResponse.json({ error: "Discord API error", detail }, { status: 502 })
  }

  // 6. 设置冷却 + 翻转图片索引（仅在成功发送后）
  try {
    await redis.set(COOLDOWN_KEY, "1", { ex: COOLDOWN_SECONDS })
  } catch (err) {
    console.error(`[bigwin][${source}] Redis error when setting cooldown:`, err)
  }
  try {
    await redis.set(IMAGE_INDEX_KEY, imageIndex === 0 ? 1 : 0)
  } catch (err) {
    console.error(`[bigwin][${source}] Redis error when flipping image index:`, err)
  }

  console.info(`[bigwin][${source}] Broadcast sent: ${amount} SC on ${game}`)
  return NextResponse.json({ ok: true, amount, game })
}

// ─── GET：Vercel Cron Job 每4小时触发，自动生成文案 ──────────────────────────

export async function GET(req: NextRequest) {
  const cronSecret = process.env.CRON_SECRET
  const authHeader = req.headers.get("authorization")
  if (!cronSecret || authHeader !== `Bearer ${cronSecret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }
  return broadcast(randomAmount(), randomGame(), "cron")
}

// ─── POST：外部接口传入真实数据 ───────────────────────────────────────────────

export async function POST(req: NextRequest) {
  // 1. Auth
  const apiKey = process.env.BROADCAST_API_KEY
  const authHeader = req.headers.get("authorization")
  if (!apiKey || !authHeader || authHeader !== `Bearer ${apiKey}`) {
    console.warn("[bigwin] Unauthorized request")
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  // 2. 解析并校验请求体
  let amount: string, game: string
  try {
    const body = await req.json()
    const rawAmount = body.amount
    const rawGame = body.game
    if (rawAmount === undefined || rawAmount === null) {
      return NextResponse.json({ error: "Missing required field: amount" }, { status: 400 })
    }
    if (!rawGame || typeof rawGame !== "string") {
      return NextResponse.json({ error: "Missing required field: game (must be a string)" }, { status: 400 })
    }
    if (typeof rawAmount === "number") {
      amount = rawAmount.toLocaleString("en-US")
    } else if (typeof rawAmount === "string") {
      amount = rawAmount.trim()
    } else {
      return NextResponse.json({ error: "Invalid amount: must be a number or string" }, { status: 400 })
    }
    game = rawGame.trim()
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 })
  }

  if (!/^[\d,. ]+$/.test(amount) || amount.length === 0 || amount.length > 30) {
    return NextResponse.json({ error: "Invalid amount format (digits, commas, dots only, max 30 chars)" }, { status: 400 })
  }
  if (game.length > 100 || /^@/.test(game)) {
    return NextResponse.json({ error: "Invalid game format (max 100 chars, must not start with @)" }, { status: 400 })
  }

  return broadcast(amount, game, "api")
}
