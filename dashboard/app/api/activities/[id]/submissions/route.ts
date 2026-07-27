import { NextRequest, NextResponse } from "next/server"

import { filterActivitySubmissions } from "@/lib/activities"
import type { ActivitySubmissionOutcome } from "@/lib/types"
import {
  activityApiGuard,
  loadSubmissions,
} from "../../helpers"


type Context = { params: { id: string } }

export async function GET(req: NextRequest, { params }: Context) {
  const guarded = await activityApiGuard(req)
  if (guarded) return guarded
  const { submissions, error } = await loadSubmissions(params.id)
  if (error) return NextResponse.json({ error }, { status: 500 })

  const outcomeParam = req.nextUrl.searchParams.get("outcome")
  const outcome: ActivitySubmissionOutcome | "all" =
    outcomeParam === "winner" || outcomeParam === "sold_out"
      ? outcomeParam
      : "all"
  const search = req.nextUrl.searchParams.get("search") ?? ""
  return NextResponse.json(filterActivitySubmissions(submissions, search, outcome))
}
