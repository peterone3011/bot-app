# Fortune Purple Discord Bot

Fortune Purple 的 Discord automation 项目，包含 Railway 上运行的 Python Bot，以及部署在 Vercel 的内部管理后台。Bot 负责 Discord 内的订阅身份组、Embed 发布、Big Win / Jackpot 播报、Updates 自动发布和新成员自动授权；Dashboard 负责后台管理、历史记录和外部播报 API。

## Current Architecture

```text
bot.py                 Discord Bot entrypoint on Railway
cogs/
  roles.py             DB-driven notification role selector
  embed.py             Discord embed builder and scheduled publishing
  bigwin.py            Random 6-14h Big Win trigger through Dashboard API
  jackpot.py           Daily Jackpot broadcast, gated by JACKPOT_ENABLED
  updates.py           Feishu Bitable -> Discord midnight updates publisher
  community_metrics.py Daily Discord community metrics -> Feishu Base
  screenshot_activity.py Screenshot proof reward codes -> Lark Sheet
  autorole.py          Auto-assign member role up to 3000 users
  db.py                Supabase helper used by Bot cogs
dashboard/             Next.js admin dashboard deployed to Vercel
docs/                  Integration notes and implementation plans
tests/                 Python unit tests
```

## Runtime Services

| Service | Platform | Notes |
|---|---|---|
| Discord Bot | Railway | Starts with `python bot.py` from `Procfile`. GitHub push to `main` triggers deploy. |
| Dashboard | Vercel | Production URL: `https://fortunepurplebot.vercel.app`. Manual deploy may be needed if GitHub integration does not trigger. |
| Database | Supabase | Shared by Bot and Dashboard. Service role key is server-side only. |
| Big Win history / cooldown | Upstash Redis | Used by Dashboard API for cooldown, image rotation, and history. |
| Updates source | Feishu Bitable | Bot checks at 00:01 BJT and retries failures at 00:06 / 00:16. |

## Main Workflows

- **Notification roles**: `/dashboard/roles` manages the role list. `cogs/roles.py` loads the list from Supabase and updates the `🔔roles` selector message.
- **Embeds**: Dashboard and `/embed` slash command manage draft, scheduled, and published embed messages.
- **Big Win**: `cogs/bigwin.py` calls `GET /api/broadcast/bigwin` every random 6-14 hours. Real external wins can call `POST /api/broadcast/bigwin` with `amount` and `game`.
- **Big Win history**: Dashboard page `/dashboard/bigwin` reads the last 30 days of Redis-backed broadcast records.
- **Jackpot**: `cogs/jackpot.py` posts at 19:00 Beijing time when `JACKPOT_ENABLED=1`.
- **Updates**: `cogs/updates.py` checks Feishu Bitable at Beijing midnight, publishes `待发布` records dated before today, retries read/image/send failures twice, and marks successful records `已发布`.
- **Community metrics**: `cogs/community_metrics.py` records join/leave events, then upserts daily metrics at 23:59 Beijing time into the Feishu Base table `FP-DC数据`.
- **Screenshot activity**: `cogs/screenshot_activity.py` watches one configured Discord channel for image submissions, assigns the next available Lark Sheet code, DMs it to the player, and writes the claim record back to Lark.
- **Autorole**: `cogs/autorole.py` backfills and assigns the configured member role until the 3000-user cap.

## Environment Variables

Secrets live in Railway, Vercel, or local `.env` files. Do not commit real tokens or keys.

Common Bot variables:

| Variable | Purpose |
|---|---|
| `TOKEN` | Discord Bot token |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | Supabase access for Bot cogs |
| `DASHBOARD_URL` / `CRON_SECRET` | Big Win cron trigger |
| `BIGWIN_BUTTON_URL` | Link button URL for Big Win and Jackpot posts |
| `JACKPOT_CHANNEL_ID` / `JACKPOT_ENABLED` | Jackpot broadcast configuration |
| `UPDATE_CHANNEL_ID` / `STAFF_CHAT_CHANNEL_ID` | Updates channel and staff alerts |
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | Feishu custom app credentials |
| `FEISHU_UPDATES_BASE_APP_TOKEN` / `FEISHU_UPDATES_TABLE_ID` | Updates Bitable source |
| `FEISHU_METRICS_BASE_APP_TOKEN` / `FEISHU_METRICS_TABLE_ID` | Community metrics Base target |
| `FEISHU_NOTIFY_CHAT_ID` | Optional Feishu failure-notification chat |
| `METRICS_GAMING_ROLE_NAME` / `METRICS_UPDATES_ROLE_NAME` | Optional role-name matching override for metrics |
| `SCREENSHOT_ACTIVITY_CHANNEL_ID` | Discord channel where players submit screenshot proofs |
| `SCREENSHOT_CODES_SPREADSHEET_TOKEN` / `SCREENSHOT_CODES_SHEET_ID` | Lark Sheet that stores screenshot activity reward codes |
| `SCREENSHOT_CODES_RANGE` | Optional code sheet read range, defaults to `A:I` |

Default community metrics Base target:

```text
app: CeqtbxWt5azkkHs8OzpjZ9D1p2e
table: tblMeRm8yocZPqUR
```

Screenshot activity code sheet columns:

```text
A code
B status
C discord_user_id
D discord_name
E discord_message_id
F screenshot_url
G claimed_at_bjt
H dm_status
I note
```

Put reward codes in `A2:A26` in the exact order they should be sent. Leave `B:I` blank. The bot treats blank / `available` / `可用` as available and writes `reserved`, `sent`, or `dm_failed` after each submission.

Dashboard variables are documented in `dashboard/README.md`.

## Local Checks

```bash
python -m pytest tests -q
cd dashboard
npm test
```

On Windows PowerShell, if `npm` is blocked by execution policy, use:

```bat
cmd /c npm test
```

## Operational Notes

- Avoid changing Bot runtime code while production is healthy unless there is a clear reason and tests pass.
- Feature work should be done on a feature branch, then pushed and deployed intentionally.
- Do not rely blindly on automatic deploys. Confirm Railway / Vercel deployment status after changes that affect production.
- External integration docs should use placeholders such as `<BROADCAST_API_KEY>`; share real keys through a secure channel only.
