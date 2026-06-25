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
_POST_WEEKDAYS = {1, 3, 5}  # Tuesday=1, Thursday=3, Saturday=5
_BROADCAST_TIME = datetime.time(hour=11, minute=0, tzinfo=_UTC)

UPDATE_CHANNEL_ID: int = int(os.getenv("UPDATE_CHANNEL_ID", "0"))
STAFF_CHAT_CHANNEL_ID: int = int(os.getenv("STAFF_CHAT_CHANNEL_ID", "0"))
LARK_BASE = "https://open.larksuite.com/open-apis"
LARK_APP_ID: str = os.getenv("LARK_APP_ID", "")
LARK_APP_SECRET: str = os.getenv("LARK_APP_SECRET", "")
LARK_SPREADSHEET_TOKEN: str = os.getenv("LARK_SPREADSHEET_TOKEN", "")
LARK_SHEET_ID: str = os.getenv("LARK_SHEET_ID", "")
LARK_NOTIFY_CHAT_ID: str = os.getenv("LARK_NOTIFY_CHAT_ID", "")


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
                parts.append(link or "")
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

# ── Lark API client ───────────────────────────────────────────────────────────

async def _send_lark_dm(text: str) -> None:
    if not LARK_NOTIFY_CHAT_ID:
        return
    token = await _get_lark_token()
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"{LARK_BASE}/im/v1/messages?receive_id_type=chat_id",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"receive_id": LARK_NOTIFY_CHAT_ID, "msg_type": "text",
                  "content": f'{{"text":"{text}"}}'},
        )


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
    range_str = f"{LARK_SHEET_ID}!{col}{sheet_row}:{col}{sheet_row}"
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
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(1, retries + 1):
        try:
            await _write_cell(sheet_row, col, value)
            return
        except Exception as exc:
            last_exc = exc
            print(
                f"[updates] Lark write {col}{sheet_row}={value!r} "
                f"attempt {attempt}/{retries} failed: {exc}",
                flush=True,
            )
            if attempt < retries:
                await asyncio.sleep(5)
    raise RuntimeError(
        f"Lark write {col}{sheet_row}={value!r} failed after {retries} retries"
    ) from last_exc


# ── Modal ─────────────────────────────────────────────────────────────────────

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


# ── Cog ───────────────────────────────────────────────────────────────────────

class UpdatesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.auto_post.start()

    def cog_unload(self) -> None:
        self.auto_post.cancel()

    @tasks.loop(time=[_BROADCAST_TIME])
    async def auto_post(self) -> None:
        if datetime.datetime.now(_UTC).weekday() not in _POST_WEEKDAYS:
            return
        await self._do_post()

    @auto_post.before_loop
    async def before_auto_post(self) -> None:
        await self.bot.wait_until_ready()

    @discord.app_commands.command(name="edit_update", description="编辑已发布的 updates 消息（仅管理员）")
    async def edit_update(self, interaction: discord.Interaction) -> None:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("无权限。", ephemeral=True)
            return
        await interaction.response.send_modal(EditUpdateModal())

    @discord.app_commands.command(name="edit_update_image", description="替换已发布的 updates 消息图片（仅管理员）")
    @discord.app_commands.describe(
        message_id="消息 ID（右键消息 → 复制消息 ID）",
        image="新图片",
    )
    async def edit_update_image(
        self,
        interaction: discord.Interaction,
        message_id: str,
        image: discord.Attachment,
    ) -> None:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("无权限。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            channel = interaction.client.get_channel(UPDATE_CHANNEL_ID)
            if not isinstance(channel, discord.abc.Messageable):
                await interaction.followup.send("找不到 updates 频道。", ephemeral=True)
                return
            msg = await channel.fetch_message(int(message_id.strip()))
            image_bytes = await image.read()
            await msg.edit(attachments=[discord.File(io.BytesIO(image_bytes), filename=image.filename)])
            await interaction.followup.send("图片已更新。", ephemeral=True)
        except ValueError:
            await interaction.followup.send("消息 ID 格式不正确，请填入纯数字。", ephemeral=True)
        except discord.NotFound:
            await interaction.followup.send("找不到该消息，请确认 ID 是否正确。", ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"更新失败：{exc}", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.channel.id != UPDATE_CHANNEL_ID:
            return
        emojis = ["🍀"] + random.sample(REACTION_POOL, 9)
        for emoji in emojis:
            try:
                await message.add_reaction(emoji)
            except Exception:
                pass

    async def _do_post(self) -> None:
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

        try:
            await _write_cell_with_retry(sheet_row, "F", "发布中")
        except Exception as exc:
            # Best-effort guard against double-post on restart; don't abort posting.
            print(f"[updates] Warning: could not mark row {sheet_row} as 发布中: {exc}", flush=True)

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
                await _write_cell_with_retry(sheet_row, "F", "待发布")
                staff = self.bot.get_channel(STAFF_CHAT_CHANNEL_ID)
                if isinstance(staff, discord.abc.Messageable):
                    await staff.send(
                        f"⚠️ Updates 自动发布失败：图片下载重试 3 次均失败，请手动处理。\n"
                        f"表格第 {sheet_row} 行已恢复为「待发布」。"
                    )
                print(f"[updates] Aborted row {sheet_row}: image unavailable", flush=True)
                return

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

        print(f"[updates] Posted row {sheet_row}, Discord message ID {msg.id}", flush=True)
        try:
            await _write_cell_with_retry(sheet_row, "F", "已发布")
        except Exception as exc:
            msg_text = f"⚠️ Updates 表格状态更新失败，请手动将第 {sheet_row} 行改为「已发布」"
            print(f"[updates] {msg_text}: {exc}", flush=True)
            await _send_lark_dm(msg_text)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UpdatesCog(bot))
