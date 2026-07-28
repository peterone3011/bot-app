# Activity Dashboard Expiry and Cache Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Dashboard display expired activities correctly and prevent stale draft data from appearing when opening another campaign.

**Architecture:** Add a pure display-status helper that derives `expired` from `status` and `ends_at`, while leaving stored campaign status and Bot behavior unchanged. Force fresh document navigation into activity details and synchronize the editor's local state whenever refreshed server campaign props change.

**Tech Stack:** Next.js 14, React 18, TypeScript, Supabase server client, Vitest, Testing Library

## Global Constraints

- Do not modify Discord Bot code.
- Do not modify Supabase schemas, RPCs, tables, or production campaign data.
- Do not add scheduled jobs or background processing.
- A stored active campaign with a future `ends_at` must continue displaying `进行中`.
- A stored active campaign with an elapsed `ends_at` displays `已结束` but remains active in the database.
- The expired campaign's Discord button remains clickable and the Bot continues returning the configured ended message.
- Closing an expired campaign remains optional and is presented as `禁用 Discord 按钮`.
- Deploy only the Vercel Dashboard after tests and build pass.

---

### Task 1: Correct Activity Display Status and Page Freshness

**Files:**
- Modify: `dashboard/lib/types.ts`
- Modify: `dashboard/lib/activities.ts`
- Modify: `dashboard/components/activity-list.tsx`
- Modify: `dashboard/components/activity-editor.tsx`
- Modify: `dashboard/app/dashboard/activities/[id]/page.tsx`
- Modify: `dashboard/__tests__/activities-domain.test.ts`
- Modify: `dashboard/__tests__/activity-list.test.tsx`
- Modify: `dashboard/__tests__/activity-editor.test.tsx`

**Interfaces:**
- Consumes: `ActivityCampaign.status`, `ActivityCampaign.ends_at`, `ActivityCampaign.updated_at`, and existing `router.refresh()` mutation behavior.
- Produces: `ActivityDisplayStatus` and `getActivityDisplayStatus(campaign, nowMs?)`.

- [x] **Step 1: Add failing domain tests for effective status**

Import `getActivityDisplayStatus` and add deterministic tests:

```ts
describe("activity display status", () => {
  const now = Date.parse("2026-07-28T12:00:00.000Z")

  it("keeps a future active campaign running", () => {
    expect(
      getActivityDisplayStatus(
        {
          status: "active",
          ends_at: "2026-07-28T12:00:01.000Z",
        },
        now
      )
    ).toBe("active")
  })

  it("shows an elapsed active campaign as expired", () => {
    expect(
      getActivityDisplayStatus(
        {
          status: "active",
          ends_at: "2026-07-28T12:00:00.000Z",
        },
        now
      )
    ).toBe("expired")
  })

  it("preserves explicit draft and closed states", () => {
    expect(
      getActivityDisplayStatus(
        { status: "draft", ends_at: "2020-01-01T00:00:00.000Z" },
        now
      )
    ).toBe("draft")
    expect(
      getActivityDisplayStatus(
        { status: "closed", ends_at: "2099-01-01T00:00:00.000Z" },
        now
      )
    ).toBe("closed")
  })
})
```

- [x] **Step 2: Add failing component tests for expired labels and stale-prop replacement**

In the list test, render an active campaign with a past `ends_at`, assert
`已结束`, and assert its detail entry has the intended direct `href`.

In the editor test, use Testing Library's `rerender`:

```tsx
const { rerender } = render(
  <ActivityEditor
    initial={{
      ...campaign,
      id: "copy",
      name: "Old Copy",
      status: "draft",
      revision: 1,
      updated_at: "2026-07-28T01:00:00Z",
    }}
  />
)

rerender(
  <ActivityEditor
    initial={{
      ...campaign,
      id: "active",
      name: "Current Activity",
      status: "active",
      revision: 5,
      updated_at: "2026-07-28T02:00:00Z",
    }}
  />
)

expect(screen.getByDisplayValue("Current Activity")).toBeInTheDocument()
expect(screen.queryByDisplayValue("Old Copy")).toBeNull()
expect(screen.getByText("进行中")).toBeInTheDocument()
```

Add an editor test for a past active campaign:

```tsx
render(
  <ActivityEditor
    initial={{
      ...campaign,
      status: "active",
      ends_at: "2020-01-01T00:00:00.000Z",
    }}
  />
)

expect(screen.getByText("已结束")).toBeInTheDocument()
expect(
  screen.getByRole("button", { name: "禁用 Discord 按钮" })
).toBeInTheDocument()
```

- [x] **Step 3: Run focused tests and confirm the intended failures**

Run:

```powershell
npm test -- __tests__/activities-domain.test.ts __tests__/activity-list.test.tsx __tests__/activity-editor.test.tsx
```

Working directory: `dashboard`

Expected: failures because `ActivityDisplayStatus`,
`getActivityDisplayStatus`, expired labels, and editor prop synchronization do
not exist yet.

- [x] **Step 4: Add the pure display-status interface**

In `dashboard/lib/types.ts`:

```ts
export type ActivityDisplayStatus = ActivityStatus | "expired"
```

In `dashboard/lib/activities.ts`:

```ts
export function getActivityDisplayStatus(
  campaign: Pick<ActivityCampaign, "status" | "ends_at">,
  nowMs = Date.now()
): ActivityDisplayStatus {
  if (campaign.status !== "active") return campaign.status
  if (!campaign.ends_at) return "active"
  const endsAt = Date.parse(campaign.ends_at)
  return Number.isFinite(endsAt) && endsAt <= nowMs ? "expired" : "active"
}
```

Invalid or missing end times remain displayed as active. Publishing validation
already prevents a real published campaign from having an invalid end time.

- [x] **Step 5: Apply display status without changing stored status**

Update the list and editor label maps to accept `ActivityDisplayStatus`:

```ts
const statusLabels: Record<ActivityDisplayStatus, string> = {
  draft: "草稿",
  active: "进行中",
  expired: "已结束",
  closed: "已关闭",
}
```

Compute `getActivityDisplayStatus(campaign)` during rendering. Continue using
`campaign.status` for mutation rules and API requests.

For stored active campaigns, keep the close action but change its visible text
when the display status is expired:

```tsx
{displayStatus === "expired" ? "禁用 Discord 按钮" : "关闭活动"}
```

- [x] **Step 6: Prevent stale activity detail state**

Replace activity detail `Link` entries with normal anchors:

```tsx
<a href={`/dashboard/activities/${campaign.id}`} ...>
```

This intentionally performs a full document navigation and does not reuse a
prefetched detail payload.

Synchronize editor state when server props change:

```ts
useEffect(() => {
  setCampaign(initial)
  setMessage("")
}, [initial])
```

Key the editor in the server detail page:

```tsx
<ActivityEditor
  key={`${campaign.id}:${campaign.revision ?? campaign.updated_at}`}
  initial={campaign}
/>
```

Keep existing immediate local updates and `router.refresh()` after mutations.
The synchronized prop effect ensures refreshed server data replaces stale
local state.

- [x] **Step 7: Run focused tests**

Run:

```powershell
npm test -- __tests__/activities-domain.test.ts __tests__/activity-list.test.tsx __tests__/activity-editor.test.tsx
```

Working directory: `dashboard`

Expected: all focused tests pass.

- [x] **Step 8: Run complete Dashboard verification**

Run:

```powershell
npm test
npm run build
git diff --check
```

Expected: all Dashboard tests pass, Next.js production build succeeds, and
the diff check is clean.

- [x] **Step 9: Review and commit**

Confirm the diff contains no files under `cogs/`, `supabase/`, or migration
directories. Commit only the Dashboard implementation, tests, and this plan:

```powershell
git add dashboard/lib/types.ts dashboard/lib/activities.ts dashboard/components/activity-list.tsx dashboard/components/activity-editor.tsx dashboard/app/dashboard/activities/[id]/page.tsx dashboard/__tests__/activities-domain.test.ts dashboard/__tests__/activity-list.test.tsx dashboard/__tests__/activity-editor.test.tsx docs/superpowers/plans/2026-07-28-activity-dashboard-expiry-cache.md
git commit -m "fix: refresh activity dashboard status"
```

- [ ] **Step 10: Deploy and verify without mutating activities**

Push the reviewed commit and verify Vercel production deployment success.
Perform read-only Supabase checks before and after deployment:

- Current formal campaign remains `active`.
- Its Discord message ID is unchanged.
- Its `ends_at` is unchanged.
- The old test campaign remains `closed`.

Verify the Dashboard production build serves the new commit. Do not publish,
close, save, or otherwise mutate either activity during deployment
verification.
