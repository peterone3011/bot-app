from __future__ import annotations

import discord
from discord.ext import commands

from app.core.config import ReactionRule
from app.core.runtime import ProjectRuntime


class AutoReactionCog(commands.Cog):
    def __init__(self, runtime: ProjectRuntime) -> None:
        self.runtime = runtime
        self._rules_by_channel: dict[int, list[ReactionRule]] = {}
        for rule in runtime.config.auto_reactions:
            self._rules_by_channel.setdefault(rule.channel_id, []).append(rule)

    def _is_enabled_rule(self, rule: ReactionRule) -> bool:
        exclusive_channel = self.runtime.config.channels.exclusive_updates
        if rule.channel_id == exclusive_channel:
            return self.runtime.config.features.exclusive_updates_reaction
        return self.runtime.config.features.auto_reaction

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        rules = [
            rule
            for rule in self._rules_by_channel.get(message.channel.id, [])
            if self._is_enabled_rule(rule)
            and (not message.author.bot or rule.include_bot_messages)
        ]
        for rule in rules:
            for emoji in rule.emojis:
                try:
                    await message.add_reaction(emoji)
                except (discord.Forbidden, discord.HTTPException, TypeError, ValueError) as exc:
                    print(
                        f"[{self.runtime.config.slug}][auto_reaction] "
                        f"channel={message.channel.id} emoji={emoji!r} failed: {exc}",
                        flush=True,
                    )


async def install(runtime: ProjectRuntime) -> None:
    await runtime.bot.add_cog(AutoReactionCog(runtime))
