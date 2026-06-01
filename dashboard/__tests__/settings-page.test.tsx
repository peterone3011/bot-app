// @vitest-environment jsdom

import { render, screen, waitFor } from "@testing-library/react"
import { describe, it, expect, vi, afterEach } from "vitest"
import SettingsPage from "@/app/dashboard/settings/page"

describe("SettingsPage – save buttons after load failure", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it("keeps save button disabled when /api/settings returns an error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) })
    )

    render(<SettingsPage />)

    await waitFor(() =>
      expect(screen.getByText(/加载失败，请刷新页面重试/)).toBeInTheDocument()
    )

    expect(screen.getByRole("button", { name: /^保存$/ })).toBeDisabled()
  })

  it("keeps save button disabled when /api/settings throws a network error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("Network error"))
    )

    render(<SettingsPage />)

    await waitFor(() =>
      expect(screen.getByText(/加载失败，请刷新页面重试/)).toBeInTheDocument()
    )

    expect(screen.getByRole("button", { name: /^保存$/ })).toBeDisabled()
  })

  it("enables save button when /api/settings loads successfully", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ roles_channel_name: "roles" }),
      })
    )

    render(<SettingsPage />)

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^保存$/ })).not.toBeDisabled()
    )
  })

  it("does not show image configuration section", () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }))

    render(<SettingsPage />)

    expect(screen.queryByText(/大奖播报配图/)).not.toBeInTheDocument()
    expect(screen.queryByText(/保存两张图片/)).not.toBeInTheDocument()
  })
})
