from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.config import (
    ChannelConfig,
    DiscordConfig,
    FeatureFlags,
    ProjectConfig,
)
from app import runner


def config(slug: str, guild_id: int) -> ProjectConfig:
    return ProjectConfig(
        slug=slug,
        brand_name=slug.title(),
        discord=DiscordConfig(
            token=f"{slug}-token",
            guild_id=guild_id,
            admin_role_ids=(),
            manual_embed_channel_ids=(),
        ),
        features=FeatureFlags(False, False, False, False, False, False),
        channels=ChannelConfig(None, None, None, None),
        role_selector=None,
        auto_reactions=(),
        feishu=None,
    )


@pytest.mark.asyncio
async def test_sync_project_commands_targets_only_the_project_guild() -> None:
    bot = Mock()
    bot.tree = Mock()
    bot.tree.sync = AsyncMock()

    await runner.sync_project_commands(bot, config("alpha", 101))

    guild = bot.tree.copy_global_to.call_args.kwargs["guild"]
    assert guild.id == 101
    synced_guild = bot.tree.sync.await_args.kwargs["guild"]
    assert synced_guild.id == 101


@pytest.mark.asyncio
async def test_run_enabled_projects_starts_each_project(monkeypatch, tmp_path: Path) -> None:
    started: list[tuple[str, Path]] = []

    monkeypatch.setattr(runner, "enabled_project_slugs", lambda _: ("alpha", "beta"))
    monkeypatch.setattr(runner, "load_projects", lambda *_: [config("alpha", 101), config("beta", 202)])

    async def fake_run_project(project: ProjectConfig, state_root: Path) -> None:
        started.append((project.slug, state_root))

    monkeypatch.setattr(runner, "run_project", fake_run_project)

    await runner.run_enabled_projects(tmp_path, {"ENABLED_PROJECTS": "alpha,beta"})

    assert started == [("alpha", Path("/data")), ("beta", Path("/data"))]


def test_state_root_uses_railway_volume_when_configured() -> None:
    assert runner.state_root({"RAILWAY_VOLUME_MOUNT_PATH": "D:/volume"}) == Path("D:/volume")
    assert runner.state_root({}) == Path("/data")
