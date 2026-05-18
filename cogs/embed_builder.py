from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

MESSAGES_FILE = Path("messages.json")
CST = timezone(timedelta(hours=8))


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def load_messages() -> list[dict[str, Any]]:
    try:
        return json.loads(MESSAGES_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


def save_messages(messages: list[dict[str, Any]]) -> None:
    MESSAGES_FILE.write_text(
        json.dumps(messages, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_message(msg_id: str) -> dict[str, Any] | None:
    return next((m for m in load_messages() if m["id"] == msg_id), None)


def upsert_message(msg: dict[str, Any]) -> None:
    messages = load_messages()
    for i, m in enumerate(messages):
        if m["id"] == msg["id"]:
            messages[i] = msg
            save_messages(messages)
            return
    messages.append(msg)
    save_messages(messages)


def delete_message(msg_id: str) -> None:
    save_messages([m for m in load_messages() if m["id"] != msg_id])


def new_draft(channel_id: int, label: str | None = None) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "status": "draft",
        "label": label,
        "created_at": datetime.now(CST).isoformat(),
        "channel_id": channel_id,
        "send_at": None,
        "message_id": None,
        "title": None,
        "description": None,
        "footer": None,
        "image_url": None,
        "button_label": None,
        "button_url": None,
        "color": None,
    }


# ---------------------------------------------------------------------------
# Parsing utilities
# ---------------------------------------------------------------------------

def parse_color(value: str) -> int | None:
    """Returns color int, None for empty input, -1 for invalid."""
    value = value.strip().lstrip("#")
    if not value:
        return None
    if len(value) != 6:
        return -1
    try:
        return int(value, 16)
    except ValueError:
        return -1


def parse_send_at(value: str) -> str | None:
    """Returns ISO 8601 string (UTC+8) or None if invalid or in the past."""
    try:
        dt = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=CST)
    except ValueError:
        return None
    if dt <= datetime.now(CST):
        return None
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def build_embed(msg: dict[str, Any]) -> discord.Embed:
    embed = discord.Embed(
        title=msg["title"],
        description=msg["description"],
        color=msg["color"],
    )
    if msg["footer"]:
        embed.set_footer(text=msg["footer"])
    if msg["image_url"]:
        embed.set_image(url=msg["image_url"])
    return embed


def build_view(msg: dict[str, Any]) -> discord.ui.View | None:
    if not (msg["button_label"] and msg["button_url"]):
        return None
    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label=msg["button_label"],
        url=msg["button_url"],
        style=discord.ButtonStyle.link,
    ))
    return view


def display_label(msg: dict[str, Any], bot: commands.Bot | None) -> str:
    if msg.get("label"):
        return msg["label"]
    if bot:
        ch = bot.get_channel(msg["channel_id"])
        ch_name = f"#{ch.name}" if ch else f"#{msg['channel_id']}"
    else:
        ch_name = f"#{msg['channel_id']}"
    date = (msg.get("created_at") or "")[:10]
    title = msg.get("title") or ""
    preview = (title[:20] + "…") if len(title) > 20 else (title or "(untitled)")
    return f"{ch_name} · {date} · \"{preview}\""


# ---------------------------------------------------------------------------
# Content formatters
# ---------------------------------------------------------------------------

def _field_summary(msg: dict[str, Any]) -> str:
    color_val = msg["color"]
    color_str = f"#{color_val:06X}" if color_val is not None else "(none)"
    desc = msg["description"] or ""
    desc_preview = (desc[:50] + "…") if len(desc) > 50 else (desc or "(none)")
    btn = f"{msg['button_label']} | {msg['button_url']}" if (msg["button_label"] and msg["button_url"]) else "(none)"
    return "\n".join([
        f"Title:       {msg['title'] or '(none)'}",
        f"Description: {desc_preview}",
        f"Footer:      {msg['footer'] or '(none)'}",
        f"Image:       {'set' if msg['image_url'] else '(none)'}",
        f"Button:      {btn}",
        f"Color:       {color_str}",
    ])


def format_builder_content(msg: dict[str, Any]) -> str:
    status = "Scheduled" if msg["status"] == "scheduled" else "Draft"
    send_time = ""
    if msg["send_at"]:
        send_time = " · " + msg["send_at"][:16].replace("T", " ")
    header = f"**{msg.get('label') or '(untitled)'}**  |  <#{msg['channel_id']}>  |  {status}{send_time}"
    return f"{header}\n\n```\n{_field_summary(msg)}\n```"


def format_edit_fields_content(msg: dict[str, Any]) -> str:
    return f"**Edit Fields** — click a field to update it\n\n```\n{_field_summary(msg)}\n```"


def parse_message_link(link: str) -> tuple[int, int] | None:
    """Returns (channel_id, message_id) from a Discord message URL, or None."""
    match = re.search(r"channels/\d+/(\d+)/(\d+)", link)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def draft_from_message(message: discord.Message) -> dict[str, Any]:
    embed = message.embeds[0] if message.embeds else None
    button_label = None
    button_url = None
    for row in message.components:
        for component in row.children:
            if getattr(component, "url", None):
                button_label = component.label
                button_url = component.url
                break

    draft = new_draft(message.channel.id)
    if embed:
        draft["title"] = embed.title or None
        draft["description"] = embed.description or None
        draft["footer"] = embed.footer.text if embed.footer else None
        draft["image_url"] = embed.image.url if embed.image else None
        draft["color"] = embed.color.value if embed.color else None
    draft["button_label"] = button_label
    draft["button_url"] = button_url
    draft["message_id"] = message.id
    return draft


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------

class TitleModal(discord.ui.Modal, title="Update Title"):
    value_input = discord.ui.TextInput(
        label="Title",
        max_length=256,
        required=False,
        placeholder="Leave blank to clear",
    )

    def __init__(self, msg_id: str):
        super().__init__()
        self.msg_id = msg_id

    async def on_submit(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        msg["title"] = self.value_input.value.strip() or None
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_edit_fields_content(msg),
            view=EditFieldsView(self.msg_id),
        )


class DescriptionModal(discord.ui.Modal, title="Update Description"):
    value_input = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=False,
        placeholder="Leave blank to clear",
    )

    def __init__(self, msg_id: str):
        super().__init__()
        self.msg_id = msg_id

    async def on_submit(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        msg["description"] = self.value_input.value.strip() or None
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_edit_fields_content(msg),
            view=EditFieldsView(self.msg_id),
        )


class FooterModal(discord.ui.Modal, title="Update Footer"):
    value_input = discord.ui.TextInput(
        label="Footer",
        max_length=2048,
        required=False,
        placeholder="Leave blank to clear",
    )

    def __init__(self, msg_id: str):
        super().__init__()
        self.msg_id = msg_id

    async def on_submit(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        msg["footer"] = self.value_input.value.strip() or None
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_edit_fields_content(msg),
            view=EditFieldsView(self.msg_id),
        )


class ImageModal(discord.ui.Modal, title="Update Image URL"):
    value_input = discord.ui.TextInput(
        label="Image URL",
        required=False,
        placeholder="Leave blank to clear",
    )

    def __init__(self, msg_id: str):
        super().__init__()
        self.msg_id = msg_id

    async def on_submit(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        msg["image_url"] = self.value_input.value.strip() or None
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_edit_fields_content(msg),
            view=EditFieldsView(self.msg_id),
        )


class LinkButtonModal(discord.ui.Modal, title="Update Link Button"):
    label_input = discord.ui.TextInput(
        label="Button Label",
        max_length=80,
        required=False,
        placeholder="Leave blank to remove button",
    )
    url_input = discord.ui.TextInput(
        label="Button URL",
        required=False,
        placeholder="https://...",
    )

    def __init__(self, msg_id: str):
        super().__init__()
        self.msg_id = msg_id

    async def on_submit(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        msg["button_label"] = self.label_input.value.strip() or None
        msg["button_url"] = self.url_input.value.strip() or None
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_edit_fields_content(msg),
            view=EditFieldsView(self.msg_id),
        )


class ColorModal(discord.ui.Modal, title="Update Color"):
    value_input = discord.ui.TextInput(
        label="Hex Color (e.g. 9B59B6)",
        max_length=7,
        required=False,
        placeholder="Leave blank to clear",
    )

    def __init__(self, msg_id: str):
        super().__init__()
        self.msg_id = msg_id

    async def on_submit(self, interaction: discord.Interaction):
        result = parse_color(self.value_input.value)
        if result == -1:
            await interaction.response.send_message(
                content="❌ Invalid hex color. Use 6 hex digits, e.g. `9B59B6` or `#FF0000`.",
                ephemeral=True,
            )
            return
        msg = get_message(self.msg_id)
        msg["color"] = result
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_edit_fields_content(msg),
            view=EditFieldsView(self.msg_id),
        )


class ScheduleModal(discord.ui.Modal, title="Set Send Time"):
    time_input = discord.ui.TextInput(
        label="Send time (Beijing time, UTC+8)",
        placeholder="YYYY-MM-DD HH:MM",
        max_length=16,
    )

    def __init__(self, msg_id: str):
        super().__init__()
        self.msg_id = msg_id

    async def on_submit(self, interaction: discord.Interaction):
        send_at = parse_send_at(self.time_input.value)
        if send_at is None:
            await interaction.response.send_message(
                content="❌ Invalid or past time. Use format `YYYY-MM-DD HH:MM` (Beijing time).",
                ephemeral=True,
            )
            return
        msg = get_message(self.msg_id)
        msg["status"] = "scheduled"
        msg["send_at"] = send_at
        upsert_message(msg)
        display_time = send_at[:16].replace("T", " ")
        await interaction.response.edit_message(
            content=f"✅ Scheduled for **{display_time}** (UTC+8)\n\n{format_builder_content(msg)}",
            view=BuilderMainView(self.msg_id),
        )


class NewMessageModal(discord.ui.Modal, title="New Message"):
    label_input = discord.ui.TextInput(
        label="Label (optional)",
        placeholder='e.g. "May Announcement" — leave blank for auto label',
        required=False,
        max_length=100,
    )

    def __init__(self, channel_id: int):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        label = self.label_input.value.strip() or None
        msg = new_draft(self.channel_id, label)
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_builder_content(msg),
            view=BuilderMainView(msg["id"]),
        )


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------

class SendNowButton(discord.ui.Button):
    def __init__(self, msg_id: str):
        super().__init__(label="Send Now", style=discord.ButtonStyle.success)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        channel = interaction.guild.get_channel(msg["channel_id"])
        if channel is None:
            await interaction.response.send_message(
                content="❌ Target channel not found.", ephemeral=True
            )
            return
        try:
            await channel.send(embed=build_embed(msg), view=build_view(msg))
            delete_message(self.msg_id)
            await interaction.response.edit_message(
                content=f"✅ Sent to {channel.mention}.", view=None
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                content=f"❌ Bot doesn't have permission to post in {channel.mention}.",
                ephemeral=True,
            )


class ScheduleButton(discord.ui.Button):
    def __init__(self, msg_id: str, label: str = "Schedule"):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ScheduleModal(self.msg_id))


class CancelScheduleButton(discord.ui.Button):
    def __init__(self, msg_id: str):
        super().__init__(label="Cancel Schedule", style=discord.ButtonStyle.danger)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        msg["status"] = "draft"
        msg["send_at"] = None
        upsert_message(msg)
        await interaction.response.edit_message(
            content=format_builder_content(msg),
            view=BuilderMainView(self.msg_id),
        )


class BackToBuilderButton(discord.ui.Button):
    def __init__(self, msg_id: str):
        super().__init__(label="← Back", style=discord.ButtonStyle.secondary, row=1)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        msg = get_message(self.msg_id)
        await interaction.response.edit_message(
            content=format_builder_content(msg),
            view=BuilderMainView(self.msg_id),
        )


class SaveChangesButton(discord.ui.Button):
    def __init__(self, msg_id: str):
        super().__init__(label="Save Changes", style=discord.ButtonStyle.success)
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        draft = get_message(self.msg_id)
        channel = interaction.guild.get_channel(draft["channel_id"])
        if channel is None:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return
        try:
            original = await channel.fetch_message(draft["message_id"])
            await original.edit(embed=build_embed(draft), view=build_view(draft))
            delete_message(self.msg_id)
            await interaction.response.edit_message(
                content=f"✅ Embed updated in {channel.mention}.", view=None
            )
        except discord.NotFound:
            await interaction.response.send_message(
                "❌ Original message not found (may have been deleted).", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Bot lacks permission to edit that message.", ephemeral=True
            )


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class EditFieldsView(discord.ui.View):
    def __init__(self, msg_id: str):
        super().__init__(timeout=600)
        self.msg_id = msg_id

    @discord.ui.button(label="Title", style=discord.ButtonStyle.secondary, row=0)
    async def title_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TitleModal(self.msg_id))

    @discord.ui.button(label="Description", style=discord.ButtonStyle.secondary, row=0)
    async def desc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DescriptionModal(self.msg_id))

    @discord.ui.button(label="Footer", style=discord.ButtonStyle.secondary, row=0)
    async def footer_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FooterModal(self.msg_id))

    @discord.ui.button(label="Image URL", style=discord.ButtonStyle.secondary, row=1)
    async def image_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImageModal(self.msg_id))

    @discord.ui.button(label="Link Button", style=discord.ButtonStyle.secondary, row=1)
    async def link_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LinkButtonModal(self.msg_id))

    @discord.ui.button(label="Color", style=discord.ButtonStyle.secondary, row=1)
    async def color_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self.msg_id))

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.primary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg = get_message(self.msg_id)
        await interaction.response.edit_message(
            content=format_builder_content(msg),
            view=BuilderMainView(self.msg_id),
        )


class BuilderMainView(discord.ui.View):
    def __init__(self, msg_id: str):
        super().__init__(timeout=600)
        self.msg_id = msg_id

    @discord.ui.button(label="Edit Fields", style=discord.ButtonStyle.primary)
    async def edit_fields(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg = get_message(self.msg_id)
        await interaction.response.edit_message(
            content=format_edit_fields_content(msg),
            view=EditFieldsView(self.msg_id),
        )

    @discord.ui.button(label="Overview", style=discord.ButtonStyle.secondary)
    async def overview(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg = get_message(self.msg_id)
        await interaction.response.send_message(
            embed=build_embed(msg),
            view=build_view(msg),
            ephemeral=True,
        )

    @discord.ui.button(label="Send", style=discord.ButtonStyle.success)
    async def send_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg = get_message(self.msg_id)
        await interaction.response.edit_message(
            content="**When to send?**",
            view=SendView(self.msg_id),
        )


class SendView(discord.ui.View):
    def __init__(self, msg_id: str):
        super().__init__(timeout=600)
        msg = get_message(msg_id)
        is_edit = bool(msg and msg.get("message_id"))
        is_scheduled = msg and msg["status"] == "scheduled"

        if is_edit:
            self.add_item(SaveChangesButton(msg_id))
        else:
            self.add_item(SendNowButton(msg_id))
            if is_scheduled:
                self.add_item(ScheduleButton(msg_id, label="Update Schedule"))
                self.add_item(CancelScheduleButton(msg_id))
            else:
                self.add_item(ScheduleButton(msg_id))
        self.add_item(BackToBuilderButton(msg_id))


class NewMessageChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="Select target channel...",
            channel_types=[discord.ChannelType.text],
        )

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        await interaction.response.send_modal(NewMessageModal(channel.id))


class NewMessageView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(NewMessageChannelSelect())


class MessageSelect(discord.ui.Select):
    def __init__(self, messages: list[dict[str, Any]], bot: commands.Bot):
        options = []
        for msg in messages[:25]:
            label = display_label(msg, bot)[:100]
            emoji = "📅" if msg["status"] == "scheduled" else "📝"
            options.append(discord.SelectOption(label=label, value=msg["id"], emoji=emoji))
        super().__init__(placeholder="Select a message to edit...", options=options)

    async def callback(self, interaction: discord.Interaction):
        msg = get_message(self.values[0])
        await interaction.response.edit_message(
            content=format_builder_content(msg),
            view=BuilderMainView(self.values[0]),
        )


class MessageListView(discord.ui.View):
    def __init__(self, messages: list[dict[str, Any]], bot: commands.Bot):
        super().__init__(timeout=300)
        self.add_item(MessageSelect(messages, bot))

    @discord.ui.button(label="+ New Message", style=discord.ButtonStyle.primary, row=1)
    async def new_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Select the channel to post in:",
            view=NewMessageView(),
        )


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class EmbedBuilderCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.send_loop.start()

    def cog_unload(self):
        self.send_loop.cancel()

    @tasks.loop(seconds=60)
    async def send_loop(self):
        now = datetime.now(CST)
        for msg in list(load_messages()):
            if msg["status"] != "scheduled":
                continue
            if datetime.fromisoformat(msg["send_at"]) > now:
                continue
            channel = self.bot.get_channel(msg["channel_id"])
            if channel is None:
                print(f"[embed_builder] Channel {msg['channel_id']} not found, removing {msg['id']}")
                delete_message(msg["id"])
                continue
            try:
                await channel.send(embed=build_embed(msg), view=build_view(msg))
                delete_message(msg["id"])
            except Exception as e:
                print(f"[embed_builder] Failed to send {msg['id']}: {e}")

    @send_loop.before_loop
    async def before_send_loop(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="embed", description="Build and send a rich embed message")
    @app_commands.guild_only()
    async def embed_cmd(self, interaction: discord.Interaction):
        messages = sorted(
            load_messages(),
            key=lambda m: (m["status"] != "scheduled", m.get("send_at") or m.get("created_at", "")),
        )
        if messages:
            await interaction.response.send_message(
                content="Select a message to edit, or create a new one:",
                view=MessageListView(messages, self.bot),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                content="Select the channel to post in:",
                view=NewMessageView(),
                ephemeral=True,
            )

    @app_commands.command(name="edit-embed", description="Edit a published embed by message link")
    @app_commands.guild_only()
    async def edit_embed_cmd(self, interaction: discord.Interaction, message_link: str):
        result = parse_message_link(message_link)
        if result is None:
            await interaction.response.send_message("❌ Invalid message link.", ephemeral=True)
            return
        channel_id, message_id = result
        channel = interaction.guild.get_channel(channel_id)
        if channel is None:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await interaction.response.send_message("❌ Message not found.", ephemeral=True)
            return
        if message.author != self.bot.user:
            await interaction.response.send_message(
                "❌ That message was not sent by this bot.", ephemeral=True
            )
            return
        if not message.embeds:
            await interaction.response.send_message(
                "❌ That message has no embed.", ephemeral=True
            )
            return
        draft = draft_from_message(message)
        upsert_message(draft)
        await interaction.response.send_message(
            content=format_builder_content(draft),
            view=BuilderMainView(draft["id"]),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    cog = EmbedBuilderCog(bot)
    await bot.add_cog(cog)

    @app_commands.context_menu(name="Edit Embed")
    @app_commands.guild_only()
    async def edit_embed_menu(interaction: discord.Interaction, message: discord.Message):
        if message.author != bot.user:
            await interaction.response.send_message(
                "❌ That message was not sent by this bot.", ephemeral=True
            )
            return
        if not message.embeds:
            await interaction.response.send_message(
                "❌ That message has no embed.", ephemeral=True
            )
            return
        draft = draft_from_message(message)
        upsert_message(draft)
        await interaction.response.send_message(
            content=format_builder_content(draft),
            view=BuilderMainView(draft["id"]),
            ephemeral=True,
        )

    bot.tree.add_command(edit_embed_menu)
