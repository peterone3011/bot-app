// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ActivityList } from "@/components/activity-list"


const push = vi.fn()

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
}))

describe("ActivityList", () => {
  afterEach(() => {
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

  it("shows an elapsed active campaign as expired and links directly to its detail page", () => {
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
  })
})
