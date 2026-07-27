"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import {
  Copy,
  Plus,
  RefreshCw,
  Save,
  Send,
  Square,
  Trash2,
  X,
} from "lucide-react"

import { ChannelSelect } from "@/components/channel-select"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { validateCampaignInput } from "@/lib/activities"
import type { ActivityCampaign, ActivityQuestion } from "@/lib/types"


function newQuestion(position: number, campaignId: string): ActivityQuestion {
  return {
    id: crypto.randomUUID(),
    campaign_id: campaignId,
    field_key: `question_${Date.now()}_${position}`,
    position,
    label: "New Question",
    input_style: "short",
    required: true,
    placeholder: "",
    min_length: 1,
    max_length: 100,
    prefill_discord_username: false,
    is_participant_key: false,
  }
}

function toBeijingInputValue(value: string | null): string {
  if (!value) return ""
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp)) return ""
  return new Date(timestamp + 8 * 60 * 60 * 1000).toISOString().slice(0, 16)
}

function fromBeijingInputValue(value: string): string | null {
  if (!value) return null
  return new Date(`${value}:00+08:00`).toISOString()
}

export function ActivityEditor({ initial }: { initial: ActivityCampaign }) {
  const router = useRouter()
  const [campaign, setCampaign] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState("")
  const locked = campaign.status !== "draft"
  const closed = campaign.status === "closed"

  function update<K extends keyof ActivityCampaign>(
    field: K,
    value: ActivityCampaign[K]
  ) {
    setCampaign((current) => ({ ...current, [field]: value }))
  }

  function updateQuestion(index: number, patch: Partial<ActivityQuestion>) {
    setCampaign((current) => ({
      ...current,
      questions: current.questions.map((question, questionIndex) =>
        questionIndex === index ? { ...question, ...patch } : question
      ),
    }))
  }

  function markUnique(index: number, checked: boolean) {
    setCampaign((current) => ({
      ...current,
      questions: current.questions.map((question, questionIndex) => ({
        ...question,
        is_participant_key: questionIndex === index ? checked : false,
        required: questionIndex === index && checked ? true : question.required,
      })),
    }))
  }

  async function save(): Promise<boolean> {
    const validationError = validateCampaignInput(campaign)
    if (validationError) {
      setMessage(validationError)
      return false
    }
    setBusy(true)
    setMessage("")
    try {
      const response = await fetch(`/api/activities/${campaign.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(campaign),
      })
      const data = await response.json()
      if (!response.ok) {
        setMessage(data.error ?? "Save failed")
        return false
      }
      setCampaign((current) => ({ ...current, ...data }))
      setMessage("Saved")
      router.refresh()
      return true
    } catch {
      setMessage("Network error")
      return false
    } finally {
      setBusy(false)
    }
  }

  async function action(path: string, confirmText: string) {
    if (!confirm(confirmText)) return
    setBusy(true)
    setMessage("")
    try {
      const response = await fetch(`/api/activities/${campaign.id}/${path}`, {
        method: "POST",
      })
      const data = await response.json()
      if (!response.ok) {
        setMessage(data.error ?? `${path} failed`)
        return
      }
      if (path === "copy" && data.id) {
        router.push(`/dashboard/activities/${data.id}`)
      } else {
        if (path === "close") {
          setCampaign((current) => ({ ...current, status: "closed" }))
        } else if (path === "publish") {
          setCampaign((current) => ({
            ...current,
            status: "active",
            discord_message_id: data.message_id,
          }))
        }
        router.refresh()
      }
      if (data.warning) {
        setMessage(data.warning)
      }
    } catch {
      setMessage("Network error")
    } finally {
      setBusy(false)
    }
  }

  async function publish() {
    if (!(await save())) return
    await action("publish", "Publish this activity to Discord?")
  }

  async function remove() {
    if (!confirm("Delete this draft activity?")) return
    setBusy(true)
    setMessage("")
    try {
      const response = await fetch(`/api/activities/${campaign.id}`, {
        method: "DELETE",
      })
      if (response.ok) {
        router.push("/dashboard/activities")
        router.refresh()
      } else {
        const data = await response.json()
        setMessage(data.error ?? "Delete failed")
      }
    } catch {
      setMessage("Network error")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-7">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
        <div className="flex items-center gap-2">
          <span className="fp-pill fp-pill-muted capitalize">{campaign.status}</span>
          {message && <span className="text-[12px] text-muted-foreground">{message}</span>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => action("copy", "Copy this activity?")} disabled={busy}>
            <Copy className="h-3.5 w-3.5" /> Copy
          </Button>
          {!closed && (
            <Button variant="outline" size="sm" onClick={save} disabled={busy}>
              <Save className="h-3.5 w-3.5" /> Save
            </Button>
          )}
          {campaign.status === "draft" && (
            <>
              <Button size="sm" onClick={publish} disabled={busy}>
                <Send className="h-3.5 w-3.5" /> Publish
              </Button>
              <Button variant="destructive" size="sm" onClick={remove} disabled={busy}>
                <Trash2 className="h-3.5 w-3.5" /> Delete
              </Button>
            </>
          )}
          {campaign.status === "active" && (
            <Button variant="destructive" size="sm" onClick={() => action("close", "Close this activity?")} disabled={busy}>
              <Square className="h-3.5 w-3.5" /> Close
            </Button>
          )}
          {closed && (
            <Button variant="outline" size="sm" onClick={() => action("close", "Retry updating the Discord message?")} disabled={busy}>
              <RefreshCw className="h-3.5 w-3.5" /> Retry Discord Update
            </Button>
          )}
        </div>
      </div>

      <fieldset disabled={closed} className="contents">
      <section className="grid gap-4 md:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="activity-name">Activity Name</Label>
          <Input id="activity-name" value={campaign.name} onChange={(event) => update("name", event.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="activity-channel">Discord Channel</Label>
          <ChannelSelect value={campaign.discord_channel_id ?? ""} onChange={(value) => update("discord_channel_id", value)} disabled={locked} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="winner-limit">Winner Limit</Label>
          <Input id="winner-limit" aria-label="Winner Limit" type="number" min={1} value={campaign.winner_limit} onChange={(event) => update("winner_limit", Number(event.target.value))} disabled={locked} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="activity-end-time">Activity End Time (Beijing)</Label>
          <Input
            id="activity-end-time"
            aria-label="Activity End Time"
            type="datetime-local"
            value={toBeijingInputValue(campaign.ends_at)}
            onChange={(event) => update("ends_at", fromBeijingInputValue(event.target.value))}
            disabled={locked}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="modal-title">Modal Title</Label>
          <Input id="modal-title" aria-label="Modal Title" value={campaign.modal_title} maxLength={45} onChange={(event) => update("modal_title", event.target.value)} disabled={locked} />
        </div>
      </section>

      <section className="space-y-4 border-t border-border pt-6">
        <h2 className="text-[15px] font-semibold">Discord Message</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="embed-title">Embed Title</Label>
            <Input id="embed-title" aria-label="Embed Title" value={campaign.embed_title ?? ""} maxLength={256} onChange={(event) => update("embed_title", event.target.value || null)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="button-label">Button Label</Label>
            <Input id="button-label" value={campaign.button_label} maxLength={80} onChange={(event) => update("button_label", event.target.value)} />
          </div>
          <div className="space-y-1.5 md:col-span-2">
            <Label htmlFor="embed-description">Embed Description</Label>
            <Textarea id="embed-description" rows={5} value={campaign.embed_description ?? ""} maxLength={4000} onChange={(event) => update("embed_description", event.target.value || null)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="image-url">Image URL</Label>
            <Input id="image-url" value={campaign.image_url ?? ""} onChange={(event) => update("image_url", event.target.value || null)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="embed-color">Embed Color</Label>
            <div className="flex items-center gap-2">
              <input id="embed-color" type="color" className="h-9 w-12 rounded-md border border-input bg-background p-1" value={`#${(campaign.color ?? 0xff9933).toString(16).padStart(6, "0")}`} onChange={(event) => update("color", Number.parseInt(event.target.value.slice(1), 16))} />
              <span className="font-mono text-[12px] text-muted-foreground">
                #{(campaign.color ?? 0xff9933).toString(16).padStart(6, "0").toUpperCase()}
              </span>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4 border-t border-border pt-6">
        <div className="flex items-center justify-between">
          <h2 className="text-[15px] font-semibold">Modal Questions</h2>
          {!locked && campaign.questions.length < 5 && (
            <Button variant="outline" size="sm" onClick={() => update("questions", [...campaign.questions, newQuestion(campaign.questions.length + 1, campaign.id)])}>
              <Plus className="h-3.5 w-3.5" /> Add Question
            </Button>
          )}
        </div>
        <div className="space-y-3">
          {campaign.questions.map((question, index) => (
            <div key={question.id} className="rounded-md border border-border bg-card/50 p-4">
              <div className="grid gap-3 md:grid-cols-[1fr_160px_40px]">
                <div className="space-y-1.5">
                  <Label htmlFor={`question-${index}`}>Question Label</Label>
                  <Input id={`question-${index}`} aria-label="Question Label" value={question.label} maxLength={45} disabled={locked} onChange={(event) => updateQuestion(index, { label: event.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor={`style-${index}`}>Input Style</Label>
                  <select id={`style-${index}`} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm" value={question.input_style} disabled={locked} onChange={(event) => updateQuestion(index, { input_style: event.target.value as "short" | "paragraph", max_length: event.target.value === "paragraph" ? 1000 : 100 })}>
                    <option value="short">Short</option>
                    <option value="paragraph">Paragraph</option>
                  </select>
                </div>
                {!locked && campaign.questions.length > 1 && (
                  <Button variant="ghost" size="icon" title="Remove Question" className="mt-6" onClick={() => update("questions", campaign.questions.filter((_, questionIndex) => questionIndex !== index).map((item, itemIndex) => ({ ...item, position: itemIndex + 1 })))}>
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-[1fr_100px_100px]">
                <Input aria-label={`Question ${index + 1} Placeholder`} placeholder="Placeholder" value={question.placeholder ?? ""} disabled={locked} onChange={(event) => updateQuestion(index, { placeholder: event.target.value })} />
                <Input aria-label={`Question ${index + 1} Minimum Length`} type="number" min={0} value={question.min_length} disabled={locked} onChange={(event) => updateQuestion(index, { min_length: Number(event.target.value) })} />
                <Input aria-label={`Question ${index + 1} Maximum Length`} type="number" min={1} max={4000} value={question.max_length} disabled={locked} onChange={(event) => updateQuestion(index, { max_length: Number(event.target.value) })} />
              </div>
              <div className="mt-3 flex flex-wrap gap-5 text-[12.5px] text-muted-foreground">
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={question.required} disabled={locked || question.is_participant_key} onChange={(event) => updateQuestion(index, { required: event.target.checked })} /> Required
                </label>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={question.prefill_discord_username} disabled={locked} onChange={(event) => setCampaign((current) => ({ ...current, questions: current.questions.map((item, itemIndex) => ({ ...item, prefill_discord_username: itemIndex === index ? event.target.checked : false })) }))} /> Prefill Discord username
                </label>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={question.is_participant_key} disabled={locked} onChange={(event) => markUnique(index, event.target.checked)} /> Unique participant ID
                </label>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-4 border-t border-border pt-6">
        <h2 className="text-[15px] font-semibold">Private Replies</h2>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="winner-message">Winner Reply</Label>
            <Textarea id="winner-message" rows={3} value={campaign.winner_message} onChange={(event) => update("winner_message", event.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sold-out-message">Sold-out Reply</Label>
            <Textarea id="sold-out-message" rows={3} value={campaign.sold_out_message} onChange={(event) => update("sold_out_message", event.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="closed-message">Closed Reply</Label>
            <Textarea id="closed-message" rows={3} value={campaign.closed_message} onChange={(event) => update("closed_message", event.target.value)} />
          </div>
        </div>
      </section>
      </fieldset>
    </div>
  )
}
