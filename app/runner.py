from __future__ import annotations

import asyncio
import os
from pathlib import Path
import traceback
from typing import Callable, Mapping

import discord
from discord.ext import commands

from app.cogs import auto_reaction, community_metrics, daily_updates, manual_embed, role_selector
from app.core.config import ProjectConfig, enabled_project_slugs, load_projects
from app.core.embed_store import EmbedMessageStore
from app.core.feishu import FeishuClient
from app.core.legacy_embed_import import import_fortunepurple_embed_messages
from app.core.runtime import ProjectRuntime
from app.core.state import ProjectState


CogInstaller = Callable[[ProjectRuntime], object]
COG_INSTALLERS: dict[str, CogInstaller] = {
    "manual_embed": manual_embed.install,
    "role_selector": role_selector.install,
    "auto_reaction": auto_reaction.install,
    "daily_updates": daily_updates.install,
    "community_metrics": community_metrics.install,
}


def state_root(environ: Mapping[str, str]) -> Path:
    return Path(environ.get("RAILWAY_VOLUME_MOUNT_PATH", "/data"))


def _log(slug: str, feature: str, message: str) -> None:
    print(f"[{slug}][{feature}] {message}", flush=True)


def _make_feishu_client(config: ProjectConfig) -> FeishuClient | None:
    if config.feishu is None:
        return None
    return FeishuClient(config.feishu.app_id, config.feishu.app_secret)


async def build_embed_store(runtime: ProjectRuntime) -> EmbedMessageStore:
    store = EmbedMessageStore(runtime.state.embed_messages_file)
    importer = (
        import_fortunepurple_embed_messages
        if runtime.config.slug == "fortunepurple"
        else None
    )
    await store.ensure_initialized(importer)
    runtime.embed_store = store
    return store


async def sync_project_commands(bot: commands.Bot, config: ProjectConfig) -> None:
    guild = discord.Object(id=config.discord.guild_id)
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)


def create_project_bot(config: ProjectConfig) -> commands.Bot:
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.tree.error
    async def on_app_command_error(
        interaction: discord.Interaction,
        error: Exception,
    ) -> None:
        _log(config.slug, "commands", f"app command error: {error}\n{traceback.format_exc()}")
        message = "Something went wrong. Please try again later."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except Exception as response_error:
            _log(config.slug, "commands", f"failed to send error response: {response_error}")

    @bot.event
    async def on_ready() -> None:
        await sync_project_commands(bot, config)
        _log(
            config.slug,
            "runner",
            f"logged in as {bot.user} guild={config.discord.guild_id}",
        )

    return bot


async def install_enabled_cogs(runtime: ProjectRuntime) -> None:
    features = runtime.config.features
    enabled: list[str] = []
    if features.manual_embed:
        enabled.append("manual_embed")
    if features.role_selector:
        enabled.append("role_selector")
    if features.auto_reaction or features.exclusive_updates_reaction:
        enabled.append("auto_reaction")
    if features.daily_updates:
        enabled.append("daily_updates")
    if features.community_metrics:
        enabled.append("community_metrics")
    for name in enabled:
        installer = COG_INSTALLERS[name]
        result = installer(runtime)
        if hasattr(result, "__await__"):
            await result
        _log(runtime.config.slug, "runner", f"loaded cog={name}")


async def run_project(config: ProjectConfig, root: Path) -> None:
    while True:
        bot = create_project_bot(config)
        runtime = ProjectRuntime(
            config=config,
            bot=bot,
            state=ProjectState(root, config.slug),
            feishu=_make_feishu_client(config),
        )
        try:
            await build_embed_store(runtime)
            await install_enabled_cogs(runtime)
            await bot.start(config.discord.token)
        except asyncio.CancelledError:
            await bot.close()
            raise
        except Exception:
            _log(config.slug, "runner", traceback.format_exc())
        finally:
            if not bot.is_closed():
                await bot.close()
        await asyncio.sleep(10)


async def run_enabled_projects(
    repo_root: Path,
    environ: Mapping[str, str],
) -> None:
    configs = load_projects(repo_root, enabled_project_slugs(environ), environ)
    root = state_root(environ)
    await asyncio.gather(*(run_project(config, root) for config in configs))


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    asyncio.run(run_enabled_projects(repo_root, os.environ))
