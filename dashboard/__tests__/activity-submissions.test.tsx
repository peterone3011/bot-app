// @vitest-environment jsdom

import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ActivitySubmissions } from "@/components/activity-submissions"
import type { ActivityQuestion } from "@/lib/types"


const questions: ActivityQuestion[] = [
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

const submissions = [
  {
    id: "s1",
    campaign_id: "c1",
    discord_user_id: "100",
    discord_username: "Alice",
    answers: { fp_id: "FP-1" },
    participant_key_normalized: "fp-1",
    outcome: "winner" as const,
    reward_code: "CODE-1",
    submitted_at: "2026-07-27T01:00:00Z",
  },
  {
    id: "s2",
    campaign_id: "c1",
    discord_user_id: "200",
    discord_username: "Bob",
    answers: { fp_id: "FP-2" },
    participant_key_normalized: "fp-2",
    outcome: "sold_out" as const,
    reward_code: null,
    submitted_at: "2026-07-27T02:00:00Z",
  },
]


describe("ActivitySubmissions", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it("searches Discord and FP ID and filters winners", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => submissions })
    )
    render(<ActivitySubmissions campaignId="c1" questions={questions} />)

    expect(await screen.findByText("Alice")).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("搜索提交记录"), {
      target: { value: "FP-2" },
    })
    expect(screen.queryByText("Alice")).toBeNull()
    expect(screen.getByText("Bob")).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("中奖状态筛选"), {
      target: { value: "winner" },
    })
    expect(screen.queryByText("Bob")).toBeNull()
  })

  it("provides the authenticated CSV export endpoint", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => submissions })
    )
    render(<ActivitySubmissions campaignId="c1" questions={questions} />)

    const link = await screen.findByRole("link", { name: "导出 CSV" })
    expect(link).toHaveAttribute(
      "href",
      "/api/activities/c1/submissions/export"
    )
  })

  it("shows Chinese management labels without translating player answers", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => submissions })
    )
    render(<ActivitySubmissions campaignId="c1" questions={questions} />)

    expect(await screen.findByText("中奖")).toBeInTheDocument()
    expect(screen.getAllByText("未中奖（已发完）")).toHaveLength(2)
    expect(screen.getByText("FortunePurple ID")).toBeInTheDocument()
    expect(screen.getByText("FP-1")).toBeInTheDocument()
  })
})
