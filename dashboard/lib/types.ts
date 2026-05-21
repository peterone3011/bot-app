export interface Message {
  id: string
  status: "draft" | "scheduled" | "published"
  label: string | null
  created_at: string
  channel_id: number
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

export interface Site {
  id: string
  name: string
  display_order: number
  created_at: string
}

export interface Config {
  key: string
  value: string
}
