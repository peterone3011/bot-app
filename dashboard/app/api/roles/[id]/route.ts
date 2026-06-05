import { NextRequest, NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { supabase } from "@/lib/supabase"
import { rateLimitCheck } from "@/lib/rate-limit"

const MAX_LABEL_LENGTH = 100

export async function PUT(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const limited = await rateLimitCheck(req)
  if (limited) return limited

  const session = await auth()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  let body: Record<string, unknown>
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 })
  }

  const updates: Record<string, unknown> = {}
  if (typeof body.label === "string") {
    const trimmed = body.label.trim()
    if (trimmed.length === 0)
      return NextResponse.json({ error: "label cannot be empty" }, { status: 400 })
    if (trimmed.length > MAX_LABEL_LENGTH)
      return NextResponse.json(
        { error: `label must be ${MAX_LABEL_LENGTH} characters or fewer` },
        { status: 400 }
      )
    updates.label = trimmed
  }
  if (typeof body.description === "string") updates.description = body.description.trim()
  if (
    typeof body.display_order === "number" &&
    Number.isInteger(body.display_order)
  ) {
    updates.display_order = body.display_order
  }

  if (Object.keys(updates).length === 0)
    return NextResponse.json({ error: "No valid fields to update" }, { status: 400 })

  const { data, error } = await supabase
    .from("roles")
    .update(updates)
    .eq("id", params.id)
    .select()
    .single()

  if (error) {
    if (error.code === "PGRST116")
      return NextResponse.json({ error: "Not found" }, { status: 404 })
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
  return NextResponse.json(data)
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const limited = await rateLimitCheck(req)
  if (limited) return limited

  const session = await auth()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  const { count, error: countError } = await supabase
    .from("roles")
    .select("*", { count: "exact", head: true })

  if (countError) return NextResponse.json({ error: countError.message }, { status: 500 })
  if (count !== null && count <= 1)
    return NextResponse.json({ error: "Cannot delete the last role" }, { status: 400 })

  const { error } = await supabase.from("roles").delete().eq("id", params.id)
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return new NextResponse(null, { status: 204 })
}
