// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { ActivityCampaign } from "@/lib/types"

const { state } = vi.hoisted(() => ({
  state: {
    campaign: null as ActivityCampaign | null,
    router: { push: vi.fn(), refresh: vi.fn() },
  },
}))

vi.mock("next/navigation", () => ({
  notFound: vi.fn(),
  useRouter: () => state.router,
}))

vi.mock("@/lib/supabase", () => ({
  supabase: {
    from: () => ({
      select: () => ({
        eq: () => ({
          single: async () => ({
            data: state.campaign && {
              ...state.campaign,
              activity_questions: state.campaign.questions,
            },
            error: null,
          }),
        }),
      }),
    }),
  },
}))

vi.mock("@/components/channel-select", () => ({
  ChannelSelect: ({ value, disabled }: { value: string; disabled?: boolean }) => (
    <input aria-label="Discord channel" value={value} disabled={disabled} readOnly />
  ),
}))

import ActivityPage from "@/app/dashboard/activities/[id]/page"

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
  created_at: "2026-07-28T00:00:00.000Z",
  updated_at: "2026-07-28T00:00:00.000Z",
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

async function detailPage() {
  return ActivityPage({ params: { id: "c1" } })
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve
  })
  return { promise, resolve }
}

describe("activity detail refresh", () => {
  afterEach(() => {
    state.campaign = null
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it("keeps draft mutation controls disabled while a same-ID revision refresh arrives during publish save", async () => {
    state.campaign = {
      ...campaign,
      revision: 1,
      updated_at: "2026-07-28T01:00:00.000Z",
    }
    const response = deferred<{ ok: boolean; json: () => Promise<ActivityCampaign> }>()
    const fetchMock = vi.fn().mockReturnValue(response.promise)
    vi.stubGlobal("confirm", vi.fn(() => true))
    vi.stubGlobal("fetch", fetchMock)

    const view = render(await detailPage())
    fireEvent.click(screen.getByRole("button", { name: "\u53d1\u5e03\u6d3b\u52a8" }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(screen.getByRole("button", { name: "\u4fdd\u5b58" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "\u53d1\u5e03\u6d3b\u52a8" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "\u5220\u9664\u8349\u7a3f" })).toBeDisabled()

    state.campaign = {
      ...campaign,
      revision: 2,
      updated_at: "2026-07-28T02:00:00.000Z",
    }
    view.rerender(await detailPage())

    expect(screen.getByRole("button", { name: "\u4fdd\u5b58" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "\u53d1\u5e03\u6d3b\u52a8" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "\u5220\u9664\u8349\u7a3f" })).toBeDisabled()
  })

  it("keeps a close warning visible after a same-ID closed refresh", async () => {
    const warning = "\u6d3b\u52a8\u5df2\u5173\u95ed\uff0c\u4f46 Discord \u6d88\u606f\u66f4\u65b0\u5931\u8d25"
    state.campaign = {
      ...campaign,
      status: "active",
      revision: 1,
      updated_at: "2026-07-28T01:00:00.000Z",
    }
    vi.stubGlobal("confirm", vi.fn(() => true))
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ ok: true, discord_updated: false, warning }),
      })
    )

    const view = render(await detailPage())
    fireEvent.click(screen.getByRole("button", { name: "\u5173\u95ed\u6d3b\u52a8" }))
    expect(await screen.findByText(warning)).toBeInTheDocument()

    state.campaign = {
      ...campaign,
      status: "closed",
      revision: 2,
      updated_at: "2026-07-28T02:00:00.000Z",
    }
    view.rerender(await detailPage())

    expect(screen.getByText(warning)).toBeInTheDocument()
  })
})
