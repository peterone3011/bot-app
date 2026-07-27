import { NextRequest, NextResponse } from "next/server"

import {
  buildActivityDiscordBody,
  parseRewardCodes,
  validateCampaignInput,
} from "@/lib/activities"
import { supabase } from "@/lib/supabase"
import { activityApiGuard, loadActivity } from "../../helpers"


type Context = { params: { id: string } }

const activationErrorMessages: Record<string, string> = {
  invalid_code_count: "福利码数量与中奖人数不一致",
  invalid_end_time: "活动结束时间无效或已过期",
  invalid_questions: "活动问题配置无效",
  stale_draft: "活动配置已发生变化，请刷新后重试",
}

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
      { error: "Discord Bot Token 或服务器尚未配置" },
      { status: 503 }
    )
  }

  const { activity, error } = await loadActivity(params.id)
  if (!activity) return NextResponse.json({ error }, { status: 404 })
  if (activity.status === "closed") {
    return NextResponse.json({ error: "活动已结束，无法发布" }, { status: 409 })
  }
  if (!activity.discord_channel_id || !/^\d+$/.test(activity.discord_channel_id)) {
    return NextResponse.json({ error: "请选择 Discord 频道" }, { status: 400 })
  }
  if (!activity.embed_title && !activity.embed_description) {
    return NextResponse.json(
      { error: "消息标题和正文至少填写一项" },
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
      { error: "活动结束时间必须晚于当前时间" },
      { status: 400 }
    )
  }

  const { data: codeRows, error: codeError } = await supabase
    .from("activity_codes")
    .select("id,position,code")
    .eq("campaign_id", params.id)
    .order("position")
  if (codeError) {
    return NextResponse.json({ error: "福利码加载失败" }, { status: 500 })
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
    return NextResponse.json({ error: "暂时无法连接 Discord，请稍后重试" }, { status: 502 })
  }
  if (!discordResponse.ok) {
    return NextResponse.json({ error: "Discord 发布失败，请检查频道权限" }, { status: 502 })
  }
  if (updating) return NextResponse.json({ ok: true, message_id: activity.discord_message_id })

  const discordMessage = await discordResponse.json() as { id?: string }
  if (!discordMessage.id) {
    return NextResponse.json(
      { error: "Discord 返回的消息数据无效" },
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
      return NextResponse.json({ error: "Discord 消息已发送，但活动启用失败" }, { status: 500 })
    }
    if (activation?.outcome === "already_active") {
      return NextResponse.json(
        {
          error: "活动已经发布，请勿重复操作",
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
      {
        error:
          activationErrorMessages[activation?.outcome] ??
          "活动启用失败，请稍后重试",
      },
      { status: invalidDraft ? 409 : 500 }
    )
  }
  return NextResponse.json({ ok: true, message_id: discordMessage.id })
}
