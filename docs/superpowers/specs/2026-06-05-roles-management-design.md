# Roles Management — Design Spec
Date: 2026-06-05

## Overview

Replace the static hardcoded role list in the bot with a database-driven list managed via the dashboard. Remove the now-unused 站点管理 and 全局设置 pages.

## Database Changes — Phase 1 (run before deploying code)

```sql
CREATE TABLE roles (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  label         varchar(100) NOT NULL,
  description   text NOT NULL DEFAULT '',
  display_order integer NOT NULL DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

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

ALTER TABLE roles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "deny anon" ON roles FOR ALL TO anon USING (false);
```

## Database Changes — Phase 2 (run after deployment is verified)

```sql
DROP TABLE sites;
```

## Dashboard — Files to Add

| File | Description |
|---|---|
| `app/api/roles/route.ts` | GET list (auth required), POST add, PUT reorder |
| `app/api/roles/[id]/route.ts` | PUT rename/description, DELETE |
| `app/dashboard/roles/page.tsx` | 身份组管理 page (server component) |
| `components/roles-list.tsx` | Drag-drop role list (client component) |
| `__tests__/roles-list.test.tsx` | Unit tests mirroring existing sites-list tests |

**PUT reorder payload:**
```json
[{ "id": "<uuid>", "display_order": 0 }, { "id": "<uuid>", "display_order": 1 }]
```
Full array with new `display_order` values. API does a bulk `upsert` on conflict by `id`.

**DELETE protection:** Before deleting, API checks `SELECT count(*) FROM roles`. If count is 1, return 400 with `"Cannot delete the last role"`.

**Label validation:** Both API (POST/PUT) and frontend enforce `label.length <= 100` (matching Discord SelectOption limit). DB column is `varchar(100)` as a hard stop.

**Description editing:** Each role row in the dashboard includes an inline editable description field. `PUT /api/roles/[id]` accepts both `label` and `description` updates.

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

**`lib/types.ts`**: replace `Site` with `Role` (`label` instead of `name`, add `description` and `updated_at`); remove `Config`.

**`components/sidebar.tsx`**: replace `/dashboard/sites` with `/dashboard/roles` (label: 身份组管理, icon: Users); remove `/dashboard/settings`.

## Bot Changes

**`cogs/db.py`**:
- Add `load_roles() -> list[dict]` — reads `id`, `label`, `description`, `display_order` from `roles` ordered by `display_order`
- Remove `load_sites()`

**`cogs/roles.py`**:
- Remove module-level `SUBSCRIPTION_ROLES` constant
- Remove `get_config("roles_channel_name", ...)` call; hardcode `"🔔roles"` directly
- In `_post_role_embeds()`: call `load_roles()` fresh each time to build the `discord.SelectOption` list
  - If `load_roles()` raises an exception: log the error and return early (existing Discord message unchanged)
  - If `load_roles()` returns an empty list: log a warning and return early (same behaviour)
- `SubscriptionSelect.__init__` accepts an `options` list parameter passed in from `_post_role_embeds`

**Effect timing:** `_post_role_embeds()` queries the DB fresh on every call (on_ready and cog_load). Role changes take effect on next bot restart or Discord reconnect.

## Decisions Not Taken

| Suggestion | Reason skipped |
|---|---|
| `display_order` unique constraint | Bulk reorder upsert hits intermediate states that would violate the constraint; dashboard prevents duplicates anyway |
| `created_by` / `updated_by` audit fields | Single admin account, no multi-user scenario; YAGNI |
| Local role cache on DB failure | Bot already returns early on error, leaving the existing Discord message intact — sufficient fallback with no extra complexity |
| Migrate sites data to roles | `sites` table contains site names, not role names; seed data covers the two initial roles |
