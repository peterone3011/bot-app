// @vitest-environment node

import { describe, it, expect, vi, beforeEach } from "vitest"

vi.mock("@upstash/redis", () => ({
  Redis: { fromEnv: vi.fn(() => ({})) },
}))

const mockLimit = vi.fn().mockResolvedValue({ success: true })

vi.mock("@upstash/ratelimit", () => ({
  Ratelimit: class {
    constructor() {}
    static slidingWindow() { return {} }
    limit = mockLimit
  },
}))

describe("rateLimitCheck", () => {
  beforeEach(() => mockLimit.mockResolvedValue({ success: true }))

  it("returns null when request is within limit", async () => {
    const { rateLimitCheck } = await import("@/lib/rate-limit")
    const mockReq = {
      ip: "1.2.3.4",
      headers: { get: () => null },
    } as any
    const result = await rateLimitCheck(mockReq)
    expect(result).toBeNull()
  })

  it("returns 429 response when rate limit is exceeded", async () => {
    mockLimit.mockResolvedValueOnce({ success: false })
    const { rateLimitCheck } = await import("@/lib/rate-limit")
    const mockReq = { headers: { get: () => null } } as any
    const result = await rateLimitCheck(mockReq)
    expect(result).not.toBeNull()
    expect(result!.status).toBe(429)
  })

  it("returns null (fail-open) when Redis throws", async () => {
    mockLimit.mockRejectedValueOnce(new Error("Redis connection refused"))
    const { rateLimitCheck } = await import("@/lib/rate-limit")
    const mockReq = { headers: { get: () => null } } as any
    const result = await rateLimitCheck(mockReq)
    expect(result).toBeNull()
  })
})
