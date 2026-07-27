import { NextRequest, NextResponse } from "next/server"

import { toActivityCsv } from "@/lib/activities"
import { supabase } from "@/lib/supabase"
import type { ActivityQuestion } from "@/lib/types"
import {
  activityApiGuard,
  loadSubmissions,
} from "../../../helpers"


type Context = { params: { id: string } }

export async function GET(req: NextRequest, { params }: Context) {
  const guarded = await activityApiGuard(req)
  if (guarded) return guarded

  const { data: questions, error: questionError } = await supabase
    .from("activity_questions")
    .select("*")
    .eq("campaign_id", params.id)
    .order("position")
  if (questionError) {
    return NextResponse.json(
      { error: "问题配置加载失败，无法导出" },
      { status: 500 }
    )
  }
  const { submissions, error } = await loadSubmissions(params.id)
  if (error) return NextResponse.json({ error }, { status: 500 })

  const csv = toActivityCsv(
    submissions,
    (questions ?? []) as ActivityQuestion[]
  )
  return new NextResponse(csv, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="activity-${params.id}-submissions.csv"`,
      "Cache-Control": "no-store",
    },
  })
}
