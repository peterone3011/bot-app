import os
import aiohttp
from discord.ext import commands, tasks

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://fortunepurplebot.vercel.app")
CRON_SECRET = os.getenv("CRON_SECRET")


class BigwinCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.auto_broadcast.start()

    def cog_unload(self):
        self.auto_broadcast.cancel()

    @tasks.loop(hours=4)
    async def auto_broadcast(self):
        if not CRON_SECRET:
            print("[bigwin] CRON_SECRET not set, skipping", flush=True)
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{DASHBOARD_URL}/api/broadcast/bigwin",
                    headers={"Authorization": f"Bearer {CRON_SECRET}"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        if data.get("skipped"):
                            print(f"[bigwin] Skipped: {data.get('reason')}", flush=True)
                        else:
                            print(
                                f"[bigwin] Broadcast sent: {data.get('amount')} SC on {data.get('game')}",
                                flush=True,
                            )
                    else:
                        print(f"[bigwin] Failed: HTTP {resp.status} {data}", flush=True)
        except Exception as exc:
            print(f"[bigwin] Error: {exc}", flush=True)

    @auto_broadcast.before_loop
    async def before_auto_broadcast(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(BigwinCog(bot))
