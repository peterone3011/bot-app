from __future__ import annotations

import asyncio
import datetime
import json
import os
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

import aiohttp
import discord
from discord.ext import commands, tasks

_BJT = datetime.timezone(datetime.timedelta(hours=8))
_UTC = datetime.timezone.utc
_ROLLUP_TIME_UTC = datetime.time(hour=15, minute=59, tzinfo=_UTC)

_DATA_DIR = Path(os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "/data"))
_EVENTS_FILE = _DATA_DIR / "community_metrics_events.jsonl"

LARK_BASE = "https://open.larksuite.com/open-apis"
LARK_APP_ID = os.getenv("LARK_APP_ID", "")
LARK_APP_SECRET = os.getenv("LARK_APP_SECRET", "")
METRICS_SPREADSHEET_TOKEN = os.getenv(
    "COMMUNITY_METRICS_SPREADSHEET_TOKEN",
    "PA8usyjmshX40HtXaeTjkr4Apne",
)
METRICS_SHEET_ID = os.getenv("COMMUNITY_METRICS_SHEET_ID", "e348a1")

UPDATE_CHANNEL_ID = int(os.getenv("UPDATE_CHANNEL_ID", "0") or "0")
GAMING_ROLE_NAME = os.getenv("METRICS_GAMING_ROLE_NAME", "Gaming Alerts")
UPDATES_ROLE_NAME = os.getenv("METRICS_UPDATES_ROLE_NAME", "Exclusive Updates")
WEEKLY_FIRST_COL = "I"
WEEKLY_LAST_COL = "P"
WEEKLY_RANGE_COLS = "I:P"

EventType = Literal["join", "leave", "role_subscribe"]


def _now_bjt() -> datetime.datetime:
    return datetime.datetime.now(_BJT)


def _day_window(day: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    start = datetime.datetime.combine(day, datetime.time.min, tzinfo=_BJT)
    return start, start + datetime.timedelta(days=1)


def _week_window(day: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    monday = day - datetime.timedelta(days=day.weekday())
    start = datetime.datetime.combine(monday, datetime.time.min, tzinfo=_BJT)
    return start, start + datetime.timedelta(days=7)


def _parse_ts(value: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(value).astimezone(_BJT)
    except (TypeError, ValueError):
        return None


def _count_events(
    events: Iterable[dict[str, Any]],
    event_type: EventType,
    start: datetime.datetime,
    end: datetime.datetime,
    role_contains: str | None = None,
) -> int:
    count = 0
    for event in events:
        if event.get("type") != event_type:
            continue
        if role_contains and role_contains.lower() not in str(event.get("role", "")).lower():
            continue
        ts = _parse_ts(str(event.get("ts", "")))
        if ts is not None and start <= ts < end:
            count += 1
    return count


def _count_unique_role_subscribers(
    events: Iterable[dict[str, Any]],
    start: datetime.datetime,
    end: datetime.datetime,
    role_contains: str,
) -> int:
    members: set[str] = set()
    needle = role_contains.lower()
    for event in events:
        if event.get("type") != "role_subscribe":
            continue
        if needle not in str(event.get("role", "")).lower():
            continue
        ts = _parse_ts(str(event.get("ts", "")))
        member_id = event.get("member_id")
        if ts is not None and member_id and start <= ts < end:
            members.add(str(member_id))
    return len(members)


def _find_role(guild: discord.Guild, name_part: str) -> Optional[discord.Role]:
    needle = name_part.lower()
    return next((role for role in guild.roles if needle in role.name.lower()), None)


def _normalize_sheet_date(value: Any) -> str:
    if isinstance(value, (int, float)):
        # Lark/Excel-style serial date, matching the existing sheet rows.
        base = datetime.date(1899, 12, 30)
        return _format_sheet_date(base + datetime.timedelta(days=int(value)))
    text = str(value or "").strip()
    try:
        return _format_sheet_date(datetime.date.fromisoformat(text))
    except ValueError:
        return text


def _format_sheet_date(day: datetime.date) -> str:
    return day.strftime("%Y/%m/%d")


async def record_metric_event(
    event_type: EventType,
    *,
    member_id: int | None = None,
    role: str | None = None,
    at: datetime.datetime | None = None,
) -> None:
    """Best-effort append-only local event log used for daily/weekly rollups."""
    event = {
        "type": event_type,
        "ts": (at or _now_bjt()).isoformat(),
        "member_id": str(member_id) if member_id is not None else None,
        "role": role,
    }
    try:
        await asyncio.to_thread(_append_event_sync, event)
    except Exception as exc:
        print(f"[community_metrics] Failed to record event {event_type}: {exc}", flush=True)


def _append_event_sync(event: dict[str, Any]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _EVENTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _load_events_sync() -> list[dict[str, Any]]:
    try:
        with _EVENTS_FILE.open("r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []


async def _load_events() -> list[dict[str, Any]]:
    return await asyncio.to_thread(_load_events_sync)


class LarkSheetClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at = datetime.datetime.min.replace(tzinfo=_UTC)

    async def _get_token(self) -> str:
        now = datetime.datetime.now(_UTC)
        if self._token and now < self._token_expires_at:
            return self._token
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LARK_BASE}/auth/v3/app_access_token/internal",
                json={"app_id": LARK_APP_ID, "app_secret": LARK_APP_SECRET},
            ) as resp:
                data = await resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Lark token error: {data.get('msg')}")
        self._token = data["tenant_access_token"]
        self._token_expires_at = now + datetime.timedelta(seconds=int(data.get("expire", 3600)) - 300)
        return self._token

    async def read_values(self, range_name: str) -> list[list[Any]]:
        token = await self._get_token()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{LARK_BASE}/sheets/v2/spreadsheets/{METRICS_SPREADSHEET_TOKEN}"
                f"/values/{range_name}",
                headers={"Authorization": f"Bearer {token}"},
            ) as resp:
                data = await resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Lark read error: {data.get('msg')}")
        return data["data"]["valueRange"].get("values", [])

    async def write_values(self, range_name: str, values: list[list[Any]]) -> None:
        token = await self._get_token()
        async with aiohttp.ClientSession() as session:
            async with session.put(
                f"{LARK_BASE}/sheets/v2/spreadsheets/{METRICS_SPREADSHEET_TOKEN}/values",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
                json={"valueRange": {"range": range_name, "values": values}},
            ) as resp:
                data = await resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Lark write error: {data.get('msg')}")


class CommunityMetricsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.sheet = LarkSheetClient()
        self.daily_rollup.start()
        self.weekly_rollup.start()

    def cog_unload(self) -> None:
        self.daily_rollup.cancel()
        self.weekly_rollup.cancel()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not member.bot:
            await record_metric_event("join", member_id=member.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if not member.bot:
            await record_metric_event("leave", member_id=member.id)

    @tasks.loop(time=[_ROLLUP_TIME_UTC])
    async def daily_rollup(self) -> None:
        await self._write_daily(_now_bjt().date())

    @daily_rollup.before_loop
    async def before_daily_rollup(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(time=[_ROLLUP_TIME_UTC])
    async def weekly_rollup(self) -> None:
        today = _now_bjt().date()
        if today.weekday() == 6:  # Sunday
            await self._write_weekly(today)

    @weekly_rollup.before_loop
    async def before_weekly_rollup(self) -> None:
        await self.bot.wait_until_ready()

    async def _write_daily(self, day: datetime.date) -> None:
        guild = self.bot.guilds[0] if self.bot.guilds else None
        if guild is None:
            print("[community_metrics] No guild available for daily rollup", flush=True)
            return

        events = await _load_events()
        start, end = _day_window(day)
        joins = _count_events(events, "join", start, end)
        leaves = _count_events(events, "leave", start, end)
        gaming_subs = _count_unique_role_subscribers(events, start, end, GAMING_ROLE_NAME)
        updates_subs = _count_unique_role_subscribers(events, start, end, UPDATES_ROLE_NAME)
        total_members = guild.member_count or len([m for m in guild.members if not m.bot])
        sheet_date = _format_sheet_date(day)

        row = [
            sheet_date,
            total_members,
            joins,
            leaves,
            joins - leaves,
            gaming_subs,
            updates_subs,
        ]
        try:
            target = await self._find_or_next_row("A", sheet_date, "A:G")
            await self.sheet.write_values(f"{METRICS_SHEET_ID}!A{target}:G{target}", [row])
            print(f"[community_metrics] Daily row updated for {sheet_date} at row {target}", flush=True)
        except Exception as exc:
            print(f"[community_metrics] Daily rollup failed: {exc}", flush=True)

    async def _write_weekly(self, day: datetime.date) -> None:
        guild = self.bot.guilds[0] if self.bot.guilds else None
        if guild is None:
            print("[community_metrics] No guild available for weekly rollup", flush=True)
            return

        events = await _load_events()
        start, end = _week_window(day)
        joins = _count_events(events, "join", start, end)
        leaves = _count_events(events, "leave", start, end)
        total_members = guild.member_count or len([m for m in guild.members if not m.bot])
        gaming_role = _find_role(guild, GAMING_ROLE_NAME)
        updates_role = _find_role(guild, UPDATES_ROLE_NAME)
        reaction_count = await self._count_weekly_update_reactions(start, end)
        sheet_date = _format_sheet_date(day)

        row = [
            sheet_date,
            total_members,
            joins,
            leaves,
            joins - leaves,
            reaction_count,
            len(gaming_role.members) if gaming_role else 0,
            len(updates_role.members) if updates_role else 0,
        ]
        try:
            target = await self._find_or_next_row(WEEKLY_FIRST_COL, sheet_date, WEEKLY_RANGE_COLS)
            await self.sheet.write_values(
                f"{METRICS_SHEET_ID}!{WEEKLY_FIRST_COL}{target}:{WEEKLY_LAST_COL}{target}",
                [row],
            )
            print(f"[community_metrics] Weekly row updated for {sheet_date} at row {target}", flush=True)
        except Exception as exc:
            print(f"[community_metrics] Weekly rollup failed: {exc}", flush=True)

    async def _find_or_next_row(self, first_col: str, key: str, range_cols: str) -> int:
        values = await self.sheet.read_values(f"{METRICS_SHEET_ID}!{range_cols}")
        next_row = 2
        for index, row in enumerate(values[1:], start=2):
            first = row[0] if row else None
            if _normalize_sheet_date(first) == key:
                return index
            if first not in (None, ""):
                next_row = index + 1
        return next_row

    async def _count_weekly_update_reactions(
        self,
        start: datetime.datetime,
        end: datetime.datetime,
    ) -> int:
        if not UPDATE_CHANNEL_ID:
            return 0
        channel = self.bot.get_channel(UPDATE_CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
            return 0
        total = 0
        after = start.astimezone(_UTC).replace(tzinfo=None)
        before = end.astimezone(_UTC).replace(tzinfo=None)
        try:
            async for message in channel.history(limit=None, after=after, before=before):
                for reaction in message.reactions:
                    total += await _count_human_reaction_users(reaction)
        except Exception as exc:
            print(f"[community_metrics] Failed to count update reactions: {exc}", flush=True)
        return total


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommunityMetricsCog(bot))


async def _count_human_reaction_users(reaction: discord.Reaction) -> int:
    count = 0
    async for user in reaction.users(limit=None):
        if not user.bot:
            count += 1
    return count
