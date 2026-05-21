import { describe, it, expect } from "vitest"

describe("supabase client", () => {
  it("throws if SUPABASE_URL is missing", async () => {
    const original = process.env.SUPABASE_URL
    delete process.env.SUPABASE_URL
    await expect(import("@/lib/supabase")).rejects.toThrow()
    process.env.SUPABASE_URL = original
  })

  it("throws if SUPABASE_SERVICE_KEY is missing", async () => {
    const original = process.env.SUPABASE_SERVICE_KEY
    delete process.env.SUPABASE_SERVICE_KEY
    await expect(import("@/lib/supabase")).rejects.toThrow()
    process.env.SUPABASE_SERVICE_KEY = original
  })
})
