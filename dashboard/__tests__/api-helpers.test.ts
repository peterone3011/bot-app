// @vitest-environment node
import { describe, it, expect } from "vitest"
import { validateEmbedBody } from "@/app/api/embeds/helpers"

describe("validateEmbedBody", () => {
  it("accepts a valid minimal body", () => {
    expect(validateEmbedBody({ channel_id: 123456789 })).toBeNull()
  })

  it("rejects missing channel_id", () => {
    expect(validateEmbedBody({})).toMatch(/channel_id/)
  })

  it("rejects non-numeric channel_id", () => {
    expect(validateEmbedBody({ channel_id: "abc" })).toMatch(/channel_id/)
  })

  it("rejects title longer than 256 chars", () => {
    expect(validateEmbedBody({ channel_id: 1, title: "x".repeat(257) })).toMatch(/title/)
  })

  it("rejects description longer than 4000 chars", () => {
    expect(validateEmbedBody({ channel_id: 1, description: "x".repeat(4001) })).toMatch(/description/)
  })
})
