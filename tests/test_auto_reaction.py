from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.cogs.auto_reaction import AutoReactionCog
from app.core.config import (
    ChannelConfig,
    DiscordConfig,
    FeatureFlags,
    ProjectConfig,
    ReactionRule,
)
from app.core.runtime import ProjectRuntime
from app.core.state import ProjectState


def runtime(*, exclusive_enabled: bool = True, include_bots: bool = True) -> ProjectRuntime:
    config = ProjectConfig(
        slug="alpha",
        brand_name="Alpha",
        discord=DiscordConfig("token", 101, (), ()),
        features=FeatureFlags(False, False, True, exclusive_enabled, False, False),
        channels=ChannelConfig(None, 800, None, None),
        role_selector=None,
        auto_reactions=(
            ReactionRule(700, ("🔥", "🎉"), include_bots),
            ReactionRule(800, ("💜",), True),
        ),
        feishu=None,
    )
    return ProjectRuntime(config, SimpleNamespace(), ProjectState(Path("/tmp"), "alpha"), None)


def message(
    *,
    channel_id: int,
    guild_id: int = 101,
    is_bot: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        guild=SimpleNamespace(id=guild_id),
        channel=SimpleNamespace(id=channel_id),
        author=SimpleNamespace(bot=is_bot),
        add_reaction=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_reacts_in_configured_order() -> None:
    incoming = message(channel_id=700)

    await AutoReactionCog(runtime()).on_message(incoming)

    assert [call.args[0] for call in incoming.add_reaction.await_args_list] == ["🔥", "🎉"]


@pytest.mark.asyncio
async def test_skips_bot_message_when_the_matching_rule_excludes_bots() -> None:
    incoming = message(channel_id=700, is_bot=True)

    await AutoReactionCog(runtime(include_bots=False)).on_message(incoming)

    incoming.add_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_exclusive_updates_rule_can_be_disabled_independently() -> None:
    incoming = message(channel_id=800)

    await AutoReactionCog(runtime(exclusive_enabled=False)).on_message(incoming)

    incoming.add_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_ignores_messages_from_another_guild() -> None:
    incoming = message(channel_id=700, guild_id=999)

    await AutoReactionCog(runtime()).on_message(incoming)

    incoming.add_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_random_rule_chooses_configured_number_without_duplicates(monkeypatch) -> None:
    active = runtime()
    active = ProjectRuntime(
        replace(
            active.config,
            auto_reactions=(
                ReactionRule(
                    700,
                    ("1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"),
                    True,
                    mode="random",
                    random_count=10,
                ),
            ),
        ),
        active.bot,
        active.state,
        active.feishu,
    )
    incoming = message(channel_id=700)
    monkeypatch.setattr("app.cogs.auto_reaction.random.sample", lambda pool, count: list(pool)[1:11])

    await AutoReactionCog(active).on_message(incoming)

    assert [call.args[0] for call in incoming.add_reaction.await_args_list] == [
        "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"
    ]
