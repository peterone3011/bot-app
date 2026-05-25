import { Ratelimit } from "@upstash/ratelimit"
import { Redis } from "@upstash/redis"
import { type NextRequest, NextResponse } from "next/server"

// Lazy-initialize so Redis.fromEnv() is not called at module load time.
// This prevents build failures when env vars are missing or malformed.
let _ratelimit: Ratelimit | null = null

function getRatelimit(): Ratelimit {
  if (!_ratelimit) {
    _ratelimit = new Ratelimit({
      redis: Redis.fromEnv(),
      limiter: Ratelimit.slidingWindow(30, "1 m"),
    })
  }
  return _ratelimit
}

export async function rateLimitCheck(req: NextRequest): Promise<NextResponse | null> {
  const ip =
    req.headers.get("x-forwarded-for")?.split(",")[0].trim() ??
    req.headers.get("x-real-ip") ??
    "anonymous"
  let success = true
  try {
    ;({ success } = await getRatelimit().limit(ip))
  } catch (err) {
    console.error("[rate-limit] Upstash unavailable, failing open:", err)
  }
  if (!success) {
    return NextResponse.json({ error: "Too many requests" }, { status: 429 })
  }
  return null
}
