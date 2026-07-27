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
  if (error) return NextResponse.json({ error: "福利码加载失败" }, { status: 500 })
  return NextResponse.json(data ?? [])
}

export async function PUT(req: NextRequest, { params }: Context) {
  const guarded = await activityApiGuard(req)
  if (guarded) return guarded
  const { activity, error } = await loadActivity(params.id)
  if (!activity) return NextResponse.json({ error }, { status: 404 })
  if (activity.status !== "draft") {
    return NextResponse.json(
      { error: "福利码发布后不可修改" },
      { status: 409 }
    )
  }

  let body: { codes?: unknown; raw?: unknown }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "请求数据格式无效" }, { status: 400 })
  }
  let codes: string[]
  try {
    if (typeof body.raw === "string") {
      codes = parseRewardCodes(body.raw)
    } else if (Array.isArray(body.codes)) {
      codes = parseRewardCodes(body.codes.map(String).join("\n"))
    } else {
      throw new ActivityValidationError("请输入福利码")
    }
  } catch (validationError) {
    const message =
      validationError instanceof Error ? validationError.message : "福利码格式无效"
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
      { error: locked ? "福利码发布后不可修改" : "福利码保存失败" },
      { status: locked ? 409 : 500 }
    )
  }
  return NextResponse.json({ count: data ?? codes.length })
}
