from __future__ import annotations

from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from app.core.runtime import ProjectRuntime


def parse_color(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().lstrip("#")
    if len(normalized) != 6:
        return None
    try:
        return int(normalized, 16)
    except ValueError:
        return None


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def build_embed(
    *,
    title: str,
    description: str,
    color: int | None,
    image_url: str | None,
    button_label: str | None,
    button_url: str | None,
) -> tuple[discord.Embed, discord.ui.View | None]:
    embed = discord.Embed(title=title, description=description, color=color)
    if image_url:
        embed.set_image(url=image_url)
    if not button_label or not button_url:
        return embed, None
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label=button_label, url=button_url))
    return embed, view


class ManualEmbedCog(commands.Cog):
    def __init__(self, runtime: ProjectRuntime) -> None:
        self.runtime = runtime

    def _is_admin(self, user: discord.Member | discord.User) -> bool:
        role_ids = {getattr(role, "id", None) for role in getattr(user, "roles", ())}
        return bool(role_ids.intersection(self.runtime.config.discord.admin_role_ids))

    @app_commands.command(name="embed", description="Publish an embed message")
    @app_commands.describe(
        channel="The configured channel that should receive the message",
        title="Embed title",
        description="Embed body",
        color="Optional six-digit hex color, such as FF9933",
        image_url="Optional https image URL",
        button_label="Optional link button label",
        button_url="Optional https link button URL",
    )
    async def publish(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        description: str,
        color: str | None = None,
        image_url: str | None = None,
        button_label: str | None = None,
        button_url: str | None = None,
    ) -> None:
        if not self._is_admin(interaction.user):
            await interaction.response.send_message(
                "You are not allowed to use this command.", ephemeral=True
            )
            return
        if channel.id not in self.runtime.config.discord.manual_embed_channel_ids:
            await interaction.response.send_message(
                "That channel is not enabled for embed publishing.", ephemeral=True
            )
            return
        parsed_color = parse_color(color)
        if color is not None and color.strip() and parsed_color is None:
            await interaction.response.send_message(
                "Color must be a six-digit hex value.", ephemeral=True
            )
            return
        if image_url and not _is_http_url(image_url):
            await interaction.response.send_message(
                "Image URL must use http or https.", ephemeral=True
            )
            return
        if bool(button_label) != bool(button_url):
            await interaction.response.send_message(
                "Button label and URL must be used together.", ephemeral=True
            )
            return
        if button_url and not _is_http_url(button_url):
            await interaction.response.send_message(
                "Button URL must use http or https.", ephemeral=True
            )
            return

        embed, view = build_embed(
            title=title,
            description=description,
            color=parsed_color,
            image_url=image_url,
            button_label=button_label,
            button_url=button_url,
        )
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            message = await channel.send(
                embed=embed,
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(
                f"[{self.runtime.config.slug}][manual_embed] publish failed: {exc}",
                flush=True,
            )
            await interaction.edit_original_response(
                content="The embed could not be published. Please check the bot permissions."
            )
            return
        await interaction.edit_original_response(content=f"Published: {message.jump_url}")


async def install(runtime: ProjectRuntime) -> None:
    await runtime.bot.add_cog(ManualEmbedCog(runtime))
