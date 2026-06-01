// @vitest-environment jsdom

import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { describe, it, expect, vi, afterEach } from "vitest"
import { SitesList } from "@/components/sites-list"

const SAMPLE_SITES = [{ id: "s1", name: "Fortune Purple", display_order: 0 }]

describe("SitesList – rename validation", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it("does not call the API when renaming to an empty string", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal("fetch", mockFetch)

    render(<SitesList initialSites={SAMPLE_SITES} />)

    // Open rename mode
    fireEvent.click(screen.getByTitle("改名"))

    // Clear the input
    const input = screen.getByDisplayValue("Fortune Purple")
    fireEvent.change(input, { target: { value: "" } })

    // Confirm rename
    fireEvent.click(screen.getByTitle("保存"))

    // Should NOT have called the API
    await waitFor(() => expect(mockFetch).not.toHaveBeenCalled())
  })

  it("does not call the API when renaming to whitespace only", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal("fetch", mockFetch)

    render(<SitesList initialSites={SAMPLE_SITES} />)

    fireEvent.click(screen.getByTitle("改名"))
    const input = screen.getByDisplayValue("Fortune Purple")
    fireEvent.change(input, { target: { value: "   " } })
    fireEvent.click(screen.getByTitle("保存"))

    await waitFor(() => expect(mockFetch).not.toHaveBeenCalled())
  })
})
