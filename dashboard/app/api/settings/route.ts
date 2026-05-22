import { NextRequest, NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { supabase } from "@/lib/supabase"
import { rateLimitCheck } from "@/lib/rate-limit"

export async function GET(req: NextRequest) {
  const limited = await rateLimitCheck(req)
  if (limited) return limited

  const session = await auth()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  const { data, error } = await supabase.from("config").select("*")
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })

  const config = Object.fromEntries(
    (data ?? []).map((row: { key: string; value: string }) => [row.key, row.value])
  )
  return NextResponse.json(config)
}

export async function PUT(req: NextRequest) {
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

  const { key, value } = body
  if (!key || typeof key !== "string") {
    return NextResponse.json({ error: "key is required" }, { status: 400 })
  }
  if (value === undefined || value === null) {
    return NextResponse.json({ error: "value is required" }, { status: 400 })
  }

  const { error } = await supabase
    .from("config")
    .upsert({ key, value: String(value) })
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json({ key, value: String(value) })
}
