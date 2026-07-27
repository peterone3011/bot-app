import { NextRequest, NextResponse } from "next/server"

import { auth } from "@/lib/auth"
import { rateLimitCheck } from "@/lib/rate-limit"
import { supabase } from "@/lib/supabase"
import type {
  ActivityCampaign,
  ActivityQuestion,
  ActivitySubmission,
} from "@/lib/types"


export async function activityApiGuard(
  req: NextRequest
): Promise<NextResponse | null> {
  const limited = await rateLimitCheck(req)
  if (limited) return limited
  const session = await auth()
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }
  return null
}

export async function loadActivity(
  id: string
): Promise<{ activity: ActivityCampaign | null; error: string | null }> {
  const { data, error } = await supabase
    .from("activity_campaigns")
    .select("*, activity_questions(*)")
    .eq("id", id)
    .single()
  if (error || !data) {
    return {
      activity: null,
      error: error?.message ?? "Activity not found",
    }
  }
  const raw = data as unknown as ActivityCampaign & {
    activity_questions?: ActivityQuestion[]
  }
  return {
    activity: {
      ...raw,
      questions: [...(raw.activity_questions ?? raw.questions ?? [])].sort(
        (a, b) => a.position - b.position
      ),
    },
    error: null,
  }
}

export function campaignFields(
  body: Record<string, unknown>
): Record<string, unknown> {
  const allowed = [
    "name",
    "winner_limit",
    "ends_at",
    "discord_guild_id",
    "discord_channel_id",
    "embed_title",
    "embed_description",
    "image_url",
    "color",
    "button_label",
    "modal_title",
    "winner_message",
    "sold_out_message",
    "closed_message",
  ]
  return Object.fromEntries(
    allowed.filter((field) => field in body).map((field) => [field, body[field]])
  )
}

export function questionRows(
  campaignId: string,
  questions: ActivityQuestion[]
): Array<Record<string, unknown>> {
  return questions.map((question, index) => ({
    id: question.id || crypto.randomUUID(),
    campaign_id: campaignId,
    field_key: question.field_key,
    position: index + 1,
    label: question.label,
    input_style: question.input_style,
    required: question.required,
    placeholder: question.placeholder || null,
    min_length: question.min_length,
    max_length: question.max_length,
    prefill_discord_username: question.prefill_discord_username,
    is_participant_key: question.is_participant_key,
  }))
}

export function mapSubmission(row: Record<string, unknown>): ActivitySubmission {
  const reward = row.reward_code
  const rewardCode =
    reward && typeof reward === "object" && "code" in reward
      ? String((reward as { code: unknown }).code)
      : typeof reward === "string"
        ? reward
        : null
  return {
    id: String(row.id),
    campaign_id: String(row.campaign_id),
    discord_user_id: String(row.discord_user_id),
    discord_username: String(row.discord_username),
    answers: (row.answers ?? {}) as Record<string, string>,
    participant_key_normalized:
      row.participant_key_normalized == null
        ? null
        : String(row.participant_key_normalized),
    outcome: row.outcome as ActivitySubmission["outcome"],
    reward_code: rewardCode,
    submitted_at: String(row.submitted_at),
  }
}

export async function loadSubmissions(id: string): Promise<{
  submissions: ActivitySubmission[]
  error: string | null
}> {
  const { data, error } = await supabase
    .from("activity_submissions")
    .select(
      "id,campaign_id,discord_user_id,discord_username,answers,participant_key_normalized,outcome,submitted_at,reward_code:activity_codes(code)"
    )
    .eq("campaign_id", id)
    .order("submitted_at", { ascending: false })
  if (error) return { submissions: [], error: error.message }
  return {
    submissions: ((data ?? []) as Record<string, unknown>[]).map(mapSubmission),
    error: null,
  }
}
