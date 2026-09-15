from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.cogs import manual_embed
from app.cogs.manual_embed import ManualEmbedCog, build_embed, parse_color
from app.core.config import ChannelConfig, DiscordConfig, FeatureFlags, ProjectConfig
from app.core.runtime import ProjectRuntime
from app.core.state import ProjectState


def runtime() -> ProjectRuntime:
    config = ProjectConfig(
        slug="alpha",
        brand_name="Alpha",
        discord=DiscordConfig(
            token="token",
            guild_id=101,
            admin_role_ids=(500,),
            manual_embed_channel_ids=(600,),
        ),
        features=FeatureFlags(True, False, False, False, False, False),
        channels=ChannelConfig(None, None, None, None),
        role_selector=None,
        auto_reactions=(),
        feishu=None,
    )
    return ProjectRuntime(config, SimpleNamespace(), ProjectState(__import__("pathlib").Path("/tmp"), "alpha"), None)


def interaction(role_ids: tuple[int, ...]) -> SimpleNamespace:
    return SimpleNamespace(
        user=SimpleNamespace(roles=[SimpleNamespace(id=role_id) for role_id in role_ids]),
        response=SimpleNamespace(
            send_message=AsyncMock(),
            defer=AsyncMock(),
            is_done=lambda: False,
        ),
        edit_original_response=AsyncMock(),
    )


def test_parse_color_accepts_optional_hex_and_rejects_bad_values() -> None:
    assert parse_color(None) is None
    assert parse_color("#FF9933") == 0xFF9933
    assert parse_color("not-a-color") is None


def test_build_embed_adds_optional_image_and_button() -> None:
    embed, view = build_embed(
        title="Welcome",
        description="Hello",
        color=0xFF9933,
        image_url="https://example.com/image.png",
        button_label="Claim",
        button_url="https://example.com/claim",
    )

    assert embed.title == "Welcome"
    assert embed.color.value == 0xFF9933
    assert embed.image.url == "https://example.com/image.png"
    assert view is not None
    assert view.children[0].label == "Claim"


@pytest.mark.asyncio
async def test_embed_command_rejects_unconfigured_admin_role() -> None:
    cog = ManualEmbedCog(runtime())
    call = interaction(())
    channel = SimpleNamespace(id=600)

    await cog.publish.callback(cog, call, channel, "Title", "Body", None, None, None, None)

    call.response.send_message.assert_awaited_once_with(
        "You are not allowed to use this command.", ephemeral=True
    )


@pytest.mark.asyncio
async def test_embed_command_sends_to_allowlisted_channel() -> None:
    cog = ManualEmbedCog(runtime())
    call = interaction((500,))
    message = SimpleNamespace(jump_url="https://discord.com/channels/101/600/1")
    channel = SimpleNamespace(id=600, send=AsyncMock(return_value=message))

    await cog.publish.callback(
        cog,
        call,
        channel,
        "Title",
        "Body",
        "FF9933",
        None,
        "Open",
        "https://example.com",
    )

    call.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    sent_embed = channel.send.await_args.kwargs["embed"]
    assert sent_embed.title == "Title"
    assert channel.send.await_args.kwargs["view"].children[0].label == "Open"
    call.edit_original_response.assert_awaited_once_with(
        content="Published: https://discord.com/channels/101/600/1"
    )


@pytest.mark.asyncio
async def test_embed_command_allows_any_channel_when_the_allowlist_is_empty() -> None:
    active = runtime()
    active = ProjectRuntime(
        replace(
            active.config,
            discord=replace(active.config.discord, manual_embed_channel_ids=()),
        ),
        active.bot,
        active.state,
        active.feishu,
    )
    cog = ManualEmbedCog(active)
    call = interaction((500,))
    message = SimpleNamespace(jump_url="https://discord.com/channels/101/601/1")
    channel = SimpleNamespace(id=601, send=AsyncMock(return_value=message))

    await cog.publish.callback(cog, call, channel, "Title", "Body", None, None, None, None)

    channel.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_install_uses_the_project_scoped_embed_builder(monkeypatch) -> None:
    shared_install = AsyncMock()
    monkeypatch.setattr(manual_embed, "install_shared_embed_builder", shared_install)
    active = runtime()

    await manual_embed.install(active)

    shared_install.assert_awaited_once_with(active)
