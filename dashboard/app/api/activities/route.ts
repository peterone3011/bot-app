import { NextRequest, NextResponse } from "next/server"

import { validateCampaignInput } from "@/lib/activities"
import { supabase } from "@/lib/supabase"
import type { ActivityQuestion } from "@/lib/types"
import {
  activityApiGuard,
  campaignFields,
  questionRows,
} from "./helpers"


export async function GET(req: NextRequest) {
  const guarded = await activityApiGuard(req)
  if (guarded) return guarded

  const { data, error } = await supabase
    .from("activity_campaigns")
    .select("*, activity_questions(*), activity_codes(count), activity_submissions(count)")
    .order("created_at", { ascending: false })
  if (error) return NextResponse.json({ error: "活动列表加载失败" }, { status: 500 })
  return NextResponse.json(data ?? [])
}

export async function POST(req: NextRequest) {
  const guarded = await activityApiGuard(req)
  if (guarded) return guarded

  let body: Record<string, unknown>
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "请求数据格式无效" }, { status: 400 })
  }
  const validationError = validateCampaignInput(body)
  if (validationError) {
    return NextResponse.json({ error: validationError }, { status: 400 })
  }

  const id = crypto.randomUUID()
  const { data, error } = await supabase
    .from("activity_campaigns")
    .insert({ id, status: "draft", ...campaignFields(body) })
    .select()
    .single()
  if (error) return NextResponse.json({ error: "活动创建失败" }, { status: 500 })

  const questions = body.questions as ActivityQuestion[]
  const { error: questionError } = await supabase
    .from("activity_questions")
    .insert(questionRows(id, questions))
  if (questionError) {
    await supabase.from("activity_campaigns").delete().eq("id", id)
    return NextResponse.json({ error: "活动问题保存失败" }, { status: 500 })
  }
  return NextResponse.json({ ...data, questions }, { status: 201 })
}
