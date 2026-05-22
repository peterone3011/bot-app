import { Ratelimit } from "@upstash/ratelimit"
import { Redis } from "@upstash/redis"
import { type NextRequest, NextResponse } from "next/server"

const ratelimit = new Ratelimit({
  redis: Redis.fromEnv(),
  limiter: Ratelimit.slidingWindow(30, "1 m"),
})

export async function rateLimitCheck(req: NextRequest): Promise<NextResponse | null> {
  const ip =
    req.headers.get("x-forwarded-for")?.split(",")[0].trim() ??
    req.headers.get("x-real-ip") ??
    "anonymous"
  let success = true
  try {
    ;({ success } = await ratelimit.limit(ip))
  } catch (err) {
    console.error("[rate-limit] Upstash unavailable, failing open:", err)
  }
  if (!success) {
    return NextResponse.json({ error: "Too many requests" }, { status: 429 })
  }
  return null
}
