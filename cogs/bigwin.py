import os
import random
import asyncio
import datetime
import aiohttp
from discord.ext import commands, tasks

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://fortunepurplebot.vercel.app")
CRON_SECRET = os.getenv("CRON_SECRET")

MAX_RETRIES = 3
RETRY_DELAY = 30  # seconds between retries

_UTC = datetime.timezone.utc
_MIN_INTERVAL_H = 6
_MAX_INTERVAL_H = 14

_DATA_DIR = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "/data")
_STATE_FILE = os.path.join(_DATA_DIR, "bigwin_next_broadcast.txt")

# Legacy fixed-time scheme (6×/day at UTC 0/4/8/12/16/20) — restore if needed:
# BROADCAST_TIMES = [datetime.time(hour=h, tzinfo=_UTC) for h in range(0, 24, 4)]


def _random_interval() -> datetime.timedelta:
    return datetime.timedelta(seconds=random.uniform(_MIN_INTERVAL_H * 3600, _MAX_INTERVAL_H * 3600))


def _load_next_broadcast() -> datetime.datetime:
    """Read persisted next-broadcast time; fall back to now + random interval."""
    now = datetime.datetime.now(_UTC)
    try:
        with open(_STATE_FILE) as f:
            ts = float(f.read().strip())
        saved = datetime.datetime.fromtimestamp(ts, tz=_UTC)
        # Accept only if it's still in the future and within the max window
        if now < saved <= now + datetime.timedelta(hours=_MAX_INTERVAL_H):
            return saved
    except Exception:
        pass
    return now + _random_interval()


def _save_next_broadcast(dt: datetime.datetime) -> None:
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_STATE_FILE, "w") as f:
            f.write(str(dt.timestamp()))
    except Exception as exc:
        print(f"[bigwin] Warning: could not save next broadcast time: {exc}", flush=True)


class BigwinCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._next_broadcast = _load_next_broadcast()
        print(f"[bigwin] Next broadcast scheduled at {self._next_broadcast.isoformat()}", flush=True)
        self.auto_broadcast.start()

    def cog_unload(self):
        self.auto_broadcast.cancel()

    @tasks.loop(minutes=15)
    async def auto_broadcast(self):
        if not CRON_SECRET:
            print("[bigwin] CRON_SECRET not set, skipping", flush=True)
            return
        if datetime.datetime.now(_UTC) < self._next_broadcast:
            return
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{DASHBOARD_URL}/api/broadcast/bigwin",
                        headers={"Authorization": f"Bearer {CRON_SECRET}"},
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("skipped"):
                                print(f"[bigwin] Skipped: {data.get('reason')}", flush=True)
                            else:
                                print(
                                    f"[bigwin] Broadcast sent: {data.get('amount')} SC on {data.get('game')}",
                                    flush=True,
                                )
                            self._next_broadcast = datetime.datetime.now(_UTC) + _random_interval()
                            _save_next_broadcast(self._next_broadcast)
                            break
                        else:
                            body = await resp.text()
                            print(f"[bigwin] Failed (attempt {attempt}/{MAX_RETRIES}): HTTP {resp.status} {body[:200]}", flush=True)
            except Exception as exc:
                print(f"[bigwin] Error (attempt {attempt}/{MAX_RETRIES}): {exc}", flush=True)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
        else:
            # All retries failed — retry in 30 min instead of skipping the full interval
            self._next_broadcast = datetime.datetime.now(_UTC) + datetime.timedelta(minutes=30)
            _save_next_broadcast(self._next_broadcast)
            print("[bigwin] All retries exhausted, will retry in 30 min", flush=True)

    @auto_broadcast.before_loop
    async def before_auto_broadcast(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(BigwinCog(bot))
