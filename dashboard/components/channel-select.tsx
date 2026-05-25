"use client"
import { useEffect, useState } from "react"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

interface Channel {
  id: string
  name: string
  category: string | null
}

interface ChannelSelectProps {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
}

export function ChannelSelect({ value, onChange, disabled }: ChannelSelectProps) {
  const [channels, setChannels] = useState<Channel[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    fetch("/api/discord/channels")
      .then((r) => {
        if (!r.ok) throw new Error("fetch failed")
        return r.json() as Promise<Channel[]>
      })
      .then((data) => {
        setChannels(data)
        setLoading(false)
      })
      .catch(() => {
        setError("无法加载频道列表，请检查 Bot Token 配置")
        setLoading(false)
      })
  }, [])

  if (loading) {
    return <div className="h-10 rounded-md border border-input bg-muted animate-pulse" />
  }

  if (error) {
    return <p className="text-sm text-destructive">{error}</p>
  }

  // Group by category
  const grouped: Record<string, Channel[]> = {}
  const ungrouped: Channel[] = []
  for (const ch of channels) {
    if (ch.category) {
      ;(grouped[ch.category] ??= []).push(ch)
    } else {
      ungrouped.push(ch)
    }
  }

  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger>
        <SelectValue placeholder="选择频道…" />
      </SelectTrigger>
      <SelectContent>
        {ungrouped.map((c) => (
          <SelectItem key={c.id} value={c.id}>
            # {c.name}
          </SelectItem>
        ))}
        {Object.entries(grouped).map(([category, chs]) => (
          <SelectGroup key={category}>
            <SelectLabel>{category}</SelectLabel>
            {chs.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                # {c.name}
              </SelectItem>
            ))}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  )
}
