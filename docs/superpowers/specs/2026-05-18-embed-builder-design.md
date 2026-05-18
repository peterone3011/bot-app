# Embed Builder Feature Design

## Overview

Allow server admins to build and send rich Discord embeds (with title, description, footer, image, link button, and color) via an interactive builder inside Discord. Supports both immediate posting and scheduled delivery. Multiple drafts can coexist and be managed independently.

## Requirements

- Single `/embed` slash command as entry point
- List view of all existing drafts and scheduled messages on entry
- Interactive field-by-field builder with persistent draft state
- Optional label per message for identification; falls back to auto-generated label
- Preview (overview) before sending
- Send immediately or schedule for a future time (UTC+8)
- Edit or cancel scheduled messages via the same builder interface
- All message state persists across bot restarts
- Error message if bot lacks permission in selected channel
- Edit already-published embeds via right-click context menu ("Edit Embed") or `/edit-embed <message_link>` command

## Architecture

**New file:** `cogs/embed_builder.py` — independent cog, hot-reloadable without affecting `roles.py`

**Unified storage:** `messages.json` in project root — single JSON array covering both drafts and scheduled messages, distinguished by a `status` field. Read from and written to disk on every operation; never cached in memory.

**Timer:** `discord.ext.tasks` loop every 60 seconds; sends and removes any entry with `status: "scheduled"` whose `send_at <= now`.

## Data Model

Each entry in `messages.json`:

```json
{
  "id": "uuid4-string",
  "status": "draft | scheduled",
  "label": "五月公告",
  "channel_id": 123456789,
  "send_at": "2026-05-20T20:00:00+08:00",
  "title": "Announcement",
  "description": "Full body text here.",
  "footer": "Footer text",
  "image_url": "https://example.com/image.png",
  "button_label": "Read more",
  "button_url": "https://example.com",
  "color": 10053324
}
```

**Field notes:**
- `label`: optional user-defined name; if null, display falls back to auto label (see below)
- `send_at`: null for drafts, ISO 8601 string with UTC+8 offset for scheduled entries
- All embed fields (title, description, footer, image_url, button_label, button_url, color) are optional (null if not set)

**Auto label format** (used when `label` is null):

```
#channel-name · YYYY-MM-DD · "Title preview…"
```

If title is also null: `#channel-name · YYYY-MM-DD · (untitled)`

## Interaction Flow

### Step 1 — Entry point

User runs `/embed`.

- **If `messages.json` has existing entries:** bot sends ephemeral message with a select dropdown listing all drafts and scheduled messages (max 25 entries shown), each labeled by its display label, plus a **[+ New Message]** button below.
- **If no entries exist:** skip the list and go directly to Step 2 (new message flow).

### Step 2 — New message creation

User clicks **[+ New Message]** (or is sent here automatically if no messages exist).

Bot sends an ephemeral channel select dropdown (`ChannelSelect` — always reflects current server channels). Below it, an optional **Label** text input (single line, max 100 chars). User selects channel and optionally fills label, then confirms.

Bot creates a new draft entry in `messages.json` with the chosen channel and label, then transitions to the builder (Step 3).

### Step 3 — Builder main view

Bot updates the ephemeral message to show the current draft state:

```
📋 五月公告  |  #announcements  |  Draft

Title:       (none)
Description: (none)
Footer:      (none)
Image:       (none)
Button:      (none)
Color:       (none)

[Edit Fields]   [Overview]   [Send]
```

For scheduled entries, the header shows the scheduled time instead of "Draft".

### Step 4 — Edit Fields

Clicking **Edit Fields** updates the message to show field buttons:

```
[Title]       [Description]   [Footer]
[Image URL]   [Link Button]   [Color]
[← Back]
```

Clicking any button opens a modal with only that field's input(s):

| Button | Modal inputs | Constraints |
|---|---|---|
| Title | Single-line text | Max 256 chars |
| Description | Paragraph text | Max 4000 chars |
| Footer | Single-line text | Max 2048 chars |
| Image URL | Single-line text | Optional; left blank = clear existing |
| Link Button | Two inputs: Label + URL | Both optional; leaving blank clears both |
| Color | Single-line hex (e.g. `9B59B6`) | Optional; left blank = clear existing |

On submit, the entry in `messages.json` is updated and the Edit Fields view refreshes to show current values.

### Step 5 — Overview

Clicking **Overview** sends a separate ephemeral message rendered as the actual Discord embed (with link button attached if both label and URL are set). Does not consume or modify the draft.

### Step 6 — Send

Clicking **Send** updates the message based on current status:

**If status is `draft`:**
```
[Send Now]   [Schedule]   [← Back]
```

**If status is `scheduled`:**
```
[Send Now]   [Update Schedule]   [Cancel Schedule]   [← Back]
```

**Send Now:** Posts the embed to the selected channel immediately. On permission error, sends an ephemeral error message. On success, removes the entry from `messages.json` and confirms.

**Schedule / Update Schedule:** Opens a modal with one field — send time in `YYYY-MM-DD HH:MM` (Beijing time / UTC+8). Validates format and that the time is in the future. Updates `status` to `"scheduled"` and sets `send_at`. Confirms with the formatted send time.

**Cancel Schedule:** Reverts `status` to `"draft"` and clears `send_at`. Confirms with ephemeral message. Entry remains editable.

## Editing Published Embeds

Two entry points reconstruct a draft from an existing bot message, then open the same builder interface.

### Entry point A — Context menu

User right-clicks any bot message → **Apps → Edit Embed**. Bot validates the message was sent by itself and contains an embed, then reconstructs a temporary draft from the embed fields and any link button component. Opens the builder pre-filled.

### Entry point B — Slash command

`/edit-embed message_link:<url>` — user pastes the Discord message link (format `https://discord.com/channels/GUILD/CHANNEL/MESSAGE`). Bot parses channel and message IDs, fetches the message, performs the same validation and reconstruction.

### Edit-mode builder differences

When a draft carries a `message_id`, the **Send** step shows only one button: **[Save Changes]** (replaces Send Now / Schedule). Clicking it edits the original message in-place. On success, the draft is removed from `messages.json`.

### Draft reconstruction

All embed fields are read from `discord.Message.embeds[0]`. The link button (if any) is read from `discord.Message.components`. The reconstructed draft is saved to `messages.json` as a regular draft entry with an additional `message_id` field.

## Embed Rendering

```python
embed = discord.Embed(
    title=entry["title"],
    description=entry["description"],
    color=entry["color"],
)
if entry["footer"]:
    embed.set_footer(text=entry["footer"])
if entry["image_url"]:
    embed.set_image(url=entry["image_url"])

view = discord.ui.View()
if entry["button_label"] and entry["button_url"]:
    view.add_item(discord.ui.Button(
        label=entry["button_label"],
        url=entry["button_url"],
        style=discord.ButtonStyle.link,
    ))
```

## Error Handling

| Scenario | Behavior |
|---|---|
| Bot lacks send permission in channel | Ephemeral error: "Bot doesn't have permission to post in #channel-name" |
| Invalid hex color input | Ephemeral error after modal submit; entry unchanged |
| Invalid time format on schedule | Ephemeral error; entry unchanged |
| Scheduled time is in the past | Ephemeral error; user must re-enter |
| Channel deleted before scheduled send | Log error, remove entry from JSON, continue loop |
| Image URL unreachable | Message sends; Discord shows broken image (acceptable) |
| `messages.json` missing on startup | Create empty file and continue |
| More than 25 messages in list | Show first 25 (sorted: scheduled first by send_at, then drafts by creation time) |
| Edit target message not found (deleted) | Ephemeral error: "Original message not found" |
| Invalid message link format | Ephemeral error; command aborted |
| Message not sent by this bot | Ephemeral error: "That message was not sent by this bot" |
| Message has no embed | Ephemeral error: "That message has no embed" |

## Hot-Reload Compatibility

- `messages.json` is read/written on every operation, never cached
- Task loop stopped in `cog_unload`, restarted in `cog_load`
- `!reload embed_builder` works cleanly with no data loss (all state is on disk)
