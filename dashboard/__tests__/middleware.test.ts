import { describe, it, expect, vi } from "vitest"

// The middleware uses next-auth/middleware which is difficult to unit test
// directly. We verify the matcher config covers the right paths.
describe("middleware config", () => {
  it("protects dashboard and API routes", async () => {
    const { config } = await import("@/middleware")
    const matcher = config.matcher as string[]
    expect(matcher).toContain("/dashboard/:path*")
    expect(matcher.some((m) => m.includes("/api/embeds"))).toBe(true)
    expect(matcher.some((m) => m.includes("/api/discord"))).toBe(true)
    expect(matcher.some((m) => m.includes("/api/roles"))).toBe(true)
    expect(matcher.some((m) => m.includes("/api/activities"))).toBe(true)
  })
})
