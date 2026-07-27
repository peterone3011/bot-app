# Discord Reusable Activity System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable Supabase-backed Discord Modal campaign system operated from the existing Dashboard, with atomic ordered reward-code allocation and ephemeral player responses.

**Architecture:** A repeatable PostgreSQL migration owns data integrity and the atomic claim transaction. A new Discord Activity Cog resolves a campaign by persistent message button ID and renders dynamic Modals. Authenticated Next.js API routes and focused Dashboard components manage campaigns, Discord publication, codes, and submissions.

**Tech Stack:** PostgreSQL/Supabase, Python 3 with discord.py and pytest, Next.js 14/React 18/TypeScript, Supabase JS, Vitest.

## Global Constraints

- Campaign status is exactly `draft | active | closed`.
- A campaign has 1-5 questions and at most one unique participant-key question.
- The initial winner limit is exactly 20 and publish requires exactly 20 non-empty, unique codes.
- Reward codes are assigned in import order and never reused.
- All player replies are ephemeral; no reward is sent by DM.
- The persistent Discord button custom ID is exactly `activity_join`.
- The immutable Discord User ID and normalized FP ID are unique per campaign.
- Duplicate winners receive their original code; sold-out answers are retained.
- Closing updates the database before attempting to disable the Discord button.
- Only draft campaigns may be deleted.
- The formal campaign is created only as `FP Favorite Game Reward - Draft`; it is not automatically published.

---

### Task 1: Database Schema And Atomic Claim RPC

**Files:**
- Create: `supabase/migrations/20260727_activity_campaigns.sql`
- Create: `tests/sql/activity_campaigns_integration.sql`
- Create: `scripts/apply_activity_migration.py`

**Interfaces:**
- Produces: tables `activity_campaigns`, `activity_questions`, `activity_codes`, `activity_submissions`.
- Produces: RPC `claim_activity_reward(p_campaign_id uuid, p_discord_user_id text, p_discord_username text, p_answers jsonb, p_participant_key text)`.
- Produces: one-row result `{ outcome text, reward_code text }`.

- [ ] **Step 1: Write SQL integration assertions**

Create a transaction-scoped SQL test that imports ordered codes, exercises a
winner, duplicate winner, duplicate participant key, sold-out participant, and
closed campaign, then raises on any unexpected outcome.

- [ ] **Step 2: Verify the assertions fail before the migration**

Run the SQL integration script against a disposable or configured Supabase
database. Expected: failure because the activity tables/RPC do not exist.

- [ ] **Step 3: Add the repeatable migration**

Create enums/check constraints, tables, indexes, RLS, deny policies, trigger
helpers, the security-definer RPC, grants for `service_role`, and a guarded seed
for the formal draft. Normalize participant keys with
`lower(regexp_replace(trim(value), '\s+', '', 'g'))`.

- [ ] **Step 4: Add a guarded migration runner**

`scripts/apply_activity_migration.py` must require an explicit database URL,
execute the migration as one transaction, and never print credentials.

- [ ] **Step 5: Run the SQL integration assertions**

Expected: all `DO`-block assertions complete and the transaction rolls back.

- [ ] **Step 6: Commit**

Commit message: `feat: add activity campaign database schema`

### Task 2: Bot Database Contract And Dynamic Modal

**Files:**
- Create: `tests/test_activities.py`
- Create: `cogs/activities.py`
- Modify: `cogs/db.py`
- Modify: `bot.py`

**Interfaces:**
- Consumes: `claim_activity_reward` and activity tables from Task 1.
- Produces: `aget_activity_by_message(message_id: str)`, `aclaim_activity_reward(...)`.
- Produces: `ActivityView`, `ActivityModal`, and `ActivitiesCog`.

- [ ] **Step 1: Write failing Bot tests**

Cover one-to-five dynamic questions, short/paragraph styles, Discord username
prefill, persistent `activity_join`, question-load timeout, all RPC outcomes,
duplicate-code redisplay, closed state, participant-key conflict, and database
exception fallback.

- [ ] **Step 2: Run the Bot tests and confirm RED**

Run: `python -m pytest tests/test_activities.py -q`
Expected: import failure because `cogs.activities` does not exist.

- [ ] **Step 3: Add focused DB wrappers**

Implement synchronous Supabase calls plus `asyncio.to_thread` wrappers. Resolve
campaign and ordered questions by Discord message ID. Call the RPC without
client-side code selection.

- [ ] **Step 4: Implement persistent button and dynamic Modal**

Register `ActivityView(timeout=None)`. On click, use a two-second timeout to
load configuration before `send_modal`. On submit, defer ephemerally, normalize
the participant key, call the RPC, and edit the original response with the
configured copy. Escape replacement values except the configured `{code}`
placeholder replacement.

- [ ] **Step 5: Register the Cog**

Load `cogs.activities` in `bot.py` without altering existing extension order or
behavior beyond adding the new extension.

- [ ] **Step 6: Run focused and full Python tests**

Run:
- `python -m pytest tests/test_activities.py -q`
- `python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 7: Commit**

Commit message: `feat: add Discord activity modal workflow`

### Task 3: Dashboard Activity Domain And API

**Files:**
- Create: `dashboard/lib/activities.ts`
- Modify: `dashboard/lib/types.ts`
- Modify: `dashboard/middleware.ts`
- Create: `dashboard/app/api/activities/route.ts`
- Create: `dashboard/app/api/activities/[id]/route.ts`
- Create: `dashboard/app/api/activities/[id]/codes/route.ts`
- Create: `dashboard/app/api/activities/[id]/publish/route.ts`
- Create: `dashboard/app/api/activities/[id]/close/route.ts`
- Create: `dashboard/app/api/activities/[id]/copy/route.ts`
- Create: `dashboard/app/api/activities/[id]/submissions/route.ts`
- Create: `dashboard/app/api/activities/[id]/submissions/export/route.ts`
- Create: `dashboard/__tests__/activities-domain.test.ts`
- Create: `dashboard/__tests__/activities-api.test.ts`
- Modify: `dashboard/__tests__/middleware.test.ts`

**Interfaces:**
- Consumes: Supabase tables from Task 1 and Discord API v10.
- Produces: validated campaign CRUD and lifecycle endpoints.
- Produces: pure helpers `validateCampaignInput`, `parseRewardCodes`,
  `buildActivityDiscordBody`, and `toCsv`.

- [ ] **Step 1: Write failing domain tests**

Test one-to-five question validation, one unique key, Discord limits, exact code
count and duplicate rejection, active-field locking, Discord component payload,
CSV quoting/UTF-8 BOM, search and outcome filters.

- [ ] **Step 2: Verify domain tests fail**

Run: `npm.cmd test -- activities-domain.test.ts`
Expected: failure because `lib/activities.ts` does not exist.

- [ ] **Step 3: Implement pure domain helpers**

Keep validation and payload generation independent of Next.js routes so tests
exercise real behavior without network mocks.

- [ ] **Step 4: Write failing API tests**

Test authentication, draft creation/update/delete, active-field lock, exact code
import, publish orphan cleanup, copy exclusions, database-first close, filtering,
and CSV response headers/escaping.

- [ ] **Step 5: Implement authenticated, rate-limited API routes**

Use existing `auth`, `rateLimitCheck`, and server-only Supabase patterns.
Discord snowflakes remain strings. Publish inserts/updates Discord and stores
message ID; if DB activation fails after POST, best-effort DELETE the orphan.
Close commits `closed` first and only then PATCHes a disabled button.

- [ ] **Step 6: Protect activity APIs in middleware**

Add `/api/activities/:path*` and update its test.

- [ ] **Step 7: Run focused API/domain tests**

Run: `npm.cmd test -- activities-domain.test.ts activities-api.test.ts middleware.test.ts`
Expected: all focused tests pass.

- [ ] **Step 8: Commit**

Commit message: `feat: add activity management APIs`

### Task 4: Dashboard Activity Management UI

**Files:**
- Create: `dashboard/components/activity-list.tsx`
- Create: `dashboard/components/activity-editor.tsx`
- Create: `dashboard/components/activity-code-pool.tsx`
- Create: `dashboard/components/activity-submissions.tsx`
- Create: `dashboard/app/dashboard/activities/page.tsx`
- Create: `dashboard/app/dashboard/activities/[id]/page.tsx`
- Modify: `dashboard/components/sidebar.tsx`
- Create: `dashboard/__tests__/activity-editor.test.tsx`
- Create: `dashboard/__tests__/activity-submissions.test.tsx`

**Interfaces:**
- Consumes: Task 3 APIs and activity TypeScript interfaces.
- Produces: list page and detail view with `Settings`, `Reward Codes`, and
  `Submissions` tabs.

- [ ] **Step 1: Write failing component tests**

Test draft field editing, one-to-five questions, lock state after publish, exact
code count feedback, copy/close/delete action visibility, submission search and
outcome filtering, and CSV download action.

- [ ] **Step 2: Verify component tests fail**

Run: `npm.cmd test -- activity-editor.test.tsx activity-submissions.test.tsx`
Expected: component import failures.

- [ ] **Step 3: Implement activity list and detail pages**

Use the existing compact operational visual language. Do not nest cards. Use
tabs for the three views, icons for actions, swatches for embed colors, and
native form controls for question settings. All controls must have loading,
error, empty, and locked states.

- [ ] **Step 4: Add Activity Management navigation**

Add a Lucide clipboard/list icon and route `/dashboard/activities`.

- [ ] **Step 5: Run focused tests and Next build**

Run:
- `npm.cmd test -- activity-editor.test.tsx activity-submissions.test.tsx`
- `npm.cmd run build`

Expected: tests and production build pass.

- [ ] **Step 6: Commit**

Commit message: `feat: add activity management dashboard`

### Task 5: Integration, Review, Deployment, And Private Validation

**Files:**
- Modify only files required by review findings.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: deployed Bot and Dashboard with a formal unpublished draft.

- [ ] **Step 1: Apply migration before application deployment**

Apply `20260727_activity_campaigns.sql` once against production Supabase and
verify the formal draft exists without channel, codes, or Discord message ID.

- [ ] **Step 2: Run complete verification**

Run:
- `python -m pytest -q`
- `npm.cmd test`
- `npm.cmd run build`
- the Supabase SQL integration script

Expected: every command exits zero.

- [ ] **Step 3: Perform whole-branch code review**

Review concurrency, authorization, RLS, Discord lifecycle order, code leakage,
CSV injection/escaping, locked fields, and regression risk. Resolve all critical
or important findings and rerun affected suites.

- [ ] **Step 4: Push and verify deployments**

Push the feature branch/approved integration target, verify Railway registers
`ActivitiesCog`, and verify Vercel serves authenticated Activity Management
routes.

- [ ] **Step 5: Validate in private `bot-commands`**

Create a temporary active campaign using dummy codes only. Verify first claim,
concurrent claims, duplicate winner, participant-key conflict, sold-out,
closed behavior, persistent button after Bot restart, Dashboard filtering, and
CSV. Close and clean the temporary campaign.

- [ ] **Step 6: Confirm formal draft remains unpublished**

Verify `FP Favorite Game Reward - Draft` has the approved three questions,
winner limit 20, approved replies, no codes, no channel, and no Discord message.
