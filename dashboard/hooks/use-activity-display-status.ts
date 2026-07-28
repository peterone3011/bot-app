"use client"

import { useEffect, useState } from "react"

import { getActivityDisplayStatus } from "@/lib/activities"
import type { ActivityCampaign, ActivityDisplayStatus } from "@/lib/types"


const MAX_TIMEOUT_MS = 2_147_483_647

export function useActivityDisplayStatus(
  campaign: Pick<ActivityCampaign, "status" | "ends_at">,
  renderedAtMs: number
): ActivityDisplayStatus {
  const [nowMs, setNowMs] = useState(renderedAtMs)

  useEffect(() => {
    setNowMs(renderedAtMs)
    if (campaign.status !== "active" || !campaign.ends_at) return

    const endsAtMs = Date.parse(campaign.ends_at)
    if (!Number.isFinite(endsAtMs)) return

    let timeoutId: ReturnType<typeof setTimeout> | undefined

    const scheduleExpiry = () => {
      const remainingMs = endsAtMs - Date.now()
      if (remainingMs <= 0) {
        setNowMs(endsAtMs)
        return
      }

      timeoutId = setTimeout(() => {
        scheduleExpiry()
      }, Math.min(remainingMs, MAX_TIMEOUT_MS))
    }

    scheduleExpiry()
    return () => {
      if (timeoutId !== undefined) clearTimeout(timeoutId)
    }
  }, [campaign.ends_at, campaign.status, renderedAtMs])

  return getActivityDisplayStatus(campaign, nowMs)
}
