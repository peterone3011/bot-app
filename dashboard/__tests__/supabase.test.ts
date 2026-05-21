import { describe, it, expect } from "vitest"

describe("supabase client", () => {
  it("throws if SUPABASE_URL is missing", async () => {
    const original = process.env.SUPABASE_URL
    delete process.env.SUPABASE_URL
    await expect(import("@/lib/supabase")).rejects.toThrow()
    process.env.SUPABASE_URL = original
  })
})
