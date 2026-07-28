// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ActivityEditor } from "@/components/activity-editor"
import { ActivityCodePool } from "@/components/activity-code-pool"
import type { ActivityCampaign } from "@/lib/types"


vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}))

vi.mock("@/components/channel-select", () => ({
  ChannelSelect: ({ value, disabled }: { value: string; disabled?: boolean }) => (
    <input aria-label="Discord 频道" value={value} disabled={disabled} readOnly />
  ),
}))

const campaign: ActivityCampaign = {
  id: "c1",
  name: "Test Activity",
  status: "draft",
  winner_limit: 20,
  discord_guild_id: "1498581314495053834",
  discord_channel_id: "1519235126201024633",
  discord_message_id: null,
  embed_title: "Join us",
  embed_description: "Click the button",
  image_url: null,
  color: 0xff9933,
  button_label: "Join Activity",
  modal_title: "Survey",
  winner_message: "Winner **{code}**",
  sold_out_message: "Sold out",
  closed_message: "Closed",
  ends_at: "2099-08-01T12:00:00.000Z",
  created_at: "",
  updated_at: "",
  published_at: null,
  closed_at: null,
  questions: [
    {
      id: "q1",
      campaign_id: "c1",
      field_key: "fp_id",
      position: 1,
      label: "FortunePurple ID",
      input_style: "short",
      required: true,
      placeholder: "",
      min_length: 1,
      max_length: 100,
      prefill_discord_username: false,
      is_participant_key: true,
    },
  ],
}


describe("ActivityEditor", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it("allows a draft to add questions and save", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => campaign,
    })
    vi.stubGlobal("fetch", fetchMock)
    render(<ActivityEditor initial={campaign} />)

    fireEvent.click(screen.getByRole("button", { name: "添加问题" }))
    expect(screen.getAllByLabelText("问题标题")).toHaveLength(2)
    fireEvent.click(screen.getByRole("button", { name: "保存" }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/activities/c1",
        expect.objectContaining({ method: "PUT" })
      )
    )
  })

  it("locks channel, end time, winner limit, modal title and questions after publish", () => {
    render(<ActivityEditor initial={{ ...campaign, status: "active" }} />)

    expect(screen.getByLabelText("Discord 频道")).toBeDisabled()
    expect(screen.getByLabelText("活动结束时间")).toBeDisabled()
    expect(screen.getByLabelText("中奖人数")).toBeDisabled()
    expect(screen.getByLabelText("弹窗标题")).toBeDisabled()
    expect(screen.queryByRole("button", { name: "添加问题" })).toBeNull()
    expect(screen.getByLabelText("消息标题")).not.toBeDisabled()
  })

  it("shows a warning when closing succeeds but Discord cannot be updated", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true))
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ok: true,
          discord_updated: false,
          warning: "活动已关闭，但 Discord 消息更新失败",
        }),
      })
    )
    render(<ActivityEditor initial={{ ...campaign, status: "active" }} />)

    fireEvent.click(screen.getByRole("button", { name: "关闭活动" }))

    expect(
      await screen.findByText("活动已关闭，但 Discord 消息更新失败")
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "重试更新 Discord" })
    ).toBeInTheDocument()
  })

  it("lets a closed activity retry the Discord button update", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true))
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, discord_updated: true }),
    })
    vi.stubGlobal("fetch", fetchMock)
    render(<ActivityEditor initial={{ ...campaign, status: "closed" }} />)

    fireEvent.click(
      screen.getByRole("button", { name: "重试更新 Discord" })
    )

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/activities/c1/close",
        expect.objectContaining({ method: "POST" })
      )
    )
  })

  it("does not offer editing or save controls for a closed activity", () => {
    render(<ActivityEditor initial={{ ...campaign, status: "closed" }} />)

    expect(screen.queryByRole("button", { name: "保存" })).toBeNull()
    expect(screen.getByLabelText("消息标题")).toBeDisabled()
    expect(screen.getByLabelText("中奖回复")).toBeDisabled()
  })

  it("recovers after a network error while deleting a draft", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true))
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")))
    render(<ActivityEditor initial={campaign} />)

    const deleteButton = screen.getByRole("button", { name: "删除草稿" })
    fireEvent.click(deleteButton)

    expect(await screen.findByText("网络错误")).toBeInTheDocument()
    expect(deleteButton).not.toBeDisabled()
  })

  it("uses Chinese management labels while preserving player-facing English", () => {
    render(<ActivityEditor initial={campaign} />)

    expect(screen.getByText("Discord 消息")).toBeInTheDocument()
    expect(screen.getByText("玩家填写问题")).toBeInTheDocument()
    expect(screen.getByText("仅玩家可见回复")).toBeInTheDocument()
    expect(screen.getByDisplayValue("Join Activity")).toBeInTheDocument()
    expect(screen.getByDisplayValue("Survey")).toBeInTheDocument()
    expect(screen.getByDisplayValue("Winner **{code}**")).toBeInTheDocument()
    expect(screen.queryByText("Discord Message")).toBeNull()
  })

  it("replaces local state when refreshed server props identify a different campaign", () => {
    const { rerender } = render(
      <ActivityEditor
        initial={{
          ...campaign,
          id: "copy",
          name: "Old Copy",
          status: "draft",
          revision: 1,
          updated_at: "2026-07-28T01:00:00Z",
        }}
      />
    )

    rerender(
      <ActivityEditor
        initial={{
          ...campaign,
          id: "active",
          name: "Current Activity",
          status: "active",
          revision: 5,
          updated_at: "2026-07-28T02:00:00Z",
        }}
      />
    )

    expect(screen.getByDisplayValue("Current Activity")).toBeInTheDocument()
    expect(screen.queryByDisplayValue("Old Copy")).toBeNull()
    expect(screen.getByText("\u8fdb\u884c\u4e2d")).toBeInTheDocument()
  })

  it("shows an elapsed active campaign as expired and offers to disable its Discord button", () => {
    render(
      <ActivityEditor
        initial={{
          ...campaign,
          status: "active",
          ends_at: "2020-01-01T00:00:00.000Z",
        }}
      />
    )

    expect(screen.getByText("\u5df2\u7ed3\u675f")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "\u7981\u7528 Discord \u6309\u94ae" })
    ).toBeInTheDocument()
  })
})


describe("ActivityCodePool", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it("shows exact code progress and imports draft codes", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ count: 2 }) })
    vi.stubGlobal("fetch", fetchMock)
    render(<ActivityCodePool campaign={campaign} />)

    const textarea = await screen.findByLabelText("福利码")
    fireEvent.change(textarea, { target: { value: "CODE-1\nCODE-2" } })
    expect(screen.getByText("2 / 20")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "导入福利码" }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith(
        "/api/activities/c1/codes",
        expect.objectContaining({ method: "PUT" })
      )
    )
  })

  it("is read-only after publish", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [{ position: 1, code: "CODE-1" }],
      })
    )
    render(<ActivityCodePool campaign={{ ...campaign, status: "active" }} />)

    expect(await screen.findByLabelText("福利码")).toBeDisabled()
    expect(screen.queryByRole("button", { name: "导入福利码" })).toBeNull()
  })
})
