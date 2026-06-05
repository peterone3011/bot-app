# Roles Management — Design Spec
Date: 2026-06-05

## Overview

Replace the static hardcoded role list in the bot with a database-driven list managed via the dashboard. Remove the now-unused 站点管理 and 全局设置 pages.

## Database Changes

Run via Supabase Management API (`sbp_*` token):

```sql
CREATE TABLE roles (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  label         text NOT NULL,
  description   text NOT NULL DEFAULT '',
  display_order integer NOT NULL DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- Keep roles in sync with updated_at on every update
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;
CREATE TRIGGER roles_set_updated_at
  BEFORE UPDATE ON roles
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

INSERT INTO roles (label, description, display_order) VALUES
  ('📢 Exclusive Updates', 'Access our exclusive updates channel', 0),
  ('🎰Gaming Alerts',      'Get notified for jackpots and big wins', 1);

-- RLS: enable and deny anonymous access; service role bypasses RLS implicitly
ALTER TABLE roles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "deny anon" ON roles FOR ALL TO anon USING (false);

-- Prerequisite: deploy dashboard + bot code changes before running this
DROP TABLE sites;
```

## Dashboard — Files to Add

| File | Description |
|---|---|
| `app/api/roles/route.ts` | GET list (auth required), POST add, PUT reorder |
| `app/api/roles/[id]/route.ts` | PUT rename, DELETE |
| `app/dashboard/roles/page.tsx` | 身份组管理 page (server component) |
| `components/roles-list.tsx` | Drag-drop role list (client component) |
| `__tests__/roles-list.test.tsx` | Unit tests mirroring existing sites-list tests |

All modelled on the existing `sites` equivalents. Key differences:
- Table name: `roles`; field: `label` instead of `name`
- Delete confirm text references roles, not sites

**PUT reorder payload** (same as `/api/sites` PUT):
```json
[{ "id": "<uuid>", "display_order": 0 }, { "id": "<uuid>", "display_order": 1 }]
```
Full array of all roles with their new `display_order` values. API does a bulk `upsert` on conflict by `id`.

**GET /api/roles authentication**: required (session check), consistent with `/api/sites`.

## Dashboard — Files to Delete

- `app/api/sites/route.ts`
- `app/api/sites/[id]/route.ts`
- `app/api/settings/route.ts`
- `app/dashboard/sites/page.tsx`
- `app/dashboard/settings/page.tsx`
- `components/sites-list.tsx`
- `__tests__/settings-page.test.tsx`
- `__tests__/sites-list-rename.test.tsx`

## Dashboard — Files to Modify

**`lib/types.ts`**: replace `Site` interface with `Role` (`label` instead of `name`, add `description` and `updated_at`); remove `Config` interface.

**`components/sidebar.tsx`**: replace `/dashboard/sites` nav item with `/dashboard/roles` (label: 身份组管理, icon: Users); remove `/dashboard/settings` nav item.

## Bot Changes

**`cogs/db.py`**:
- Add `load_roles() -> list[dict]` — reads `id`, `label`, `description`, `display_order` from `roles` ordered by `display_order`
- Remove `load_sites()`

**`cogs/roles.py`**:
- Remove module-level `SUBSCRIPTION_ROLES` constant
- Remove `get_config("roles_channel_name", ...)` call; hardcode `"🔔roles"` directly
- In `_post_role_embeds()`: call `load_roles()` fresh each time to build the `discord.SelectOption` list
  - If `load_roles()` raises an exception: log the error and return early (bot keeps running, existing Discord message unchanged)
  - If `load_roles()` returns an empty list: log a warning and return early (same behaviour)
- `SubscriptionSelect.__init__` accepts an `options` list parameter (passed in from `_post_role_embeds`)

**Effect timing**: `_post_role_embeds()` is called on `on_ready` and `cog_load`, both of which fire on bot restart or reconnect. Role changes in the dashboard take effect on the bot's next restart or Discord reconnect — no caching, each call queries the DB fresh.

## Out of Scope

- Hot-reload roles without reconnect
- Per-role emoji icon management in dashboard
- Description field editable in dashboard (stored in DB, set at seed time only)
