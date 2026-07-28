# Activity Dashboard Expiry and Cache Fix Design

## Goal

Ensure the activity Dashboard always shows the current campaign record and
shows active campaigns as ended once their configured end time has passed,
without changing Discord Bot behavior or stored activity data.

## Confirmed Root Causes

The production database is correct:

- `7/28 FP Favorite Game Reward` is active and bound to its current Discord
  message.
- `FP Favorite Game Reward 7/28` is closed.
- The deleted draft-copy name shown by the Dashboard no longer exists in the
  database.

The stale screen is caused by client-side navigation and editor state:

- Activity links can reuse a previously prefetched Next.js route payload.
- `ActivityEditor` initializes state from `initial` only once, so refreshed
  server props do not replace an older campaign held in component state.

The stored `status` and configured `ends_at` currently have different
responsibilities. Expiry blocks submissions in the Bot and database RPC, but
does not automatically change `status` from `active` to `closed`.

## Dashboard Behavior

Introduce an effective display status:

- `draft` remains `draft`.
- `closed` remains `closed`.
- `active` with a future end time remains `active`.
- `active` with an end time at or before the current time displays as
  `expired`.

The internal Chinese labels are:

- `draft`: `草稿`
- `active`: `进行中`
- `expired`: `已结束`
- `closed`: `已关闭`

An expired campaign remains stored as `active`. Its Discord button therefore
remains clickable, and the Bot continues returning the configured
activity-ended ephemeral message because it independently checks `ends_at`.
No reward code can be claimed after expiry.

For an expired campaign, the existing close action remains available but is
labelled `禁用 Discord 按钮`. Using it changes the stored status to `closed`
and disables the public Discord button. This is optional.

## Freshness Strategy

- Activity list entries use full document navigation instead of a prefetched
  client route, ensuring the detail page is read from the server.
- `ActivityEditor` synchronizes its local campaign state whenever a new
  `initial` campaign revision is received.
- The detail page keys the editor by campaign ID and update timestamp so a
  changed campaign cannot reuse another campaign's local editor state.
- Successful publish and close actions reload the current detail document so
  the rendered page is verified against the database response.
- Draft saving still updates local state before publishing and does not
  interrupt the publish sequence.

## Scope and Safety

- No Discord Bot code changes.
- No Supabase schema, migration, RPC, or campaign-data changes.
- No new scheduled jobs.
- No change to reward allocation, duplicate submission handling, or activity
  end-time enforcement.
- Only the Vercel Dashboard is redeployed.

## Verification

Dashboard tests will cover:

- Effective status before and after `ends_at`.
- Closed status taking precedence over expiry.
- Expired labels in the activity list and detail editor.
- The optional expired close action label.
- Editor state replacement when refreshed props contain a different campaign
  ID, revision, or update timestamp.
- Existing draft, active, publish, close, copy, and save behavior.

Run Dashboard Vitest and Next.js production build before deployment.
