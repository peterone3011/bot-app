# Embed Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/embed` slash command that lets an admin build, preview, and send (immediately or scheduled) rich Discord embed messages via an interactive button-driven builder.

**Architecture:** A single new cog `cogs/embed_builder.py` handles all UI and logic. All state (drafts + scheduled messages) persists in `messages.json` on disk, read/written on every operation — no in-memory cache. A 60-second task loop checks for due scheduled messages.

**Tech Stack:** discord.py (`discord.ui.View`, `discord.ui.Modal`, `discord.ui.ChannelSelect`, `discord.ext.tasks`), Python stdlib (`json`, `uuid`, `datetime`, `pathlib`)

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `cogs/embed_builder.py` | All storage, parsing, rendering, views, modals, cog |
| Create | `tests/test_embed_builder.py` | Unit tests for pure-Python functions |
| Modify | `bot.py` | Register new cog |

---

## Task 1: Storage utilities

**Files:**
- Create: `cogs/embed_builder.py`
- Create: `tests/test_embed_builder.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_embed_builder.py`:

```python
import json
import pytest
import cogs.embed_builder as eb


def test_new_draft_structure():
    draft = eb.new_draft(123456789)
    assert draft["status"] == "draft"
    assert draft["channel_id"] == 123456789
    assert draft["label"] is None
    assert draft["title"] is None
    assert draft["send_at"] is None
    assert "id" in draft
    assert "created_at" in draft


def test_new_draft_with_label():
    draft = eb.new_draft(111, label="May Announcement")
    assert draft["label"] == "May Announcement"


def test_load_messages_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")
    result = eb.load_messages()
    assert result == []
    assert (tmp_path / "messages.json").exists()


def test_upsert_inserts_new(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")
    draft = eb.new_draft(111)
    eb.upsert_message(draft)
    assert eb.load_messages() == [draft]


def test_upsert_updates_existing(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")
    draft = eb.new_draft(111)
    eb.upsert_message(draft)
    draft["title"] = "Updated"
    eb.upsert_message(draft)
    messages = eb.load_messages()
    assert len(messages) == 1
    assert messages[0]["title"] == "Updated"


def test_get_message(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")
    draft = eb.new_draft(222)
    eb.upsert_message(draft)
    found = eb.get_message(draft["id"])
    assert found["channel_id"] == 222


def test_get_message_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")
    assert eb.get_message("nonexistent-id") is None


def test_delete_message(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")
    draft = eb.new_draft(333)
    eb.upsert_message(draft)
    eb.delete_message(draft["id"])
    assert eb.get_message(draft["id"]) is None


def test_delete_nonexistent_is_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")
    eb.delete_message("does-not-exist")  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_embed_builder.py -v
```

Expected: ImportError or multiple FAILs — `cogs/embed_builder.py` does not exist yet.

- [ ] **Step 3: Implement storage utilities**

Create `cogs/embed_builder.py`:

```python
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

MESSAGES_FILE = Path("messages.json")
CST = timezone(timedelta(hours=8))


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def load_messages() -> list[dict[str, Any]]:
    if not MESSAGES_FILE.exists():
        MESSAGES_FILE.write_text("[]", encoding="utf-8")
    return json.loads(MESSAGES_FILE.read_text(encoding="utf-8"))


def save_messages(messages: list[dict[str, Any]]) -> None:
    MESSAGES_FILE.write_text(
        json.dumps(messages, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_message(msg_id: str) -> dict[str, Any] | None:
    return next((m for m in load_messages() if m["id"] == msg_id), None)


def upsert_message(msg: dict[str, Any]) -> None:
    messages = load_messages()
    for i, m in enumerate(messages):
        if m["id"] == msg["id"]:
            messages[i] = msg
            save_messages(messages)
            return
    messages.append(msg)
    save_messages(messages)


def delete_message(msg_id: str) -> None:
    save_messages([m for m in load_messages() if m["id"] != msg_id])


def new_draft(channel_id: int, label: str | None = None) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "status": "draft",
        "label": label,
        "created_at": datetime.now(CST).isoformat(),
        "channel_id": channel_id,
        "send_at": None,
        "title": None,
        "description": None,
        "footer": None,
        "image_url": None,
        "button_label": None,
        "button_url": None,
        "color": None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_embed_builder.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```
git add cogs/embed_builder.py tests/test_embed_builder.py
git commit -m "feat: add embed_builder storage utilities with tests"
```

---

## Task 2: Parsing and rendering utilities

**Files:**
- Modify: `cogs/embed_builder.py` (append after storage section)
- Modify: `tests/test_embed_builder.py` (append new tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_embed_builder.py`:

```python
# ---------------------------------------------------------------------------
# parse_color
# ---------------------------------------------------------------------------

def test_parse_color_valid_no_hash():
    assert eb.parse_color("9B59B6") == 0x9B59B6


def test_parse_color_valid_with_hash():
    assert eb.parse_color("#FF0000") == 0xFF0000


def test_parse_color_black():
    assert eb.parse_color("000000") == 0


def test_parse_color_empty():
    assert eb.parse_color("") is None
    assert eb.parse_color("   ") is None


def test_parse_color_invalid_chars():
    assert eb.parse_color("ZZZZZZ") == -1


def test_parse_color_wrong_length():
    assert eb.parse_color("FFF") == -1
    assert eb.parse_color("1234567") == -1


# ---------------------------------------------------------------------------
# parse_send_at
# ---------------------------------------------------------------------------

def test_parse_send_at_valid_future():
    from datetime import datetime, timedelta, timezone
    cst = timezone(timedelta(hours=8))
    future = (datetime.now(cst) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    result = eb.parse_send_at(future)
    assert result is not None
    assert "+08:00" in result


def test_parse_send_at_past():
    assert eb.parse_send_at("2000-01-01 00:00") is None


def test_parse_send_at_invalid_format():
    assert eb.parse_send_at("not a date") is None
    assert eb.parse_send_at("2026/05/20 15:00") is None


# ---------------------------------------------------------------------------
# build_embed / build_view
# ---------------------------------------------------------------------------

def _full_msg(**overrides):
    base = {
        "title": "Test Title",
        "description": "Test body",
        "footer": "Footer text",
        "image_url": "https://example.com/img.png",
        "color": 0xFF0000,
        "button_label": "Click",
        "button_url": "https://example.com",
    }
    return {**base, **overrides}


def test_build_embed_sets_all_fields():
    embed = eb.build_embed(_full_msg())
    assert embed.title == "Test Title"
    assert embed.description == "Test body"
    assert embed.color.value == 0xFF0000
    assert embed.footer.text == "Footer text"
    assert embed.image.url == "https://example.com/img.png"


def test_build_embed_no_footer_or_image():
    embed = eb.build_embed(_full_msg(footer=None, image_url=None))
    assert embed.title == "Test Title"
    assert embed.description == "Test body"


def test_build_view_with_button():
    view = eb.build_view(_full_msg())
    assert view is not None
    assert len(view.children) == 1
    btn = view.children[0]
    assert btn.url == "https://example.com"
    assert btn.label == "Click"


def test_build_view_no_button():
    assert eb.build_view(_full_msg(button_label=None, button_url=None)) is None


def test_build_view_partial_button():
    # label without url → no button
    assert eb.build_view(_full_msg(button_url=None)) is None


# ---------------------------------------------------------------------------
# display_label
# ---------------------------------------------------------------------------

class _FakeChannel:
    name = "announcements"


class _FakeBot:
    def get_channel(self, _id):
        return _FakeChannel()


def test_display_label_uses_custom_label():
    msg = {"label": "My Post", "channel_id": 1, "created_at": "2026-05-18T10:00:00+08:00", "title": "X"}
    assert eb.display_label(msg, bot=None) == "My Post"


def test_display_label_auto_with_title():
    msg = {"label": None, "channel_id": 1, "created_at": "2026-05-18T10:00:00+08:00", "title": "Hello World"}
    label = eb.display_label(msg, bot=_FakeBot())
    assert "#announcements" in label
    assert "2026-05-18" in label
    assert "Hello World" in label


def test_display_label_auto_no_title():
    msg = {"label": None, "channel_id": 1, "created_at": "2026-05-18T10:00:00+08:00", "title": None}
    label = eb.display_label(msg, bot=_FakeBot())
    assert "(untitled)" in label
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_embed_builder.py -v -k "parse or build or display"
```

Expected: FAILs — functions not yet defined.

- [ ] **Step 3: Implement utilities**

Append to `cogs/embed_builder.py` after the storage section:

```python
# ---------------------------------------------------------------------------
# Parsing utilities
# ---------------------------------------------------------------------------

def parse_color(value: str) -> int | None:
    """Returns color int, None for empty input, -1 for invalid."""
    value = value.strip().lstrip("#")
    if not value:
        return None
    if len(value) != 6:
        return -1
    try:
        return int(value, 16)
    except ValueError:
        return -1


def parse_send_at(value: str) -> str | None:
    """Returns ISO 8601 string (UTC+8) or None if invalid or in the past."""
    try:
        dt = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=CST)
    except ValueError:
        return None
    if dt <= datetime.now(CST):
        return None
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def build_embed(msg: dict[str, Any]) -> discord.Embed:
    embed = discord.Embed(
        title=msg["title"],
        description=msg["description"],
        color=msg["color"],
    )
    if msg["footer"]:
        embed.set_footer(text=msg["footer"])
    if msg["image_url"]:
        embed.set_image(url=msg["image_url"])
    return embed


def build_view(msg: dict[str, Any]) -> discord.ui.View | None:
    if not (msg["button_label"] and msg["button_url"]):
        return None
    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label=msg["button_label"],
        url=msg["button_url"],
        style=discord.ButtonStyle.link,
    ))
    return view


def display_label(msg: dict[str, Any], bot: commands.Bot | None) -> str:
    if msg.get("label"):
        return msg["label"]
    if bot:
        ch = bot.get_channel(msg["channel_id"])
        ch_name = f"#{ch.name}" if ch else f"#{msg['channel_id']}"
    else:
        ch_name = f"#{msg['channel_id']}"
    date = (msg.get("created_at") or "")[:10]
    title = msg.get("title") or ""
    preview = (title[:20] + "…") if len(title) > 20 else (title or "(untitled)")
    return f"{ch_name} · {date} · \"{preview}\""


# ---------------------------------------------------------------------------
# Content formatters
# ---------------------------------------------------------------------------

def _field_summary(msg: dict[str, Any]) -> str:
    color_val = msg["color"]
    color_str = f"#{color_val:06X}" if color_val is not None else "(none)"
    desc = msg["description"] or ""
    desc_preview = (desc[:50] + "…") if len(desc) > 50 else (desc or "(none)")
    btn = f"{msg['button_label']} | {msg['button_url']}" if msg["button_label"] else "(none)"
    return "\n".join([
        f"Title:       {msg['title'] or '(none)'}",
        f"Description: {desc_preview}",
        f"Footer:      {msg['footer'] or '(none)'}",
        f"Image:       {'set' if msg['image_url'] else '(none)'}",
        f"Button:      {btn}",
        f"Color:       {color_str}",
    ])


def format_builder_content(msg: dict[str, Any]) -> str:
    status = "Scheduled" if msg["status"] == "scheduled" else "Draft"
    send_time = ""
    if msg["send_at"]:
        send_time = " · " + msg["send_at"][:16].replace("T", " ")
    header = f"**{msg.get('label') or '(untitled)'}**  |  <#{msg['channel_id']}>  |  {status}{send_time}"
    return f"{header}\n\n```\n{_field_summary(msg)}\n```"


def format_edit_fields_content(msg: dict[str, Any]) -> str:
    return f"**Edit Fields** — click a field to update it\n\n```\n{_field_summary(msg)}\n```"
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_embed_builder.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```
git add cogs/embed_builder.py tests/test_embed_builder.py
git commit -m "feat: add parsing, rendering, and formatting utilities with tests"
```

---

## Task 3: Modals

**Files:**
- Modify: `cogs/embed_builder.py` (append after formatters)

No unit tests for Discord UI components.

- [ ] **Step 1: Append all modals to `cogs/embed_builder.py`**

```python
# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------

class TitleModal(discord.ui.Modal, title="Update Title"):
    value_input = discord.ui.TextInput(
        label="Title",
        max_length=256,
        required=False,
        placeholder="Leave blank to clear",
    )

    def __init__(self, msg_id: str):
        super().__init__()
        self.msg_id = msg_id

    async def on_submit(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        msg["title"] = self.value_input.value.strip() or None
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_edit_fields_content(msg),
            view=EditFieldsView(self.msg_id),
        )


class DescriptionModal(discord.ui.Modal, title="Update Description"):
    value_input = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=False,
        placeholder="Leave blank to clear",
    )

    def __init__(self, msg_id: str):
        super().__init__()
        self.msg_id = msg_id

    async def on_submit(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        msg["description"] = self.value_input.value.strip() or None
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_edit_fields_content(msg),
            view=EditFieldsView(self.msg_id),
        )


class FooterModal(discord.ui.Modal, title="Update Footer"):
    value_input = discord.ui.TextInput(
        label="Footer",
        max_length=2048,
        required=False,
        placeholder="Leave blank to clear",
    )

    def __init__(self, msg_id: str):
        super().__init__()
        self.msg_id = msg_id

    async def on_submit(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        msg["footer"] = self.value_input.value.strip() or None
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_edit_fields_content(msg),
            view=EditFieldsView(self.msg_id),
        )


class ImageModal(discord.ui.Modal, title="Update Image URL"):
    value_input = discord.ui.TextInput(
        label="Image URL",
        required=False,
        placeholder="Leave blank to clear",
    )

    def __init__(self, msg_id: str):
        super().__init__()
        self.msg_id = msg_id

    async def on_submit(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        msg["image_url"] = self.value_input.value.strip() or None
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_edit_fields_content(msg),
            view=EditFieldsView(self.msg_id),
        )


class LinkButtonModal(discord.ui.Modal, title="Update Link Button"):
    label_input = discord.ui.TextInput(
        label="Button Label",
        max_length=80,
        required=False,
        placeholder="Leave blank to remove button",
    )
    url_input = discord.ui.TextInput(
        label="Button URL",
        required=False,
        placeholder="https://...",
    )

    def __init__(self, msg_id: str):
        super().__init__()
        self.msg_id = msg_id

    async def on_submit(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        label = self.label_input.value.strip() or None
        url = self.url_input.value.strip() or None
        msg["button_label"] = label
        msg["button_url"] = url
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_edit_fields_content(msg),
            view=EditFieldsView(self.msg_id),
        )


class ColorModal(discord.ui.Modal, title="Update Color"):
    value_input = discord.ui.TextInput(
        label="Hex Color (e.g. 9B59B6)",
        max_length=7,
        required=False,
        placeholder="Leave blank to clear",
    )

    def __init__(self, msg_id: str):
        super().__init__()
        self.msg_id = msg_id

    async def on_submit(self, interaction: discord.Interaction):
        result = parse_color(self.value_input.value)
        if result == -1:
            await interaction.response.send_message(
                content="❌ Invalid hex color. Use 6 hex digits, e.g. `9B59B6` or `#FF0000`.",
                ephemeral=True,
            )
            return
        msg = get_message(self.msg_id)
        msg["color"] = result
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_edit_fields_content(msg),
            view=EditFieldsView(self.msg_id),
        )


class ScheduleModal(discord.ui.Modal, title="Set Send Time"):
    time_input = discord.ui.TextInput(
        label="Send time (Beijing time, UTC+8)",
        placeholder="YYYY-MM-DD HH:MM",
        max_length=16,
    )

    def __init__(self, msg_id: str):
        super().__init__()
        self.msg_id = msg_id

    async def on_submit(self, interaction: discord.Interaction):
        send_at = parse_send_at(self.time_input.value)
        if send_at is None:
            await interaction.response.send_message(
                content="❌ Invalid or past time. Use format `YYYY-MM-DD HH:MM` (Beijing time).",
                ephemeral=True,
            )
            return
        msg = get_message(self.msg_id)
        msg["status"] = "scheduled"
        msg["send_at"] = send_at
        upsert_message(msg)
        display_time = send_at[:16].replace("T", " ")
        await interaction.response.edit_message(
            content=f"✅ Scheduled for **{display_time}** (UTC+8)\n\n{format_builder_content(msg)}",
            view=BuilderMainView(self.msg_id),
        )


class NewMessageModal(discord.ui.Modal, title="New Message"):
    label_input = discord.ui.TextInput(
        label="Label (optional)",
        placeholder='e.g. "May Announcement" — leave blank for auto label',
        required=False,
        max_length=100,
    )

    def __init__(self, channel_id: int):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        label = self.label_input.value.strip() or None
        msg = new_draft(self.channel_id, label)
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_builder_content(msg),
            view=BuilderMainView(msg["id"]),
        )
```

- [ ] **Step 2: Commit**

```
git add cogs/embed_builder.py
git commit -m "feat: add embed builder modals"
```

---

## Task 4: Button subclasses (for SendView)

**Files:**
- Modify: `cogs/embed_builder.py` (append after modals)

- [ ] **Step 1: Append button classes**

```python
# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------

class SendNowButton(discord.ui.Button):
    def __init__(self, msg_id: str):
        super().__init__(label="Send Now", style=discord.ButtonStyle.success)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        channel = interaction.guild.get_channel(msg["channel_id"])
        if channel is None:
            await interaction.response.send_message(
                content="❌ Target channel not found.", ephemeral=True
            )
            return
        try:
            await channel.send(embed=build_embed(msg), view=build_view(msg))
            delete_message(self.msg_id)
            await interaction.response.edit_message(
                content=f"✅ Sent to {channel.mention}.", view=None
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                content=f"❌ Bot doesn't have permission to post in {channel.mention}.",
                ephemeral=True,
            )


class ScheduleButton(discord.ui.Button):
    def __init__(self, msg_id: str, label: str = "Schedule"):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ScheduleModal(self.msg_id))


class CancelScheduleButton(discord.ui.Button):
    def __init__(self, msg_id: str):
        super().__init__(label="Cancel Schedule", style=discord.ButtonStyle.danger)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        msg["status"] = "draft"
        msg["send_at"] = None
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_builder_content(msg),
            view=BuilderMainView(self.msg_id),
        )


class BackToBuilderButton(discord.ui.Button):
    def __init__(self, msg_id: str):
        super().__init__(label="← Back", style=discord.ButtonStyle.secondary, row=1)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        await interaction.response.edit_message(
            content=format_builder_content(msg),
            view=BuilderMainView(self.msg_id),
        )
```

- [ ] **Step 2: Commit**

```
git add cogs/embed_builder.py
git commit -m "feat: add send-flow button classes"
```

---

## Task 5: EditFieldsView, BuilderMainView, SendView

**Files:**
- Modify: `cogs/embed_builder.py` (append after buttons)

- [ ] **Step 1: Append views**

```python
# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class EditFieldsView(discord.ui.View):
    def __init__(self, msg_id: str):
        super().__init__(timeout=600)
        self.msg_id = msg_id

    @discord.ui.button(label="Title", style=discord.ButtonStyle.secondary, row=0)
    async def title_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TitleModal(self.msg_id))

    @discord.ui.button(label="Description", style=discord.ButtonStyle.secondary, row=0)
    async def desc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DescriptionModal(self.msg_id))

    @discord.ui.button(label="Footer", style=discord.ButtonStyle.secondary, row=0)
    async def footer_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FooterModal(self.msg_id))

    @discord.ui.button(label="Image URL", style=discord.ButtonStyle.secondary, row=1)
    async def image_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImageModal(self.msg_id))

    @discord.ui.button(label="Link Button", style=discord.ButtonStyle.secondary, row=1)
    async def link_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LinkButtonModal(self.msg_id))

    @discord.ui.button(label="Color", style=discord.ButtonStyle.secondary, row=1)
    async def color_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self.msg_id))

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.primary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg = get_message(self.msg_id)
        await interaction.response.edit_message(
            content=format_builder_content(msg),
            view=BuilderMainView(self.msg_id),
        )


class BuilderMainView(discord.ui.View):
    def __init__(self, msg_id: str):
        super().__init__(timeout=600)
        self.msg_id = msg_id

    @discord.ui.button(label="Edit Fields", style=discord.ButtonStyle.primary)
    async def edit_fields(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg = get_message(self.msg_id)
        await interaction.response.edit_message(
            content=format_edit_fields_content(msg),
            view=EditFieldsView(self.msg_id),
        )

    @discord.ui.button(label="Overview", style=discord.ButtonStyle.secondary)
    async def overview(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg = get_message(self.msg_id)
        await interaction.response.send_message(
            embed=build_embed(msg),
            view=build_view(msg),
            ephemeral=True,
        )

    @discord.ui.button(label="Send", style=discord.ButtonStyle.success)
    async def send_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg = get_message(self.msg_id)
        await interaction.response.edit_message(
            content="**When to send?**",
            view=SendView(self.msg_id),
        )


class SendView(discord.ui.View):
    def __init__(self, msg_id: str):
        super().__init__(timeout=600)
        msg = get_message(msg_id)
        is_scheduled = msg and msg["status"] == "scheduled"
        self.add_item(SendNowButton(msg_id))
        if is_scheduled:
            self.add_item(ScheduleButton(msg_id, label="Update Schedule"))
            self.add_item(CancelScheduleButton(msg_id))
        else:
            self.add_item(ScheduleButton(msg_id))
        self.add_item(BackToBuilderButton(msg_id))
```

- [ ] **Step 2: Commit**

```
git add cogs/embed_builder.py
git commit -m "feat: add EditFieldsView, BuilderMainView, SendView"
```

---

## Task 6: MessageListView + NewMessageView

**Files:**
- Modify: `cogs/embed_builder.py` (append after SendView)

- [ ] **Step 1: Append entry-point views**

```python
class NewMessageChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="Select target channel...",
            channel_types=[discord.ChannelType.text],
        )

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        await interaction.response.send_modal(NewMessageModal(channel.id))


class NewMessageView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(NewMessageChannelSelect())


class MessageSelect(discord.ui.Select):
    def __init__(self, messages: list[dict[str, Any]], bot: commands.Bot):
        options = []
        for msg in messages[:25]:
            label = display_label(msg, bot)[:100]
            emoji = "📅" if msg["status"] == "scheduled" else "📝"
            options.append(discord.SelectOption(label=label, value=msg["id"], emoji=emoji))
        super().__init__(placeholder="Select a message to edit...", options=options)

    async def callback(self, interaction: discord.Interaction):
        msg = get_message(self.values[0])
        await interaction.response.edit_message(
            content=format_builder_content(msg),
            view=BuilderMainView(self.values[0]),
        )


class MessageListView(discord.ui.View):
    def __init__(self, messages: list[dict[str, Any]], bot: commands.Bot):
        super().__init__(timeout=300)
        self.add_item(MessageSelect(messages, bot))

    @discord.ui.button(label="+ New Message", style=discord.ButtonStyle.primary, row=1)
    async def new_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Select the channel to post in:",
            view=NewMessageView(),
        )
```

- [ ] **Step 2: Commit**

```
git add cogs/embed_builder.py
git commit -m "feat: add MessageListView and NewMessageView"
```

---

## Task 7: EmbedBuilderCog + slash command + task loop

**Files:**
- Modify: `cogs/embed_builder.py` (append at end)

- [ ] **Step 1: Append cog class and setup function**

```python
# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class EmbedBuilderCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.send_loop.start()

    def cog_unload(self):
        self.send_loop.cancel()

    @tasks.loop(seconds=60)
    async def send_loop(self):
        now = datetime.now(CST)
        for msg in list(load_messages()):
            if msg["status"] != "scheduled":
                continue
            if datetime.fromisoformat(msg["send_at"]) > now:
                continue
            channel = self.bot.get_channel(msg["channel_id"])
            if channel is None:
                print(f"[embed_builder] Channel {msg['channel_id']} not found, removing {msg['id']}")
                delete_message(msg["id"])
                continue
            try:
                await channel.send(embed=build_embed(msg), view=build_view(msg))
            except Exception as e:
                print(f"[embed_builder] Failed to send {msg['id']}: {e}")
            finally:
                delete_message(msg["id"])

    @send_loop.before_loop
    async def before_send_loop(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="embed", description="Build and send a rich embed message")
    @app_commands.guild_only()
    async def embed_cmd(self, interaction: discord.Interaction):
        messages = sorted(
            load_messages(),
            key=lambda m: (m["status"] != "scheduled", m.get("send_at") or m.get("created_at", "")),
        )
        if messages:
            await interaction.response.send_message(
                content="Select a message to edit, or create a new one:",
                view=MessageListView(messages, self.bot),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                content="Select the channel to post in:",
                view=NewMessageView(),
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedBuilderCog(bot))
```

- [ ] **Step 2: Run all tests to confirm nothing broke**

```
pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 3: Commit**

```
git add cogs/embed_builder.py
git commit -m "feat: add EmbedBuilderCog with slash command and send loop"
```

---

## Task 8: Register cog in bot.py + deploy

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Add the new cog to bot.py**

In `bot.py`, find:

```python
await bot.load_extension("cogs.roles")
```

Change to:

```python
await bot.load_extension("cogs.roles")
await bot.load_extension("cogs.embed_builder")
```

- [ ] **Step 2: Run tests one final time**

```
pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 3: Commit**

```
git add bot.py
git commit -m "feat: register embed_builder cog in bot"
```

- [ ] **Step 4: Push to trigger Railway redeploy**

```
git push
```

Railway will detect the push and automatically redeploy. The bot will be briefly offline while the new container starts.

- [ ] **Step 5: Verify in Discord**

1. In your server, run `/embed`
2. Confirm an ephemeral message appears with "Select the channel to post in:" and a channel dropdown
3. Select a channel → confirm builder view appears with `[Edit Fields] [Overview] [Send]`
4. Click **Edit Fields** → confirm field buttons appear
5. Click **Title** → confirm a modal pops up with one text field → submit → confirm title updates in the view
6. Click **Color** → enter `9B59B6` → confirm color updates
7. Click **Overview** → confirm an ephemeral embed preview renders with correct color and title
8. Click **Send** → click **Schedule** → enter a time 2 minutes from now → confirm schedule confirmation message
9. Wait for the scheduled time → confirm the embed appears in the target channel
10. Run `/embed` again → confirm the draft/scheduled message appears in the list dropdown

---

## Task 9: Edit published embeds (context menu + /edit-embed)

**Files:**
- Modify: `cogs/embed_builder.py` (add utilities, button, update SendView, add commands)
- Modify: `tests/test_embed_builder.py` (add tests for new utilities)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_embed_builder.py`:

```python
# ---------------------------------------------------------------------------
# parse_message_link
# ---------------------------------------------------------------------------

def test_parse_message_link_valid():
    link = "https://discord.com/channels/111/222333/444555"
    assert eb.parse_message_link(link) == (222333, 444555)


def test_parse_message_link_ptb():
    link = "https://ptb.discord.com/channels/111/222333/444555"
    assert eb.parse_message_link(link) == (222333, 444555)


def test_parse_message_link_invalid():
    assert eb.parse_message_link("not a link") is None
    assert eb.parse_message_link("https://discord.com/channels/111") is None


# ---------------------------------------------------------------------------
# draft_from_message
# ---------------------------------------------------------------------------

class _FakeEmbed:
    title = "Test Title"
    description = "Body text"
    color = type("C", (), {"value": 0xFF0000})()
    footer = type("F", (), {"text": "Footer"})()
    image = type("I", (), {"url": "https://example.com/img.png"})()


class _FakeButton:
    url = "https://example.com"
    label = "Click me"


class _FakeRow:
    children = [_FakeButton()]


class _FakeChannel2:
    id = 999


class _FakeMessage:
    id = 12345
    embeds = [_FakeEmbed()]
    components = [_FakeRow()]
    channel = _FakeChannel2()


def test_draft_from_message_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")
    draft = eb.draft_from_message(_FakeMessage())
    assert draft["title"] == "Test Title"
    assert draft["description"] == "Body text"
    assert draft["footer"] == "Footer"
    assert draft["image_url"] == "https://example.com/img.png"
    assert draft["color"] == 0xFF0000
    assert draft["button_label"] == "Click me"
    assert draft["button_url"] == "https://example.com"
    assert draft["message_id"] == 12345
    assert draft["channel_id"] == 999


def test_draft_from_message_no_button(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")

    class _NoButtonRow:
        children = []

    class _MsgNoBtn:
        id = 1
        embeds = [_FakeEmbed()]
        components = [_NoButtonRow()]
        channel = _FakeChannel2()

    draft = eb.draft_from_message(_MsgNoBtn())
    assert draft["button_label"] is None
    assert draft["button_url"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_embed_builder.py -v -k "parse_message or draft_from"
```

Expected: FAILs — functions not yet defined.

- [ ] **Step 3: Add `parse_message_link` and `draft_from_message` to `cogs/embed_builder.py`**

Add after the `_field_summary` / formatter functions (before the Modals section):

```python
import re

def parse_message_link(link: str) -> tuple[int, int] | None:
    """Returns (channel_id, message_id) from a Discord message URL, or None."""
    match = re.search(r"channels/\d+/(\d+)/(\d+)", link)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def draft_from_message(message: discord.Message) -> dict[str, Any]:
    embed = message.embeds[0] if message.embeds else None
    button_label = None
    button_url = None
    for row in message.components:
        for component in row.children:
            if getattr(component, "url", None):
                button_label = component.label
                button_url = component.url
                break

    draft = new_draft(message.channel.id)
    if embed:
        draft["title"] = embed.title or None
        draft["description"] = embed.description or None
        draft["footer"] = embed.footer.text if embed.footer else None
        draft["image_url"] = embed.image.url if embed.image else None
        draft["color"] = embed.color.value if embed.color else None
    draft["button_label"] = button_label
    draft["button_url"] = button_url
    draft["message_id"] = message.id
    return draft
```

Also add `"message_id": None` to `new_draft()` so all drafts carry the field:

```python
def new_draft(channel_id: int, label: str | None = None) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "status": "draft",
        "label": label,
        "created_at": datetime.now(CST).isoformat(),
        "channel_id": channel_id,
        "send_at": None,
        "message_id": None,        # ← new field
        "title": None,
        "description": None,
        "footer": None,
        "image_url": None,
        "button_label": None,
        "button_url": None,
        "color": None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_embed_builder.py -v
```

Expected: all PASS.

- [ ] **Step 5: Add `SaveChangesButton` to `cogs/embed_builder.py`**

Append after `BackToBuilderButton`:

```python
class SaveChangesButton(discord.ui.Button):
    def __init__(self, msg_id: str):
        super().__init__(label="Save Changes", style=discord.ButtonStyle.success)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        draft = get_message(self.msg_id)
        channel = interaction.guild.get_channel(draft["channel_id"])
        if channel is None:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return
        try:
            original = await channel.fetch_message(draft["message_id"])
            await original.edit(embed=build_embed(draft), view=build_view(draft))
            delete_message(self.msg_id)
            await interaction.response.edit_message(
                content=f"✅ Embed updated in {channel.mention}.", view=None
            )
        except discord.NotFound:
            await interaction.response.send_message(
                "❌ Original message not found (may have been deleted).", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Bot lacks permission to edit that message.", ephemeral=True
            )
```

- [ ] **Step 6: Update `SendView` to show Save Changes when editing**

Replace the existing `SendView` class with:

```python
class SendView(discord.ui.View):
    def __init__(self, msg_id: str):
        super().__init__(timeout=600)
        msg = get_message(msg_id)
        is_edit = bool(msg and msg.get("message_id"))
        is_scheduled = msg and msg["status"] == "scheduled"

        if is_edit:
            self.add_item(SaveChangesButton(msg_id))
        else:
            self.add_item(SendNowButton(msg_id))
            if is_scheduled:
                self.add_item(ScheduleButton(msg_id, label="Update Schedule"))
                self.add_item(CancelScheduleButton(msg_id))
            else:
                self.add_item(ScheduleButton(msg_id))
        self.add_item(BackToBuilderButton(msg_id))
```

- [ ] **Step 7: Add context menu command and `/edit-embed` to `EmbedBuilderCog`**

Add inside the `EmbedBuilderCog` class, after `embed_cmd`:

```python
    @app_commands.context_menu(name="Edit Embed")
    @app_commands.guild_only()
    async def edit_embed_menu(self, interaction: discord.Interaction, message: discord.Message):
        if message.author != self.bot.user:
            await interaction.response.send_message(
                "❌ That message was not sent by this bot.", ephemeral=True
            )
            return
        if not message.embeds:
            await interaction.response.send_message(
                "❌ That message has no embed.", ephemeral=True
            )
            return
        draft = draft_from_message(message)
        upsert_message(draft)
        await interaction.response.send_message(
            content=format_builder_content(draft),
            view=BuilderMainView(draft["id"]),
            ephemeral=True,
        )

    @app_commands.command(name="edit-embed", description="Edit a published embed by message link")
    @app_commands.guild_only()
    async def edit_embed_cmd(self, interaction: discord.Interaction, message_link: str):
        result = parse_message_link(message_link)
        if result is None:
            await interaction.response.send_message("❌ Invalid message link.", ephemeral=True)
            return
        channel_id, message_id = result
        channel = interaction.guild.get_channel(channel_id)
        if channel is None:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await interaction.response.send_message("❌ Message not found.", ephemeral=True)
            return
        if message.author != self.bot.user:
            await interaction.response.send_message(
                "❌ That message was not sent by this bot.", ephemeral=True
            )
            return
        if not message.embeds:
            await interaction.response.send_message(
                "❌ That message has no embed.", ephemeral=True
            )
            return
        draft = draft_from_message(message)
        upsert_message(draft)
        await interaction.response.send_message(
            content=format_builder_content(draft),
            view=BuilderMainView(draft["id"]),
            ephemeral=True,
        )
```

Also register the context menu command in `setup()`:

```python
async def setup(bot: commands.Bot):
    cog = EmbedBuilderCog(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(cog.edit_embed_menu)
```

- [ ] **Step 8: Run all tests**

```
pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 9: Commit**

```
git add cogs/embed_builder.py tests/test_embed_builder.py
git commit -m "feat: add edit-embed context menu and /edit-embed command"
```
