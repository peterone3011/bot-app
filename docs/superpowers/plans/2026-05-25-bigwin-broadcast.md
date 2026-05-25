# Big Win Broadcast API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `POST /api/broadcast/bigwin` to the Dashboard so the tech team's backend can trigger a formatted Discord big win announcement with a link button.

**Architecture:** Single new Next.js API route. Uses the existing Bot Token to call Discord API v10. Uses Upstash Redis (already configured for rate limiting) to enforce a 4-hour global cooldown. No changes to the Python Bot or any existing Dashboard routes.

**Tech Stack:** Next.js App Router, TypeScript, `@upstash/redis`, Discord REST API v10, Vitest

---

### Task 1: Write failing tests

**Files:**
- Create: `dashboard/__tests__/broadcast-bigwin.test.ts`

- [ ] **Step 1: Create the test file**

```typescript
// @vitest-environment node

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

const mockRedisGet = vi.fn()
const mockRedisSet = vi.fn()

vi.mock("@upstash/redis", () => ({
  Redis: {
    fromEnv: vi.fn(() => ({
      get: mockRedisGet,
      set: mockRedisSet,
    })),
  },
}))

function makeReq(body: unknown, authHeader?: string) {
  return new Request("https://x.com/api/broadcast/bigwin", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(authHeader ? { authorization: authHeader } : {}),
    },
    body: JSON.stringify(body),
  })
}

describe("POST /api/broadcast/bigwin", () => {
  const mockFetch = vi.fn()

  beforeEach(() => {
    vi.stubGlobal("fetch", mockFetch)
    process.env.BROADCAST_API_KEY = "test-key"
    process.env.DISCORD_BOT_TOKEN = "test-bot-token"
    process.env.BIGWIN_CHANNEL_ID = "channel-123"
    process.env.BIGWIN_BUTTON_URL = "https://fortunepurple.com"
    mockRedisGet.mockResolvedValue(null)
    mockRedisSet.mockResolvedValue("OK")
    mockFetch.mockResolvedValue({ ok: true, text: () => Promise.resolve("") })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    delete process.env.BROADCAST_API_KEY
    delete process.env.DISCORD_BOT_TOKEN
    delete process.env.BIGWIN_CHANNEL_ID
    delete process.env.BIGWIN_BUTTON_URL
  })

  it("returns 401 with no Authorization header", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }) as any)
    expect(res.status).toBe(401)
  })

  it("returns 401 with wrong API key", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }, "Bearer wrong-key") as any)
    expect(res.status).toBe(401)
  })

  it("returns 400 when amount is missing", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ game: "Fortune Dragon" }, "Bearer test-key") as any)
    expect(res.status).toBe(400)
  })

  it("returns 400 when game is missing", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "10,000.0" }, "Bearer test-key") as any)
    expect(res.status).toBe(400)
  })

  it("returns skipped:cooldown and skips Discord when cooldown is active", async () => {
    mockRedisGet.mockResolvedValueOnce("1")
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }, "Bearer test-key") as any)
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data).toEqual({ skipped: true, reason: "cooldown" })
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it("sends Discord message with correct format and returns ok:true", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }, "Bearer test-key") as any)
    expect(res.status).toBe(200)
    expect(await res.json()).toEqual({ ok: true })
    expect(mockFetch).toHaveBeenCalledOnce()
    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe("https://discord.com/api/v10/channels/channel-123/messages")
    expect(options.headers.Authorization).toBe("Bot test-bot-token")
    const body = JSON.parse(options.body)
    expect(body.embeds[0].description).toContain("10,000.0 SC")
    expect(body.embeds[0].description).toContain("Fortune Dragon")
    expect(body.embeds[0].color).toBe(0x9B59B6)
    expect(body.components[0].components[0].url).toBe("https://fortunepurple.com")
    expect(body.components[0].components[0].label).toBe("Play Now")
  })

  it("writes cooldown key with 4h TTL after successful Discord send", async () => {
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }, "Bearer test-key") as any)
    expect(mockRedisSet).toHaveBeenCalledWith("bigwin:cooldown", "1", { ex: 14400 })
  })

  it("returns 502 and does NOT write cooldown when Discord returns error status", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500, text: () => Promise.resolve("Internal Server Error") })
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }, "Bearer test-key") as any)
    expect(res.status).toBe(502)
    expect(mockRedisSet).not.toHaveBeenCalled()
  })

  it("returns 502 and does NOT write cooldown when Discord is unreachable", async () => {
    mockFetch.mockRejectedValueOnce(new Error("ECONNREFUSED"))
    const { POST } = await import("@/app/api/broadcast/bigwin/route")
    const res = await POST(makeReq({ amount: "10,000.0", game: "Fortune Dragon" }, "Bearer test-key") as any)
    expect(res.status).toBe(502)
    expect(mockRedisSet).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run tests — verify all fail**

```bash
cd dashboard && npx vitest run __tests__/broadcast-bigwin.test.ts
```

Expected: All 9 tests fail with `Cannot find module '@/app/api/broadcast/bigwin/route'`

---

### Task 2: Implement the route

**Files:**
- Create: `dashboard/app/api/broadcast/bigwin/route.ts`

- [ ] **Step 1: Create the route file**

```typescript
import { NextRequest, NextResponse } from "next/server"
import { Redis } from "@upstash/redis"

const COOLDOWN_KEY = "bigwin:cooldown"
const COOLDOWN_SECONDS = 14400 // 4 hours

export async function POST(req: NextRequest) {
  // 1. Auth
  const apiKey = process.env.BROADCAST_API_KEY
  const authHeader = req.headers.get("authorization")
  if (!apiKey || !authHeader || authHeader !== `Bearer ${apiKey}`) {
    console.warn("[bigwin] Unauthorized request")
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  // 2. Parse and validate body
  let amount: string, game: string
  try {
    const body = await req.json()
    amount = body.amount
    game = body.game
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 })
  }
  if (!amount || !game) {
    return NextResponse.json({ error: "Missing required fields: amount, game" }, { status: 400 })
  }

  // 3. Cooldown check (fail-open if Redis unavailable)
  const redis = Redis.fromEnv()
  try {
    const inCooldown = await redis.get(COOLDOWN_KEY)
    if (inCooldown) {
      console.info("[bigwin] Skipped: cooldown active")
      return NextResponse.json({ skipped: true, reason: "cooldown" })
    }
  } catch (err) {
    console.error("[bigwin] Redis error during cooldown check:", err)
  }

  // 4. Check required env vars
  const botToken = process.env.DISCORD_BOT_TOKEN
  const channelId = process.env.BIGWIN_CHANNEL_ID
  const buttonUrl = process.env.BIGWIN_BUTTON_URL
  if (!botToken || !channelId || !buttonUrl) {
    console.error("[bigwin] Missing env vars")
    return NextResponse.json({ error: "Server misconfigured" }, { status: 503 })
  }

  // 5. Send to Discord
  const discordBody = {
    embeds: [{
      description: `🏆 **BIG WIN ALERT!!**\n\nA Fortune Chasers just won **${amount} SC** on **${game}**!\nThink you're next? Jump in and spin! 🎰💜`,
      color: 0x9B59B6,
    }],
    components: [{
      type: 1,
      components: [{
        type: 2,
        style: 5,
        label: "Play Now",
        url: buttonUrl,
      }],
    }],
  }

  let discordRes: Response
  try {
    discordRes = await fetch(
      `https://discord.com/api/v10/channels/${channelId}/messages`,
      {
        method: "POST",
        headers: {
          Authorization: `Bot ${botToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(discordBody),
      }
    )
  } catch {
    console.error("[bigwin] Discord API unreachable")
    return NextResponse.json({ error: "Discord API unreachable" }, { status: 502 })
  }

  if (!discordRes.ok) {
    const detail = await discordRes.text()
    console.error("[bigwin] Discord API error:", discordRes.status, detail)
    return NextResponse.json({ error: "Discord API error", detail }, { status: 502 })
  }

  // 6. Write cooldown AFTER successful send only
  try {
    await redis.set(COOLDOWN_KEY, "1", { ex: COOLDOWN_SECONDS })
  } catch (err) {
    console.error("[bigwin] Redis error when setting cooldown:", err)
    // Don't fail the request — message was already sent
  }

  console.info(`[bigwin] Broadcast sent: ${amount} SC on ${game}`)
  return NextResponse.json({ ok: true })
}
```

- [ ] **Step 2: Run tests — verify all pass**

```bash
cd dashboard && npx vitest run __tests__/broadcast-bigwin.test.ts
```

Expected: `9 passed`

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/api/broadcast/bigwin/route.ts dashboard/__tests__/broadcast-bigwin.test.ts
git commit -m "feat: add POST /api/broadcast/bigwin with 4h cooldown

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Add environment variables to Vercel

- [ ] **Step 1: Get #big-wins channel ID from Discord**

In Discord: go to **User Settings → Advanced → enable Developer Mode**.
Then right-click the **#big-wins** channel in the sidebar → **Copy Channel ID**.

- [ ] **Step 2: Generate BROADCAST_API_KEY**

Run in PowerShell:
```powershell
[System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
```
Copy the output string. **Save it somewhere safe** (password manager) — you'll need it to share with the tech team.

- [ ] **Step 3: Add variables in Vercel**

Go to [vercel.com](https://vercel.com) → project `dashboard` → **Settings → Environment Variables**. Add these three (select both **Production** and **Preview**):

| Key | Value |
|-----|-------|
| `BROADCAST_API_KEY` | (output from step 2) |
| `BIGWIN_CHANNEL_ID` | (channel ID from step 1) |
| `BIGWIN_BUTTON_URL` | `https://fortunepurple.com` |

- [ ] **Step 4: Redeploy**

Vercel dashboard → **Deployments** → click the three-dot menu on the latest deployment → **Redeploy**. Wait for green ✅.

---

### Task 4: End-to-end test on production

- [ ] **Step 1: Test happy path**

Open Chrome, navigate to `about:blank`, press F12 → Console. Run (replace `YOUR_KEY`):

```javascript
fetch("https://fortunepurplebot.vercel.app/api/broadcast/bigwin", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_KEY"
  },
  body: JSON.stringify({ amount: "10,000.0", game: "Fortune Dragon" })
}).then(r => r.json()).then(console.log)
```

Expected: `{ ok: true }` in console, and a message with embed + Play Now button appears in #big-wins.

- [ ] **Step 2: Test cooldown**

Run the exact same fetch again immediately.

Expected: `{ skipped: true, reason: "cooldown" }`. No new Discord message.

- [ ] **Step 3: Test 401**

```javascript
fetch("https://fortunepurplebot.vercel.app/api/broadcast/bigwin", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ amount: "10,000.0", game: "Fortune Dragon" })
}).then(r => console.log("status:", r.status))
```

Expected: `status: 401`

---

### Task 5: Push

- [ ] **Step 1: Push to remote**

```bash
git -c http.proxy=socks5://127.0.0.1:10808 push origin feat/dashboard
```

Expected: `feat/dashboard -> feat/dashboard`
