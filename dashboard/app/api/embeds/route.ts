import { NextRequest, NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { supabase } from "@/lib/supabase"
import { rateLimitCheck } from "@/lib/rate-limit"
import { validateEmbedBody } from "./helpers"

export async function GET(req: NextRequest) {
  const limited = await rateLimitCheck(req)
  if (limited) return limited

  const session = await auth()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  const { data, error } = await supabase
    .from("messages")
    .select("*")
    .order("created_at", { ascending: false })

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json(data)
}

export async function POST(req: NextRequest) {
  const limited = await rateLimitCheck(req)
  if (limited) return limited

  const session = await auth()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  const body = await req.json()
  const validationError = validateEmbedBody(body)
  if (validationError) return NextResponse.json({ error: validationError }, { status: 400 })

  const now = new Date().toISOString()
  const message = {
    id: crypto.randomUUID(),
    status: "draft",
    label: body.label ?? null,
    created_at: now,
    channel_id: body.channel_id,
    send_at: null,
    message_id: null,
    title: body.title ?? null,
    description: body.description ?? null,
    footer: body.footer ?? null,
    image_url: body.image_url ?? null,
    button_label: body.button_label ?? null,
    button_url: body.button_url ?? null,
    color: body.color ?? null,
  }

  const { data, error } = await supabase.from("messages").insert(message).select().single()
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json(data, { status: 201 })
}
