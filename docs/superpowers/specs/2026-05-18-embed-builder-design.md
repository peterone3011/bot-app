# Embed Builder Feature Design

## Overview

Allow server admins to build and send rich Discord embeds (with title, description, footer, image, link button, and color) via an interactive builder inside Discord. Supports both immediate posting and scheduled delivery.

## Requirements

- Single `/embed` slash command as entry point
- Interactive field-by-field builder with live draft state
- Preview (overview) before sending
- Send immediately or schedule for a future time (UTC+8)
- Scheduled messages persist across bot restarts
- Error message if bot lacks permission in selected channel

## Architecture

**New file:** `cogs/embed_builder.py` — independent cog, hot-reloadable without affecting `roles.py`

**Draft storage:** In-memory `dict[int, EmbedDraft]` keyed by `user_id`. Temporary; lost on restart (acceptable — drafts are short-lived).

**Scheduled storage:** `scheduled_embeds.json` in project root — JSON array, written on every change.

**Timer:** `discord.ext.tasks` loop every 60 seconds; sends and removes any entry whose `send_at <= now`.

## Data Models

### EmbedDraft (in-memory)

```python
@dataclass
class EmbedDraft:
    channel_id: int
    title: str | None = None
    description: str | None = None
    footer: str | None = None
    image_url: str | None = None
    button_label: str | None = None
    button_url: str | None = None
    color: int | None = None  # e.g. 0x9B59B6
```

### Scheduled entry (JSON)

```json
{
  "id": "uuid4-string",
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

All embed fields except `channel_id` and `send_at` are optional (null if not set).

## Interaction Flow

### Step 1 — Channel selection

User runs `/embed`. Bot replies with an ephemeral message containing a `ChannelSelect` dropdown (Discord native component — always reflects current server channels). User picks the target channel.

### Step 2 — Builder main view

Bot updates the ephemeral message to show the builder:

```
📋 Draft  |  #announcements

Title:       (none)
Description: (none)
Footer:      (none)
Image:       (none)
Button:      (none)
Color:       (none)

[Edit Fields]   [Overview]   [Send]
```

### Step 3 — Edit Fields

Clicking **Edit Fields** updates the message to show field buttons:

```
[Title]       [Description]   [Footer]
[Image URL]   [Link Button]   [Color]
[← Back]
```

Clicking any button opens a modal with only that field's input(s):

| Button | Modal inputs |
|---|---|
| Title | Single-line text (max 256 chars) |
| Description | Paragraph text (max 4000 chars) |
| Footer | Single-line text (max 2048 chars) |
| Image URL | Single-line text, optional |
| Link Button | Two inputs: Label + URL |
| Color | Single-line hex input (e.g. `9B59B6` or `#9B59B6`), optional |

On submit, draft is updated and the Edit Fields view refreshes showing current values.

### Step 4 — Overview

Clicking **Overview** sends a separate ephemeral message rendered as the actual Discord embed (with link button attached if set). This does not consume or clear the draft.

### Step 5 — Send

Clicking **Send** updates the message:

```
[Send Now]   [Schedule]   [← Back]
```

**Send Now:** Posts the embed to the selected channel immediately. If the bot lacks permission, sends an ephemeral error instead. On success, clears the draft and confirms.

**Schedule:** Opens a modal with one field — send time in `YYYY-MM-DD HH:MM` format (Beijing time / UTC+8). On submit, validates the format and that the time is in the future, saves to `scheduled_embeds.json`, clears the draft, and confirms with the formatted send time.

## Embed Rendering

Built from draft fields at send time:

```python
embed = discord.Embed(
    title=draft.title,
    description=draft.description,
    color=draft.color,
)
if draft.footer:
    embed.set_footer(text=draft.footer)
if draft.image_url:
    embed.set_image(url=draft.image_url)

view = discord.ui.View()
if draft.button_label and draft.button_url:
    view.add_item(discord.ui.Button(
        label=draft.button_label,
        url=draft.button_url,
        style=discord.ButtonStyle.link,
    ))
```

## Error Handling

| Scenario | Behavior |
|---|---|
| Bot lacks send permission in channel | Ephemeral error: "Bot doesn't have permission to post in #channel-name" |
| Invalid hex color input | Modal rejects with ephemeral error; draft unchanged |
| Invalid time format on schedule | Ephemeral error; modal does not proceed |
| Scheduled time is in the past | Ephemeral error; user must re-enter |
| Channel deleted before scheduled send | Log error, skip and remove entry from JSON |
| Image URL unreachable | Message sends; Discord shows broken image (acceptable) |
| `scheduled_embeds.json` missing on startup | Create empty file and continue |

## Hot-Reload Compatibility

- JSON is read/written on every operation, never cached
- Task loop stopped in `cog_unload`, restarted in `cog_load`
- `!reload embed_builder` works cleanly; in-progress drafts are lost (acceptable)
