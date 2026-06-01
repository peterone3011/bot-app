// @vitest-environment node

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

const mockUpsert = vi.fn()

vi.mock("@/lib/supabase", () => ({
  supabase: {
    from: vi.fn(() => ({
      select: vi.fn(() => ({ data: [], error: null })),
      upsert: mockUpsert,
    })),
  },
}))

vi.mock("@/lib/auth", () => ({
  auth: vi.fn(async () => ({ user: { id: "u1" } })),
}))

vi.mock("@/lib/rate-limit", () => ({
  rateLimitCheck: vi.fn(async () => null),
}))

function makePut(key: string, value: string) {
  return new Request("https://x.com/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  })
}

describe("PUT /api/settings – key whitelist", () => {
  beforeEach(() => {
    mockUpsert.mockResolvedValue({ error: null })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("accepts roles_channel_name", async () => {
    const { PUT } = await import("@/app/api/settings/route")
    const res = await PUT(makePut("roles_channel_name", "🔔roles") as any)
    expect(res.status).toBe(200)
  })

  it.each(["bigwin_image_1", "bigwin_image_2"])(
    "rejects '%s' – images are now hardcoded, not configurable",
    async (key) => {
      const { PUT } = await import("@/app/api/settings/route")
      const res = await PUT(makePut(key, "https://example.com/img.jpg") as any)
      expect(res.status).toBe(400)
      const body = await res.json()
      expect(body.error).toMatch(/not allowed/i)
    }
  )

  it.each(["arbitrary_key", "discord_token", "__proto__", "admin"])(
    "rejects disallowed key '%s' with 400",
    async (key) => {
      const { PUT } = await import("@/app/api/settings/route")
      const res = await PUT(makePut(key, "value") as any)
      expect(res.status).toBe(400)
      const body = await res.json()
      expect(body.error).toMatch(/not allowed/i)
    }
  )
})
