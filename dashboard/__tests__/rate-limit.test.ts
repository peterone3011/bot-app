import { describe, it, expect, vi, beforeEach } from "vitest"

vi.mock("@upstash/redis", () => ({
  Redis: { fromEnv: vi.fn(() => ({})) },
}))

vi.mock("@upstash/ratelimit", () => ({
  Ratelimit: class {
    constructor() {}
    static slidingWindow() { return {} }
    async limit(_ip: string) { return { success: true } }
  },
}))

describe("rateLimitCheck", () => {
  it("returns null when request is within limit", async () => {
    const { rateLimitCheck } = await import("@/lib/rate-limit")
    const mockReq = {
      ip: "1.2.3.4",
      headers: { get: () => null },
    } as any
    const result = await rateLimitCheck(mockReq)
    expect(result).toBeNull()
  })
})
