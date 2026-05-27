import os
import random
import asyncio
import datetime
import aiohttp
from discord.ext import commands, tasks

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://fortunepurplebot.vercel.app")
CRON_SECRET = os.getenv("CRON_SECRET")

# 每天 UTC 0/4/8/12/16/20 点整触发，重启不影响节奏
_UTC = datetime.timezone.utc
BROADCAST_TIMES = [datetime.time(hour=h, tzinfo=_UTC) for h in range(0, 24, 4)]


class BigwinCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.auto_broadcast.start()

    def cog_unload(self):
        self.auto_broadcast.cancel()

    @tasks.loop(time=BROADCAST_TIMES)
    async def auto_broadcast(self):
        # 先检查配置，避免无意义等待
        if not CRON_SECRET:
            print("[bigwin] CRON_SECRET not set, skipping", flush=True)
            return
        await asyncio.sleep(random.randint(0, 300))  # 整点后随机浮动 0~5 分钟
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
                    else:
                        body = await resp.text()
                        print(f"[bigwin] Failed: HTTP {resp.status} {body[:200]}", flush=True)
        except Exception as exc:
            print(f"[bigwin] Error: {exc}", flush=True)

    @auto_broadcast.before_loop
    async def before_auto_broadcast(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(BigwinCog(bot))
