from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
import json
from typing import Any, Iterable

import discord
from discord.ext import commands, tasks

from app.core.runtime import ProjectRuntime


BJT = timezone(timedelta(hours=8))
ROLLUP_TIME_UTC = time(15, 59, tzinfo=timezone.utc)
DAILY_FIELDS = ("日期", "当前总人数", "新增人数", "离开人数", "净增长")


def day_window(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=BJT)
    return start, start + timedelta(days=1)


def _parse_timestamp(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value)).astimezone(BJT)
    except (TypeError, ValueError):
        return None


def count_events(
    events: Iterable[dict[str, Any]],
    event_type: str,
    start: datetime,
    end: datetime,
) -> int:
    return sum(
        1
        for event in events
        if event.get("type") == event_type
        and (timestamp := _parse_timestamp(event.get("ts"))) is not None
        and start <= timestamp < end
    )


class CommunityMetricsCog(commands.Cog):
    def __init__(self, runtime: ProjectRuntime) -> None:
        self.runtime = runtime
        self.bot = runtime.bot
        self._pending_lock = asyncio.Lock()

    def _log(self, message: str) -> None:
        print(f"[{self.runtime.config.slug}][community_metrics] {message}", flush=True)

    async def cog_load(self) -> None:
        if not self.daily_rollup.is_running():
            self.daily_rollup.start()
        asyncio.create_task(self._replay_after_ready())

    def cog_unload(self) -> None:
        self.daily_rollup.cancel()

    async def _replay_after_ready(self) -> None:
        await self.bot.wait_until_ready()
        await self.flush_pending()

    def _load_events_sync(self) -> list[dict[str, Any]]:
        try:
            return [
                json.loads(line)
                for line in self.runtime.state.events_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except FileNotFoundError:
            return []

    def _append_event_sync(self, event: dict[str, Any]) -> None:
        self.runtime.state.ensure_directory()
        with self.runtime.state.events_file.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

    async def record_event(
        self,
        event_type: str,
        *,
        member_id: int,
        at: datetime | None = None,
    ) -> None:
        event = {
            "type": event_type,
            "member_id": str(member_id),
            "ts": (at or datetime.now(BJT)).astimezone(BJT).isoformat(),
        }
        await asyncio.to_thread(self._append_event_sync, event)

    def _load_pending_sync(self) -> dict[str, dict[str, object]]:
        try:
            payload = json.loads(
                self.runtime.state.pending_rollups_file.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            return {}
        if not isinstance(payload, dict):
            raise RuntimeError("pending rollups file must contain an object")
        return {
            str(key): value
            for key, value in payload.items()
            if isinstance(value, dict)
        }

    def _write_pending_sync(self, pending: dict[str, dict[str, object]]) -> None:
        self.runtime.state.ensure_directory()
        path = self.runtime.state.pending_rollups_file
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(pending, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        temporary.replace(path)

    async def _queue_pending(self, key: str, fields: dict[str, object]) -> None:
        async with self._pending_lock:
            pending = await asyncio.to_thread(self._load_pending_sync)
            pending[key] = fields
            await asyncio.to_thread(self._write_pending_sync, pending)

    async def _remove_pending(self, key: str, fields: dict[str, object]) -> None:
        async with self._pending_lock:
            pending = await asyncio.to_thread(self._load_pending_sync)
            if pending.get(key) == fields:
                del pending[key]
                await asyncio.to_thread(self._write_pending_sync, pending)

    async def _upsert(self, key: str, fields: dict[str, object]) -> str:
        config = self.runtime.config.feishu
        client = self.runtime.feishu
        if config is None or client is None:
            raise RuntimeError("Feishu community metrics is not configured")
        return await client.upsert_record_by_text_field(
            config.metrics_base_id,
            config.metrics_table_id,
            "日期",
            key,
            fields,
        )

    async def flush_pending(self) -> int:
        async with self._pending_lock:
            pending = await asyncio.to_thread(self._load_pending_sync)
        completed = 0
        for key, fields in pending.items():
            try:
                await self._upsert(key, fields)
            except Exception as exc:
                self._log(f"pending rollup {key} still failed: {exc}")
                continue
            await self._remove_pending(key, fields)
            completed += 1
        return completed

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if (
            not member.bot
            and member.guild.id == self.runtime.config.discord.guild_id
        ):
            await self.record_event("join", member_id=member.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if (
            not member.bot
            and member.guild.id == self.runtime.config.discord.guild_id
        ):
            await self.record_event("leave", member_id=member.id)

    @tasks.loop(time=[ROLLUP_TIME_UTC])
    async def daily_rollup(self) -> None:
        await self.write_daily(datetime.now(BJT).date())

    @daily_rollup.before_loop
    async def before_daily_rollup(self) -> None:
        await self.bot.wait_until_ready()

    async def write_daily(self, day: date) -> None:
        await self.flush_pending()
        guild = next(
            (
                item
                for item in self.bot.guilds
                if item.id == self.runtime.config.discord.guild_id
            ),
            None,
        )
        if guild is None:
            self._log("no guild available for daily rollup")
            return
        events = await asyncio.to_thread(self._load_events_sync)
        start, end = day_window(day)
        joins = count_events(events, "join", start, end)
        leaves = count_events(events, "leave", start, end)
        total = guild.member_count
        if total is None:
            total = sum(1 for member in guild.members if not member.bot)
        key = day.strftime("%Y/%m/%d")
        fields: dict[str, object] = {
            "日期": key,
            "当前总人数": total,
            "新增人数": joins,
            "离开人数": leaves,
            "净增长": joins - leaves,
        }
        await self._queue_pending(key, fields)
        try:
            action = await self._upsert(key, fields)
        except Exception as exc:
            self._log(f"daily rollup queued after Feishu failure: {exc}")
            return
        await self._remove_pending(key, fields)
        self._log(f"daily record {action} for {key}")


async def install(runtime: ProjectRuntime) -> None:
    await runtime.bot.add_cog(CommunityMetricsCog(runtime))
