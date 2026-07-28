// @vitest-environment jsdom

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ActivityList as ActivityListComponent } from "@/components/activity-list"
import type { ActivityCampaign } from "@/lib/types"


const push = vi.fn()

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
}))

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a data-testid="next-link-prefetch" href={href}>{children}</a>
  ),
}))

function ActivityList({
  campaigns,
  renderedAtMs = Date.now(),
}: {
  campaigns: ActivityCampaign[]
  renderedAtMs?: number
}) {
  return <ActivityListComponent campaigns={campaigns} renderedAtMs={renderedAtMs} />
}

describe("ActivityList", () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it("creates a draft from a Chinese admin form with English player defaults", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: "campaign-1" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    render(<ActivityList campaigns={[]} />)

    fireEvent.change(screen.getByPlaceholderText("输入活动名称"), {
      target: { value: "Summer Event" },
    })
    fireEvent.click(screen.getByRole("button", { name: "创建草稿" }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    const request = fetchMock.mock.calls[0][1]
    const body = JSON.parse(request.body)
    expect(body.button_label).toBe("Join Activity")
    expect(body.modal_title).toBe("Activity Entry")
    expect(body.winner_message).toContain("Congratulations!")
    expect(body.sold_out_message).toBe(
      "Sorry, all reward codes have been claimed. Please keep following our server—more events are coming soon!"
    )
    expect(body.closed_message).toBe(
      "This activity has ended. Please stay tuned for more events."
    )
    expect(body.questions[0].label).toBe("Discord Username")
    expect(body.questions[0].placeholder).toBe("Your Discord username")
    expect(screen.getByText("暂无活动")).toBeInTheDocument()
  })

  it("shows Chinese status and counters", () => {
    render(
      <ActivityList
        campaigns={[
          {
            id: "c1",
            name: "English Campaign Name",
            status: "active",
            color: 0xff9933,
            code_count: 20,
            submission_count: 8,
          } as any,
        ]}
      />
    )

    expect(screen.getByText("进行中")).toBeInTheDocument()
    expect(screen.getByText("20 个福利码 · 8 条提交")).toBeInTheDocument()
    expect(screen.getByText("English Campaign Name")).toBeInTheDocument()
  })

  it("shows an elapsed active campaign as expired with a native detail anchor", () => {
    render(
      <ActivityList
        campaigns={[
          {
            id: "expired-campaign",
            name: "Expired Campaign",
            status: "active",
            ends_at: "2020-01-01T00:00:00.000Z",
            color: 0xff9933,
          } as any,
        ]}
      />
    )

    expect(screen.getByText("\u5df2\u7ed3\u675f")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Expired Campaign/ })).toHaveAttribute(
      "href",
      "/dashboard/activities/expired-campaign"
    )
    expect(screen.queryByTestId("next-link-prefetch")).toBeNull()
  })

  it("changes an open list item to expired when its end time passes", () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-07-28T12:00:00.000Z"))
    const renderedAtMs = Date.now()

    render(
      <ActivityList
        renderedAtMs={renderedAtMs}
        campaigns={[
          {
            id: "expiring-campaign",
            name: "Expiring Campaign",
            status: "active",
            ends_at: "2026-07-28T12:00:01.000Z",
            color: 0xff9933,
          } as any,
        ]}
      />
    )

    expect(screen.getByText("\u8fdb\u884c\u4e2d")).toBeInTheDocument()

    act(() => vi.advanceTimersByTime(1000))

    expect(screen.getByText("\u5df2\u7ed3\u675f")).toBeInTheDocument()
  })

  it("reschedules a capped timeout until a far-future campaign expires", () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-07-28T12:00:00.000Z"))
    const endsAtMs = Date.parse("2026-08-28T12:00:00.000Z")

    render(
      <ActivityList
        renderedAtMs={Date.now()}
        campaigns={[
          {
            id: "far-future-campaign",
            name: "Far Future Campaign",
            status: "active",
            ends_at: new Date(endsAtMs).toISOString(),
            color: 0xff9933,
          } as any,
        ]}
      />
    )

    expect(screen.getByText("\u8fdb\u884c\u4e2d")).toBeInTheDocument()
    expect(vi.getTimerCount()).toBe(1)

    act(() => vi.advanceTimersByTime(2_147_483_647))

    expect(screen.getByText("\u8fdb\u884c\u4e2d")).toBeInTheDocument()
    expect(vi.getTimerCount()).toBe(1)

    act(() => vi.advanceTimersByTime(endsAtMs - Date.now()))

    expect(screen.getByText("\u5df2\u7ed3\u675f")).toBeInTheDocument()
    expect(vi.getTimerCount()).toBe(0)
  })

  it("clears the expiry timeout when the activity list unmounts", () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-07-28T12:00:00.000Z"))

    const { unmount } = render(
      <ActivityList
        renderedAtMs={Date.now()}
        campaigns={[
          {
            id: "unmounted-campaign",
            name: "Unmounted Campaign",
            status: "active",
            ends_at: "2026-07-28T12:00:01.000Z",
            color: 0xff9933,
          } as any,
        ]}
      />
    )

    expect(vi.getTimerCount()).toBe(1)

    unmount()

    expect(vi.getTimerCount()).toBe(0)
  })
})
