import { describe, it, expect, vi, beforeEach } from "vitest"
import { checkAdminRole } from "@/lib/auth"

// Mock global fetch
const mockFetch = vi.fn()
vi.stubGlobal("fetch", mockFetch)

beforeEach(() => vi.clearAllMocks())

describe("checkAdminRole", () => {
  it("returns true when user has the admin role", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ roles: ["111", "222", "ADMIN_ROLE_ID"] }),
    })
    process.env.DISCORD_GUILD_ID = "GUILD_ID"
    process.env.DISCORD_ADMIN_ROLE_ID = "ADMIN_ROLE_ID"
    const result = await checkAdminRole("access-token-123")
    expect(result).toBe(true)
    expect(mockFetch).toHaveBeenCalledWith(
      "https://discord.com/api/users/@me/guilds/GUILD_ID/member",
      expect.objectContaining({ headers: { Authorization: "Bearer access-token-123" } })
    )
  })

  it("returns false when user lacks the admin role", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ roles: ["111", "222"] }),
    })
    process.env.DISCORD_GUILD_ID = "GUILD_ID"
    process.env.DISCORD_ADMIN_ROLE_ID = "ADMIN_ROLE_ID"
    const result = await checkAdminRole("access-token-456")
    expect(result).toBe(false)
  })

  it("returns false when Discord API returns non-ok response", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false })
    process.env.DISCORD_GUILD_ID = "GUILD_ID"
    process.env.DISCORD_ADMIN_ROLE_ID = "ADMIN_ROLE_ID"
    const result = await checkAdminRole("bad-token")
    expect(result).toBe(false)
    expect(mockFetch).toHaveBeenCalledTimes(1)
  })

  it("returns false when env vars are missing", async () => {
    const savedGuild = process.env.DISCORD_GUILD_ID
    const savedRole = process.env.DISCORD_ADMIN_ROLE_ID
    delete process.env.DISCORD_GUILD_ID
    delete process.env.DISCORD_ADMIN_ROLE_ID
    const result = await checkAdminRole("any-token")
    expect(result).toBe(false)
    expect(mockFetch).not.toHaveBeenCalled()
    process.env.DISCORD_GUILD_ID = savedGuild
    process.env.DISCORD_ADMIN_ROLE_ID = savedRole
  })
})
