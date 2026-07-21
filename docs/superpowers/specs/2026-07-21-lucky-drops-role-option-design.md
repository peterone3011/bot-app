# Lucky Drops Role Option Design

## Goal

Expose the existing Discord role `🎉Lucky Drops` in the `🔔roles` channel so members can subscribe or unsubscribe through the bot's existing role selector.

## Existing State

- Discord role ID `1519235126201024633` already exists as `🎉Lucky Drops`.
- The role already has permission to view the `EVENTS` category.
- The role selector is populated from the Supabase `roles` table.
- The current selector contains `📢 Exclusive Updates` and `🎰Gaming Alerts`.

## Change

1. Insert a third Supabase role row:
   - Label: `🎉Lucky Drops`
   - Description: `Access exclusive events and rewards`
   - Display order: `2`
2. Update the existing bot-authored selector message in `🔔roles` in place so the new option appears immediately.
3. Preserve the existing embed, existing options, message ID, and persistent component custom ID.

## Safety Boundaries

- Do not create, rename, reposition, or delete Discord roles.
- Do not change channel or category permission overwrites.
- Do not restart or redeploy the production bot.
- Do not modify runtime code or secrets.
- If either the Supabase write or Discord message update fails, inspect the resulting state before retrying. Do not create duplicate rows or messages.

## Verification

- Read the Supabase role list and confirm exactly one `🎉Lucky Drops` row at display order `2`.
- Read the existing `🔔roles` message and confirm it has all three options with `custom_id=subscription_role_select`.
- Confirm Discord role ID `1519235126201024633` still exists and the `EVENTS` permission overwrite is unchanged.

