import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"

describe("supabase client", () => {
  const originalUrl = process.env.SUPABASE_URL
  const originalKey = process.env.SUPABASE_SERVICE_KEY

  beforeEach(() => {
    vi.resetModules()
    process.env.SUPABASE_URL = "https://example.supabase.co"
    process.env.SUPABASE_SERVICE_KEY = "service-key"
  })

  afterEach(() => {
    process.env.SUPABASE_URL = originalUrl
    process.env.SUPABASE_SERVICE_KEY = originalKey
  })

  it("throws if SUPABASE_URL is missing", async () => {
    delete process.env.SUPABASE_URL
    await expect(import("@/lib/supabase")).rejects.toThrow("Missing env: SUPABASE_URL")
  })

  it("throws if SUPABASE_SERVICE_KEY is missing", async () => {
    delete process.env.SUPABASE_SERVICE_KEY
    await expect(import("@/lib/supabase")).rejects.toThrow("Missing env: SUPABASE_SERVICE_KEY")
  })
})
