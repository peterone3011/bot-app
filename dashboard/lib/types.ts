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
