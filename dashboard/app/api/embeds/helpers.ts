export function validateEmbedBody(body: Record<string, unknown>): string | null {
  if (body.channel_id === undefined || body.channel_id === null) {
    return "channel_id is required"
  }
  if (typeof body.channel_id !== "number" || !Number.isInteger(body.channel_id)) {
    return "channel_id must be an integer"
  }
  if (body.title !== undefined && body.title !== null) {
    if (typeof body.title !== "string" || body.title.length > 256) {
      return "title must be a string of at most 256 characters"
    }
  }
  if (body.description !== undefined && body.description !== null) {
    if (typeof body.description !== "string" || body.description.length > 4000) {
      return "description must be a string of at most 4000 characters"
    }
  }
  if (body.footer !== undefined && body.footer !== null) {
    if (typeof body.footer !== "string" || body.footer.length > 2048) {
      return "footer must be a string of at most 2048 characters"
    }
  }
  if (body.color !== undefined && body.color !== null) {
    if (typeof body.color !== "number" || !Number.isInteger(body.color) || body.color < 0 || body.color > 0xFFFFFF) {
      return "color must be an integer between 0 and 16777215"
    }
  }
  return null
}
