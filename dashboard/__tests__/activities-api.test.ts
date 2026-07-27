// @vitest-environment node

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"


const mocks = vi.hoisted(() => ({
  auth: vi.fn(),
  rateLimitCheck: vi.fn(),
  from: vi.fn(),
  rpc: vi.fn(),
  fetch: vi.fn(),
}))

vi.mock("@/lib/auth", () => ({ auth: mocks.auth }))
vi.mock("@/lib/rate-limit", () => ({ rateLimitCheck: mocks.rateLimitCheck }))
vi.mock("@/lib/supabase", () => ({
  supabase: { from: mocks.from, rpc: mocks.rpc },
}))

type DbResult = { data?: unknown; error?: { message: string; code?: string } | null }

function query(result: DbResult, events?: string[], event?: string) {
  const builder: Record<string, any> = {}
  for (const method of [
    "select",
    "eq",
    "order",
    "limit",
    "single",
    "insert",
    "update",
    "delete",
    "or",
  ]) {
    builder[method] = vi.fn(() => builder)
  }
  builder.then = (resolve: (value: DbResult) => unknown) => {
    if (events && event) events.push(event)
    return Promise.resolve(resolve(result))
  }
  return builder
}

function request(path: string, method = "GET", body?: unknown) {
  return new Request(`https://dashboard.test${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

const questions = [
  {
    id: "q1",
    campaign_id: "c1",
    field_key: "fp_id",
    position: 1,
    label: "FortunePurple ID",
    input_style: "short",
    required: true,
    placeholder: null,
    min_length: 1,
    max_length: 100,
    prefill_discord_username: false,
    is_participant_key: true,
  },
]

const campaign = {
  id: "c1",
  name: "Campaign",
  status: "draft",
  winner_limit: 2,
  discord_guild_id: "1498581314495053834",
  discord_channel_id: "1519235126201024633",
  discord_message_id: null,
  embed_title: "Join",
  embed_description: "Click below",
  image_url: null,
  color: 0xff9933,
  button_label: "Join Activity",
  modal_title: "Survey",
  winner_message: "Winner **{code}**",
  sold_out_message: "Sold out",
  closed_message: "Closed",
  ends_at: "2099-08-01T12:00:00.000Z",
  created_at: "2026-07-27T00:00:00Z",
  updated_at: "2026-07-27T00:00:00Z",
  published_at: null,
  closed_at: null,
  questions,
}


describe("activity APIs", () => {
  beforeEach(() => {
    mocks.auth.mockResolvedValue({ user: { name: "admin" } })
    mocks.rateLimitCheck.mockResolvedValue(null)
    vi.stubGlobal("fetch", mocks.fetch)
    process.env.DISCORD_BOT_TOKEN = "bot-token"
    process.env.DISCORD_GUILD_ID = "guild"
  })

  afterEach(() => {
    vi.clearAllMocks()
    vi.unstubAllGlobals()
    delete process.env.DISCORD_BOT_TOKEN
    delete process.env.DISCORD_GUILD_ID
  })

  it("rejects unauthenticated campaign creation", async () => {
    mocks.auth.mockResolvedValueOnce(null)
    const { POST } = await import("@/app/api/activities/route")

    const response = await POST(request("/api/activities", "POST", campaign) as any)

    expect(response.status).toBe(401)
    expect(mocks.from).not.toHaveBeenCalled()
  })

  it("short-circuits activity APIs when rate limited", async () => {
    mocks.rateLimitCheck.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: "Too many requests" }), {
        status: 429,
      })
    )
    const { GET } = await import("@/app/api/activities/route")

    const response = await GET(request("/api/activities") as any)

    expect(response.status).toBe(429)
    expect(mocks.auth).not.toHaveBeenCalled()
    expect(mocks.from).not.toHaveBeenCalled()
  })

  it("allows deletion only while a campaign is a draft", async () => {
    mocks.from.mockReturnValueOnce(
      query({ data: { ...campaign, status: "active" }, error: null })
    )
    const { DELETE } = await import("@/app/api/activities/[id]/route")

    const response = await DELETE(
      request("/api/activities/c1", "DELETE") as any,
      { params: { id: "c1" } }
    )

    expect(response.status).toBe(409)
    expect(await response.json()).toEqual({
      error: "只能删除草稿状态的活动",
    })
    expect(mocks.from).toHaveBeenCalledTimes(1)
  })

  it("does not delete a draft when publication wins the race", async () => {
    mocks.from
      .mockReturnValueOnce(query({ data: campaign, error: null }))
      .mockReturnValueOnce(query({ data: [], error: null }))
    const { DELETE } = await import("@/app/api/activities/[id]/route")

    const response = await DELETE(
      request("/api/activities/c1", "DELETE") as any,
      { params: { id: "c1" } }
    )

    expect(response.status).toBe(409)
  })

  it("deletes an orphan Discord message when activation save fails", async () => {
    mocks.from
      .mockReturnValueOnce(query({ data: campaign, error: null }))
      .mockReturnValueOnce(
        query({
          data: [
            { id: "code1", position: 1, code: "A" },
            { id: "code2", position: 2, code: "B" },
          ],
          error: null,
        })
      )
    mocks.rpc.mockReturnValueOnce(
      query({ data: null, error: { message: "activation failed" } })
    )
    mocks.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: "discord-message" }),
      })
      .mockResolvedValueOnce({ ok: true })
    const { POST } = await import("@/app/api/activities/[id]/publish/route")

    const response = await POST(
      request("/api/activities/c1/publish", "POST") as any,
      { params: { id: "c1" } }
    )

    expect(response.status).toBe(500)
    expect(mocks.fetch).toHaveBeenNthCalledWith(
      2,
      "https://discord.com/api/v10/channels/1519235126201024633/messages/discord-message",
      expect.objectContaining({ method: "DELETE" })
    )
  })

  it("rejects publication when the activity has no end time", async () => {
    const noEnd = { ...campaign, ends_at: null }
    mocks.from.mockReturnValueOnce(query({ data: noEnd, error: null }))
    const { POST } = await import("@/app/api/activities/[id]/publish/route")

    const response = await POST(
      request("/api/activities/c1/publish", "POST") as any,
      { params: { id: "c1" } }
    )

    expect(response.status).toBe(400)
    expect(await response.json()).toEqual({
      error: "活动结束时间必须晚于当前时间",
    })
    expect(mocks.fetch).not.toHaveBeenCalled()
  })

  it("deletes its Discord message when another publish wins activation", async () => {
    mocks.from
      .mockReturnValueOnce(query({ data: campaign, error: null }))
      .mockReturnValueOnce(
        query({
          data: [
            { id: "code1", position: 1, code: "A" },
            { id: "code2", position: 2, code: "B" },
          ],
          error: null,
        })
      )
    mocks.rpc.mockReturnValueOnce(
      query({
        data: [{ outcome: "already_active", existing_message_id: "winner-message" }],
        error: null,
      })
    )
    mocks.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: "orphan-message" }),
      })
      .mockResolvedValueOnce({ ok: true })
    const { POST } = await import("@/app/api/activities/[id]/publish/route")

    const response = await POST(
      request("/api/activities/c1/publish", "POST") as any,
      { params: { id: "c1" } }
    )

    expect(response.status).toBe(409)
    expect(mocks.fetch).toHaveBeenNthCalledWith(
      2,
      "https://discord.com/api/v10/channels/1519235126201024633/messages/orphan-message",
      expect.objectContaining({ method: "DELETE" })
    )
  })

  it("deletes its Discord message when the draft revision changed", async () => {
    mocks.from
      .mockReturnValueOnce(query({ data: { ...campaign, revision: 7 }, error: null }))
      .mockReturnValueOnce(
        query({
          data: [
            { id: "code1", position: 1, code: "A" },
            { id: "code2", position: 2, code: "B" },
          ],
          error: null,
        })
      )
    mocks.rpc.mockReturnValueOnce(
      query({
        data: [{ outcome: "stale_draft", existing_message_id: null }],
        error: null,
      })
    )
    mocks.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: "stale-message" }),
      })
      .mockResolvedValueOnce({ ok: true })
    const { POST } = await import("@/app/api/activities/[id]/publish/route")

    const response = await POST(
      request("/api/activities/c1/publish", "POST") as any,
      { params: { id: "c1" } }
    )

    expect(response.status).toBe(409)
    expect(await response.json()).toEqual({
      error: "活动配置已发生变化，请刷新后重试",
    })
    expect(mocks.rpc).toHaveBeenCalledWith(
      "activate_activity_campaign",
      expect.objectContaining({ p_expected_revision: 7 })
    )
    expect(mocks.fetch).toHaveBeenNthCalledWith(
      2,
      "https://discord.com/api/v10/channels/1519235126201024633/messages/stale-message",
      expect.objectContaining({ method: "DELETE" })
    )
  })

  it("saves draft questions through one locking RPC", async () => {
    mocks.from.mockReturnValueOnce(query({ data: campaign, error: null }))
    mocks.rpc.mockReturnValueOnce(
      query({ data: campaign, error: null })
    )
    const { PUT } = await import("@/app/api/activities/[id]/route")

    const response = await PUT(
      request("/api/activities/c1", "PUT", campaign) as any,
      { params: { id: "c1" } }
    )

    expect(response.status).toBe(200)
    expect(mocks.rpc).toHaveBeenCalledWith(
      "save_activity_draft",
      expect.objectContaining({ p_campaign_id: "c1" })
    )
  })

  it("replaces a draft code pool through one locking RPC", async () => {
    mocks.from.mockReturnValueOnce(query({ data: campaign, error: null }))
    mocks.rpc.mockReturnValueOnce(
      query({ data: 2, error: null })
    )
    const { PUT } = await import("@/app/api/activities/[id]/codes/route")

    const response = await PUT(
      request("/api/activities/c1/codes", "PUT", { codes: ["A", "B"] }) as any,
      { params: { id: "c1" } }
    )

    expect(response.status).toBe(200)
    expect(mocks.rpc).toHaveBeenCalledWith("replace_activity_codes", {
      p_campaign_id: "c1",
      p_codes: ["A", "B"],
    })
  })

  it("returns a Chinese error when reward codes cannot be loaded", async () => {
    mocks.from.mockReturnValueOnce(
      query({ data: null, error: { message: "database unavailable" } })
    )
    const { GET } = await import("@/app/api/activities/[id]/codes/route")

    const response = await GET(
      request("/api/activities/c1/codes") as any,
      { params: { id: "c1" } }
    )

    expect(response.status).toBe(500)
    expect(await response.json()).toEqual({ error: "福利码加载失败" })
  })

  it("closes in the database before disabling the Discord button", async () => {
    const events: string[] = []
    const active = {
      ...campaign,
      status: "active",
      discord_message_id: "message",
    }
    mocks.from
      .mockReturnValueOnce(query({ data: active, error: null }))
      .mockReturnValueOnce(
        query({ data: { ...active, status: "closed" }, error: null }, events, "db-closed")
      )
    mocks.fetch.mockImplementationOnce(async (_url, options) => {
      events.push("discord-disabled")
      const body = JSON.parse(options.body)
      expect(body.components[0].components[0].disabled).toBe(true)
      return { ok: true }
    })
    const { POST } = await import("@/app/api/activities/[id]/close/route")

    const response = await POST(
      request("/api/activities/c1/close", "POST") as any,
      { params: { id: "c1" } }
    )

    expect(response.status).toBe(200)
    expect(events).toEqual(["db-closed", "discord-disabled"])
  })

  it("retries disabling the Discord button for an already closed activity", async () => {
    const closed = {
      ...campaign,
      status: "closed",
      discord_message_id: "message",
    }
    mocks.from.mockReturnValueOnce(query({ data: closed, error: null }))
    mocks.fetch.mockResolvedValueOnce({ ok: true })
    const { POST } = await import("@/app/api/activities/[id]/close/route")

    const response = await POST(
      request("/api/activities/c1/close", "POST") as any,
      { params: { id: "c1" } }
    )

    expect(response.status).toBe(200)
    expect(mocks.fetch).toHaveBeenCalledOnce()
    expect(await response.json()).toMatchObject({ discord_updated: true })
  })

  it("returns copied question IDs belonging to the new campaign", async () => {
    const copiedCampaign = { ...campaign, id: "copy-campaign" }
    const copiedQuestions = [
      { ...questions[0], id: "copy-question", campaign_id: "copy-campaign" },
    ]
    mocks.from
      .mockReturnValueOnce(query({ data: campaign, error: null }))
      .mockReturnValueOnce(query({ data: copiedCampaign, error: null }))
      .mockReturnValueOnce(query({ data: copiedQuestions, error: null }))
    const { POST } = await import("@/app/api/activities/[id]/copy/route")

    const response = await POST(
      request("/api/activities/c1/copy", "POST") as any,
      { params: { id: "c1" } }
    )
    const result = await response.json()

    expect(response.status).toBe(201)
    expect(result.questions).toEqual(copiedQuestions)
    expect(result.questions[0].id).not.toBe(questions[0].id)
    expect(result.questions[0].campaign_id).toBe("copy-campaign")
  })

  it("exports a UTF-8 CSV attachment", async () => {
    mocks.from
      .mockReturnValueOnce(query({ data: questions, error: null }))
      .mockReturnValueOnce(
        query({
          data: [
            {
              id: "s1",
              campaign_id: "c1",
              discord_user_id: "1",
              discord_username: "Alice",
              answers: { fp_id: "FP1" },
              participant_key_normalized: "fp1",
              outcome: "winner",
              submitted_at: "2026-07-27T01:00:00Z",
              reward_code: { code: "CODE1" },
            },
          ],
          error: null,
        })
      )
    const { GET } = await import(
      "@/app/api/activities/[id]/submissions/export/route"
    )

    const response = await GET(
      request("/api/activities/c1/submissions/export") as any,
      { params: { id: "c1" } }
    )

    expect(response.status).toBe(200)
    expect(response.headers.get("content-type")).toContain("text/csv")
    expect(response.headers.get("content-disposition")).toContain("attachment")
    expect(
      Array.from(new Uint8Array(await response.arrayBuffer()).slice(0, 3))
    ).toEqual([0xef, 0xbb, 0xbf])
  })

  it("returns a Chinese error when CSV questions cannot be loaded", async () => {
    mocks.from.mockReturnValueOnce(
      query({ data: null, error: { message: "database unavailable" } })
    )
    const { GET } = await import(
      "@/app/api/activities/[id]/submissions/export/route"
    )

    const response = await GET(
      request("/api/activities/c1/submissions/export") as any,
      { params: { id: "c1" } }
    )

    expect(response.status).toBe(500)
    expect(await response.json()).toEqual({
      error: "问题配置加载失败，无法导出",
    })
  })
})
