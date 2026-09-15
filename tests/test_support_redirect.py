from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from cogs.support_redirect import (
    SupportRedirectConfig,
    SupportRedirectCog,
    build_support_embed,
    is_financial_support_issue,
    normalize_message,
)


@pytest.mark.parametrize(
    "content",
    [
        "How do I withdraw?",
        "My WITHDRAWAL is still processing",
        "cash-out help please",
        "cashout",
        "I need to redeem SC",
        "redemption problem",
        "my deposit did not arrive",
        "Where is my refund?",
        "payment issue",
        "payment failed again",
        "my card was charged twice",
        "duplicate charge",
        "money missing from my balance",
        "funds not received",
    ],
)
def test_financial_messages_match(content: str) -> None:
    assert is_financial_support_issue(content) is True


@pytest.mark.parametrize(
    "content",
    [
        "pending",
        "missing",
        "failed",
        "bonus missing",
        "reward missing",
        "the game is not loading",
        "I cannot log in",
        "verification pending",
        "what is your favorite game?",
    ],
)
def test_non_financial_messages_do_not_match(content: str) -> None:
    assert is_financial_support_issue(content) is False


def test_normalization_handles_punctuation_and_spaces() -> None:
    assert normalize_message("  CASH--OUT!!!  pending ") == "cash out pending"


def test_config_parses_enabled_channel_list_and_cooldown() -> None:
    config = SupportRedirectConfig.from_env(
        {
            "SUPPORT_REDIRECT_ENABLED": "1",
            "SUPPORT_TRIGGER_CHANNEL_IDS": "1546766591096787026,1546766625209065492",
            "SUPPORT_CHANNEL_ID": "1509148079566225480",
            "SUPPORT_REDIRECT_COOLDOWN_SECONDS": "600",
        }
    )
    assert config.enabled is True
    assert config.trigger_channel_ids == frozenset(
        {1546766591096787026, 1546766625209065492}
    )
    assert config.support_channel_id == 1509148079566225480
    assert config.cooldown_seconds == 600


@pytest.mark.parametrize(
    "overrides",
    [
        {"SUPPORT_TRIGGER_CHANNEL_IDS": ""},
        {"SUPPORT_TRIGGER_CHANNEL_IDS": "not-a-channel"},
        {"SUPPORT_CHANNEL_ID": "0"},
        {"SUPPORT_REDIRECT_COOLDOWN_SECONDS": "-1"},
    ],
)
def test_enabled_config_rejects_invalid_values(overrides: dict[str, str]) -> None:
    environ = {
        "SUPPORT_REDIRECT_ENABLED": "1",
        "SUPPORT_TRIGGER_CHANNEL_IDS": "1546766591096787026",
        "SUPPORT_CHANNEL_ID": "1509148079566225480",
        "SUPPORT_REDIRECT_COOLDOWN_SECONDS": "600",
    }
    environ.update(overrides)
    with pytest.raises(ValueError):
        SupportRedirectConfig.from_env(environ)


def make_message(
    *,
    content: str = "withdrawal pending",
    channel_id: int = 101,
    user_id: int = 202,
    bot: bool = False,
):
    return SimpleNamespace(
        id=303,
        content=content,
        guild=SimpleNamespace(id=404),
        channel=SimpleNamespace(id=channel_id),
        author=SimpleNamespace(id=user_id, bot=bot),
        reply=AsyncMock(),
    )


def enabled_config() -> SupportRedirectConfig:
    return SupportRedirectConfig(True, frozenset({101, 102, 103}), 505, 600)


def test_support_embed_contains_approved_copy() -> None:
    embed = build_support_embed(505)
    assert embed.title == "⚠️ Discord cannot handle order-related issues"
    assert embed.color.value == 0xED4245
    assert "deposit, withdrawal, or refund issues" in embed.description
    assert "<#505>" in embed.description
    assert "queue" not in embed.description.casefold()
    assert "reward" not in embed.description.casefold()


@pytest.mark.asyncio
async def test_listener_replies_without_mentions() -> None:
    message = make_message()
    cog = SupportRedirectCog(SimpleNamespace(), enabled_config(), clock=lambda: 1000.0)
    await cog.on_message(message)
    message.reply.assert_awaited_once()
    kwargs = message.reply.await_args.kwargs
    assert kwargs["mention_author"] is False
    assert kwargs["embed"].title == "⚠️ Discord cannot handle order-related issues"
    assert kwargs["allowed_mentions"].everyone is False
    assert kwargs["allowed_mentions"].roles is False
    assert kwargs["allowed_mentions"].users is False


@pytest.mark.asyncio
async def test_listener_ignores_bots_unlisted_channels_and_nonmatches() -> None:
    cog = SupportRedirectCog(SimpleNamespace(), enabled_config(), clock=lambda: 1000.0)
    messages = [
        make_message(bot=True),
        make_message(channel_id=999),
        make_message(content="reward missing"),
    ]
    for message in messages:
        await cog.on_message(message)
        message.reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_cooldown_is_per_user_and_channel() -> None:
    now = [1000.0]
    cog = SupportRedirectCog(SimpleNamespace(), enabled_config(), clock=lambda: now[0])
    first = make_message()
    repeated = make_message()
    other_user = make_message(user_id=203)
    other_channel = make_message(channel_id=102)
    await cog.on_message(first)
    await cog.on_message(repeated)
    await cog.on_message(other_user)
    await cog.on_message(other_channel)
    first.reply.assert_awaited_once()
    repeated.reply.assert_not_awaited()
    other_user.reply.assert_awaited_once()
    other_channel.reply.assert_awaited_once()
    now[0] += 601
    await cog.on_message(repeated)
    repeated.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_reply_does_not_start_cooldown() -> None:
    message = make_message()
    message.reply.side_effect = [RuntimeError("network"), None]
    cog = SupportRedirectCog(SimpleNamespace(), enabled_config(), clock=lambda: 1000.0)
    await cog.on_message(message)
    await cog.on_message(message)
    assert message.reply.await_count == 2


@pytest.mark.asyncio
async def test_concurrent_messages_from_same_user_reply_once() -> None:
    reply_started = asyncio.Event()
    release_reply = asyncio.Event()

    async def slow_reply(**_kwargs) -> None:
        reply_started.set()
        await release_reply.wait()

    first = make_message()
    second = make_message()
    first.reply.side_effect = slow_reply
    cog = SupportRedirectCog(SimpleNamespace(), enabled_config(), clock=lambda: 1000.0)

    first_task = asyncio.create_task(cog.on_message(first))
    await reply_started.wait()
    second_task = asyncio.create_task(cog.on_message(second))
    await asyncio.sleep(0)
    release_reply.set()
    await asyncio.gather(first_task, second_task)

    first.reply.assert_awaited_once()
    second.reply.assert_not_awaited()


def test_shared_entrypoint_does_not_load_retired_support_redirect_extension() -> None:
    bot_source = Path("bot.py").read_text(encoding="utf-8")
    assert 'await bot.load_extension("cogs.support_redirect")' not in bot_source
    assert "from app.runner import main" in bot_source
