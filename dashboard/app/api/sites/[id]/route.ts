import { NextRequest, NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { supabase } from "@/lib/supabase"
import { rateLimitCheck } from "@/lib/rate-limit"

export async function PUT(req: NextRequest, { params }: { params: { id: string } }) {
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
  if (typeof body.name === "string") updates.name = body.name.trim()
  if (typeof body.display_order === "number" && Number.isInteger(body.display_order)) {
    updates.display_order = body.display_order
  }

  if (Object.keys(updates).length === 0) {
    return NextResponse.json({ error: "No valid fields to update" }, { status: 400 })
  }

  const { data, error } = await supabase
    .from("sites")
    .update(updates)
    .eq("id", params.id)
    .select()
    .single()

  if (error) {
    if (error.code === "PGRST116") return NextResponse.json({ error: "Not found" }, { status: 404 })
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
  return NextResponse.json(data)
}

export async function DELETE(req: NextRequest, { params }: { params: { id: string } }) {
  const limited = await rateLimitCheck(req)
  if (limited) return limited

  const session = await auth()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  const { error } = await supabase.from("sites").delete().eq("id", params.id)
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return new NextResponse(null, { status: 204 })
}
