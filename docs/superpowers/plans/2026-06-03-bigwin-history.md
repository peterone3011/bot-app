# Big Win 播报历史记录 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为每条 Big Win 播报写入 Redis 审计记录（30天留存），并在 Dashboard 提供可筛选的历史查看页面。

**Architecture:** 在现有 `broadcast()` 函数中，Discord 发送成功后用 Redis pipeline 向三个 Sorted Set（全量/cron/api）各写一条记录，score 为毫秒时间戳，同时清除 30 天前数据。新增 GET 历史查询接口（session 鉴权）和 Dashboard 页面（下拉筛选来源）。

**Tech Stack:** Next.js 15, Upstash Redis (`@upstash/redis`), NextAuth (`auth()`), React, Tailwind CSS, shadcn/ui, Vitest

---

## File Map

| 文件 | 操作 |
|---|---|
| `dashboard/__tests__/broadcast-bigwin.test.ts` | 修改：更新 Redis mock（加 pipeline）、更新响应断言、加历史写入相关测试 |
| `dashboard/app/api/broadcast/bigwin/route.ts` | 修改：提取 Discord message ID、pipeline 写历史、更新响应结构 |
| `dashboard/__tests__/bigwin-history.test.ts` | 新建：历史查询接口的完整测试 |
| `dashboard/app/api/broadcast/bigwin/history/route.ts` | 新建：GET 历史查询接口 |
| `dashboard/app/dashboard/bigwin/page.tsx` | 新建：历史记录 Dashboard 页面 |
| `dashboard/components/sidebar.tsx` | 修改：新增「Big Win 记录」导航项 |

---

## Task 1: 更新播报路由测试与实现

**Files:**
- Modify: `dashboard/__tests__/broadcast-bigwin.test.ts`
- Modify: `dashboard/app/api/broadcast/bigwin/route.ts`

- [ ] **Step 1: 更新测试文件 — 扩展 Redis mock、修正断言、加新测试**

将 `dashboard/__tests__/broadcast-bigwin.test.ts` 的全部内容替换为：

```typescript
// @vitest-environment node

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

const mockRedisGet = vi.fn()
const mockRedisSet = vi.fn()
const mockPipelineExec = vi.fn()
const mockPipeline = {
  zadd: vi.fn().mockReturnThis(),
  zremrangebyscore: vi.fn().mockReturnThis(),
  exec: mockPipelineExec,
}
const mockRedisPipeline = vi.fn(() => mockPipeline)

vi.mock("@upstash/redis", () => ({
  Redis: {
    fromEnv: vi.fn(() => ({
      get: mockRedisGet,
      set: mockRedisSet,
      pipeline: mockRedisPipeline,
    })),
  },
}))

function makeReq(body: unknown, authHeader?: string) {
  return new Request("https://x.com/api/broadcast/bigwin", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(authHeader ? { authorization: authHeader } : {}),
    },
    body: JSON.stringify(body),
  })
}

describe("POST /api/broadcast/bigwin", () => {
  const mockFetch = vi.fn()

  beforeEach(() => {
    vi.stubGlobal("fetch", mockFetch)
    process.env.BROADCAST_API_KEY = "test-key"
    process.env.DISCORD_BOT_TOKEN = "test-bot-token"
    process.env.BIGWIN_CHANNEL_ID = "channel-123"
    process.env.BIGWIN_BUTTON_URL = "https://fortunepurple.com"
    mockRedisGet.mockResolvedValue(null)
    mockRedisSet.mockResolvedValue("OK")
    mockPipelineExec.mockResolvedValue([])
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: "discord-msg-id-123" }),
      text: () => Promise.resolve(""),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    delete process.env.BROADCAST_API_KEY
    delete process.env.DISCORD_BOT_TOKEN
    delete process.env.BIGWIN_CHANNEL_ID
    delete process.env.BIGWIN_BUTTON_URL
  })

  it("returns 401 with no Authorization header", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }) as any)
    expect(res.status).toBe(401)
  })

  it("returns 401 with wrong API key", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }, "Bearer wrong-key") as any)
    expect(res.status).toBe(401)
  })

  it("returns 400 when amount is missing", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ game: "Fortune Dragon" }, "Bearer test-key") as any)
    expect(res.status).toBe(400)
  })

  it("returns 400 when game is missing", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "10,000.0" }, "Bearer test-key") as any)
    expect(res.status).toBe(400)
  })

  it("returns skipped:cooldown and skips Discord when cooldown is active", async () => {
    mockRedisGet.mockResolvedValueOnce("1")
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }, "Bearer test-key") as any)
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data).toEqual({ skipped: true, reason: "cooldown" })
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it("sends Discord message with correct format and returns full ok response", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }, "Bearer test-key") as any)
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data).toMatchObject({
      ok: true,
      amount: "10,000.0",
      game: "Fortune Dragon",
      source: "api",
      recorded: true,
    })
    expect(data.id).toBe("discord-msg-id-123")
    expect(mockFetch).toHaveBeenCalledOnce()
    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe("https://discord.com/api/v10/channels/channel-123/messages")
    expect(options.headers.Authorization).toBe("Bot test-bot-token")
    const body = JSON.parse(options.body)
    expect(body.embeds[0].description).toContain("10,000.0 SC")
    expect(body.embeds[0].description).toContain("Fortune Dragon")
    expect(body.embeds[0].color).toBe(0xff9933)
    expect(body.components[0].components[0].url).toBe("https://fortunepurple.com")
    expect(body.components[0].components[0].label).toBe("Play Now")
  })

  it("embed always includes an image URL without any external config", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "5,000.0", game: "Zeus Power" }, "Bearer test-key") as any)
    expect(res.status).toBe(200)
    const [, options] = mockFetch.mock.calls[0]
    const body = JSON.parse(options.body)
    expect(body.embeds[0].image?.url).toMatch(/^https:\/\/.+\.(jpg|png|webp|gif)/)
  })

  it("writes cooldown key with correct TTL after successful Discord send", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }, "Bearer test-key") as any)
    expect(mockRedisSet).toHaveBeenCalledWith("bigwin:cooldown", "1", { ex: 21600 })
  })

  it("returns 502 and does NOT write cooldown when Discord returns error status", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500, text: () => Promise.resolve("Internal Server Error") })
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }, "Bearer test-key") as any)
    expect(res.status).toBe(502)
    expect(mockRedisSet).not.toHaveBeenCalled()
  })

  it("returns 502 and does NOT write cooldown when Discord is unreachable", async () => {
    mockFetch.mockRejectedValueOnce(new Error("ECONNREFUSED"))
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }, "Bearer test-key") as any)
    expect(res.status).toBe(502)
    expect(mockRedisSet).not.toHaveBeenCalled()
  })

  it("writes history to bigwin:history and bigwin:history:api after successful POST", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    await POST(makeReq({ amount: "5,000.0", game: "Zeus" }, "Bearer test-key") as any)
    expect(mockRedisPipeline).toHaveBeenCalled()
    expect(mockPipeline.zadd).toHaveBeenCalledWith(
      "bigwin:history",
      expect.objectContaining({ member: expect.stringContaining('"source":"api"') })
    )
    expect(mockPipeline.zadd).toHaveBeenCalledWith(
      "bigwin:history:api",
      expect.objectContaining({ member: expect.stringContaining('"source":"api"') })
    )
    expect(mockPipelineExec).toHaveBeenCalled()
  })

  it("does not write history when cooldown is active", async () => {
    mockRedisGet.mockResolvedValueOnce("1")
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    await POST(makeReq({ amount: "5,000.0", game: "Zeus" }, "Bearer test-key") as any)
    expect(mockRedisPipeline).not.toHaveBeenCalled()
  })

  it("does not write history when Discord send fails", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500, text: () => Promise.resolve("error") })
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    await POST(makeReq({ amount: "5,000.0", game: "Zeus" }, "Bearer test-key") as any)
    expect(mockRedisPipeline).not.toHaveBeenCalled()
  })

  it("returns recorded:false when Redis history write throws but broadcast succeeds", async () => {
    mockPipelineExec.mockRejectedValueOnce(new Error("Redis error"))
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "5,000.0", game: "Zeus" }, "Bearer test-key") as any)
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data.ok).toBe(true)
    expect(data.recorded).toBe(false)
  })
})
```

- [ ] **Step 2: 运行测试，确认新加的测试全部 FAIL（旧测试可能也有几条 FAIL）**

```bash
cd E:/company-ai/fpbot/dashboard && npm test -- --reporter=verbose 2>&1 | tail -50
```

预期：`history` 相关新测试报 FAIL（route 还没改），cooldown TTL 测试可能报 FAIL（旧值不一致，属已有问题）。

- [ ] **Step 3: 更新 `dashboard/app/api/broadcast/bigwin/route.ts`**

用以下内容完整替换该文件：

```typescript
import { NextRequest, NextResponse } from "next/server"
import { Redis } from "@upstash/redis"

export const dynamic = "force-dynamic"

const COOLDOWN_KEY = "bigwin:cooldown"
const COOLDOWN_SECONDS = 21600 // 6h safety net — matches bot's minimum interval (_MIN_INTERVAL_H)
const IMAGE_INDEX_KEY = "bigwin:image_index"
const HISTORY_KEY = "bigwin:history"
const HISTORY_TTL_MS = 30 * 24 * 60 * 60 * 1000 // 30 days in ms

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

  // 5. 提取 Discord message ID（best-effort）
  let discordMessageId = ""
  try {
    const discordData = await discordRes.json()
    discordMessageId = discordData?.id ?? ""
  } catch {
    // message ID is non-critical, proceed without it
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

  // 7. 写入播报历史（fail-open：写入失败不阻断播报响应）
  const ts = Date.now()
  const cutoff = ts - HISTORY_TTL_MS
  const sourceKey = `${HISTORY_KEY}:${source}` as const
  const member = JSON.stringify({ id: discordMessageId, ts, amount, game, source, discordMessageId })
  let recorded = true
  try {
    const pipeline = redis.pipeline()
    pipeline.zadd(HISTORY_KEY, { score: ts, member })
    pipeline.zremrangebyscore(HISTORY_KEY, 0, cutoff)
    pipeline.zadd(sourceKey, { score: ts, member })
    pipeline.zremrangebyscore(sourceKey, 0, cutoff)
    await pipeline.exec()
  } catch (err) {
    console.error(`[bigwin][${source}] Redis error writing history:`, err)
    recorded = false
  }

  console.info(`[bigwin][${source}] Broadcast sent: ${amount} SC on ${game}`)
  return NextResponse.json({ ok: true, id: discordMessageId, amount, game, source, recorded })
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
```

- [ ] **Step 4: 运行测试，确认 Task 1 相关测试全部 PASS**

```bash
cd E:/company-ai/fpbot/dashboard && npm test -- --reporter=verbose 2>&1 | tail -50
```

预期：所有历史写入相关测试 PASS，旧测试 PASS（cooldown TTL 测试若仍 FAIL 属已有问题，不在本任务范围内）。

- [ ] **Step 5: Commit**

```bash
cd E:/company-ai/fpbot && git add dashboard/__tests__/broadcast-bigwin.test.ts dashboard/app/api/broadcast/bigwin/route.ts && git commit -m "feat: write bigwin broadcast history to Redis on successful send"
```

---

## Task 2: 新建历史查询接口

**Files:**
- Create: `dashboard/__tests__/bigwin-history.test.ts`
- Create: `dashboard/app/api/broadcast/bigwin/history/route.ts`

- [ ] **Step 1: 新建测试文件 `dashboard/__tests__/bigwin-history.test.ts`**

```typescript
// @vitest-environment node

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

const mockRedisZrange = vi.fn()

vi.mock("@upstash/redis", () => ({
  Redis: {
    fromEnv: vi.fn(() => ({
      zrange: mockRedisZrange,
    })),
  },
}))

const mockAuth = vi.fn()
vi.mock("@/lib/auth", () => ({ auth: mockAuth }))

function makeReq(search = "") {
  return new Request(`https://x.com/api/broadcast/bigwin/history${search}`)
}

const sampleRecord = {
  id: "111222333",
  ts: 1748880000000,
  amount: "1,500.0",
  game: "ZEUS POWER",
  source: "cron",
  discordMessageId: "111222333",
}

describe("GET /api/broadcast/bigwin/history", () => {
  beforeEach(() => {
    mockAuth.mockResolvedValue({ user: { name: "Admin" } })
    mockRedisZrange.mockResolvedValue([])
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("returns 401 when not authenticated", async () => {
    mockAuth.mockResolvedValue(null)
    const { GET } = await import("@/app/api/broadcast/bigwin/history/route")
    const res = await GET(makeReq() as any)
    expect(res.status).toBe(401)
    expect(await res.json()).toEqual({ error: "Unauthorized" })
  })

  it("returns 400 for invalid source param", async () => {
    const { GET } = await import("@/app/api/broadcast/bigwin/history/route")
    const res = await GET(makeReq("?source=foo") as any)
    expect(res.status).toBe(400)
    expect(await res.json()).toEqual({ error: "Invalid source" })
  })

  it("returns empty records array when history is empty", async () => {
    const { GET } = await import("@/app/api/broadcast/bigwin/history/route")
    const res = await GET(makeReq() as any)
    expect(res.status).toBe(200)
    expect(await res.json()).toEqual({ records: [] })
  })

  it("reads from bigwin:history and returns parsed records when no source filter", async () => {
    mockRedisZrange.mockResolvedValue([JSON.stringify(sampleRecord)])
    const { GET } = await import("@/app/api/broadcast/bigwin/history/route")
    const res = await GET(makeReq() as any)
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data.records).toHaveLength(1)
    expect(data.records[0]).toEqual(sampleRecord)
    expect(mockRedisZrange).toHaveBeenCalledWith("bigwin:history", 0, 199, { rev: true })
  })

  it("reads from bigwin:history:cron when source=cron", async () => {
    const { GET } = await import("@/app/api/broadcast/bigwin/history/route")
    await GET(makeReq("?source=cron") as any)
    expect(mockRedisZrange).toHaveBeenCalledWith("bigwin:history:cron", 0, 199, { rev: true })
  })

  it("reads from bigwin:history:api when source=api", async () => {
    const { GET } = await import("@/app/api/broadcast/bigwin/history/route")
    await GET(makeReq("?source=api") as any)
    expect(mockRedisZrange).toHaveBeenCalledWith("bigwin:history:api", 0, 199, { rev: true })
  })

  it("skips corrupted JSON entries without throwing and returns valid ones", async () => {
    const goodRecord = JSON.stringify(sampleRecord)
    mockRedisZrange.mockResolvedValue(["not-valid-json{{{", goodRecord])
    const { GET } = await import("@/app/api/broadcast/bigwin/history/route")
    const res = await GET(makeReq() as any)
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data.records).toHaveLength(1)
    expect(data.records[0]).toEqual(sampleRecord)
  })

  it("returns 500 when Redis throws", async () => {
    mockRedisZrange.mockRejectedValue(new Error("Redis connection refused"))
    const { GET } = await import("@/app/api/broadcast/bigwin/history/route")
    const res = await GET(makeReq() as any)
    expect(res.status).toBe(500)
    expect(await res.json()).toEqual({ error: "History unavailable" })
  })
})
```

- [ ] **Step 2: 运行测试，确认全部 FAIL（文件未存在）**

```bash
cd E:/company-ai/fpbot/dashboard && npm test -- --reporter=verbose 2>&1 | grep -E "FAIL|PASS|bigwin-history" | head -20
```

预期：`bigwin-history.test.ts` 中所有测试报错（Cannot find module）。

- [ ] **Step 3: 新建 `dashboard/app/api/broadcast/bigwin/history/route.ts`**

```typescript
import { NextRequest, NextResponse } from "next/server"
import { Redis } from "@upstash/redis"
import { auth } from "@/lib/auth"

export const dynamic = "force-dynamic"

const VALID_SOURCES = ["cron", "api"] as const
type Source = (typeof VALID_SOURCES)[number]

const HISTORY_KEYS: Record<"all" | Source, string> = {
  all: "bigwin:history",
  cron: "bigwin:history:cron",
  api: "bigwin:history:api",
}

interface HistoryRecord {
  id: string
  ts: number
  amount: string
  game: string
  source: "cron" | "api"
  discordMessageId: string
}

export async function GET(req: NextRequest) {
  const session = await auth()
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const source = req.nextUrl.searchParams.get("source")
  if (source !== null && !VALID_SOURCES.includes(source as Source)) {
    return NextResponse.json({ error: "Invalid source" }, { status: 400 })
  }

  const key = source ? HISTORY_KEYS[source as Source] : HISTORY_KEYS.all

  let members: unknown[]
  try {
    const redis = Redis.fromEnv()
    members = await redis.zrange(key, 0, 199, { rev: true })
  } catch (err) {
    console.error("[bigwin][history] Redis error:", err)
    return NextResponse.json({ error: "History unavailable" }, { status: 500 })
  }

  const records: HistoryRecord[] = []
  for (const m of members) {
    try {
      records.push(JSON.parse(m as string) as HistoryRecord)
    } catch {
      // skip corrupted entries
    }
  }

  return NextResponse.json({ records })
}
```

- [ ] **Step 4: 运行测试，确认全部 PASS**

```bash
cd E:/company-ai/fpbot/dashboard && npm test -- --reporter=verbose 2>&1 | tail -30
```

预期：`bigwin-history.test.ts` 所有测试 PASS。

- [ ] **Step 5: Commit**

```bash
cd E:/company-ai/fpbot && git add dashboard/__tests__/bigwin-history.test.ts dashboard/app/api/broadcast/bigwin/history/route.ts && git commit -m "feat: add bigwin history query endpoint with session auth"
```

---

## Task 3: Dashboard 页面 + 侧边栏导航

**Files:**
- Create: `dashboard/app/dashboard/bigwin/page.tsx`
- Modify: `dashboard/components/sidebar.tsx`

- [ ] **Step 1: 新建 `dashboard/app/dashboard/bigwin/page.tsx`**

```tsx
"use client"
import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { Trophy } from "lucide-react"

interface HistoryRecord {
  id: string
  ts: number
  amount: string
  game: string
  source: "cron" | "api"
  discordMessageId: string
}

function formatTs(ts: number): string {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

export default function BigwinHistoryPage() {
  const [source, setSource] = useState<string>("all")
  const [records, setRecords] = useState<HistoryRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(false)
    const url =
      source === "all"
        ? "/api/broadcast/bigwin/history"
        : `/api/broadcast/bigwin/history?source=${source}`
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error("fetch failed")
        return r.json()
      })
      .then((data) => {
        setRecords(data.records ?? [])
        setLoading(false)
      })
      .catch(() => {
        setError(true)
        setLoading(false)
      })
  }, [source])

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
          <span>工作区</span>
          <span className="text-muted-foreground/40">/</span>
          <span className="text-foreground">Big Win 记录</span>
        </div>
        <h1 className="mt-1.5 text-[22px] font-semibold tracking-tight">Big Win 记录</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          最近 30 天播报历史，保留最新 200 条。
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Trophy className="h-4 w-4 text-brand-300" />
              播报历史
            </CardTitle>
            <Select value={source} onValueChange={setSource}>
              <SelectTrigger className="w-36 h-8 text-[13px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部</SelectItem>
                <SelectItem value="cron">我们的Bot</SelectItem>
                <SelectItem value="api">技术接口</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <CardDescription>时间为本地时间。</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="py-12 flex justify-center text-[13px] text-muted-foreground">
              加载中…
            </div>
          ) : error ? (
            <div className="py-12 flex justify-center text-[13px] text-destructive">
              加载失败，请刷新页面重试
            </div>
          ) : records.length === 0 ? (
            <div className="py-12 flex justify-center text-[13px] text-muted-foreground">
              暂无记录
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="text-left py-2 pr-4 font-medium">时间</th>
                    <th className="text-left py-2 pr-4 font-medium">金额</th>
                    <th className="text-left py-2 pr-4 font-medium">游戏</th>
                    <th className="text-left py-2 font-medium">来源</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((r) => (
                    <tr key={r.id || r.ts} className="border-b border-border/50 hover:bg-accent/20">
                      <td className="py-2.5 pr-4 tabular-nums text-muted-foreground">
                        {formatTs(r.ts)}
                      </td>
                      <td className="py-2.5 pr-4 font-medium">{r.amount} SC</td>
                      <td className="py-2.5 pr-4 text-muted-foreground">{r.game}</td>
                      <td className="py-2.5">
                        {r.source === "cron" ? (
                          <Badge
                            variant="outline"
                            className="border-success/40 text-success text-[11px]"
                          >
                            Bot
                          </Badge>
                        ) : (
                          <Badge
                            variant="outline"
                            className="border-primary/40 text-primary text-[11px]"
                          >
                            技术接口
                          </Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: 更新 `dashboard/components/sidebar.tsx` — 在 navItems 数组中新增 Big Win 记录入口**

找到：
```typescript
import {
  PanelLeftClose,
  PanelLeftOpen,
  MessageSquare,
  Globe,
  Settings,
  LogOut,
} from "lucide-react"

const navItems = [
  { href: "/dashboard/embeds",   label: "Embed 消息", icon: MessageSquare, short: "E" },
  { href: "/dashboard/sites",    label: "站点管理",    icon: Globe,         short: "S" },
  { href: "/dashboard/settings", label: "全局设置",    icon: Settings,      short: "C" },
]
```

替换为：
```typescript
import {
  PanelLeftClose,
  PanelLeftOpen,
  MessageSquare,
  Globe,
  Settings,
  LogOut,
  Trophy,
} from "lucide-react"

const navItems = [
  { href: "/dashboard/embeds",   label: "Embed 消息",   icon: MessageSquare, short: "E" },
  { href: "/dashboard/sites",    label: "站点管理",      icon: Globe,         short: "S" },
  { href: "/dashboard/settings", label: "全局设置",      icon: Settings,      short: "C" },
  { href: "/dashboard/bigwin",   label: "Big Win 记录", icon: Trophy,        short: "B" },
]
```

- [ ] **Step 3: 运行测试套件确认没有引入新失败**

```bash
cd E:/company-ai/fpbot/dashboard && npm test -- --reporter=verbose 2>&1 | tail -20
```

预期：所有测试结果与 Task 2 结束时一致，无新增 FAIL。

- [ ] **Step 4: Commit**

```bash
cd E:/company-ai/fpbot && git add dashboard/app/dashboard/bigwin/page.tsx dashboard/components/sidebar.tsx && git commit -m "feat: add bigwin history dashboard page with source filter"
```
