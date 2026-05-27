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

BUTTON_URL: str = os.getenv("BIGWIN_BUTTON_URL", "")

_UTC = datetime.timezone.utc

# 每天北京时间 19:00 = UTC 11:00
BROADCAST_TIME = datetime.time(hour=11, minute=0, tzinfo=_UTC)

IMAGE_URLS = [
    "https://raw.githubusercontent.com/peterone3011/bot-app/main/dashboard/public/jackpot1.png",
    "https://raw.githubusercontent.com/peterone3011/bot-app/main/dashboard/public/jackpot2.png",
]

# 持久化文件：记录最近一次发送日期，重启后仍有效
_SENT_DATE_FILE = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "/data") + "/jackpot_last_sent.txt"


def _read_last_sent() -> Optional[datetime.date]:
    try:
        with open(_SENT_DATE_FILE) as f:
            return datetime.date.fromisoformat(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _write_last_sent(date: datetime.date) -> None:
    try:
        with open(_SENT_DATE_FILE, "w") as f:
            f.write(date.isoformat())
    except Exception as exc:
        print(f"[jackpot] Failed to persist last sent date: {exc}", flush=True)


def random_jackpot_amount() -> str:
    """100K–500K，个位必须是 0（即 100, 110, 120, … 500）"""
    value = random.randrange(100, 501, 10)
    return f"{value}K"


class JackpotCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._image_index: int = 0
        self.auto_broadcast.start()

    def cog_unload(self) -> None:
        self.auto_broadcast.cancel()

    async def _do_broadcast(self, source: str) -> None:
        today = datetime.datetime.now(_UTC).date()
        if _read_last_sent() == today:
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

        view: Optional[discord.ui.View] = None
        if BUTTON_URL:
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                label="Play Now",
                url=BUTTON_URL,
                style=discord.ButtonStyle.link,
            ))

        try:
            await channel.send(embed=embed, view=view)
            _write_last_sent(today)
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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(JackpotCog(bot))
