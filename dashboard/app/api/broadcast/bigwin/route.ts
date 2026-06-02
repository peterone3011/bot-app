import { NextRequest, NextResponse } from "next/server"
import { Redis } from "@upstash/redis"

export const dynamic = "force-dynamic"

const COOLDOWN_KEY = "bigwin:cooldown"
const COOLDOWN_SECONDS = 21600 // 6h safety net — matches bot's minimum interval (_MIN_INTERVAL_H)
const IMAGE_INDEX_KEY = "bigwin:image_index"

const BASE_URL = "https://fortunepurplebot.vercel.app"
const IMAGE_URLS = [`${BASE_URL}/bigwins1.jpg`, `${BASE_URL}/bigwins2.jpg`]

const GAME_NAMES = [
  "MONEY COMING",
  "CASH KING",
  "MUMMY MIA",
  "ASCENT CHARGE BISON",
  "EPIC MAYAN DESTINY",
  "DEVIL FIRE 2",
  "BURNINGS WINS",
  "CIRCUS JOKER 4096",
  "MERMAID COME BACK",
  "THE FLAMING CITY",
  "ROTTEN",
  "ZEUS POWER",
  "HOT TRIPLE SEVENS",
  "FORTUNE GEMS 500",
  "LUCKY DUCKY",
  "THE PENGUINS",
  "HAMMER OF THUNDER",
  "HOT FRUITS 20",
  "DRAGON TREASURE",
  "TREASURE OF ANUBIS",
  "THE GREAT FIREFIGHTER",
  "HAND OF ANUBIS",
  "RUSH RICHES",
  "DRAGON'S PEARL",
  "JOKER BOMBS",
  "FRUIT CASE",
  "EXCALIBUR",
  "DOOMSDAY SALOON",
  "LIGHTNING CROWN",
  "JACK HAMMER",
  "CASH PIG 2",
  "3 COIN VOLCANOES",
  "3 HOT TEAPOTS",
  "3SUPER HOT CHILLIES",
]

/** 随机生成金额：1,000–8,000 之间的整数 + .0 或 .5 */
function randomAmount(): string {
  const integer = Math.floor(Math.random() * 7001) + 1000
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

  // 2. 读取图片轮换索引（0 → bigwins1.jpg，1 → bigwins2.jpg，严格交替）
  let imageIndex = 0
  try {
    const stored = await redis.get<number>(IMAGE_INDEX_KEY)
    imageIndex = stored ?? 0
  } catch (err) {
    console.error(`[bigwin][${source}] Redis error reading image index:`, err)
  }

  const imageUrl = IMAGE_URLS[imageIndex % IMAGE_URLS.length]

  // 3. 环境变量检查
  const botToken = process.env.DISCORD_BOT_TOKEN
  const channelId = process.env.BIGWIN_CHANNEL_ID
  const buttonUrl = process.env.BIGWIN_BUTTON_URL
  if (!botToken || !channelId || !buttonUrl) {
    console.error(`[bigwin][${source}] Missing env vars`)
    return NextResponse.json({ error: "Server misconfigured" }, { status: 503 })
  }

  // 4. 发送到 Discord
  const discordBody = {
    embeds: [{
      description: `🏆 **BIG WIN ALERT!!**\n\nA Fortune Chasers just won **${amount} SC** on **${game}**!\nThink you're next? Jump in and spin! 🎰💜`,
      color: 0xff9933,
      image: { url: imageUrl },
    }],
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

  // 5. 设置冷却 + 翻转图片索引（仅在成功发送后）
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

// ─── GET：Railway Bot 随机 6–14 小时触发，自动生成文案 ────────────────────────

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
  const apiKey = process.env.BROADCAST_API_KEY
  const authHeader = req.headers.get("authorization")
  if (!apiKey || !authHeader || authHeader !== `Bearer ${apiKey}`) {
    console.warn("[bigwin] Unauthorized request")
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

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
