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
import { Hash } from "lucide-react"

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
        setError("无法加载频道列表，请检查 Discord Bot 配置")
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <div className="h-9 rounded-md border border-input bg-secondary/40 animate-pulse flex items-center gap-2 px-3">
        <span className="h-2 w-2 rounded-full bg-muted-foreground/40 animate-pulse" />
        <span className="text-[12.5px] text-muted-foreground/60">正在加载频道列表…</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[12.5px] text-destructive">
        {error}
      </div>
    )
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
      <SelectTrigger aria-label="Discord 频道">
        <SelectValue placeholder="选择 Discord 频道" />
      </SelectTrigger>
      <SelectContent>
        {ungrouped.map((c) => (
          <SelectItem key={c.id} value={c.id}>
            <span className="inline-flex items-center gap-1.5">
              <Hash className="h-3 w-3 text-muted-foreground" />
              {c.name}
            </span>
          </SelectItem>
        ))}
        {Object.entries(grouped).map(([category, chs]) => (
          <SelectGroup key={category}>
            <SelectLabel>{category}</SelectLabel>
            {chs.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                <span className="inline-flex items-center gap-1.5">
                  <Hash className="h-3 w-3 text-muted-foreground" />
                  {c.name}
                </span>
              </SelectItem>
            ))}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  )
}
