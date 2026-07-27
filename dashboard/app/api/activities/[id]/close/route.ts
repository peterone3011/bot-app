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
      { error: "Only active activities can be closed" },
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
      return NextResponse.json({ error: closeError.message }, { status: 500 })
    }
  }

  const token = process.env.DISCORD_BOT_TOKEN
  if (!token || !activity.discord_channel_id || !activity.discord_message_id) {
    return NextResponse.json({
      ok: true,
      discord_updated: false,
      warning: "Activity closed, but Discord message could not be updated",
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
        warning: "Activity closed, but Discord message update failed",
      })
    }
  } catch {
    return NextResponse.json({
      ok: true,
      discord_updated: false,
      warning: "Activity closed, but Discord API was unreachable",
    })
  }
  return NextResponse.json({ ok: true, discord_updated: true })
}
