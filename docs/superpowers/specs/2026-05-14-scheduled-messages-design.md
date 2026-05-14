# Scheduled Messages Feature Design

## Overview

Allow the server operator to schedule plain messages (with optional image) to be sent to specific channels at a specified time, with a full management UI inside Discord.

## Requirements

- Create a scheduled message via `/schedule` slash command
- View, preview, edit, change channel, and cancel scheduled messages via `/schedule-list`
- Bot sends a regular (non-embed) message with text + image at the scheduled time
- Scheduled messages persist across bot restarts and hot-reloads
- All times in UTC+8 (Beijing Time)

## Architecture

**New file:** `cogs/scheduler.py` — independent cog, hot-reloadable without affecting `roles.py`

**Storage:** `scheduled_messages.json` in project root — simple JSON array, written on every change

**Timer:** `discord.ext.tasks` loop running every 60 seconds, checks for messages whose scheduled time has passed

**Entry point:** registered as a slash command group via `discord.app_commands`

## Data Model

Each scheduled message:

```json
{
  "id": "uuid4",
  "channel_id": 123456789,
  "send_at": "2026-05-15T20:00:00+08:00",
  "content": "Message text here",
  "image_url": "https://..." 
}
```

`image_url` is optional (null if not provided).

## Interaction Flow

### Creating a scheduled message

1. User types `/schedule`
2. Bot responds with an ephemeral channel-select dropdown
3. User selects a channel → modal opens with three fields:
   - **Send time** — format `YYYY-MM-DD HH:MM` (Beijing Time)
   - **Message content** — multiline text input
   - **Image URL** — optional, single-line text input
4. User submits modal → Bot validates time format, saves to JSON, replies ephemeral with a preview of the message and confirmation text

### Managing scheduled messages

1. User types `/schedule-list`
2. Bot replies ephemeral with a paginated list of all pending messages (sorted by send time), 5 per page with Previous/Next buttons, each showing: channel, send time, content preview (first 50 chars)
3. Each entry has four buttons: **Preview / Edit / Change Channel / Cancel**

**Preview** — Bot sends an ephemeral message showing exactly what the final message will look like

**Edit** — Modal opens with three fields (Send time / Content / Image URL). Any field left blank retains its current value. Non-blank fields overwrite current value. To remove an existing image URL, enter `remove` in the Image URL field.

**Change Channel** — Bot sends an ephemeral channel-select dropdown; selecting a new channel updates the record

**Cancel** — Bot removes the entry from JSON and confirms with ephemeral message

### Sending

Every 60 seconds the task loop checks all entries. Any entry whose `send_at` <= now is sent to its target channel as a regular Discord message (content + image URL on a new line if present), then removed from JSON.

## Error Handling

- Invalid time format on submit → ephemeral error, modal does not close (user must retry)
- Channel no longer exists at send time → log error, skip and remove entry
- Image URL unreachable → message still sends; Discord will show a broken preview (acceptable)
- JSON file missing on startup → create empty file, continue normally

## Hot-Reload Compatibility

- JSON file is read from disk on every write/read operation, not cached in memory
- The task loop is stopped in `cog_unload` and restarted in `cog_load`, so `!reload scheduler` works cleanly without duplicate timers or lost jobs
