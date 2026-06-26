import io
import os
import asyncio
import random
import datetime
from typing import Optional

import aiohttp
import discord
from discord.ext import commands, tasks

# ── Constants ─────────────────────────────────────────────────────────────────

_BJT = datetime.timezone(datetime.timedelta(hours=8))
_UTC = datetime.timezone.utc
_BROADCAST_TIME = datetime.time(hour=16, minute=0, tzinfo=_UTC)  # 00:00 BJT

UPDATE_CHANNEL_ID: int = int(os.getenv("UPDATE_CHANNEL_ID", "0"))
STAFF_CHAT_CHANNEL_ID: int = int(os.getenv("STAFF_CHAT_CHANNEL_ID", "0"))
LARK_BASE = "https://open.larksuite.com/open-apis"
LARK_APP_ID: str = os.getenv("LARK_APP_ID", "")
LARK_APP_SECRET: str = os.getenv("LARK_APP_SECRET", "")
LARK_NOTIFY_CHAT_ID: str = os.getenv("LARK_NOTIFY_CHAT_ID", "")

BITABLE_APP_TOKEN: str = os.getenv("BITABLE_APP_TOKEN", "IPG2bxK0IanGwksBqVljigsMpcb")
BITABLE_TABLE_ID: str = os.getenv("BITABLE_TABLE_ID", "tble5kqGbD4P0aHy")

# Bitable field IDs
_FLD_DATE = "flduHQ5WXI"
_FLD_CONTENT = "fldXByOoKH"
_FLD_IMAGE = "fld8A6l5dt"
_FLD_STATUS = "fldph5tFB3"

_STATUS_PENDING = "待发布"
_STATUS_POSTING = "发布中"
_STATUS_DONE = "已发布"

REACTION_POOL = [
    "🎉", "🎊", "🔥", "💜", "✨", "🚀", "💰", "🎰",
    "👑", "🌟", "💎", "🙌", "😍", "🤩", "💪", "🎯",
    "⚡", "🏆", "🎁", "💫",
]

# ── Pure helpers (tested) ─────────────────────────────────────────────────────

def _extract_text(value) -> str:
    """Extract plain text from a Bitable text field (string or rich-text list)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(seg.get("text", "") for seg in value if isinstance(seg, dict))
    return str(value)


def find_pending_record(
    records: list,
    today: Optional[datetime.date] = None,
) -> Optional[tuple]:
    """Return (record_id, fields) for the first record that is 待发布 and due today or earlier.

    Args:
        records: list of record dicts from Bitable API (field_id_as_field_name=true).
        today: date to compare against; defaults to current BJT date.
    """
    if today is None:
        today = datetime.datetime.now(_BJT).date()
    for rec in records:
        fields = rec.get("fields", {})
        if fields.get(_FLD_STATUS) != _STATUS_PENDING:
            continue
        date_ts = fields.get(_FLD_DATE)
        if not date_ts:
            continue
        try:
            record_date = datetime.datetime.fromtimestamp(int(date_ts) / 1000, tz=_BJT).date()
        except (ValueError, TypeError):
            continue
        if record_date <= today:
            return (rec["record_id"], fields)
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


async def _read_bitable_records() -> list:
    token = await _get_lark_token()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{LARK_BASE}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records",
            params={"field_id_as_field_name": "true", "page_size": "100"},
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            data = await resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"Bitable read error: {data.get('msg')}")
            return data["data"]["items"]


async def _download_bitable_image(url: str) -> bytes:
    token = await _get_lark_token()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Image download HTTP {resp.status}")
            return await resp.read()


async def _update_record_status(record_id: str, status: str) -> None:
    token = await _get_lark_token()
    async with aiohttp.ClientSession() as session:
        async with session.put(
            f"{LARK_BASE}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records/{record_id}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"fields": {_FLD_STATUS: status}},
        ) as resp:
            data = await resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"Bitable update error: {data.get('msg')}")


async def _update_record_status_with_retry(
    record_id: str, status: str, retries: int = 3
) -> None:
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(1, retries + 1):
        try:
            await _update_record_status(record_id, status)
            return
        except Exception as exc:
            last_exc = exc
            print(
                f"[updates] Bitable update {record_id} status={status!r} "
                f"attempt {attempt}/{retries} failed: {exc}",
                flush=True,
            )
            if attempt < retries:
                await asyncio.sleep(5)
    raise RuntimeError(
        f"Bitable update {record_id} status={status!r} failed after {retries} retries"
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
            records = await _read_bitable_records()
        except Exception as exc:
            print(f"[updates] Failed to read Bitable: {exc}", flush=True)
            return

        result = find_pending_record(records)
        if result is None:
            print("[updates] No pending record found", flush=True)
            return

        record_id, fields = result
        content = _extract_text(fields.get(_FLD_CONTENT))
        attachments = fields.get(_FLD_IMAGE) or []
        image_url = attachments[0]["url"] if attachments else None

        try:
            await _update_record_status_with_retry(record_id, _STATUS_POSTING)
        except Exception as exc:
            print(f"[updates] Warning: could not mark {record_id} as 发布中: {exc}", flush=True)

        file: Optional[discord.File] = None
        if image_url:
            for attempt in range(1, 4):
                try:
                    image_bytes = await _download_bitable_image(image_url)
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
                await _update_record_status_with_retry(record_id, _STATUS_PENDING)
                staff = self.bot.get_channel(STAFF_CHAT_CHANNEL_ID)
                if isinstance(staff, discord.abc.Messageable):
                    await staff.send(
                        f"⚠️ Updates 自动发布失败：图片下载重试 3 次均失败，请手动处理。\n"
                        f"Record ID {record_id} 已恢复为「待发布」。"
                    )
                print(f"[updates] Aborted {record_id}: image unavailable", flush=True)
                return

        channel = self.bot.get_channel(UPDATE_CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
            print(f"[updates] UPDATE_CHANNEL_ID {UPDATE_CHANNEL_ID} not found", flush=True)
            await _update_record_status_with_retry(record_id, _STATUS_PENDING)
            return

        try:
            if file:
                msg = await channel.send(content=content, file=file)
            else:
                msg = await channel.send(content=content)
        except Exception as exc:
            print(f"[updates] Discord send failed: {exc}", flush=True)
            await _update_record_status_with_retry(record_id, _STATUS_PENDING)
            return

        print(f"[updates] Posted {record_id}, Discord message ID {msg.id}", flush=True)
        try:
            await _update_record_status_with_retry(record_id, _STATUS_DONE)
        except Exception as exc:
            msg_text = f"⚠️ Updates 表格状态更新失败，请手动将 record {record_id} 改为「已发布」"
            print(f"[updates] {msg_text}: {exc}", flush=True)
            await _send_lark_dm(msg_text)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UpdatesCog(bot))
