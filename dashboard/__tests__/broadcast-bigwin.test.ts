// @vitest-environment node

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

const mockRedisGet = vi.fn()
const mockRedisSet = vi.fn()

vi.mock("@upstash/redis", () => ({
  Redis: {
    fromEnv: vi.fn(() => ({
      get: mockRedisGet,
      set: mockRedisSet,
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
    mockFetch.mockResolvedValue({ ok: true, text: () => Promise.resolve("") })
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

  it("sends Discord message with correct format and returns ok:true", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }, "Bearer test-key") as any)
    expect(res.status).toBe(200)
    expect(await res.json()).toEqual({ ok: true })
    expect(mockFetch).toHaveBeenCalledOnce()
    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe("https://discord.com/api/v10/channels/channel-123/messages")
    expect(options.headers.Authorization).toBe("Bot test-bot-token")
    const body = JSON.parse(options.body)
    expect(body.embeds[0].description).toContain("10,000.0 SC")
    expect(body.embeds[0].description).toContain("Fortune Dragon")
    expect(body.embeds[0].color).toBe(0x9B59B6)
    expect(body.components[0].components[0].url).toBe("https://fortunepurple.com")
    expect(body.components[0].components[0].label).toBe("Play Now")
  })

  it("writes cooldown key with 4h TTL after successful Discord send", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }, "Bearer test-key") as any)
    expect(mockRedisSet).toHaveBeenCalledWith("bigwin:cooldown", "1", { ex: 14400 })
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
})
