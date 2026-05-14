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


class ScheduleModal(discord.ui.Modal, title="Schedule a Message"):
    send_time = discord.ui.TextInput(
        label="Send Time (YYYY-MM-DD HH:MM, Beijing Time)",
        placeholder="2026-05-15 20:00",
        max_length=16,
    )
    content = discord.ui.TextInput(
        label="Message Content",
        style=discord.TextStyle.paragraph,
        max_length=2000,
    )
    image_url = discord.ui.TextInput(
        label="Image URL (optional)",
        required=False,
        max_length=500,
    )

    def __init__(self, channel_id: int):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        dt = parse_time(self.send_time.value)
        if dt is None:
            await interaction.response.send_message(
                "❌ Invalid time format. Use `YYYY-MM-DD HH:MM` (e.g. `2026-05-15 20:00`)",
                ephemeral=True,
            )
            return

        url = self.image_url.value.strip() or None
        msg = {
            "id": str(uuid.uuid4()),
            "channel_id": self.channel_id,
            "send_at": dt.isoformat(),
            "content": self.content.value,
            "image_url": url,
        }
        messages = load_messages()
        messages.append(msg)
        save_messages(messages)

        channel = interaction.guild.get_channel(self.channel_id)
        ch_mention = channel.mention if channel else f"<#{self.channel_id}>"
        preview = (
            f"✅ Scheduled for **{dt.strftime('%Y-%m-%d %H:%M')}** (Beijing Time) in {ch_mention}\n\n"
            f"**Preview:**\n{self.content.value}"
        )
        if url:
            preview += f"\n{url}"
        await interaction.response.send_message(preview, ephemeral=True)


class ChannelSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Select a channel...",
        channel_types=[discord.ChannelType.text],
    )
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.send_modal(ScheduleModal(select.values[0].id))


class SchedulerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="schedule", description="Schedule a message to a channel")
    async def schedule(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Select the channel to post in:", view=ChannelSelectView(), ephemeral=True
        )

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
