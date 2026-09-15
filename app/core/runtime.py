from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from discord.ext import commands

from app.core.config import ProjectConfig
from app.core.embed_store import EmbedMessageStore
from app.core.feishu import FeishuClient
from app.core.state import ProjectState


@dataclass
class ProjectRuntime:
    """Dependencies owned by exactly one configured Discord project."""

    config: ProjectConfig
    bot: commands.Bot
    state: ProjectState
    feishu: FeishuClient | None
    embed_store: EmbedMessageStore | None = None

    @property
    def state_dir(self) -> Path:
        return self.state.directory
