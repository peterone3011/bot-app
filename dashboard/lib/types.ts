export interface Message {
  id: string
  status: "draft" | "scheduled" | "published"
  label: string | null
  created_at: string
  channel_id: string
  send_at: string | null
  message_id: number | null
  title: string | null
  description: string | null
  footer: string | null
  image_url: string | null
  button_label: string | null
  button_url: string | null
  color: number | null
}

export interface Role {
  id: string
  label: string
  description: string
  display_order: number
  created_at: string
  updated_at: string
}

export type ActivityStatus = "draft" | "active" | "closed"
export type ActivityInputStyle = "short" | "paragraph"
export type ActivitySubmissionOutcome = "winner" | "sold_out"

export interface ActivityQuestion {
  id: string
  campaign_id: string
  field_key: string
  position: number
  label: string
  input_style: ActivityInputStyle
  required: boolean
  placeholder: string | null
  min_length: number
  max_length: number
  prefill_discord_username: boolean
  is_participant_key: boolean
}

export interface ActivityCampaign {
  id: string
  revision?: number
  name: string
  status: ActivityStatus
  winner_limit: number
  discord_guild_id: string | null
  discord_channel_id: string | null
  discord_message_id: string | null
  embed_title: string | null
  embed_description: string | null
  image_url: string | null
  color: number | null
  button_label: string
  modal_title: string
  winner_message: string
  sold_out_message: string
  closed_message: string
  ends_at: string | null
  created_at: string
  updated_at: string
  published_at: string | null
  closed_at: string | null
  questions: ActivityQuestion[]
  code_count?: number
  submission_count?: number
  winner_count?: number
}

export interface ActivitySubmission {
  id: string
  campaign_id: string
  discord_user_id: string
  discord_username: string
  answers: Record<string, string>
  participant_key_normalized: string | null
  outcome: ActivitySubmissionOutcome
  reward_code: string | null
  submitted_at: string
}
