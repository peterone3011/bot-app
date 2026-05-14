import json
import os
import uuid
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands, tasks
from discord import app_commands

TZ_CST = timezone(timedelta(hours=8))
DATA_FILE = "scheduled_messages.json"


def parse_time(text: str) -> datetime | None:
    try:
        dt = datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=TZ_CST)
    except ValueError:
        return None


def load_messages() -> list[dict]:
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_messages(messages: list[dict]) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


def is_due(message: dict) -> bool:
    try:
        send_at = datetime.fromisoformat(message["send_at"])
        return datetime.now(tz=TZ_CST) >= send_at
    except (KeyError, ValueError):
        return False


class SchedulerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_unload(self):
        self.send_loop.cancel()

    async def cog_load(self):
        self.send_loop.start()

    @tasks.loop(seconds=60)
    async def send_loop(self):
        messages = load_messages()
        remaining = []
        for msg in messages:
            if not is_due(msg):
                remaining.append(msg)
                continue
            channel = self.bot.get_channel(msg.get("channel_id"))
            if channel is None:
                print(f"[scheduler] channel {msg.get('channel_id')} not found, dropping {msg.get('id', '<unknown>')}")
                continue
            text = msg["content"]
            if msg.get("image_url"):
                text += f"\n{msg['image_url']}"
            try:
                await channel.send(text)
            except Exception as e:
                print(f"[scheduler] failed to send {msg.get('id', '<unknown>')}: {e}")
                remaining.append(msg)
        if len(remaining) != len(messages):
            save_messages(remaining)

    @send_loop.before_loop
    async def before_send_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(SchedulerCog(bot))
