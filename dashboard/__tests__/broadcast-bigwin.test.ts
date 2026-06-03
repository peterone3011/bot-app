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
    expect(mockPipelineExec).toHaveBeenCalled()

    const allCalls = mockPipeline.zadd.mock.calls
    const historyCall = allCalls.find(([key]: [string]) => key === "bigwin:history")
    const sourceCall = allCalls.find(([key]: [string]) => key === "bigwin:history:api")
    expect(historyCall).toBeDefined()
    expect(sourceCall).toBeDefined()

    const member = JSON.parse(historyCall![1].member)
    expect(member).toMatchObject({
      amount: "5,000.0",
      game: "Zeus",
      source: "api",
      id: "discord-msg-id-123",
    })
    expect(typeof member.ts).toBe("number")
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

function makeGetReq(authHeader?: string) {
  return new Request("https://x.com/api/broadcast/bigwin", {
    method: "GET",
    headers: {
      ...(authHeader ? { authorization: authHeader } : {}),
    },
  })
}

describe("GET /api/broadcast/bigwin (cron)", () => {
  const mockFetch = vi.fn()

  beforeEach(() => {
    vi.stubGlobal("fetch", mockFetch)
    process.env.CRON_SECRET = "cron-secret"
    process.env.DISCORD_BOT_TOKEN = "test-bot-token"
    process.env.BIGWIN_CHANNEL_ID = "channel-123"
    process.env.BIGWIN_BUTTON_URL = "https://fortunepurple.com"
    mockRedisGet.mockResolvedValue(null)
    mockRedisSet.mockResolvedValue("OK")
    mockPipelineExec.mockResolvedValue([])
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: "discord-msg-id-cron" }),
      text: () => Promise.resolve(""),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    delete process.env.CRON_SECRET
    delete process.env.DISCORD_BOT_TOKEN
    delete process.env.BIGWIN_CHANNEL_ID
    delete process.env.BIGWIN_BUTTON_URL
  })

  it("returns 401 with no Authorization header", async () => {
    const { GET } = await import("@/app/api/broadcast/bigwin/route")
    const res = await GET(makeGetReq() as any)
    expect(res.status).toBe(401)
  })

  it("returns 401 with wrong cron secret", async () => {
    const { GET } = await import("@/app/api/broadcast/bigwin/route")
    const res = await GET(makeGetReq("Bearer wrong-secret") as any)
    expect(res.status).toBe(401)
  })

  it("returns skipped:cooldown when cooldown is active", async () => {
    mockRedisGet.mockResolvedValueOnce("1")
    const { GET } = await import("@/app/api/broadcast/bigwin/route")
    const res = await GET(makeGetReq("Bearer cron-secret") as any)
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data).toEqual({ skipped: true, reason: "cooldown" })
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it("broadcasts successfully and returns source:cron", async () => {
    const { GET } = await import("@/app/api/broadcast/bigwin/route")
    const res = await GET(makeGetReq("Bearer cron-secret") as any)
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data).toMatchObject({
      ok: true,
      source: "cron",
      recorded: true,
    })
    expect(data.id).toBe("discord-msg-id-cron")
    expect(mockFetch).toHaveBeenCalledOnce()
  })

  it("writes history to bigwin:history and bigwin:history:cron after successful GET", async () => {
    const { GET } = await import("@/app/api/broadcast/bigwin/route")
    await GET(makeGetReq("Bearer cron-secret") as any)
    expect(mockRedisPipeline).toHaveBeenCalled()
    expect(mockPipelineExec).toHaveBeenCalled()

    const allCalls = mockPipeline.zadd.mock.calls
    const historyCall = allCalls.find(([key]: [string]) => key === "bigwin:history")
    const sourceCall = allCalls.find(([key]: [string]) => key === "bigwin:history:cron")
    expect(historyCall).toBeDefined()
    expect(sourceCall).toBeDefined()

    const member = JSON.parse(historyCall![1].member)
    expect(member).toMatchObject({
      source: "cron",
      id: "discord-msg-id-cron",
    })
    expect(typeof member.amount).toBe("string")
    expect(typeof member.game).toBe("string")
    expect(typeof member.ts).toBe("number")
  })

  it("writes cooldown key with correct TTL after successful cron broadcast", async () => {
    const { GET } = await import("@/app/api/broadcast/bigwin/route")
    await GET(makeGetReq("Bearer cron-secret") as any)
    expect(mockRedisSet).toHaveBeenCalledWith("bigwin:cooldown", "1", { ex: 21600 })
  })

  it("returns recorded:false when Redis history write throws but cron broadcast succeeds", async () => {
    mockPipelineExec.mockRejectedValueOnce(new Error("Redis error"))
    const { GET } = await import("@/app/api/broadcast/bigwin/route")
    const res = await GET(makeGetReq("Bearer cron-secret") as any)
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data.ok).toBe(true)
    expect(data.recorded).toBe(false)
  })
})
