import { NextRequest, NextResponse } from "next/server"

import {
  buildActivityDiscordBody,
  parseRewardCodes,
  validateCampaignInput,
} from "@/lib/activities"
import { supabase } from "@/lib/supabase"
import { activityApiGuard, loadActivity } from "../../helpers"


type Context = { params: { id: string } }

async function deleteDiscordMessage(
  channelId: string,
  messageId: string,
  token: string
) {
  try {
    await fetch(
      `https://discord.com/api/v10/channels/${channelId}/messages/${messageId}`,
      {
        method: "DELETE",
        headers: { Authorization: `Bot ${token}` },
      }
    )
  } catch {
    // Best effort cleanup. The API still reports activation failure to the admin.
  }
}

export async function POST(req: NextRequest, { params }: Context) {
  const guarded = await activityApiGuard(req)
  if (guarded) return guarded
  const token = process.env.DISCORD_BOT_TOKEN
  const guildId = process.env.DISCORD_GUILD_ID
  if (!token || !guildId) {
    return NextResponse.json(
      { error: "Discord Bot token or guild is not configured" },
      { status: 503 }
    )
  }

  const { activity, error } = await loadActivity(params.id)
  if (!activity) return NextResponse.json({ error }, { status: 404 })
  if (activity.status === "closed") {
    return NextResponse.json({ error: "Activity is closed" }, { status: 409 })
  }
  if (!activity.discord_channel_id || !/^\d+$/.test(activity.discord_channel_id)) {
    return NextResponse.json({ error: "Discord channel is required" }, { status: 400 })
  }
  if (!activity.embed_title && !activity.embed_description) {
    return NextResponse.json(
      { error: "Embed title or description is required" },
      { status: 400 }
    )
  }
  const validationError = validateCampaignInput(activity)
  if (validationError) {
    return NextResponse.json({ error: validationError }, { status: 400 })
  }
  const endsAt = activity.ends_at ? Date.parse(activity.ends_at) : Number.NaN
  if (!Number.isFinite(endsAt) || endsAt <= Date.now()) {
    return NextResponse.json(
      { error: "Activity end time must be in the future" },
      { status: 400 }
    )
  }

  const { data: codeRows, error: codeError } = await supabase
    .from("activity_codes")
    .select("id,position,code")
    .eq("campaign_id", params.id)
    .order("position")
  if (codeError) {
    return NextResponse.json({ error: codeError.message }, { status: 500 })
  }
  try {
    parseRewardCodes(
      (codeRows ?? []).map((row) => row.code).join("\n"),
      activity.winner_limit
    )
  } catch (codeValidationError) {
    return NextResponse.json(
      { error: (codeValidationError as Error).message },
      { status: 400 }
    )
  }

  const updating = activity.status === "active" && activity.discord_message_id
  const url = updating
    ? `https://discord.com/api/v10/channels/${activity.discord_channel_id}/messages/${activity.discord_message_id}`
    : `https://discord.com/api/v10/channels/${activity.discord_channel_id}/messages`
  let discordResponse: Response
  try {
    discordResponse = await fetch(url, {
      method: updating ? "PATCH" : "POST",
      headers: {
        Authorization: `Bot ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(buildActivityDiscordBody(activity)),
    })
  } catch {
    return NextResponse.json({ error: "Discord API unreachable" }, { status: 502 })
  }
  if (!discordResponse.ok) {
    return NextResponse.json({ error: "Discord API error" }, { status: 502 })
  }
  if (updating) return NextResponse.json({ ok: true, message_id: activity.discord_message_id })

  const discordMessage = await discordResponse.json() as { id?: string }
  if (!discordMessage.id) {
    return NextResponse.json(
      { error: "Discord API returned an invalid message" },
      { status: 502 }
    )
  }

  const { data: activationData, error: activationError } = await supabase.rpc(
    "activate_activity_campaign",
    {
      p_campaign_id: params.id,
      p_expected_revision: activity.revision ?? 0,
      p_discord_guild_id: guildId,
      p_discord_message_id: discordMessage.id,
    }
  )
  const activation = Array.isArray(activationData)
    ? activationData[0]
    : activationData
  if (activationError || activation?.outcome !== "activated") {
    await deleteDiscordMessage(
      activity.discord_channel_id,
      discordMessage.id,
      token
    )
    if (activationError) {
      return NextResponse.json({ error: activationError.message }, { status: 500 })
    }
    if (activation?.outcome === "already_active") {
      return NextResponse.json(
        {
          error: "Activity was already published",
          message_id: activation.existing_message_id,
        },
        { status: 409 }
      )
    }
    const invalidDraft = [
      "invalid_code_count",
      "invalid_end_time",
      "invalid_questions",
      "stale_draft",
    ].includes(activation?.outcome)
    return NextResponse.json(
      { error: `Activity activation failed: ${activation?.outcome ?? "unknown"}` },
      { status: invalidDraft ? 409 : 500 }
    )
  }
  return NextResponse.json({ ok: true, message_id: discordMessage.id })
}
