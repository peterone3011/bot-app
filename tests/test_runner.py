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
from app.core.runtime import ProjectRuntime
from app.core.state import ProjectState


def test_production_entrypoint_delegates_to_the_shared_runner() -> None:
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")

    assert "from app.runner import main" in source
    assert 'if __name__ == "__main__":' in source


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


@pytest.mark.asyncio
async def test_registry_loads_auto_reaction_once_when_both_reaction_flags_are_enabled(
    monkeypatch,
) -> None:
    loaded: list[str] = []
    assert set(runner.COG_INSTALLERS) == {
        "manual_embed",
        "role_selector",
        "auto_reaction",
        "daily_updates",
        "community_metrics",
    }
    active = config("alpha", 101)
    active = ProjectConfig(
        **{
            **active.__dict__,
            "features": FeatureFlags(True, True, True, True, True, True),
        }
    )
    runtime = runner.ProjectRuntime(active, Mock(), runner.ProjectState(Path("/tmp"), "alpha"), None)

    async def installer(name: str) -> None:
        loaded.append(name)

    monkeypatch.setattr(
        runner,
        "COG_INSTALLERS",
        {
            "manual_embed": lambda _: installer("manual_embed"),
            "role_selector": lambda _: installer("role_selector"),
            "auto_reaction": lambda _: installer("auto_reaction"),
            "daily_updates": lambda _: installer("daily_updates"),
            "community_metrics": lambda _: installer("community_metrics"),
        },
    )

    await runner.install_enabled_cogs(runtime)

    assert loaded == [
        "manual_embed",
        "role_selector",
        "auto_reaction",
        "daily_updates",
        "community_metrics",
    ]


@pytest.mark.asyncio
async def test_build_embed_store_isolates_each_project_path(tmp_path: Path) -> None:
    alpha = ProjectRuntime(config("alpha", 101), Mock(), ProjectState(tmp_path, "alpha"), None)
    beta = ProjectRuntime(config("beta", 202), Mock(), ProjectState(tmp_path, "beta"), None)

    alpha_store = await runner.build_embed_store(alpha)
    beta_store = await runner.build_embed_store(beta)

    assert alpha_store.path == tmp_path / "alpha" / "embed-messages.json"
    assert beta_store.path == tmp_path / "beta" / "embed-messages.json"
    assert alpha_store.path != beta_store.path
    assert alpha.embed_store is alpha_store
    assert beta.embed_store is beta_store


@pytest.mark.asyncio
async def test_build_embed_store_imports_legacy_records_only_for_fortunepurple(
    monkeypatch, tmp_path: Path
) -> None:
    importer = AsyncMock(return_value=[{"id": "legacy", "status": "draft"}])
    monkeypatch.setattr(runner, "import_fortunepurple_embed_messages", importer)
    alpha = ProjectRuntime(config("alpha", 101), Mock(), ProjectState(tmp_path, "alpha"), None)
    fp = ProjectRuntime(
        config("fortunepurple", 202), Mock(), ProjectState(tmp_path, "fortunepurple"), None
    )

    await runner.build_embed_store(alpha)
    await runner.build_embed_store(fp)

    importer.assert_awaited_once()
    assert await alpha.embed_store.list() == []
    assert await fp.embed_store.get("legacy") == {"id": "legacy", "status": "draft"}
