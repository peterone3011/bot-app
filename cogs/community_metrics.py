from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import os
import uuid
from contextlib import contextmanager
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
_PENDING_ROLLUPS_FILE = _DATA_DIR / "community_metrics_pending.json"
_PENDING_ROLLUPS_LOCK = asyncio.Lock()

LARK_BASE = "https://open.larksuite.com/open-apis"
LARK_APP_ID = os.getenv("LARK_APP_ID", "")
LARK_APP_SECRET = os.getenv("LARK_APP_SECRET", "")
METRICS_BASE_APP_TOKEN = os.getenv(
    "COMMUNITY_METRICS_BASE_APP_TOKEN",
    "CeqtbxWt5azkkHs8OzpjZ9D1p2e",
)
METRICS_BASE_TABLE_ID = os.getenv(
    "COMMUNITY_METRICS_BASE_TABLE_ID",
    "tblMeRm8yocZPqUR",
)

UPDATE_CHANNEL_ID = int(os.getenv("UPDATE_CHANNEL_ID", "0") or "0")
GAMING_ROLE_NAME = os.getenv("METRICS_GAMING_ROLE_NAME", "Gaming Alerts")
UPDATES_ROLE_NAME = os.getenv("METRICS_UPDATES_ROLE_NAME", "Exclusive Updates")
LUCKY_DROPS_ROLE_NAME = os.getenv(
    "METRICS_LUCKY_DROPS_ROLE_NAME",
    "Lucky Drops",
)
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


def _format_metric_date(day: datetime.date) -> str:
    return day.strftime("%Y/%m/%d")


def _base_date_ms(day: datetime.date) -> int:
    value = datetime.datetime.combine(day, datetime.time.min, tzinfo=_BJT)
    return int(value.timestamp() * 1000)


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


def _create_client_token(key: str) -> str:
    seed = f"{METRICS_BASE_APP_TOKEN}:{METRICS_BASE_TABLE_ID}:{key}".encode("utf-8")
    raw = bytearray(hashlib.sha256(seed).digest()[:16])
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(raw)))


async def _upsert_with_retry(
    base: Any,
    key: str,
    fields: dict[str, object],
    *,
    delays: tuple[float, ...] = (5, 15),
) -> Literal["created", "updated"]:
    for attempt in range(len(delays) + 1):
        try:
            return await base.upsert_record(key, fields)
        except Exception as exc:
            if attempt == len(delays):
                raise
            print(
                f"[community_metrics] Base upsert {key!r} attempt {attempt + 1} failed: {exc}",
                flush=True,
            )
            await asyncio.sleep(delays[attempt])
    raise RuntimeError("unreachable Base upsert retry state")


def _load_pending_rollups_unlocked() -> dict[str, dict[str, object]]:
    try:
        data = json.loads(_PENDING_ROLLUPS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise RuntimeError("community metrics pending file must contain an object")
    return {
        str(key): fields
        for key, fields in data.items()
        if isinstance(fields, dict)
    }


def _write_pending_rollups_unlocked(pending: dict[str, dict[str, object]]) -> None:
    _PENDING_ROLLUPS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _PENDING_ROLLUPS_FILE.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(pending, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(_PENDING_ROLLUPS_FILE)


@contextmanager
def _pending_file_lock():
    lock_path = _PENDING_ROLLUPS_FILE.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"0")
            lock_file.flush()
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            lock_file.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _load_pending_rollups_sync() -> dict[str, dict[str, object]]:
    with _pending_file_lock():
        return _load_pending_rollups_unlocked()


def _queue_pending_rollup_sync(key: str, fields: dict[str, object]) -> None:
    with _pending_file_lock():
        pending = _load_pending_rollups_unlocked()
        pending[key] = fields
        _write_pending_rollups_unlocked(pending)


def _remove_pending_rollup_sync(key: str, fields: dict[str, object]) -> None:
    with _pending_file_lock():
        pending = _load_pending_rollups_unlocked()
        if pending.get(key) != fields:
            return
        del pending[key]
        _write_pending_rollups_unlocked(pending)


async def _queue_pending_rollup(key: str, fields: dict[str, object]) -> None:
    async with _PENDING_ROLLUPS_LOCK:
        await asyncio.to_thread(_queue_pending_rollup_sync, key, fields)


async def _remove_pending_rollup(key: str, fields: dict[str, object]) -> None:
    async with _PENDING_ROLLUPS_LOCK:
        await asyncio.to_thread(_remove_pending_rollup_sync, key, fields)


async def _persisted_upsert(
    base: Any,
    key: str,
    fields: dict[str, object],
    *,
    delays: tuple[float, ...] = (5, 15),
) -> Literal["created", "updated"]:
    await _queue_pending_rollup(key, fields)
    action = await _upsert_with_retry(base, key, fields, delays=delays)
    await _remove_pending_rollup(key, fields)
    return action


async def _flush_pending_rollups(
    base: Any,
    *,
    delays: tuple[float, ...] = (5, 15),
) -> int:
    completed = 0
    async with _PENDING_ROLLUPS_LOCK:
        pending = await asyncio.to_thread(_load_pending_rollups_sync)
    for key, fields in list(pending.items()):
        try:
            await _upsert_with_retry(base, key, fields, delays=delays)
        except Exception as exc:
            print(
                f"[community_metrics] Pending Base rollup {key!r} still failed: {exc}",
                flush=True,
            )
            continue
        await _remove_pending_rollup(key, fields)
        completed += 1
    return completed


def _extract_lark_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            str(item.get("text", "")) for item in value if isinstance(item, dict)
        )
    return str(value)


def _decode_lark_response(method: str, status: int, raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Lark Base {method} returned non-JSON HTTP {status}: {raw[:200]}"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Lark Base {method} returned an invalid JSON payload")
    if status >= 400 or data.get("code") != 0:
        raise RuntimeError(
            f"Lark Base {method} error: HTTP {status}: {data.get('msg')}"
        )
    return data


class LarkBaseClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at = datetime.datetime.min.replace(tzinfo=_UTC)
        self._upsert_lock = asyncio.Lock()

    async def _get_token(self) -> str:
        now = datetime.datetime.now(_UTC)
        if self._token and now < self._token_expires_at:
            return self._token
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LARK_BASE}/auth/v3/app_access_token/internal",
                json={"app_id": LARK_APP_ID, "app_secret": LARK_APP_SECRET},
            ) as resp:
                data = await resp.json(content_type=None)
        if resp.status >= 400 or data.get("code") != 0:
            raise RuntimeError(f"Lark token error: HTTP {resp.status}: {data.get('msg')}")
        token = str(data.get("tenant_access_token") or "")
        if not token:
            raise RuntimeError("Lark token response missing tenant_access_token")
        self._token = token
        self._token_expires_at = now + datetime.timedelta(
            seconds=max(60, int(data.get("expire", 3600)) - 300)
        )
        return token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        token = await self._get_token()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.request(
                method,
                f"{LARK_BASE}{path}",
                params=params,
                json=json,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            ) as resp:
                raw = await resp.text()
                status = resp.status
        try:
            return _decode_lark_response(method, status, raw)
        except Exception:
            self._token = None
            self._token_expires_at = datetime.datetime.min.replace(tzinfo=_UTC)
            raise

    async def _list_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params = {"page_size": "500"}
            if page_token:
                params["page_token"] = page_token
            data = await self._request(
                "GET",
                f"/bitable/v1/apps/{METRICS_BASE_APP_TOKEN}/tables/"
                f"{METRICS_BASE_TABLE_ID}/records",
                params=params,
            )
            page = data.get("data", {})
            records.extend(page.get("items", []))
            if not page.get("has_more"):
                return records
            page_token = str(page.get("page_token") or "")
            if not page_token:
                raise RuntimeError("Lark Base pagination missing page_token")

    async def upsert_record(
        self,
        key: str,
        fields: dict[str, object],
    ) -> Literal["created", "updated"]:
        async with self._upsert_lock:
            records = await self._list_records()
            matches = [
                record
                for record in records
                if _extract_lark_text((record.get("fields") or {}).get("记录")) == key
            ]
            if len(matches) > 1:
                raise RuntimeError(f"duplicate Base records for key {key!r}")
            base_path = (
                f"/bitable/v1/apps/{METRICS_BASE_APP_TOKEN}/tables/"
                f"{METRICS_BASE_TABLE_ID}/records"
            )
            if matches:
                await self._request(
                    "PUT",
                    f"{base_path}/{matches[0]['record_id']}",
                    json={"fields": fields},
                )
                return "updated"
            await self._request(
                "POST",
                base_path,
                params={"client_token": _create_client_token(key)},
                json={"fields": fields},
            )
            return "created"


class CommunityMetricsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.base = LarkBaseClient()
        self._pending_replay_task = asyncio.create_task(self._replay_pending_after_ready())
        self.daily_rollup.start()
        self.weekly_rollup.start()

    def cog_unload(self) -> None:
        self.daily_rollup.cancel()
        self.weekly_rollup.cancel()
        self._pending_replay_task.cancel()

    async def _replay_pending_after_ready(self) -> None:
        await self.bot.wait_until_ready()
        await self._flush_pending_safely()

    async def _flush_pending_safely(self) -> None:
        try:
            completed = await _flush_pending_rollups(self.base)
            if completed:
                print(
                    f"[community_metrics] Replayed {completed} pending Base rollup(s)",
                    flush=True,
                )
        except Exception as exc:
            print(f"[community_metrics] Pending rollup replay failed: {exc}", flush=True)

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
        await self._flush_pending_safely()
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
        lucky_drops_subs = _count_unique_role_subscribers(
            events,
            start,
            end,
            LUCKY_DROPS_ROLE_NAME,
        )
        total_members = guild.member_count or len([m for m in guild.members if not m.bot])
        date_text = _format_metric_date(day)
        key = f"日报 {date_text}"
        fields: dict[str, object] = {
            "记录": key,
            "统计类型": "日报",
            "日期": _base_date_ms(day),
            "当前总人数": total_members,
            "新增人数": joins,
            "离开人数": leaves,
            "净增长": joins - leaves,
            "Gaming Alerts 新增订阅人数": gaming_subs,
            "Exclusive Updates 新增订阅人数": updates_subs,
            "Lucky Drops 新增订阅人数": lucky_drops_subs,
            "本周贴文 Reaction 数": None,
            "Gaming Alerts 总订阅人数": None,
            "Exclusive Updates 总订阅人数": None,
            "Lucky Drops 总订阅人数": None,
        }
        try:
            action = await _persisted_upsert(self.base, key, fields)
            print(
                f"[community_metrics] Daily Base record {action} for {date_text}",
                flush=True,
            )
        except Exception as exc:
            try:
                await _queue_pending_rollup(key, fields)
            except Exception as queue_exc:
                print(
                    f"[community_metrics] Daily rollup failed and could not be queued: "
                    f"{exc}; queue error: {queue_exc}",
                    flush=True,
                )
            else:
                print(
                    f"[community_metrics] Daily rollup queued after Base failure: {exc}",
                    flush=True,
                )

    async def _write_weekly(self, day: datetime.date) -> None:
        await self._flush_pending_safely()
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
        lucky_drops_role = _find_role(guild, LUCKY_DROPS_ROLE_NAME)
        reaction_count = await self._count_weekly_update_reactions(start, end)
        date_text = _format_metric_date(day)
        key = f"周报 {date_text}"
        fields: dict[str, object] = {
            "记录": key,
            "统计类型": "周报",
            "日期": _base_date_ms(day),
            "当前总人数": total_members,
            "新增人数": joins,
            "离开人数": leaves,
            "净增长": joins - leaves,
            "Gaming Alerts 新增订阅人数": None,
            "Exclusive Updates 新增订阅人数": None,
            "Lucky Drops 新增订阅人数": None,
            "本周贴文 Reaction 数": reaction_count,
            "Gaming Alerts 总订阅人数": len(gaming_role.members) if gaming_role else 0,
            "Exclusive Updates 总订阅人数": len(updates_role.members) if updates_role else 0,
            "Lucky Drops 总订阅人数": len(lucky_drops_role.members) if lucky_drops_role else 0,
        }
        try:
            action = await _persisted_upsert(self.base, key, fields)
            print(
                f"[community_metrics] Weekly Base record {action} for {date_text}",
                flush=True,
            )
        except Exception as exc:
            try:
                await _queue_pending_rollup(key, fields)
            except Exception as queue_exc:
                print(
                    f"[community_metrics] Weekly rollup failed and could not be queued: "
                    f"{exc}; queue error: {queue_exc}",
                    flush=True,
                )
            else:
                print(
                    f"[community_metrics] Weekly rollup queued after Base failure: {exc}",
                    flush=True,
                )

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
