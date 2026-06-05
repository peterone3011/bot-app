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
  created_at    timestamptz NOT NULL DEFAULT now()
);

INSERT INTO roles (label, description, display_order) VALUES
  ('📢 Exclusive Updates', 'Access our exclusive updates channel', 0),
  ('🎰Gaming Alerts',      'Get notified for jackpots and big wins', 1);

DROP TABLE sites;
```

## Dashboard — Files to Add

| File | Description |
|---|---|
| `app/api/roles/route.ts` | GET list, POST add, PUT reorder |
| `app/api/roles/[id]/route.ts` | PUT rename, DELETE |
| `app/dashboard/roles/page.tsx` | 身份组管理 page (server component) |
| `components/roles-list.tsx` | Drag-drop role list (client component) |

All modelled directly on the existing `sites` equivalents. Key differences:
- Table name: `roles`
- Field: `label` instead of `name`
- Delete confirm text updated to mention roles, not sites

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

**`lib/types.ts`**: replace `Site` interface with `Role` (rename `name` → `label`, add `description`); remove `Config` interface.

**`components/sidebar.tsx`**: replace `/dashboard/sites` nav item with `/dashboard/roles` (label: 身份组管理, icon: Users); remove `/dashboard/settings` nav item.

## Bot Changes

**`cogs/db.py`**: add `load_roles()` that returns `list[dict]` from `roles` table ordered by `display_order`; remove `load_sites()`.

**`cogs/roles.py`**:
- Remove module-level `SUBSCRIPTION_ROLES` constant
- In `_post_role_embeds()`: call `get_config("roles_channel_name", "🔔roles")` → replace with hardcoded `"🔔roles"`
- Build `discord.SelectOption` list dynamically from `load_roles()` each time `_post_role_embeds()` runs
- `SubscriptionSelect.__init__` still accepts a pre-built options list (passed in from `_post_role_embeds`)
- If DB returns empty list, log warning and skip posting

## Behaviour After Change

- Adding/removing a role in the dashboard takes effect on next bot restart (or next `on_ready`)
- No bot code changes required to add/remove roles
- Channel name "🔔roles" is hardcoded; no longer configurable via dashboard (acceptable — channel has never been renamed)

## Out of Scope

- Hot-reload roles without bot restart
- Per-role emoji icon management in dashboard
- Description field editable in dashboard (stored in DB, set at seed time only)
