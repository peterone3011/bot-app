# Scheduled Messages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/schedule` and `/schedule-list` slash commands so the operator can schedule plain Discord messages (with optional image) to any channel, with full preview/edit/cancel management inside Discord.

**Architecture:** New `cogs/scheduler.py` cog containing pure utility functions (fully unit-tested), Discord UI classes (Modal, View, Select, Button), and a `tasks.loop` timer firing every 60 seconds to send due messages. Persistent storage in `scheduled_messages.json`. Registered in `bot.py` alongside existing `roles` cog.

**Tech Stack:** discord.py 2.x, `discord.ext.tasks`, `discord.app_commands`, `discord.ui` (Modal, View, ChannelSelect, Button), Python stdlib (`json`, `uuid`, `datetime`), pytest

---

### Task 1: Core utility functions (TDD)

**Files:**
- Create: `cogs/scheduler.py`
- Create: `tests/test_scheduler.py`

- [ ] **Step 1: Install pytest**

Run: `pip install pytest`
Expected: installs or "already satisfied"

- [ ] **Step 2: Create `cogs/scheduler.py` with imports and constants only**

```python
import json
import os
import uuid
from datetime import datetime, timezone, timedelta

TZ_CST = timezone(timedelta(hours=8))
DATA_FILE = "scheduled_messages.json"
```

- [ ] **Step 3: Create `tests/test_scheduler.py` with failing tests for `parse_time`**

```python
import pytest
from datetime import datetime, timezone, timedelta
from cogs.scheduler import parse_time, load_messages, save_messages, is_due, TZ_CST

def test_parse_time_valid():
    result = parse_time("2026-05-15 20:00")
    assert result == datetime(2026, 5, 15, 20, 0, tzinfo=TZ_CST)

def test_parse_time_strips_whitespace():
    result = parse_time("  2026-05-15 20:00  ")
    assert result == datetime(2026, 5, 15, 20, 0, tzinfo=TZ_CST)

def test_parse_time_invalid_format():
    assert parse_time("not a date") is None

def test_parse_time_wrong_separator():
    assert parse_time("2026/05/15 20:00") is None
```

- [ ] **Step 4: Run tests — verify they fail**

Run: `pytest tests/test_scheduler.py -v`
Expected: ImportError — `parse_time` not defined

- [ ] **Step 5: Implement `parse_time` in `cogs/scheduler.py`**

```python
def parse_time(text: str) -> datetime | None:
    try:
        dt = datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=TZ_CST)
    except ValueError:
        return None
```

- [ ] **Step 6: Run parse_time tests — verify they pass**

Run: `pytest tests/test_scheduler.py -v`
Expected: 4 PASSED

- [ ] **Step 7: Add failing tests for `load_messages`, `save_messages`, `is_due`**

Append to `tests/test_scheduler.py`:
```python
def test_load_messages_missing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_messages() == []

def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    messages = [{
        "id": "abc123",
        "channel_id": 111,
        "send_at": "2026-05-15T20:00:00+08:00",
        "content": "hello",
        "image_url": None,
    }]
    save_messages(messages)
    assert load_messages() == messages

def test_is_due_past_message():
    assert is_due({"send_at": "2020-01-01T00:00:00+08:00"}) is True

def test_is_due_future_message():
    assert is_due({"send_at": "2099-01-01T00:00:00+08:00"}) is False
```

- [ ] **Step 8: Run all tests — verify new ones fail**

Run: `pytest tests/test_scheduler.py -v`
Expected: 4 PASSED, 4 errors (ImportError on new names)

- [ ] **Step 9: Implement `load_messages`, `save_messages`, `is_due`**

Append to `cogs/scheduler.py`:
```python
def load_messages() -> list[dict]:
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_messages(messages: list[dict]) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

def is_due(message: dict) -> bool:
    send_at = datetime.fromisoformat(message["send_at"])
    return datetime.now(tz=TZ_CST) >= send_at
```

- [ ] **Step 10: Run all tests — verify all pass**

Run: `pytest tests/test_scheduler.py -v`
Expected: 8 PASSED

- [ ] **Step 11: Commit**

```bash
git add cogs/scheduler.py tests/test_scheduler.py
git commit -m "feat: scheduler core utilities with tests"
```

---

### Task 2: SchedulerCog skeleton + send loop

**Files:**
- Modify: `cogs/scheduler.py`

- [ ] **Step 1: Add discord imports at the top of `cogs/scheduler.py`**

After the existing imports, add:
```python
import discord
from discord.ext import commands, tasks
from discord import app_commands
```

- [ ] **Step 2: Append `SchedulerCog` and `setup` to `cogs/scheduler.py`**

```python
class SchedulerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_unload(self):
        self.send_loop.cancel()

    async def cog_load(self):
        self.send_loop.start()

    @tasks.loop(seconds=60)
    async def send_loop(self):
        messages = load_messages()
        remaining = []
        for msg in messages:
            if not is_due(msg):
                remaining.append(msg)
                continue
            channel = self.bot.get_channel(msg["channel_id"])
            if channel is None:
                print(f"[scheduler] channel {msg['channel_id']} not found, dropping {msg['id']}")
                continue
            text = msg["content"]
            if msg.get("image_url"):
                text += f"\n{msg['image_url']}"
            try:
                await channel.send(text)
            except Exception as e:
                print(f"[scheduler] failed to send {msg['id']}: {e}")
                remaining.append(msg)
        if len(remaining) != len(messages):
            save_messages(remaining)

    @send_loop.before_loop
    async def before_send_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(SchedulerCog(bot))
```

- [ ] **Step 3: Verify tests still pass**

Run: `pytest tests/test_scheduler.py -v`
Expected: 8 PASSED

- [ ] **Step 4: Commit**

```bash
git add cogs/scheduler.py
git commit -m "feat: add SchedulerCog with send loop"
```

---

### Task 3: `/schedule` command (channel select → modal → save)

**Files:**
- Modify: `cogs/scheduler.py`
- Modify: `bot.py`

- [ ] **Step 1: Insert `ScheduleModal` into `cogs/scheduler.py` before `SchedulerCog`**

```python
class ScheduleModal(discord.ui.Modal, title="Schedule a Message"):
    send_time = discord.ui.TextInput(
        label="Send Time (YYYY-MM-DD HH:MM, Beijing Time)",
        placeholder="2026-05-15 20:00",
        max_length=16,
    )
    content = discord.ui.TextInput(
        label="Message Content",
        style=discord.TextStyle.paragraph,
        max_length=2000,
    )
    image_url = discord.ui.TextInput(
        label="Image URL (optional)",
        required=False,
        max_length=500,
    )

    def __init__(self, channel_id: int):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        dt = parse_time(self.send_time.value)
        if dt is None:
            await interaction.response.send_message(
                "❌ Invalid time format. Use `YYYY-MM-DD HH:MM` (e.g. `2026-05-15 20:00`)",
                ephemeral=True,
            )
            return

        url = self.image_url.value.strip() or None
        msg = {
            "id": str(uuid.uuid4()),
            "channel_id": self.channel_id,
            "send_at": dt.isoformat(),
            "content": self.content.value,
            "image_url": url,
        }
        messages = load_messages()
        messages.append(msg)
        save_messages(messages)

        channel = interaction.guild.get_channel(self.channel_id)
        ch_mention = channel.mention if channel else f"<#{self.channel_id}>"
        preview = (
            f"✅ Scheduled for **{dt.strftime('%Y-%m-%d %H:%M')}** (Beijing Time) in {ch_mention}\n\n"
            f"**Preview:**\n{self.content.value}"
        )
        if url:
            preview += f"\n{url}"
        await interaction.response.send_message(preview, ephemeral=True)
```

- [ ] **Step 2: Insert `ChannelSelectView` into `cogs/scheduler.py` after `ScheduleModal`**

```python
class ChannelSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Select a channel...",
        channel_types=[discord.ChannelType.text],
    )
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.send_modal(ScheduleModal(select.values[0].id))
```

- [ ] **Step 3: Add `/schedule` command to `SchedulerCog`**

Inside `SchedulerCog`, after `__init__`:
```python
@app_commands.command(name="schedule", description="Schedule a message to a channel")
async def schedule(self, interaction: discord.Interaction):
    await interaction.response.send_message(
        "Select the channel to post in:", view=ChannelSelectView(), ephemeral=True
    )
```

- [ ] **Step 4: Load cog and add tree sync in `bot.py`**

In `bot.py`, replace:
```python
await bot.load_extension("cogs.roles")
await bot.start(TOKEN)
```
with:
```python
await bot.load_extension("cogs.roles")
await bot.load_extension("cogs.scheduler")

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

await bot.start(TOKEN)
```

- [ ] **Step 5: Verify tests still pass**

Run: `pytest tests/test_scheduler.py -v`
Expected: 8 PASSED

- [ ] **Step 6: Commit**

```bash
git add cogs/scheduler.py bot.py
git commit -m "feat: add /schedule command with channel select and modal"
```

---

### Task 4: `/schedule-list` with Preview and Cancel

**Files:**
- Modify: `cogs/scheduler.py`

Layout: 4 messages per page. Each message occupies one button row (4 buttons: Preview, Edit, Channel, Cancel). Navigation row at row 4. Total: max 4×4 + 2 = 18 components, within Discord's 25-component limit.

- [ ] **Step 1: Insert `build_list_embed` helper before `SchedulerCog`**

```python
PER_PAGE = 4

def build_list_embed(messages: list[dict], page: int, guild: discord.Guild) -> discord.Embed:
    total = len(messages)
    start = page * PER_PAGE
    end = min(start + PER_PAGE, total)
    total_pages = max(1, -(-total // PER_PAGE))

    embed = discord.Embed(title="Scheduled Messages", color=0x9B59B6)
    if not messages:
        embed.description = "No scheduled messages."
        return embed

    for i, msg in enumerate(messages[start:end]):
        num = start + i + 1
        channel = guild.get_channel(msg["channel_id"])
        ch_text = channel.mention if channel else f"<#{msg['channel_id']}>"
        dt = datetime.fromisoformat(msg["send_at"])
        preview = msg["content"][:50] + ("…" if len(msg["content"]) > 50 else "")
        embed.add_field(
            name=f"#{num}  {dt.strftime('%Y-%m-%d %H:%M')}  →  {ch_text}",
            value=preview,
            inline=False,
        )

    embed.set_footer(text=f"Page {page + 1}/{total_pages}  ·  {total} total")
    return embed
```

- [ ] **Step 2: Insert button classes before `SchedulerCog`**

```python
class PreviewButton(discord.ui.Button):
    def __init__(self, row_idx: int, msg_id: str):
        super().__init__(label="👁 Preview", style=discord.ButtonStyle.secondary, row=row_idx)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        msg = next((m for m in load_messages() if m["id"] == self.msg_id), None)
        if msg is None:
            await interaction.response.send_message("❌ Not found.", ephemeral=True)
            return
        text = msg["content"]
        if msg.get("image_url"):
            text += f"\n{msg['image_url']}"
        await interaction.response.send_message(f"**Preview:**\n{text}", ephemeral=True)


class EditButton(discord.ui.Button):
    def __init__(self, row_idx: int, msg_id: str):
        super().__init__(label="✏️ Edit", style=discord.ButtonStyle.primary, row=row_idx)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EditModal(self.msg_id, self.view))


class ChangeChannelButton(discord.ui.Button):
    def __init__(self, row_idx: int, msg_id: str):
        super().__init__(label="📍 Channel", style=discord.ButtonStyle.secondary, row=row_idx)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Select the new channel:",
            view=ChangeChannelSelectView(self.msg_id, self.view),
            ephemeral=True,
        )


class CancelButton(discord.ui.Button):
    def __init__(self, row_idx: int, msg_id: str):
        super().__init__(label="❌ Cancel", style=discord.ButtonStyle.danger, row=row_idx)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        messages = load_messages()
        new_messages = [m for m in messages if m["id"] != self.msg_id]
        if len(new_messages) == len(messages):
            await interaction.response.send_message("❌ Not found.", ephemeral=True)
            return
        save_messages(new_messages)
        view: ScheduleListView = self.view
        view.messages = new_messages
        if view.page > 0 and view.page * PER_PAGE >= len(new_messages):
            view.page -= 1
        view._build()
        await interaction.response.edit_message(
            embed=build_list_embed(view.messages, view.page, view.guild), view=view
        )
```

- [ ] **Step 3: Insert nav button classes and `ScheduleListView` before `SchedulerCog`**

```python
class PrevPageButton(discord.ui.Button):
    def __init__(self, page: int):
        super().__init__(label="◀ Prev", style=discord.ButtonStyle.secondary, row=4)
        self.page = page

    async def callback(self, interaction: discord.Interaction):
        view: ScheduleListView = self.view
        view.page = self.page - 1
        view._build()
        await interaction.response.edit_message(
            embed=build_list_embed(view.messages, view.page, view.guild), view=view
        )


class NextPageButton(discord.ui.Button):
    def __init__(self, page: int):
        super().__init__(label="Next ▶", style=discord.ButtonStyle.secondary, row=4)
        self.page = page

    async def callback(self, interaction: discord.Interaction):
        view: ScheduleListView = self.view
        view.page = self.page + 1
        view._build()
        await interaction.response.edit_message(
            embed=build_list_embed(view.messages, view.page, view.guild), view=view
        )


class ScheduleListView(discord.ui.View):
    def __init__(self, messages: list[dict], guild: discord.Guild, page: int = 0):
        super().__init__(timeout=300)
        self.messages = messages
        self.guild = guild
        self.page = page
        self._build()

    def _build(self):
        self.clear_items()
        start = self.page * PER_PAGE
        end = min(start + PER_PAGE, len(self.messages))
        for i, msg in enumerate(self.messages[start:end]):
            self.add_item(PreviewButton(i, msg["id"]))
            self.add_item(EditButton(i, msg["id"]))
            self.add_item(ChangeChannelButton(i, msg["id"]))
            self.add_item(CancelButton(i, msg["id"]))
        if self.page > 0:
            self.add_item(PrevPageButton(self.page))
        if end < len(self.messages):
            self.add_item(NextPageButton(self.page))
```

- [ ] **Step 4: Add `/schedule_list` command to `SchedulerCog`**

Inside `SchedulerCog`, add:
```python
@app_commands.command(name="schedule_list", description="View and manage scheduled messages")
async def schedule_list(self, interaction: discord.Interaction):
    messages = sorted(load_messages(), key=lambda m: m["send_at"])
    await interaction.response.send_message(
        embed=build_list_embed(messages, 0, interaction.guild),
        view=ScheduleListView(messages, interaction.guild),
        ephemeral=True,
    )
```

- [ ] **Step 5: Verify tests still pass**

Run: `pytest tests/test_scheduler.py -v`
Expected: 8 PASSED

- [ ] **Step 6: Commit**

```bash
git add cogs/scheduler.py
git commit -m "feat: add /schedule-list with preview and cancel"
```

---

### Task 5: Edit flow

**Files:**
- Modify: `cogs/scheduler.py`

- [ ] **Step 1: Insert `EditModal` before `ScheduleListView`**

```python
class EditModal(discord.ui.Modal, title="Edit Scheduled Message"):
    send_time = discord.ui.TextInput(
        label="New Send Time (blank = keep current)",
        placeholder="YYYY-MM-DD HH:MM",
        required=False,
        max_length=16,
    )
    content = discord.ui.TextInput(
        label="New Content (blank = keep current)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=2000,
    )
    image_url = discord.ui.TextInput(
        label="New Image URL  (blank=keep, 'remove'=clear)",
        required=False,
        max_length=500,
    )

    def __init__(self, msg_id: str, list_view: "ScheduleListView"):
        super().__init__()
        self.msg_id = msg_id
        self.list_view = list_view

    async def on_submit(self, interaction: discord.Interaction):
        messages = load_messages()
        msg = next((m for m in messages if m["id"] == self.msg_id), None)
        if msg is None:
            await interaction.response.send_message("❌ Message not found.", ephemeral=True)
            return

        if self.send_time.value.strip():
            dt = parse_time(self.send_time.value)
            if dt is None:
                await interaction.response.send_message(
                    "❌ Invalid time format. Use `YYYY-MM-DD HH:MM`", ephemeral=True
                )
                return
            msg["send_at"] = dt.isoformat()

        if self.content.value.strip():
            msg["content"] = self.content.value

        url_input = self.image_url.value.strip()
        if url_input.lower() == "remove":
            msg["image_url"] = None
        elif url_input:
            msg["image_url"] = url_input

        save_messages(messages)
        # Modal interactions cannot edit the original list message directly.
        # Confirm success; user can re-open /schedule_list to see changes.
        await interaction.response.send_message("✅ Updated.", ephemeral=True)
```

- [ ] **Step 2: Verify tests still pass**

Run: `pytest tests/test_scheduler.py -v`
Expected: 8 PASSED

- [ ] **Step 3: Commit**

```bash
git add cogs/scheduler.py
git commit -m "feat: add edit flow for scheduled messages"
```

---

### Task 6: Change Channel flow

**Files:**
- Modify: `cogs/scheduler.py`

- [ ] **Step 1: Insert `ChangeChannelSelectView` before `ScheduleListView`**

```python
class ChangeChannelSelectView(discord.ui.View):
    def __init__(self, msg_id: str, list_view: "ScheduleListView"):
        super().__init__(timeout=120)
        self.msg_id = msg_id
        self.list_view = list_view

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Select new channel...",
        channel_types=[discord.ChannelType.text],
    )
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        messages = load_messages()
        msg = next((m for m in messages if m["id"] == self.msg_id), None)
        if msg is None:
            await interaction.response.send_message("❌ Message not found.", ephemeral=True)
            return
        msg["channel_id"] = select.values[0].id
        save_messages(messages)
        # Edit the channel-select ephemeral message to confirm and close the select UI.
        await interaction.response.edit_message(content="✅ Channel updated. Re-open `/schedule_list` to see changes.", view=None)
```

- [ ] **Step 2: Verify tests still pass**

Run: `pytest tests/test_scheduler.py -v`
Expected: 8 PASSED

- [ ] **Step 3: Commit**

```bash
git add cogs/scheduler.py
git commit -m "feat: add change channel flow for scheduled messages"
```

---

### Task 7: Push + smoke test

**Files:**
- No changes

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: 8 PASSED

- [ ] **Step 2: Push to GitHub**

```bash
git push
```

Railway auto-deploys. Wait ~30 seconds for the new version to come online.

- [ ] **Step 3: Sync slash commands**

In Discord `#bot-commands`, send any message to trigger `on_ready` → tree sync.
Or wait ~1 minute and type `/` in any channel — `/schedule` and `/schedule_list` should appear.

- [ ] **Step 4: Smoke test create + send**

1. Type `/schedule` → select `#updates` → fill in a time 2 minutes from now, type any content, leave image blank → submit
2. Verify ephemeral preview appears with correct channel and time
3. Wait for send time → verify message appears in `#updates`

- [ ] **Step 5: Smoke test list management**

1. Schedule two more messages (future times)
2. Type `/schedule_list` → verify both appear in the list with correct info
3. Click `👁 Preview` on one → verify content shown
4. Click `✏️ Edit` → change only the content → submit → verify list refreshes with new content
5. Click `📍 Channel` → select a different channel → verify list shows updated channel
6. Click `❌ Cancel` on one → verify it disappears from the list
