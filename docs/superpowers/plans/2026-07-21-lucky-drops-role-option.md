# Lucky Drops Role Option Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the existing Discord role `🎉Lucky Drops` as the third option in the live `🔔roles` selector.

**Architecture:** Use the existing Supabase-driven role model as the durable source of truth, then patch the existing Discord selector message in place for immediate visibility. All writes are idempotent and followed by read-back verification.

**Tech Stack:** Supabase Python client, Discord REST API v10, Railway environment variables, PowerShell, Python

## Global Constraints

- Do not create, rename, reposition, or delete Discord roles.
- Do not change channel or category permission overwrites.
- Do not restart or redeploy the production bot.
- Do not modify runtime code or secrets.
- Preserve the existing selector message ID and `custom_id=subscription_role_select`.

---

### Task 1: Publish and Verify the Lucky Drops Selector Option

**Files:**
- No runtime files are created or modified.
- Reference: `cogs/roles.py`

**Interfaces:**
- Consumes: Supabase `roles` rows ordered by `display_order`; Discord role ID `1519235126201024633`; existing bot-authored selector message in channel `1498589172909211758`.
- Produces: One Supabase role row and one live selector option with label/value `🎉Lucky Drops`.

- [ ] **Step 1: Capture the pre-change state**

Read the current Supabase role rows, Discord role, `EVENTS` category overwrite, and existing `🔔roles` message. Abort if the role name is not exactly `🎉Lucky Drops`, if duplicate Supabase rows already exist, or if the target message does not contain `custom_id=subscription_role_select`.

- [ ] **Step 2: Upsert the durable Supabase row**

Use a fixed UUID and upsert the following exact record:

```json
{
  "id": "9f13ab53-6005-4cf6-8316-38266bc21413",
  "label": "🎉Lucky Drops",
  "description": "Access exclusive events and rewards",
  "display_order": 2
}
```

Before the upsert, if a row with label `🎉Lucky Drops` already exists, reuse that row instead of creating a second row.

- [ ] **Step 3: Patch the existing Discord message in place**

Preserve the current message content and embed. Replace only the selector options with the Supabase-ordered list and preserve this component identity:

```json
{
  "type": 3,
  "custom_id": "subscription_role_select",
  "min_values": 1,
  "max_values": 1
}
```

The resulting options must be exactly:

```text
📢 Exclusive Updates
🎰Gaming Alerts
🎉Lucky Drops
```

- [ ] **Step 4: Verify all live state**

Read back and confirm:

```text
Supabase: exactly one 🎉Lucky Drops row, display_order 2
Discord selector: exactly three options, Lucky Drops is third
Discord component: custom_id subscription_role_select
Discord role: ID 1519235126201024633 still named 🎉Lucky Drops
EVENTS overwrite: unchanged from the captured pre-change value
```

- [ ] **Step 5: Record completion without a deployment**

Do not commit runtime code, push, restart Railway, or redeploy. Report the existing roles message ID and verification results.

