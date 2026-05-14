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


PER_PAGE = 4


def build_list_embed(messages: list[dict], page: int, guild: discord.Guild) -> discord.Embed:
    total = len(messages)
    start = page * PER_PAGE
    end = min(start + PER_PAGE, total)
    total_pages = max(1, -(-total // PER_PAGE))

    embed = discord.Embed(title="Scheduled Messages", color=0x9B59B6)
    if not messages:
        embed.description = "No scheduled messages."
        return embed

    for i, msg in enumerate(messages[start:end]):
        num = start + i + 1
        channel = guild.get_channel(msg["channel_id"])
        ch_text = channel.mention if channel else f"<#{msg['channel_id']}>"
        dt = datetime.fromisoformat(msg["send_at"])
        preview = msg["content"][:50] + ("…" if len(msg["content"]) > 50 else "")
        embed.add_field(
            name=f"#{num}  {dt.strftime('%Y-%m-%d %H:%M')}  →  {ch_text}",
            value=preview,
            inline=False,
        )

    embed.set_footer(text=f"Page {page + 1}/{total_pages}  ·  {total} total")
    return embed


class PreviewButton(discord.ui.Button):
    def __init__(self, row_idx: int, msg_id: str):
        super().__init__(label="👁 Preview", style=discord.ButtonStyle.secondary, row=row_idx)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        msg = next((m for m in load_messages() if m["id"] == self.msg_id), None)
        if msg is None:
            await interaction.response.send_message("❌ Not found.", ephemeral=True)
            return
        text = msg["content"]
        if msg.get("image_url"):
            text += f"\n{msg['image_url']}"
        await interaction.response.send_message(f"**Preview:**\n{text}", ephemeral=True)


class EditButton(discord.ui.Button):
    def __init__(self, row_idx: int, msg_id: str):
        super().__init__(label="✏️ Edit", style=discord.ButtonStyle.primary, row=row_idx)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EditModal(self.msg_id, self.view))


class ChangeChannelButton(discord.ui.Button):
    def __init__(self, row_idx: int, msg_id: str):
        super().__init__(label="📍 Channel", style=discord.ButtonStyle.secondary, row=row_idx)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Select the new channel:",
            view=ChangeChannelSelectView(self.msg_id, self.view),
            ephemeral=True,
        )


class CancelButton(discord.ui.Button):
    def __init__(self, row_idx: int, msg_id: str):
        super().__init__(label="❌ Cancel", style=discord.ButtonStyle.danger, row=row_idx)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        messages = load_messages()
        new_messages = [m for m in messages if m["id"] != self.msg_id]
        if len(new_messages) == len(messages):
            await interaction.response.send_message("❌ Not found.", ephemeral=True)
            return
        save_messages(new_messages)
        view: ScheduleListView = self.view
        view.messages = new_messages
        if view.page > 0 and view.page * PER_PAGE >= len(new_messages):
            view.page -= 1
        view._build()
        await interaction.response.edit_message(
            embed=build_list_embed(view.messages, view.page, view.guild), view=view
        )


class PrevPageButton(discord.ui.Button):
    def __init__(self, page: int):
        super().__init__(label="◀ Prev", style=discord.ButtonStyle.secondary, row=4)
        self.page = page

    async def callback(self, interaction: discord.Interaction):
        view: ScheduleListView = self.view
        view.page = self.page - 1
        view._build()
        await interaction.response.edit_message(
            embed=build_list_embed(view.messages, view.page, view.guild), view=view
        )


class NextPageButton(discord.ui.Button):
    def __init__(self, page: int):
        super().__init__(label="Next ▶", style=discord.ButtonStyle.secondary, row=4)
        self.page = page

    async def callback(self, interaction: discord.Interaction):
        view: ScheduleListView = self.view
        view.page = self.page + 1
        view._build()
        await interaction.response.edit_message(
            embed=build_list_embed(view.messages, view.page, view.guild), view=view
        )


class ScheduleListView(discord.ui.View):
    def __init__(self, messages: list[dict], guild: discord.Guild, page: int = 0):
        super().__init__(timeout=300)
        self.messages = messages
        self.guild = guild
        self.page = page
        self._build()

    def _build(self):
        self.clear_items()
        start = self.page * PER_PAGE
        end = min(start + PER_PAGE, len(self.messages))
        for i, msg in enumerate(self.messages[start:end]):
            self.add_item(PreviewButton(i, msg["id"]))
            self.add_item(EditButton(i, msg["id"]))
            self.add_item(ChangeChannelButton(i, msg["id"]))
            self.add_item(CancelButton(i, msg["id"]))
        if self.page > 0:
            self.add_item(PrevPageButton(self.page))
        if end < len(self.messages):
            self.add_item(NextPageButton(self.page))


class SchedulerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="schedule", description="Schedule a message to a channel")
    @app_commands.guild_only()
    async def schedule(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Select the channel to post in:", view=ChannelSelectView(), ephemeral=True
        )

    @app_commands.command(name="schedule_list", description="View and manage scheduled messages")
    @app_commands.guild_only()
    async def schedule_list(self, interaction: discord.Interaction):
        messages = sorted(load_messages(), key=lambda m: m["send_at"])
        await interaction.response.send_message(
            embed=build_list_embed(messages, 0, interaction.guild),
            view=ScheduleListView(messages, interaction.guild),
            ephemeral=True,
        )

    def cog_unload(self):
        self.send_loop.cancel()

    async def cog_load(self):
        self.send_loop.start()

    @tasks.loop(seconds=60)
    async def send_loop(self):
        messages = load_messages()
        if not messages:
            return
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
