# Fortune Purple Dashboard

Internal Next.js dashboard for managing the Fortune Purple Discord Bot. It is deployed to Vercel and shares Supabase/Redis infrastructure with the Railway Bot.

## Stack

- Next.js 14 App Router
- TypeScript
- Tailwind CSS + shadcn-style UI components
- NextAuth v5 with Discord OAuth
- Supabase service-role client for server-side database access
- Upstash Redis / Ratelimit
- Vitest + Testing Library

## Pages

| Route | Purpose |
|---|---|
| `/login` | Discord OAuth login |
| `/dashboard/embeds` | Embed message list |
| `/dashboard/embeds/new` | Create a new embed draft |
| `/dashboard/embeds/[id]` | Edit and publish an embed |
| `/dashboard/roles` | Manage notification roles shown by the Bot selector |
| `/dashboard/bigwin` | View Big Win broadcast history |

## API Routes

| Route | Purpose |
|---|---|
| `/api/auth/[...nextauth]` | NextAuth handler |
| `/api/embeds` and `/api/embeds/[id]` | Embed CRUD |
| `/api/embeds/[id]/publish` | Publish or update a Discord embed |
| `/api/roles` and `/api/roles/[id]` | Role CRUD and ordering |
| `/api/discord/channels` | Discord channel lookup for forms |
| `/api/broadcast/bigwin` | Big Win broadcast endpoint |
| `/api/broadcast/bigwin/history` | Big Win history endpoint |

Dashboard and admin APIs require an authenticated Discord admin session, except the Big Win broadcast endpoint, which uses bearer-token auth for cron/API callers.

## Environment Variables

Real values belong in Vercel environment variables or local `.env.local`, not in git.

| Variable | Purpose |
|---|---|
| `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` | Discord OAuth app |
| `DISCORD_GUILD_ID` / `DISCORD_ADMIN_ROLE_ID` | Admin access check |
| `DISCORD_BOT_TOKEN` | Send Discord messages through API routes |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | Server-side DB access |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | Redis and rate limiting |
| `NEXTAUTH_SECRET` / `AUTH_SECRET` | NextAuth session signing |
| `BROADCAST_API_KEY` | External Big Win POST auth |
| `CRON_SECRET` | Bot cron GET auth |
| `BIGWIN_CHANNEL_ID` / `BIGWIN_BUTTON_URL` | Big Win Discord target and button |

## Local Development

```bash
npm install
npm run dev
```

The dev server uses port `3099`:

```text
http://localhost:3099
```

## Verification

```bash
npm test
npm run build
```

On Windows PowerShell, if script execution blocks `npm`, run tests through `cmd`:

```bat
cmd /c npm test
```

## Deployment

Production runs on Vercel:

```text
https://fortunepurplebot.vercel.app
```

GitHub integration may not always auto-trigger. For production changes, verify the Vercel deployment manually after pushing.
