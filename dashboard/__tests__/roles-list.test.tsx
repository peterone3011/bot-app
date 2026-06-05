// @vitest-environment jsdom

import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { describe, it, expect, vi, afterEach } from "vitest"
import { RolesList } from "@/components/roles-list"

const SAMPLE_ROLES = [
  {
    id: "r1",
    label: "📢 Exclusive Updates",
    description: "Access our updates",
    display_order: 0,
    created_at: "",
    updated_at: "",
  },
  {
    id: "r2",
    label: "🎰Gaming Alerts",
    description: "Gaming notifications",
    display_order: 1,
    created_at: "",
    updated_at: "",
  },
]
const SINGLE_ROLE = [SAMPLE_ROLES[0]]

describe("RolesList", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it("does not call the API when saving an empty label", async () => {
    const mockFetch = vi.fn()
    vi.stubGlobal("fetch", mockFetch)

    render(<RolesList initialRoles={SAMPLE_ROLES} />)
    fireEvent.click(screen.getAllByTitle("编辑")[0])

    const labelInput = screen.getByDisplayValue("📢 Exclusive Updates")
    fireEvent.change(labelInput, { target: { value: "" } })
    fireEvent.click(screen.getByTitle("保存"))

    await waitFor(() => expect(mockFetch).not.toHaveBeenCalled())
  })

  it("does not call the API when label exceeds 100 characters", async () => {
    const mockFetch = vi.fn()
    vi.stubGlobal("fetch", mockFetch)

    render(<RolesList initialRoles={SAMPLE_ROLES} />)
    fireEvent.click(screen.getAllByTitle("编辑")[0])

    const labelInput = screen.getByDisplayValue("📢 Exclusive Updates")
    fireEvent.change(labelInput, { target: { value: "a".repeat(101) } })
    fireEvent.click(screen.getByTitle("保存"))

    await waitFor(() => expect(mockFetch).not.toHaveBeenCalled())
  })

  it("shows an error message when label exceeds 100 characters", async () => {
    vi.stubGlobal("fetch", vi.fn())

    render(<RolesList initialRoles={SAMPLE_ROLES} />)
    fireEvent.click(screen.getAllByTitle("编辑")[0])

    const labelInput = screen.getByDisplayValue("📢 Exclusive Updates")
    fireEvent.change(labelInput, { target: { value: "a".repeat(101) } })
    fireEvent.click(screen.getByTitle("保存"))

    await waitFor(() => expect(screen.getByText(/最多 100 个字符/)).toBeInTheDocument())
  })

  it("calls PUT with both label and description on save", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal("fetch", mockFetch)

    render(<RolesList initialRoles={SAMPLE_ROLES} />)
    fireEvent.click(screen.getAllByTitle("编辑")[0])

    const descInput = screen.getByDisplayValue("Access our updates")
    fireEvent.change(descInput, { target: { value: "New description" } })
    fireEvent.click(screen.getByTitle("保存"))

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/roles/r1",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({
            label: "📢 Exclusive Updates",
            description: "New description",
          }),
        })
      )
    )
  })

  it("disables the delete button when only one role remains", () => {
    vi.stubGlobal("fetch", vi.fn())
    render(<RolesList initialRoles={SINGLE_ROLE} />)
    expect(screen.getByTitle("删除")).toBeDisabled()
  })

  it("enables the delete button when more than one role exists", () => {
    vi.stubGlobal("fetch", vi.fn())
    render(<RolesList initialRoles={SAMPLE_ROLES} />)
    screen.getAllByTitle("删除").forEach((btn) => expect(btn).not.toBeDisabled())
  })

  it("does not add a role when label exceeds 100 characters", async () => {
    const mockFetch = vi.fn()
    vi.stubGlobal("fetch", mockFetch)

    render(<RolesList initialRoles={SAMPLE_ROLES} />)
    const addInput = screen.getByPlaceholderText(/身份组名称/)
    fireEvent.change(addInput, { target: { value: "a".repeat(101) } })
    fireEvent.click(screen.getByRole("button", { name: /添加/ }))

    await waitFor(() => expect(mockFetch).not.toHaveBeenCalled())
    expect(screen.getByText(/最多 100 个字符/)).toBeInTheDocument()
  })
})
