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
    <input aria-label="Discord Channel" value={value} disabled={disabled} readOnly />
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

    fireEvent.click(screen.getByRole("button", { name: "Add Question" }))
    expect(screen.getAllByLabelText("Question Label")).toHaveLength(2)
    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/activities/c1",
        expect.objectContaining({ method: "PUT" })
      )
    )
  })

  it("locks channel, end time, winner limit, modal title and questions after publish", () => {
    render(<ActivityEditor initial={{ ...campaign, status: "active" }} />)

    expect(screen.getByLabelText("Discord Channel")).toBeDisabled()
    expect(screen.getByLabelText("Activity End Time")).toBeDisabled()
    expect(screen.getByLabelText("Winner Limit")).toBeDisabled()
    expect(screen.getByLabelText("Modal Title")).toBeDisabled()
    expect(screen.queryByRole("button", { name: "Add Question" })).toBeNull()
    expect(screen.getByLabelText("Embed Title")).not.toBeDisabled()
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
          warning: "Activity closed, but Discord message update failed",
        }),
      })
    )
    render(<ActivityEditor initial={{ ...campaign, status: "active" }} />)

    fireEvent.click(screen.getByRole("button", { name: "Close" }))

    expect(
      await screen.findByText("Activity closed, but Discord message update failed")
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Retry Discord Update" })
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
      screen.getByRole("button", { name: "Retry Discord Update" })
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

    expect(screen.queryByRole("button", { name: "Save" })).toBeNull()
    expect(screen.getByLabelText("Embed Title")).toBeDisabled()
    expect(screen.getByLabelText("Winner Reply")).toBeDisabled()
  })

  it("recovers after a network error while deleting a draft", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true))
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")))
    render(<ActivityEditor initial={campaign} />)

    const deleteButton = screen.getByRole("button", { name: "Delete" })
    fireEvent.click(deleteButton)

    expect(await screen.findByText("Network error")).toBeInTheDocument()
    expect(deleteButton).not.toBeDisabled()
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

    const textarea = await screen.findByLabelText("Reward Codes")
    fireEvent.change(textarea, { target: { value: "CODE-1\nCODE-2" } })
    expect(screen.getByText("2 / 20")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Import Codes" }))

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

    expect(await screen.findByLabelText("Reward Codes")).toBeDisabled()
    expect(screen.queryByRole("button", { name: "Import Codes" })).toBeNull()
  })
})
