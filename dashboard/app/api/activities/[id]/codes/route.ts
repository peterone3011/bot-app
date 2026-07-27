import { NextRequest, NextResponse } from "next/server"

import { ActivityValidationError, parseRewardCodes } from "@/lib/activities"
import { supabase } from "@/lib/supabase"
import { activityApiGuard, loadActivity } from "../../helpers"


type Context = { params: { id: string } }

export async function GET(req: NextRequest, { params }: Context) {
  const guarded = await activityApiGuard(req)
  if (guarded) return guarded
  const { data, error } = await supabase
    .from("activity_codes")
    .select("id,position,code,claimed_at,claimed_by_submission_id")
    .eq("campaign_id", params.id)
    .order("position")
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json(data ?? [])
}

export async function PUT(req: NextRequest, { params }: Context) {
  const guarded = await activityApiGuard(req)
  if (guarded) return guarded
  const { activity, error } = await loadActivity(params.id)
  if (!activity) return NextResponse.json({ error }, { status: 404 })
  if (activity.status !== "draft") {
    return NextResponse.json(
      { error: "Reward codes are locked after publish" },
      { status: 409 }
    )
  }

  let body: { codes?: unknown; raw?: unknown }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 })
  }
  let codes: string[]
  try {
    if (typeof body.raw === "string") {
      codes = parseRewardCodes(body.raw)
    } else if (Array.isArray(body.codes)) {
      codes = parseRewardCodes(body.codes.map(String).join("\n"))
    } else {
      throw new ActivityValidationError("codes or raw is required")
    }
  } catch (validationError) {
    const message =
      validationError instanceof Error ? validationError.message : "Invalid codes"
    return NextResponse.json({ error: message }, { status: 400 })
  }

  const { data, error: replaceError } = await supabase.rpc(
    "replace_activity_codes",
    {
      p_campaign_id: params.id,
      p_codes: codes,
    }
  )
  if (replaceError) {
    const locked = replaceError.message.includes("activity_locked")
    return NextResponse.json(
      { error: locked ? "Reward codes are locked after publish" : replaceError.message },
      { status: locked ? 409 : 500 }
    )
  }
  return NextResponse.json({ count: data ?? codes.length })
}
