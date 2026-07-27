import { NextRequest, NextResponse } from "next/server"

import { supabase } from "@/lib/supabase"
import {
  activityApiGuard,
  campaignFields,
  loadActivity,
  questionRows,
} from "../../helpers"


type Context = { params: { id: string } }

export async function POST(req: NextRequest, { params }: Context) {
  const guarded = await activityApiGuard(req)
  if (guarded) return guarded
  const { activity, error } = await loadActivity(params.id)
  if (!activity) return NextResponse.json({ error }, { status: 404 })

  const id = crypto.randomUUID()
  const fields = campaignFields({
    ...activity,
    name: `${activity.name} 副本`,
  })
  const { data, error: insertError } = await supabase
    .from("activity_campaigns")
    .insert({
      ...fields,
      id,
      status: "draft",
      discord_message_id: null,
      ends_at: null,
      published_at: null,
      closed_at: null,
    })
    .select()
    .single()
  if (insertError) {
    return NextResponse.json({ error: "活动复制失败" }, { status: 500 })
  }
  const { data: copiedQuestions, error: questionError } = await supabase
    .from("activity_questions")
    .insert(
      questionRows(
        id,
        activity.questions.map((question) => ({ ...question, id: "" }))
      )
    )
    .select()
  if (questionError) {
    await supabase.from("activity_campaigns").delete().eq("id", id)
    return NextResponse.json({ error: "活动问题复制失败" }, { status: 500 })
  }
  return NextResponse.json({ ...data, questions: copiedQuestions ?? [] }, { status: 201 })
}
