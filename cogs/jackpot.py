import os
import random
import asyncio
import datetime
from typing import Optional

import discord
from discord.ext import commands, tasks

try:
    JACKPOT_CHANNEL_ID: int = int(os.getenv("JACKPOT_CHANNEL_ID", "").strip())
except ValueError:
    JACKPOT_CHANNEL_ID = 0

_UTC = datetime.timezone.utc

# 每天北京时间 19:00 = UTC 11:00
BROADCAST_TIME = datetime.time(hour=11, minute=0, tzinfo=_UTC)

IMAGE_URLS = [
    "https://fortunepurplebot.vercel.app/jackpot1.png",
    "https://fortunepurplebot.vercel.app/jackpot2.png",
]


def random_jackpot_amount() -> str:
    """100K–500K，个位必须是 0（即 100, 110, 120, … 500）"""
    value = random.randrange(100, 501, 10)
    return f"{value}K"


class JackpotCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._image_index: int = 0
        self._last_sent_date: Optional[datetime.date] = None
        self.auto_broadcast.start()

    def cog_unload(self) -> None:
        self.auto_broadcast.cancel()

    async def _do_broadcast(self, source: str) -> None:
        today = datetime.datetime.now(_UTC).date()
        if self._last_sent_date == today:
            print(f"[jackpot][{source}] Already sent today, skipping", flush=True)
            return

        if not JACKPOT_CHANNEL_ID:
            print(f"[jackpot][{source}] JACKPOT_CHANNEL_ID not set, skipping", flush=True)
            return

        channel = self.bot.get_channel(JACKPOT_CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
            print(f"[jackpot][{source}] Channel {JACKPOT_CHANNEL_ID} not found or not messageable", flush=True)
            return

        amount = random_jackpot_amount()
        image_url = IMAGE_URLS[self._image_index % 2]

        embed = discord.Embed(
            description=(
                f"🎰 **Jackpot Alert!**\n\n"
                f"The jackpot is over **{amount} SC** and could drop any second!\n\n"
                f"Don't miss your chance to win big — Log in and **SPIN NOW!**"
            ),
            color=0xFFD700,
        )
        embed.set_image(url=image_url)

        try:
            await channel.send(embed=embed)
            self._last_sent_date = today
            self._image_index += 1  # 仅发送成功后才推进，保持交替正确
            print(f"[jackpot][{source}] Broadcast sent: {amount} ({image_url})", flush=True)
        except Exception as exc:
            print(f"[jackpot][{source}] Error sending: {exc}", flush=True)

    @tasks.loop(time=[BROADCAST_TIME])
    async def auto_broadcast(self) -> None:
        await self._do_broadcast("cron")

    @auto_broadcast.before_loop
    async def before_auto_broadcast(self) -> None:
        await self.bot.wait_until_ready()
        # 等待 GUILD_CREATE 事件填充频道缓存（READY 之后可能还差几帧）
        for _ in range(5):
            if self.bot.get_channel(JACKPOT_CHANNEL_ID) is not None:
                break
            await asyncio.sleep(1)
        # 启动时立即发一次（用于测试部署；正式上线后重启若当天已发会被日期守卫跳过）
        await self._do_broadcast("startup")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(JackpotCog(bot))
