import { NextRequest, NextResponse } from "next/server"
import { Redis } from "@upstash/redis"
import { auth } from "@/lib/auth"

export const dynamic = "force-dynamic"

const VALID_SOURCES = ["cron", "api"] as const
type Source = (typeof VALID_SOURCES)[number]

const HISTORY_KEYS: Record<"all" | Source, string> = {
  all: "bigwin:history",
  cron: "bigwin:history:cron",
  api: "bigwin:history:api",
}

interface HistoryRecord {
  id: string
  ts: number
  amount: string
  game: string
  source: "cron" | "api"
  discordMessageId: string
}

export async function GET(req: NextRequest) {
  const session = await auth()
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const source = new URL(req.url).searchParams.get("source")
  if (source !== null && !VALID_SOURCES.includes(source as Source)) {
    return NextResponse.json({ error: "Invalid source" }, { status: 400 })
  }

  const key = source ? HISTORY_KEYS[source as Source] : HISTORY_KEYS.all

  let members: unknown[]
  try {
    const redis = Redis.fromEnv()
    members = await redis.zrange(key, 0, 199, { rev: true })
  } catch (err) {
    console.error("[bigwin][history] Redis error:", err)
    return NextResponse.json({ error: "History unavailable" }, { status: 500 })
  }

  const records: HistoryRecord[] = []
  for (const m of members) {
    try {
      records.push(JSON.parse(m as string) as HistoryRecord)
    } catch {
      // skip corrupted entries
    }
  }

  return NextResponse.json({ records })
}
