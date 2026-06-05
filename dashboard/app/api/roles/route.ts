import { NextRequest, NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { supabase } from "@/lib/supabase"
import { rateLimitCheck } from "@/lib/rate-limit"

export const dynamic = "force-dynamic"

const MAX_LABEL_LENGTH = 100

export async function GET(req: NextRequest) {
  const limited = await rateLimitCheck(req)
  if (limited) return limited

  const session = await auth()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  const { data, error } = await supabase
    .from("roles")
    .select("*")
    .order("display_order", { ascending: true })

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json(data)
}

export async function PUT(req: NextRequest) {
  const limited = await rateLimitCheck(req)
  if (limited) return limited

  const session = await auth()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 })
  }

  if (!Array.isArray(body) || body.length === 0) {
    return NextResponse.json(
      { error: "Body must be a non-empty array of {id, display_order}" },
      { status: 400 }
    )
  }

  for (const item of body as unknown[]) {
    if (
      typeof (item as Record<string, unknown>).id !== "string" ||
      typeof (item as Record<string, unknown>).display_order !== "number" ||
      !Number.isInteger((item as Record<string, unknown>).display_order)
    ) {
      return NextResponse.json(
        { error: "Each item must have id (string) and display_order (integer)" },
        { status: 400 }
      )
    }
  }

  const updates = (body as Array<{ id: string; display_order: number }>).map(
    ({ id, display_order }) => ({ id, display_order })
  )

  const { error } = await supabase.from("roles").upsert(updates, { onConflict: "id" })
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json({ ok: true })
}

export async function POST(req: NextRequest) {
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

  if (body === null || typeof body !== "object" || Array.isArray(body)) {
    return NextResponse.json({ error: "Body must be a JSON object" }, { status: 400 })
  }

  const { label, description } = body
  if (!label || typeof label !== "string" || label.trim().length === 0) {
    return NextResponse.json({ error: "label is required" }, { status: 400 })
  }
  if (label.trim().length > MAX_LABEL_LENGTH) {
    return NextResponse.json(
      { error: `label must be ${MAX_LABEL_LENGTH} characters or fewer` },
      { status: 400 }
    )
  }

  const { data: existing, error: orderError } = await supabase
    .from("roles")
    .select("display_order")
    .order("display_order", { ascending: false })
    .limit(1)

  if (orderError) return NextResponse.json({ error: orderError.message }, { status: 500 })
  const nextOrder = existing && existing.length > 0 ? existing[0].display_order + 1 : 0

  const role = {
    id: crypto.randomUUID(),
    label: label.trim(),
    description: typeof description === "string" ? description.trim() : "",
    display_order: nextOrder,
  }

  const { data, error } = await supabase.from("roles").insert(role).select().single()
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json(data, { status: 201 })
}
