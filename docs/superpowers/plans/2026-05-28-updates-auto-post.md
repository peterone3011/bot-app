# Updates Auto-Post Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `cogs/updates.py` — a Discord bot cog that reads the Lark spreadsheet and auto-posts to `📣updates` every Tue/Thu/Sat at BJT 23:50, plus a `/edit_update` slash command for Mods to edit posted messages.

**Architecture:** Pure helper functions (text parsing, row finding) are defined at module level and unit-tested. Async Lark API client functions handle network I/O. `UpdatesCog` owns the scheduled task and slash command. The scheduled task writes "发布中" to Lark before posting to prevent duplicates on restart.

**Tech Stack:** Python 3.14, discord.py (`discord.ext.commands`, `discord.ext.tasks`), `aiohttp` for Lark HTTP calls, `pytest` for tests.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `cogs/updates.py` | Create | All logic: helpers, Lark client, cog, slash command |
| `tests/test_updates.py` | Create | Unit tests for pure helper functions |
| `bot.py` | Modify line 41 | Add `await bot.load_extension("cogs.updates")` |

---

### Task 1: Pure helper functions + unit tests

**Files:**
- Create: `cogs/updates.py` (helpers only, no cog yet)
- Create: `tests/test_updates.py`

- [ ] **Step 1: Create `cogs/updates.py` with helpers**

```python
import io
import os
import asyncio
import random
import datetime
from typing import Optional

import aiohttp
import discord
from discord.ext import commands, tasks

# ── Constants ────────────────────────────────────────────────────────────────

_BJT = datetime.timezone(datetime.timedelta(hours=8))
_UTC = datetime.timezone.utc
_POST_WEEKDAYS = {1, 3, 5}  # Tuesday=1, Thursday=3, Saturday=5 (UTC weekday, same day as BJT at 15:50 UTC)
_BROADCAST_TIME = datetime.time(hour=15, minute=50, tzinfo=_UTC)

UPDATE_CHANNEL_ID: int = int(os.getenv("UPDATE_CHANNEL_ID", "0"))
STAFF_CHAT_CHANNEL_ID: int = int(os.getenv("STAFF_CHAT_CHANNEL_ID", "0"))
MOD_ROLE_ID: int = int(os.getenv("DISCORD_ADMIN_ROLE_ID", "0"))

LARK_BASE = "https://open.larksuite.com/open-apis"
LARK_APP_ID: str = os.getenv("LARK_APP_ID", "")
LARK_APP_SECRET: str = os.getenv("LARK_APP_SECRET", "")
LARK_SPREADSHEET_TOKEN: str = os.getenv("LARK_SPREADSHEET_TOKEN", "")
LARK_SHEET_ID: str = os.getenv("LARK_SHEET_ID", "")

REACTION_POOL = [
    "🎉", "🎊", "🔥", "💜", "✨", "🚀", "💰", "🎰",
    "👑", "🌟", "💎", "🙌", "😍", "🤩", "💪", "🎯",
    "⚡", "🏆", "🎁", "💫",
]

# ── Pure helpers (tested) ─────────────────────────────────────────────────────

def parse_rich_text(cell_value) -> str:
    """Convert Lark cell value (plain string or rich-text array) to plain text.

    URL nodes get https:// prepended if missing.
    """
    if cell_value is None:
        return ""
    if isinstance(cell_value, str):
        return cell_value
    if isinstance(cell_value, list):
        parts = []
        for node in cell_value:
            if not isinstance(node, dict):
                continue
            if node.get("type") == "url":
                link = node.get("link", "")
                if link and not link.startswith(("https://", "http://")):
                    link = "https://" + link
                parts.append(link)
            else:
                parts.append(node.get("text", ""))
        return "".join(parts)
    return str(cell_value)


def get_image_token(cell_value) -> Optional[str]:
    """Return Lark fileToken if cell contains an embed-image, else None."""
    if not cell_value:
        return None
    if isinstance(cell_value, str) and cell_value.strip() in ("无", ""):
        return None
    if isinstance(cell_value, dict) and cell_value.get("type") == "embed-image":
        return cell_value.get("fileToken")
    return None


def find_pending_row(
    rows: list,
    today: Optional[datetime.date] = None,
) -> Optional[tuple]:
    """Scan rows for the first exclusive-updates row that is 待发布 and due.

    Args:
        rows: raw values list from Lark Sheets API (0-indexed, row 0 = title).
        today: date to compare against; defaults to current BJT date.

    Returns:
        (sheet_row_1based: int, row: list) or None.
    """
    if today is None:
        today = datetime.datetime.now(_BJT).date()
    for i, row in enumerate(rows):
        if len(row) < 6:
            continue
        date_val, channel, _, _, _, status = row[0], row[1], row[2], row[3], row[4], row[5]
        if not date_val or not channel or not status:
            continue
        if str(channel).strip() != "exclusive-updates":
            continue
        if str(status).strip() != "待发布":
            continue
        try:
            row_date = datetime.datetime.strptime(str(date_val).strip(), "%Y-%m-%d %H:%M").date()
        except ValueError:
            continue
        if row_date <= today:
            return (i + 1, row)  # i+1 converts to 1-based sheet row
    return None
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_updates.py
import datetime
import pytest
import cogs.updates as upd


# ── parse_rich_text ───────────────────────────────────────────────────────────

def test_parse_rich_text_none():
    assert upd.parse_rich_text(None) == ""

def test_parse_rich_text_plain_string():
    assert upd.parse_rich_text("Hello world") == "Hello world"

def test_parse_rich_text_array_text_nodes():
    nodes = [{"type": "text", "text": "Hello "}, {"type": "text", "text": "world"}]
    assert upd.parse_rich_text(nodes) == "Hello world"

def test_parse_rich_text_array_url_node_with_https():
    nodes = [{"type": "url", "link": "https://fortunepurple.com", "text": "click"}]
    assert upd.parse_rich_text(nodes) == "https://fortunepurple.com"

def test_parse_rich_text_array_url_node_without_https():
    nodes = [{"type": "url", "link": "fortunepurple.com", "text": "click"}]
    assert upd.parse_rich_text(nodes) == "https://fortunepurple.com"

def test_parse_rich_text_mixed_nodes():
    nodes = [
        {"type": "text", "text": "Play now: "},
        {"type": "url", "link": "fortunepurple.com", "text": "here"},
    ]
    assert upd.parse_rich_text(nodes) == "Play now: https://fortunepurple.com"


# ── get_image_token ───────────────────────────────────────────────────────────

def test_get_image_token_none():
    assert upd.get_image_token(None) is None

def test_get_image_token_wu():
    assert upd.get_image_token("无") is None

def test_get_image_token_empty_string():
    assert upd.get_image_token("") is None

def test_get_image_token_embed_image():
    cell = {"type": "embed-image", "fileToken": "abc123", "width": 1280, "height": 720}
    assert upd.get_image_token(cell) == "abc123"

def test_get_image_token_unknown_dict():
    assert upd.get_image_token({"type": "other"}) is None


# ── find_pending_row ──────────────────────────────────────────────────────────

_TODAY = datetime.date(2026, 5, 28)

def _make_rows(*data_rows):
    """Prepend title + header rows to match real Lark structure."""
    title = ["Fortune Purple · Discord", None, None, None, None, None, None]
    header = ["日期", "发布频道", "内容类型", "发布文案", "配图", "状态", "备注"]
    return [title, header] + list(data_rows)

def _row(date_str, channel="exclusive-updates", status="待发布", content="text", image=None):
    return [date_str, channel, "游戏上新", content, image or "无", status, None]


def test_find_pending_row_finds_due_row():
    rows = _make_rows(_row("2026-5-28 00:00"))
    result = upd.find_pending_row(rows, today=_TODAY)
    assert result is not None
    sheet_row, row = result
    assert sheet_row == 3  # index 2 → sheet row 3

def test_find_pending_row_finds_past_row():
    rows = _make_rows(_row("2026-5-20 00:00"))
    assert upd.find_pending_row(rows, today=_TODAY) is not None

def test_find_pending_row_skips_future():
    rows = _make_rows(_row("2026-6-1 00:00"))
    assert upd.find_pending_row(rows, today=_TODAY) is None

def test_find_pending_row_skips_published():
    rows = _make_rows(_row("2026-5-28 00:00", status="已发布"))
    assert upd.find_pending_row(rows, today=_TODAY) is None

def test_find_pending_row_skips_fabu_zhong():
    rows = _make_rows(_row("2026-5-28 00:00", status="发布中"))
    assert upd.find_pending_row(rows, today=_TODAY) is None

def test_find_pending_row_skips_wrong_channel():
    rows = _make_rows(_row("2026-5-28 00:00", channel="big-wins"))
    assert upd.find_pending_row(rows, today=_TODAY) is None

def test_find_pending_row_returns_first_due():
    rows = _make_rows(
        _row("2026-5-26 00:00"),
        _row("2026-5-28 00:00"),
    )
    sheet_row, _ = upd.find_pending_row(rows, today=_TODAY)
    assert sheet_row == 3  # first one

def test_find_pending_row_empty():
    assert upd.find_pending_row([], today=_TODAY) is None
```

- [ ] **Step 3: Run tests — expect PASS (helpers already implemented)**

```
cd E:\company-ai\fpbot
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe -m pytest tests/test_updates.py -v
```

Expected: all 16 tests PASS.

- [ ] **Step 4: Commit**

```
git add cogs/updates.py tests/test_updates.py
git commit -m "feat: add updates cog helpers and tests (parse_rich_text, get_image_token, find_pending_row)"
```

---

### Task 2: Lark API client functions

**Files:**
- Modify: `cogs/updates.py` — append after the pure helpers section

- [ ] **Step 1: Append Lark client functions to `cogs/updates.py`**

Add this block after the pure helpers, before `async def setup`:

```python
# ── Lark API client ───────────────────────────────────────────────────────────

async def _get_lark_token() -> str:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{LARK_BASE}/auth/v3/app_access_token/internal",
            json={"app_id": LARK_APP_ID, "app_secret": LARK_APP_SECRET},
        ) as resp:
            data = await resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"Lark token error: {data.get('msg')}")
            return data["app_access_token"]


async def _read_sheet() -> list:
    token = await _get_lark_token()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{LARK_BASE}/sheets/v2/spreadsheets/{LARK_SPREADSHEET_TOKEN}"
            f"/values/{LARK_SHEET_ID}!A1:G100",
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            data = await resp.json()
            return data["data"]["valueRange"]["values"]


async def _download_image(file_token: str) -> bytes:
    token = await _get_lark_token()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{LARK_BASE}/drive/v1/medias/{file_token}/download",
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Image download HTTP {resp.status}")
            return await resp.read()


async def _write_cell(sheet_row: int, col: str, value: str) -> None:
    """Write a single cell. sheet_row is 1-based."""
    token = await _get_lark_token()
    range_str = f"{LARK_SHEET_ID}!{col}{sheet_row}"
    async with aiohttp.ClientSession() as session:
        async with session.put(
            f"{LARK_BASE}/sheets/v2/spreadsheets/{LARK_SPREADSHEET_TOKEN}/values",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"valueRange": {"range": range_str, "values": [[value]]}},
        ) as resp:
            data = await resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"Lark write error: {data.get('msg')}")


async def _write_cell_with_retry(
    sheet_row: int, col: str, value: str, retries: int = 3
) -> None:
    for attempt in range(1, retries + 1):
        try:
            await _write_cell(sheet_row, col, value)
            return
        except Exception as exc:
            print(
                f"[updates] Lark write {col}{sheet_row}={value!r} "
                f"attempt {attempt}/{retries} failed: {exc}",
                flush=True,
            )
            if attempt < retries:
                await asyncio.sleep(5)
```

- [ ] **Step 2: Run existing tests to confirm nothing broke**

```
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe -m pytest tests/test_updates.py -v
```

Expected: all 16 tests still PASS.

- [ ] **Step 3: Commit**

```
git add cogs/updates.py
git commit -m "feat: add Lark API client functions to updates cog"
```

---

### Task 3: UpdatesCog with scheduled posting

**Files:**
- Modify: `cogs/updates.py` — append cog class + `setup`

- [ ] **Step 1: Append `UpdatesCog` class and `setup` to `cogs/updates.py`**

```python
# ── Cog ───────────────────────────────────────────────────────────────────────

class UpdatesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.auto_post.start()

    def cog_unload(self) -> None:
        self.auto_post.cancel()

    # ── Scheduled task ────────────────────────────────────────────────────────

    @tasks.loop(time=[_BROADCAST_TIME])
    async def auto_post(self) -> None:
        if datetime.datetime.now(_UTC).weekday() not in _POST_WEEKDAYS:
            return
        await self._do_post()

    @auto_post.before_loop
    async def before_auto_post(self) -> None:
        await self.bot.wait_until_ready()

    # ── Core posting logic ────────────────────────────────────────────────────

    async def _do_post(self) -> None:
        # 1. Find pending row
        try:
            rows = await _read_sheet()
        except Exception as exc:
            print(f"[updates] Failed to read Lark sheet: {exc}", flush=True)
            return

        result = find_pending_row(rows)
        if result is None:
            print("[updates] No pending row found", flush=True)
            return

        sheet_row, row = result
        content = parse_rich_text(row[3] if len(row) > 3 else None)
        image_token = get_image_token(row[4] if len(row) > 4 else None)

        # 2. Mark as 发布中 before touching Discord (prevent duplicate on restart)
        try:
            await _write_cell_with_retry(sheet_row, "F", "发布中")
        except Exception as exc:
            print(f"[updates] Cannot mark row {sheet_row} as 发布中, aborting: {exc}", flush=True)
            return

        # 3. Download image (if required), retry 3× with 15s delay
        file: Optional[discord.File] = None
        if image_token:
            for attempt in range(1, 4):
                try:
                    image_bytes = await _download_image(image_token)
                    file = discord.File(io.BytesIO(image_bytes), filename="update.jpg")
                    break
                except Exception as exc:
                    print(
                        f"[updates] Image download attempt {attempt}/3 failed: {exc}",
                        flush=True,
                    )
                    if attempt < 3:
                        await asyncio.sleep(15)

            if file is None:
                # All retries failed — alert staff-chat, revert status
                await _write_cell_with_retry(sheet_row, "F", "待发布")
                staff = self.bot.get_channel(STAFF_CHAT_CHANNEL_ID)
                if isinstance(staff, discord.abc.Messageable):
                    await staff.send(
                        f"⚠️ Updates 自动发布失败：图片下载重试 3 次均失败，请手动处理。\n"
                        f"表格第 {sheet_row} 行已恢复为「待发布」。"
                    )
                print(f"[updates] Aborted row {sheet_row}: image unavailable", flush=True)
                return

        # 4. Send to Discord
        channel = self.bot.get_channel(UPDATE_CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
            print(f"[updates] UPDATE_CHANNEL_ID {UPDATE_CHANNEL_ID} not found", flush=True)
            await _write_cell_with_retry(sheet_row, "F", "待发布")
            return

        try:
            if file:
                msg = await channel.send(content=content, file=file)
            else:
                msg = await channel.send(content=content)
        except Exception as exc:
            print(f"[updates] Discord send failed: {exc}", flush=True)
            await _write_cell_with_retry(sheet_row, "F", "待发布")
            return

        # 5. Add 10 random reactions
        for emoji in random.sample(REACTION_POOL, 10):
            try:
                await msg.add_reaction(emoji)
            except Exception:
                pass

        # 6. Write back to Lark: 已发布 + message ID
        await _write_cell_with_retry(sheet_row, "F", "已发布")
        await _write_cell_with_retry(sheet_row, "G", str(msg.id))
        print(f"[updates] Posted row {sheet_row}, Discord message ID {msg.id}", flush=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UpdatesCog(bot))
```

- [ ] **Step 2: Run tests to confirm no breakage**

```
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe -m pytest tests/test_updates.py -v
```

Expected: all 16 PASS.

- [ ] **Step 3: Commit**

```
git add cogs/updates.py
git commit -m "feat: add UpdatesCog with scheduled posting, Lark write-back, and image retry"
```

---

### Task 4: `/edit_update` slash command

**Files:**
- Modify: `cogs/updates.py` — add Modal class + slash command inside `UpdatesCog`

- [ ] **Step 1: Add `EditUpdateModal` class before `UpdatesCog`**

Insert this block directly before the `class UpdatesCog` line:

```python
class EditUpdateModal(discord.ui.Modal, title="Edit Update Message"):
    message_id = discord.ui.TextInput(
        label="Message ID",
        placeholder="Right-click message → Copy Message ID",
        required=True,
        max_length=25,
    )
    new_content = discord.ui.TextInput(
        label="New Content",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            channel = interaction.client.get_channel(UPDATE_CHANNEL_ID)
            if not isinstance(channel, discord.abc.Messageable):
                await interaction.followup.send("找不到 updates 频道。", ephemeral=True)
                return
            msg = await channel.fetch_message(int(self.message_id.value.strip()))
            await msg.edit(content=self.new_content.value)
            await interaction.followup.send("消息已更新。", ephemeral=True)
        except ValueError:
            await interaction.followup.send("消息 ID 格式不正确，请填入纯数字。", ephemeral=True)
        except discord.NotFound:
            await interaction.followup.send("找不到该消息，请确认 ID 是否正确。", ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"更新失败：{exc}", ephemeral=True)
```

- [ ] **Step 2: Add slash command inside `UpdatesCog`, after `before_auto_post`**

```python
    @discord.app_commands.command(name="edit_update", description="编辑已发布的 updates 消息（仅 Mod）")
    async def edit_update(self, interaction: discord.Interaction) -> None:
        if not any(r.id == MOD_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("无权限。", ephemeral=True)
            return
        await interaction.response.send_modal(EditUpdateModal())
```

- [ ] **Step 3: Run tests**

```
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe -m pytest tests/test_updates.py -v
```

Expected: all 16 PASS.

- [ ] **Step 4: Commit**

```
git add cogs/updates.py
git commit -m "feat: add /edit_update slash command with Mod role check and Modal"
```

---

### Task 5: Register cog in bot.py + Railway environment variables

**Files:**
- Modify: `bot.py` line 41

- [ ] **Step 1: Add `updates` cog to `bot.py`**

In `bot.py`, after line 41 (`await bot.load_extension("cogs.jackpot")`), add:

```python
            await bot.load_extension("cogs.updates")
```

- [ ] **Step 2: Add environment variables to Railway**

In Railway → Fortune Purple Bot → Variables, add:

| Variable | Value |
|----------|-------|
| `UPDATE_CHANNEL_ID` | `1501874966940094687` |
| `STAFF_CHAT_CHANNEL_ID` | `1498591761940090991` |
| `LARK_APP_ID` | `cli_a97b5b7020381e17` |
| `LARK_APP_SECRET` | `OH8Q0QtN3ritiahfhQtsnc0Ygv00PQyp` |
| `LARK_SPREADSHEET_TOKEN` | `VdvlsAsnChhGMwtrwIfj7Ynypyb` |
| `LARK_SHEET_ID` | `cBez8N` |

(`DISCORD_ADMIN_ROLE_ID=1498593298393337969` should already be set.)

- [ ] **Step 3: Run full test suite**

```
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit and push**

```
git add bot.py
git commit -m "feat: register updates cog in bot"
git -c http.proxy=socks5://127.0.0.1:10808 push origin main
```

Railway will auto-deploy. After deploy, verify bot logs show `[updates]` startup message and no errors.

---

## Post-Deploy Smoke Test

1. In Railway Logs, confirm no import errors for `cogs.updates`
2. In `#bot-commands`, run `/edit_update` as a non-Mod user → should see "无权限"
3. Run `/edit_update` as Mod → Modal should appear with two fields
4. To test posting: add a row to the Lark spreadsheet with `exclusive-updates` channel, `待发布` status, today's date, and some content. Temporarily trigger `_do_post` by calling it via a debug command or wait for the next scheduled time.
