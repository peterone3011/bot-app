from __future__ import annotations

from typing import Iterable

import discord
from discord.ext import commands

from app.core.runtime import ProjectRuntime


def _option_value(option) -> str:
    if option.role_id is not None:
        return str(option.role_id)
    return f"name:{option.role_name}"


def selector_custom_ids(runtime: ProjectRuntime) -> set[str]:
    config = runtime.config.role_selector
    if config is None:
        return set()
    return {f"roles:{runtime.config.slug}", *config.adopt_custom_ids}


def _option_by_value(runtime: ProjectRuntime, selected: str):
    config = runtime.config.role_selector
    if config is None:
        return None
    return next(
        (
            option
            for option in config.options
            if _option_value(option) == selected
        ),
        None,
    )


async def handle_selection(
    runtime: ProjectRuntime,
    interaction: discord.Interaction,
    selected: int | str,
) -> None:
    option = _option_by_value(runtime, str(selected))
    if option is None:
        await interaction.followup.send(
            "This notification role is unavailable. Please contact an admin.",
            ephemeral=True,
        )
        return
    guild = interaction.guild
    if option.role_id is not None:
        role = guild.get_role(option.role_id) if guild else None
        configured_target = f"id={option.role_id}"
    else:
        role = discord.utils.get(guild.roles, name=option.role_name) if guild else None
        configured_target = f"name={option.role_name!r}"
    if role is None:
        print(
            f"[{runtime.config.slug}][role_selector] configured role missing {configured_target}",
            flush=True,
        )
        await interaction.followup.send(
            "This notification role is unavailable. Please contact an admin.",
            ephemeral=True,
        )
        return
    member = interaction.user
    if role in member.roles:
        await member.remove_roles(role, reason="notification role opt-out")
        await interaction.followup.send(
            f"Unsubscribed from **{option.label}**.", ephemeral=True
        )
        return
    await member.add_roles(role, reason="notification role opt-in")
    await interaction.followup.send(
        f"Subscribed to **{option.label}**!", ephemeral=True
    )


class RoleSelector(discord.ui.Select):
    def __init__(self, runtime: ProjectRuntime) -> None:
        config = runtime.config.role_selector
        if config is None:
            raise ValueError("role selector requires role_selector configuration")
        super().__init__(
            placeholder=config.title,
            min_values=1,
            max_values=1,
            custom_id=f"roles:{runtime.config.slug}",
            options=[
                discord.SelectOption(
                    label=option.label,
                    value=_option_value(option),
                    description=option.description,
                )
                for option in config.options
            ],
        )
        self.runtime = runtime

    async def callback(self, interaction: discord.Interaction) -> None:
        # Re-rendering clears Discord's selected value, so the same role can be
        # selected again immediately to unsubscribe.
        await interaction.response.edit_message(view=RoleSelectorView(self.runtime))
        await handle_selection(self.runtime, interaction, self.values[0])


class RoleSelectorView(discord.ui.View):
    def __init__(self, runtime: ProjectRuntime) -> None:
        super().__init__(timeout=None)
        self.add_item(RoleSelector(runtime))


def _message_has_custom_id(message: discord.Message, custom_id: str) -> bool:
    for row in message.components:
        for component in row.children:
            if getattr(component, "custom_id", None) == custom_id:
                return True
    return False


class RoleSelectorCog(commands.Cog):
    def __init__(self, runtime: ProjectRuntime) -> None:
        self.runtime = runtime
        self.bot = runtime.bot
        self.view = RoleSelectorView(runtime)
        self.bot.add_view(self.view)

    async def _channel(self) -> discord.TextChannel | None:
        channel_id = self.runtime.config.channels.roles
        if channel_id is not None:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    return None
            return channel if isinstance(channel, discord.TextChannel) else None

        channel_name = self.runtime.config.channels.roles_name
        guild = self.bot.get_guild(self.runtime.config.discord.guild_id)
        if channel_name is None or guild is None:
            return None
        return discord.utils.get(guild.text_channels, name=channel_name)

    async def ensure_message(self) -> None:
        channel = await self._channel()
        if channel is None:
            print(
                f"[{self.runtime.config.slug}][role_selector] configured channel unavailable",
                flush=True,
            )
            return
        custom_ids = selector_custom_ids(self.runtime)
        existing: discord.Message | None = None
        async for message in channel.history(limit=100):
            if message.author.id == self.bot.user.id and any(
                _message_has_custom_id(message, custom_id) for custom_id in custom_ids
            ):
                existing = message
                break
        config = self.runtime.config.role_selector
        if config is None:
            return
        embed = discord.Embed(
            title=config.title,
            description=config.description or None,
            color=0x9B59B6,
        )
        try:
            if existing:
                await existing.edit(embed=embed, view=RoleSelectorView(self.runtime))
            else:
                await channel.send(embed=embed, view=RoleSelectorView(self.runtime))
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(
                f"[{self.runtime.config.slug}][role_selector] unable to update selector: {exc}",
                flush=True,
            )

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self.ensure_message()


async def install(runtime: ProjectRuntime) -> None:
    await runtime.bot.add_cog(RoleSelectorCog(runtime))
