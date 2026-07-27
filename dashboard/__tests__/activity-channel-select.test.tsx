// @vitest-environment jsdom

import { render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ChannelSelect } from "@/components/channel-select"


describe("ChannelSelect", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it("exposes a Chinese accessible label while preserving Discord channel names", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          { id: "123", name: "bot-commands", category: "Private" },
        ],
      })
    )

    render(<ChannelSelect value="" onChange={vi.fn()} />)

    const trigger = await screen.findByLabelText("Discord 频道")
    expect(trigger).toBeInTheDocument()
    expect(screen.getByText("选择 Discord 频道")).toBeInTheDocument()
  })
})
