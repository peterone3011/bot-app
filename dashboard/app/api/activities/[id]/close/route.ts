import { NextRequest, NextResponse } from "next/server"

import { buildActivityDiscordBody } from "@/lib/activities"
import { supabase } from "@/lib/supabase"
import { activityApiGuard, loadActivity } from "../../helpers"


type Context = { params: { id: string } }

export async function POST(req: NextRequest, { params }: Context) {
  const guarded = await activityApiGuard(req)
  if (guarded) return guarded
  const { activity, error } = await loadActivity(params.id)
  if (!activity) return NextResponse.json({ error }, { status: 404 })
  if (activity.status !== "active" && activity.status !== "closed") {
    return NextResponse.json(
      { error: "只有进行中的活动可以关闭" },
      { status: 409 }
    )
  }

  if (activity.status === "active") {
    const { error: closeError } = await supabase
      .from("activity_campaigns")
      .update({ status: "closed", closed_at: new Date().toISOString() })
      .eq("id", params.id)
      .eq("status", "active")
      .select()
      .single()
    if (closeError) {
      return NextResponse.json({ error: "活动关闭失败" }, { status: 500 })
    }
  }

  const token = process.env.DISCORD_BOT_TOKEN
  if (!token || !activity.discord_channel_id || !activity.discord_message_id) {
    return NextResponse.json({
      ok: true,
      discord_updated: false,
      warning: "活动已关闭，但缺少 Discord 消息配置，按钮未能更新",
    })
  }
  try {
    const response = await fetch(
      `https://discord.com/api/v10/channels/${activity.discord_channel_id}/messages/${activity.discord_message_id}`,
      {
        method: "PATCH",
        headers: {
          Authorization: `Bot ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(buildActivityDiscordBody(activity, true)),
      }
    )
    if (!response.ok) {
      return NextResponse.json({
        ok: true,
        discord_updated: false,
        warning: "活动已关闭，但 Discord 消息更新失败",
      })
    }
  } catch {
    return NextResponse.json({
      ok: true,
      discord_updated: false,
      warning: "活动已关闭，但暂时无法连接 Discord",
    })
  }
  return NextResponse.json({ ok: true, discord_updated: true })
}
