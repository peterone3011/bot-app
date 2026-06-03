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
