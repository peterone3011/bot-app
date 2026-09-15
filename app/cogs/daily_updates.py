from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
import io
from typing import Any

import discord
from discord.ext import commands, tasks

from app.core.runtime import ProjectRuntime


BJT = timezone(timedelta(hours=8))
UTC = timezone.utc
CHECK_SLOTS_BJT = (time(0, 1), time(0, 6), time(0, 16))
CHECK_TIMES_UTC = tuple(time(16, slot.minute, tzinfo=UTC) for slot in CHECK_SLOTS_BJT)
STATUS_PENDING = "待发布"
STATUS_POSTING = "发布中"
STATUS_DONE = "已发布"


def extract_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(str(item.get("text", "")) for item in value if isinstance(item, dict))
    return str(value)


def is_due(record: dict[str, Any], today: date) -> bool:
    fields = record.get("fields") or {}
    if fields.get("状态") != STATUS_PENDING:
        return False
    try:
        record_day = datetime.fromtimestamp(int(fields["日期"]) / 1000, tz=BJT).date()
    except (KeyError, TypeError, ValueError, OSError, OverflowError):
        return False
    return record_day < today


def startup_window_contains(now: datetime) -> bool:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start <= now <= start + timedelta(minutes=30)


def slot_for_time(now: datetime) -> time | None:
    current = now.timetz().replace(tzinfo=None)
    reached = [slot for slot in CHECK_SLOTS_BJT if slot <= current]
    return reached[-1] if reached else None


class DailyUpdatesCog(commands.Cog):
    def __init__(self, runtime: ProjectRuntime) -> None:
        self.runtime = runtime
        self.bot = runtime.bot
        self._lock = asyncio.Lock()
        self._completed_day: date | None = None
        self._attempted_slots: set[tuple[date, time]] = set()

    def _log(self, message: str) -> None:
        print(f"[{self.runtime.config.slug}][daily_updates] {message}", flush=True)

    @tasks.loop(time=CHECK_TIMES_UTC)
    async def scheduled_check(self) -> None:
        now = datetime.now(BJT)
        if startup_window_contains(now):
            await self.run_slot(now)

    @scheduled_check.before_loop
    async def before_scheduled_check(self) -> None:
        await self.bot.wait_until_ready()
        await self.startup_catchup(datetime.now(BJT))

    async def cog_load(self) -> None:
        if not self.scheduled_check.is_running():
            self.scheduled_check.start()

    def cog_unload(self) -> None:
        self.scheduled_check.cancel()

    async def run_slot(self, now: datetime) -> bool:
        if not startup_window_contains(now):
            return False
        slot = slot_for_time(now)
        if slot is None:
            return False
        day = now.date()
        key = (day, slot)
        async with self._lock:
            if self._completed_day == day:
                return True
            if key in self._attempted_slots:
                return False
            self._attempted_slots = {item for item in self._attempted_slots if item[0] == day}
            self._attempted_slots.add(key)
            success = await self.publish_due_records(now)
            if success or slot == CHECK_SLOTS_BJT[-1]:
                self._completed_day = day
                if not success:
                    self._log(f"daily update {day:%Y/%m/%d} failed after all midnight slots")
            return success

    async def startup_catchup(self, now: datetime) -> bool:
        if not startup_window_contains(now):
            return False
        first = now.replace(hour=0, minute=1, second=0, microsecond=0)
        if now < first:
            await asyncio.sleep((first - now).total_seconds())
            now = datetime.now(BJT)
        return await self.run_slot(now)

    async def _update_status_with_retry(self, record_id: str, status: str) -> None:
        config = self.runtime.config.feishu
        client = self.runtime.feishu
        if config is None or client is None:
            raise RuntimeError("Feishu daily updates is not configured")
        last_error: Exception | None = None
        for _ in range(3):
            try:
                await client.update_record(
                    config.updates_base_id,
                    config.updates_table_id,
                    record_id,
                    {"状态": status},
                )
                return
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"unable to set {record_id} status={status}") from last_error

    async def publish_due_records(self, now: datetime) -> bool:
        config = self.runtime.config.feishu
        client = self.runtime.feishu
        if config is None or client is None:
            self._log("Feishu is not configured")
            return False
        try:
            records = await client.list_records(config.updates_base_id, config.updates_table_id)
        except Exception as exc:
            self._log(f"failed to read Bitable: {exc}")
            return False
        channel_id = self.runtime.config.channels.daily_updates
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.abc.Messageable):
            self._log("configured daily updates channel is unavailable")
            return False

        success = True
        for record in records:
            if not is_due(record, now.date()):
                continue
            try:
                record_id = str(record["record_id"])
                fields = record["fields"]
                content = extract_text(fields.get("发布文案"))
                attachments = fields.get("配图") or []
                image_url = attachments[0].get("url") if attachments else None
            except (AttributeError, IndexError, KeyError, TypeError) as exc:
                self._log(f"invalid update record: {exc}")
                success = False
                continue
            try:
                await self._update_status_with_retry(record_id, STATUS_POSTING)
            except Exception as exc:
                self._log(f"cannot mark {record_id} as posting: {exc}")
                success = False
                continue
            file: discord.File | None = None
            if image_url:
                try:
                    image_bytes = await client.download_file(image_url)
                    file = discord.File(io.BytesIO(image_bytes), filename="update.jpg")
                except Exception as exc:
                    self._log(f"image download failed for {record_id}: {exc}")
                    success = False
                    try:
                        await self._update_status_with_retry(record_id, STATUS_PENDING)
                    except Exception as restore_error:
                        self._log(f"cannot restore {record_id} after image failure: {restore_error}")
                    continue
            try:
                if file:
                    message = await channel.send(content=content, file=file)
                else:
                    message = await channel.send(content=content)
            except Exception as exc:
                self._log(f"Discord send failed for {record_id}: {exc}")
                success = False
                try:
                    await self._update_status_with_retry(record_id, STATUS_PENDING)
                except Exception as restore_error:
                    self._log(f"cannot restore {record_id} after send failure: {restore_error}")
                continue
            self._log(f"posted {record_id} Discord message={message.id}")
            try:
                await self._update_status_with_retry(record_id, STATUS_DONE)
            except Exception as exc:
                self._log(f"status writeback failed for {record_id}; message was sent: {exc}")
        return success


async def install(runtime: ProjectRuntime) -> None:
    await runtime.bot.add_cog(DailyUpdatesCog(runtime))
