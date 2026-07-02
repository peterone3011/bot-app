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
  updates.py           Lark Bitable -> Discord updates polling
  community_metrics.py Daily/weekly Discord community metrics -> Lark Sheet
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
| Updates source | Lark Bitable | Bot polls every 5 minutes and publishes due records. |

## Main Workflows

- **Notification roles**: `/dashboard/roles` manages the role list. `cogs/roles.py` loads the list from Supabase and updates the `🔔roles` selector message.
- **Embeds**: Dashboard and `/embed` slash command manage draft, scheduled, and published embed messages.
- **Big Win**: `cogs/bigwin.py` calls `GET /api/broadcast/bigwin` every random 6-14 hours. Real external wins can call `POST /api/broadcast/bigwin` with `amount` and `game`.
- **Big Win history**: Dashboard page `/dashboard/bigwin` reads the last 30 days of Redis-backed broadcast records.
- **Jackpot**: `cogs/jackpot.py` posts at 19:00 Beijing time when `JACKPOT_ENABLED=1`.
- **Updates**: `cogs/updates.py` reads Lark Bitable records with status `待发布` and a date before today, posts to Discord, then marks them `已发布`.
- **Community metrics**: `cogs/community_metrics.py` records join/leave/role-subscribe events, then writes daily metrics at 12:00 Beijing time and weekly metrics every Friday at 12:00 Beijing time to the Lark sheet `FB 社群总表`.
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
| `LARK_APP_ID` / `LARK_APP_SECRET` / `LARK_NOTIFY_CHAT_ID` | Lark Bitable and alert access |
| `BITABLE_APP_TOKEN` / `BITABLE_TABLE_ID` | Updates Bitable source |
| `COMMUNITY_METRICS_SPREADSHEET_TOKEN` / `COMMUNITY_METRICS_SHEET_ID` | Optional override for the community metrics sheet |
| `METRICS_GAMING_ROLE_NAME` / `METRICS_UPDATES_ROLE_NAME` | Optional role-name matching override for metrics |

Default community metrics target:

```text
spreadsheet: PA8usyjmshX40HtXaeTjkr4Apne
sheet: e348a1
```

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
