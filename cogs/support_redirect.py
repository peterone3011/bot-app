from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Mapping

import discord
from discord.ext import commands


_TRUE_VALUES = {"1", "true", "yes", "on"}
_DIRECT_PATTERNS = (
    re.compile(r"\bwithdraw(?:al|als|ing|n|s)?\b"),
    re.compile(r"\bcash\s*out\b"),
    re.compile(r"\bredeem(?:ed|ing)?\s+sc\b"),
    re.compile(r"\bredemption(?:s)?\b"),
    re.compile(r"\bdeposit(?:ed|ing|s)?\b"),
    re.compile(r"\brefund(?:ed|ing|s)?\b"),
)
_STATUS = r"(?:issue|problem|failed|declined|pending|missing|stuck|delayed|not received)"
_CONTEXT_PATTERNS = (
    re.compile(rf"\bpayment\b.{{0,40}}\b{_STATUS}\b"),
    re.compile(rf"\b{_STATUS}\b.{{0,40}}\bpayment\b"),
    re.compile(rf"\b(?:money|funds)\b.{{0,40}}\b{_STATUS}\b"),
    re.compile(rf"\b{_STATUS}\b.{{0,40}}\b(?:money|funds)\b"),
    re.compile(r"\bcharged\s+(?:twice|double|incorrectly|wrong)\b"),
    re.compile(r"\bduplicate\s+charge\b"),
    re.compile(r"\bwrong\s+amount\s+charged\b"),
)
_TITLE = "⚠️ Discord cannot handle order-related issues"


@dataclass(frozen=True)
class SupportRedirectConfig:
    enabled: bool
    trigger_channel_ids: frozenset[int]
    support_channel_id: int
    cooldown_seconds: int = 600

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "SupportRedirectConfig":
        values = os.environ if environ is None else environ
        enabled = (
            values.get("SUPPORT_REDIRECT_ENABLED", "0").strip().casefold()
            in _TRUE_VALUES
        )
        if not enabled:
            return cls(False, frozenset(), 0, 600)

        try:
            channels = frozenset(
                int(value.strip())
                for value in values.get("SUPPORT_TRIGGER_CHANNEL_IDS", "").split(",")
                if value.strip()
            )
            support_channel_id = int(values.get("SUPPORT_CHANNEL_ID", "0"))
            cooldown_seconds = int(
                values.get("SUPPORT_REDIRECT_COOLDOWN_SECONDS", "600")
            )
        except ValueError as exc:
            raise ValueError(
                "support redirect configuration contains a non-integer value"
            ) from exc

        if not channels or any(channel_id <= 0 for channel_id in channels):
            raise ValueError(
                "SUPPORT_TRIGGER_CHANNEL_IDS must contain positive channel IDs"
            )
        if support_channel_id <= 0:
            raise ValueError("SUPPORT_CHANNEL_ID must be a positive channel ID")
        if cooldown_seconds < 0:
            raise ValueError("SUPPORT_REDIRECT_COOLDOWN_SECONDS cannot be negative")
        return cls(True, channels, support_channel_id, cooldown_seconds)


def normalize_message(content: str) -> str:
    lowered = content.casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", lowered)).strip()


def is_financial_support_issue(content: str) -> bool:
    normalized = normalize_message(content)
    if not normalized:
        return False
    return any(
        pattern.search(normalized)
        for pattern in _DIRECT_PATTERNS + _CONTEXT_PATTERNS
    )


def build_support_embed(support_channel_id: int) -> discord.Embed:
    description = (
        "For any deposit, withdrawal, or refund issues, please contact our live "
        f"support in <#{support_channel_id}>.\n\n"
        "Please fill out the form to start a chat with our support team and "
        "describe your issue clearly."
    )
    return discord.Embed(title=_TITLE, description=description, color=0xED4245)


class SupportRedirectCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        config: SupportRedirectConfig,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.bot = bot
        self.config = config
        self._clock = clock
        self._cooldowns: dict[tuple[int, int, int], float] = {}
        self._inflight: set[tuple[int, int, int]] = set()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if message.channel.id not in self.config.trigger_channel_ids:
            return
        if not is_financial_support_issue(message.content):
            return

        now = self._clock()
        key = (message.guild.id, message.channel.id, message.author.id)
        if key in self._inflight:
            return
        last_reply = self._cooldowns.get(key)
        if (
            last_reply is not None
            and now - last_reply < self.config.cooldown_seconds
        ):
            return

        self._cooldowns = {
            existing_key: timestamp
            for existing_key, timestamp in self._cooldowns.items()
            if now - timestamp < self.config.cooldown_seconds
        }
        self._inflight.add(key)
        try:
            await message.reply(
                embed=build_support_embed(self.config.support_channel_id),
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception as exc:
            print(
                "[support_redirect] Reply failed "
                f"guild={message.guild.id} channel={message.channel.id} "
                f"message={message.id} user={message.author.id}: {exc}",
                flush=True,
            )
            return
        finally:
            self._inflight.discard(key)
        self._cooldowns[key] = now


async def setup(bot: commands.Bot) -> None:
    try:
        config = SupportRedirectConfig.from_env()
    except ValueError as exc:
        print(f"[support_redirect] Disabled: {exc}", flush=True)
        return
    if not config.enabled:
        print("[support_redirect] Disabled by configuration", flush=True)
        return

    await bot.add_cog(SupportRedirectCog(bot, config))
    channels = ",".join(
        str(channel_id) for channel_id in sorted(config.trigger_channel_ids)
    )
    print(
        f"[support_redirect] Enabled channels={channels} "
        f"support_channel={config.support_channel_id} "
        f"cooldown={config.cooldown_seconds}s",
        flush=True,
    )
