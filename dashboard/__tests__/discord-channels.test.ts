// @vitest-environment node

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

vi.mock("@/lib/auth", () => ({ auth: vi.fn() }))

describe("GET /api/discord/channels", () => {
  const mockFetch = vi.fn()

  beforeEach(() => {
    vi.stubGlobal("fetch", mockFetch)
    process.env.DISCORD_GUILD_ID = "guild-123"
    process.env.DISCORD_BOT_TOKEN = "test-bot-token"
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    delete process.env.DISCORD_GUILD_ID
    delete process.env.DISCORD_BOT_TOKEN
  })

  it("returns 401 when not authenticated", async () => {
    const { auth } = await import("@/lib/auth")
    vi.mocked(auth).mockResolvedValueOnce(null as any)
    const { GET } = await import("@/app/api/discord/channels/route")
    const res = await GET()
    expect(res.status).toBe(401)
  })

  it("returns 503 when DISCORD_BOT_TOKEN is not configured", async () => {
    delete process.env.DISCORD_BOT_TOKEN
    const { auth } = await import("@/lib/auth")
    vi.mocked(auth).mockResolvedValueOnce({ user: { name: "admin" } } as any)
    const { GET } = await import("@/app/api/discord/channels/route")
    const res = await GET()
    expect(res.status).toBe(503)
  })

  it("returns 503 when DISCORD_GUILD_ID is not configured", async () => {
    delete process.env.DISCORD_GUILD_ID
    const { auth } = await import("@/lib/auth")
    vi.mocked(auth).mockResolvedValueOnce({ user: { name: "admin" } } as any)
    const { GET } = await import("@/app/api/discord/channels/route")
    const res = await GET()
    expect(res.status).toBe(503)
  })

  it("returns 502 when Discord API is unreachable (fetch throws)", async () => {
    const { auth } = await import("@/lib/auth")
    vi.mocked(auth).mockResolvedValueOnce({ user: { name: "admin" } } as any)
    mockFetch.mockRejectedValueOnce(new Error("ECONNREFUSED"))
    const { GET } = await import("@/app/api/discord/channels/route")
    const res = await GET()
    expect(res.status).toBe(502)
  })

  it("returns 502 when Discord API responds with error status", async () => {
    const { auth } = await import("@/lib/auth")
    vi.mocked(auth).mockResolvedValueOnce({ user: { name: "admin" } } as any)
    mockFetch.mockResolvedValueOnce({ ok: false, status: 401, text: () => Promise.resolve("Unauthorized") })
    const { GET } = await import("@/app/api/discord/channels/route")
    const res = await GET()
    expect(res.status).toBe(502)
  })

  it("returns only text and announcement channels, grouped by category", async () => {
    const { auth } = await import("@/lib/auth")
    vi.mocked(auth).mockResolvedValueOnce({ user: { name: "admin" } } as any)
    const rawChannels = [
      { id: "100", name: "Community", type: 4, parent_id: null, position: 0 },
      { id: "1",   name: "general",   type: 0, parent_id: "100", position: 1 },
      { id: "2",   name: "news",      type: 5, parent_id: "100", position: 0 },
      { id: "3",   name: "music",     type: 2, parent_id: null,  position: 2 },
    ]
    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(rawChannels) })
    const { GET } = await import("@/app/api/discord/channels/route")
    const res = await GET()
    expect(res.status).toBe(200)
    const data = await res.json()
    // Voice channel (type 2) and category (type 4) must be excluded
    expect(data).toHaveLength(2)
    const ids = data.map((c: { id: string }) => c.id)
    expect(ids).toContain("1")
    expect(ids).toContain("2")
    // Categories should be resolved to their name
    expect(data.find((c: { id: string }) => c.id === "1").category).toBe("Community")
    expect(data.find((c: { id: string }) => c.id === "2").category).toBe("Community")
  })

  it("sorts channels by position within results", async () => {
    const { auth } = await import("@/lib/auth")
    vi.mocked(auth).mockResolvedValueOnce({ user: { name: "admin" } } as any)
    const rawChannels = [
      { id: "b", name: "beta", type: 0, parent_id: null, position: 2 },
      { id: "a", name: "alpha", type: 0, parent_id: null, position: 1 },
    ]
    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(rawChannels) })
    const { GET } = await import("@/app/api/discord/channels/route")
    const res = await GET()
    const data = await res.json()
    expect(data[0].id).toBe("a")
    expect(data[1].id).toBe("b")
  })
})
