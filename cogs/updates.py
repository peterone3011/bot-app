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
_CHECK_SLOTS_BJT = (
    datetime.time(0, 1),
    datetime.time(0, 6),
    datetime.time(0, 16),
)
_CHECK_TIMES_UTC = [
    datetime.time(16, 1, tzinfo=_UTC),
    datetime.time(16, 6, tzinfo=_UTC),
    datetime.time(16, 16, tzinfo=_UTC),
]

UPDATE_CHANNEL_ID: int = int(os.getenv("UPDATE_CHANNEL_ID", "0"))
STAFF_CHAT_CHANNEL_ID: int = int(os.getenv("STAFF_CHAT_CHANNEL_ID", "0"))
LARK_BASE = "https://open.larksuite.com/open-apis"
LARK_APP_ID: str = os.getenv("LARK_APP_ID", "")
LARK_APP_SECRET: str = os.getenv("LARK_APP_SECRET", "")
LARK_NOTIFY_CHAT_ID: str = os.getenv("LARK_NOTIFY_CHAT_ID", "")

BITABLE_APP_TOKEN: str = os.getenv("BITABLE_APP_TOKEN", "IPG2bxK0IanGwksBqVljigsMpcb")
BITABLE_TABLE_ID: str = os.getenv("BITABLE_TABLE_ID", "tble5kqGbD4P0aHy")
# Bitable field names (larksuite international API returns field names, not IDs)
_FLD_DATE = "日期"
_FLD_CONTENT = "发布文案"
_FLD_IMAGE = "配图"
_FLD_STATUS = "状态"

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


def _is_due(rec: dict, today: Optional[datetime.date] = None) -> bool:
    """Return True if a pending record is dated exactly yesterday in BJT."""
    if today is None:
        today = datetime.datetime.now(_BJT).date()
    fields = rec.get("fields", {})
    if fields.get(_FLD_STATUS) != _STATUS_PENDING:
        return False
    date_ts = fields.get(_FLD_DATE)
    if not date_ts:
        return False
    try:
        record_date = datetime.datetime.fromtimestamp(int(date_ts) / 1000, tz=_BJT).date()
    except (OverflowError, OSError, ValueError, TypeError):
        return False
    target_date = today - datetime.timedelta(days=1)
    return record_date == target_date


def _startup_window_contains(now: datetime.datetime) -> bool:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + datetime.timedelta(minutes=30)
    return start <= now <= end


def _slot_for_time(now: datetime.datetime) -> Optional[datetime.time]:
    current = now.time().replace(tzinfo=None)
    reached = [slot for slot in _CHECK_SLOTS_BJT if slot <= current]
    return reached[-1] if reached else None


def _has_invalid_pending_date(rec: dict) -> bool:
    """Return True when a pending record has a date that cannot be converted."""
    fields = rec.get("fields", {})
    if fields.get(_FLD_STATUS) != _STATUS_PENDING:
        return False
    date_ts = fields.get(_FLD_DATE)
    if not date_ts:
        return True
    try:
        datetime.datetime.fromtimestamp(int(date_ts) / 1000, tz=_BJT)
    except (OverflowError, OSError, ValueError, TypeError):
        return True
    return False


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
            params={"page_size": "100"},
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
        self._run_lock = asyncio.Lock()
        self._completed_day: Optional[datetime.date] = None
        self._attempted_slots: set[tuple[datetime.date, datetime.time]] = set()
        self.auto_post.start()

    def cog_unload(self) -> None:
        self.auto_post.cancel()

    def _now_bjt(self) -> datetime.datetime:
        return datetime.datetime.now(_BJT)

    @tasks.loop(time=_CHECK_TIMES_UTC)
    async def auto_post(self) -> None:
        now = datetime.datetime.now(_BJT)
        if _startup_window_contains(now):
            slot = _slot_for_time(now)
            if slot is not None:
                await self._run_attempt(now, slot)

    @auto_post.before_loop
    async def before_auto_post(self) -> None:
        await self.bot.wait_until_ready()
        await self._run_startup_catchup()

    async def _run_attempt(
        self, now: datetime.datetime, slot: datetime.time
    ) -> None:
        day = now.date()
        key = (day, slot)
        deadline = now.replace(hour=0, minute=30, second=0, microsecond=0)
        async with self._run_lock:
            if self._completed_day == day or key in self._attempted_slots:
                return
            self._attempted_slots = {
                attempted for attempted in self._attempted_slots if attempted[0] == day
            }
            self._attempted_slots.add(key)
            current = self._now_bjt()
            if current.date() != day or current > deadline:
                await self._finish_failed_attempt(day, slot)
                return
            success = await self._do_post(today=day, deadline=deadline)
            if success:
                self._completed_day = day
                return
            await self._finish_failed_attempt(day, slot)

    async def _finish_failed_attempt(
        self, day: datetime.date, slot: datetime.time
    ) -> None:
        if slot != _CHECK_SLOTS_BJT[-1]:
            return
        self._completed_day = day
        note = f"Daily update {day:%Y/%m/%d} failed after all midnight slots."
        print(f"[updates] {note}", flush=True)
        try:
            await _send_lark_dm(note)
        except Exception as exc:
            print(f"[updates] Failed to send final Lark alert: {exc}", flush=True)

    async def _run_startup_catchup(self) -> None:
        now = datetime.datetime.now(_BJT)
        if not _startup_window_contains(now):
            return
        first_check = now.replace(hour=0, minute=1, second=0, microsecond=0)
        if now < first_check:
            await asyncio.sleep((first_check - now).total_seconds())
            now = datetime.datetime.now(_BJT)
        slot = _slot_for_time(now)
        if slot is not None and _startup_window_contains(now):
            await self._run_attempt(now, slot)

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

    async def _do_post(
        self,
        today: Optional[datetime.date] = None,
        deadline: Optional[datetime.datetime] = None,
    ) -> bool:
        try:
            records = await _read_bitable_records()
        except Exception as exc:
            print(f"[updates] Failed to read Bitable: {exc}", flush=True)
            return False

        if deadline is not None and self._now_bjt() > deadline:
            print("[updates] Midnight posting window expired before filtering", flush=True)
            return False

        due = []
        success = True
        for rec in records:
            try:
                if _is_due(rec, today=today):
                    due.append(rec)
                elif _has_invalid_pending_date(rec):
                    print("[updates] Invalid record date, will retry", flush=True)
                    success = False
            except (AttributeError, TypeError) as exc:
                print(f"[updates] Invalid record, will retry: {exc}", flush=True)
                success = False
                continue
        if not due:
            return success

        channel = self.bot.get_channel(UPDATE_CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
            print(f"[updates] UPDATE_CHANNEL_ID {UPDATE_CHANNEL_ID} not found", flush=True)
            return False

        for rec in due:
            try:
                record_id = rec["record_id"]
                fields = rec["fields"]
                content = _extract_text(fields.get(_FLD_CONTENT))
                attachments = fields.get(_FLD_IMAGE) or []
                image_url = attachments[0].get("url") if attachments else None
            except (AttributeError, IndexError, KeyError, TypeError) as exc:
                print(f"[updates] Invalid record, will retry: {exc}", flush=True)
                success = False
                continue

            # Download image; skip record and retry next poll on failure
            file: Optional[discord.File] = None
            if image_url:
                try:
                    image_bytes = await _download_bitable_image(image_url)
                    file = discord.File(io.BytesIO(image_bytes), filename="update.jpg")
                except Exception as exc:
                    print(f"[updates] Image download failed for {record_id}, will retry: {exc}", flush=True)
                    success = False
                    continue

            # Guard against double-post on crash: mark 发布中 before sending.
            # If the process dies after this write but before 已发布, the record
            # stays 发布中 and won't be re-picked by _is_due (which checks 待发布 only).
            try:
                await _update_record_status_with_retry(record_id, _STATUS_POSTING)
            except Exception as exc:
                success = False
                print(f"[updates] Could not mark {record_id} as 发布中, skipping: {exc}", flush=True)
                continue

            # Send to Discord; restore 待发布 on failure so next poll retries
            if deadline is not None and self._now_bjt() > deadline:
                print(
                    f"[updates] Midnight posting window expired before sending {record_id}",
                    flush=True,
                )
                success = False
                try:
                    await _update_record_status_with_retry(record_id, _STATUS_PENDING)
                except Exception as exc:
                    print(
                        f"[updates] Could not restore {record_id} to pending: {exc}",
                        flush=True,
                    )
                continue

            try:
                if file:
                    msg = await channel.send(content=content, file=file)
                else:
                    msg = await channel.send(content=content)
            except Exception as exc:
                print(f"[updates] Discord send failed for {record_id}: {exc}", flush=True)
                success = False
                try:
                    await _update_record_status_with_retry(record_id, _STATUS_PENDING)
                except Exception:
                    pass
                continue

            print(f"[updates] Posted {record_id}, Discord message ID {msg.id}", flush=True)

            # Write 已发布; retry 3×, log on persistent failure (message already sent)
            try:
                await _update_record_status_with_retry(record_id, _STATUS_DONE)
            except Exception as exc:
                success = False
                note = f"Status writeback failed for record {record_id}; message was sent."
                print(f"[updates] {note}: {exc}", flush=True)
                try:
                    await _send_lark_dm(note)
                except Exception as alert_exc:
                    print(f"[updates] Failed to send status alert: {alert_exc}", flush=True)
        return success


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UpdatesCog(bot))
