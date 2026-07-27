import { NextRequest, NextResponse } from "next/server"

import {
  buildActivityDiscordBody,
  validateCampaignInput,
  validatePublishedPatch,
} from "@/lib/activities"
import { supabase } from "@/lib/supabase"
import {
  activityApiGuard,
  campaignFields,
  loadActivity,
} from "../helpers"


type Context = { params: { id: string } }

export async function GET(req: NextRequest, { params }: Context) {
  const guarded = await activityApiGuard(req)
  if (guarded) return guarded
  const { activity, error } = await loadActivity(params.id)
  if (!activity) {
    return NextResponse.json({ error }, { status: 404 })
  }
  return NextResponse.json(activity)
}

export async function PUT(req: NextRequest, { params }: Context) {
  const guarded = await activityApiGuard(req)
  if (guarded) return guarded

  let body: Record<string, unknown>
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "请求数据格式无效" }, { status: 400 })
  }
  const { activity, error } = await loadActivity(params.id)
  if (!activity) return NextResponse.json({ error }, { status: 404 })

  const lockError = validatePublishedPatch(activity, body)
  if (lockError) return NextResponse.json({ error: lockError }, { status: 409 })

  const merged = {
    ...activity,
    ...body,
    questions:
      activity.status === "draft" && Array.isArray(body.questions)
        ? body.questions
        : activity.questions,
  }
  const validationError = validateCampaignInput(merged)
  if (validationError) {
    return NextResponse.json({ error: validationError }, { status: 400 })
  }

  const draftQuestions = Array.isArray(body.questions)
    ? body.questions
    : activity.questions
  const mutation =
    activity.status === "draft"
      ? await supabase.rpc("save_activity_draft", {
          p_campaign_id: params.id,
          p_campaign: campaignFields(body),
          p_questions: draftQuestions,
        })
      : await supabase
          .from("activity_campaigns")
          .update(campaignFields(body))
          .eq("id", params.id)
          .eq("status", "active")
          .select()
          .single()
  const { data, error: updateError } = mutation
  if (updateError) {
    const locked = updateError.message.includes("activity_locked")
    return NextResponse.json(
      { error: locked ? "活动发布后，这些设置不可修改" : "活动保存失败" },
      { status: locked ? 409 : 500 }
    )
  }

  if (
    activity.status === "active" &&
    activity.discord_channel_id &&
    activity.discord_message_id
  ) {
    const token = process.env.DISCORD_BOT_TOKEN
    if (!token) {
      return NextResponse.json(
        { error: "活动已保存，但 Discord Bot 尚未配置，公开消息未更新" },
        { status: 503 }
      )
    }
    const updated = { ...activity, ...(data as Record<string, unknown>) }
    let discordResponse: Response
    try {
      discordResponse = await fetch(
        `https://discord.com/api/v10/channels/${activity.discord_channel_id}/messages/${activity.discord_message_id}`,
        {
          method: "PATCH",
          headers: {
            Authorization: `Bot ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(buildActivityDiscordBody(updated)),
        }
      )
    } catch {
      return NextResponse.json(
        { error: "活动已保存，但暂时无法连接 Discord，公开消息未更新" },
        { status: 502 }
      )
    }
    if (!discordResponse.ok) {
      return NextResponse.json(
        { error: "活动已保存，但 Discord 公开消息更新失败" },
        { status: 502 }
      )
    }
  }

  return NextResponse.json(
    activity.status === "draft"
      ? data
      : { ...(data as Record<string, unknown>), questions: merged.questions }
  )
}

export async function DELETE(req: NextRequest, { params }: Context) {
  const guarded = await activityApiGuard(req)
  if (guarded) return guarded
  const { activity, error } = await loadActivity(params.id)
  if (!activity) return NextResponse.json({ error }, { status: 404 })
  if (activity.status !== "draft") {
    return NextResponse.json(
      { error: "只能删除草稿状态的活动" },
      { status: 409 }
    )
  }
  const { data: deleted, error: deleteError } = await supabase
    .from("activity_campaigns")
    .delete()
    .eq("id", params.id)
    .eq("status", "draft")
    .select("id")
  if (deleteError) {
    return NextResponse.json({ error: "活动删除失败" }, { status: 500 })
  }
  if (!Array.isArray(deleted) || deleted.length === 0) {
    return NextResponse.json(
      { error: "活动已不再是草稿，无法删除" },
      { status: 409 }
    )
  }
  return new NextResponse(null, { status: 204 })
}
